import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import CsvUpload from '../components/CsvUpload'
import DataTable from '../components/DataTable'

const DEFAULT_SORT = { sortBy: 'created_at', sortDir: 'desc' }
const DEFAULT_FILTERS = { atsGroup: '' }
const EMPTY_STATS = { totalUrls: 0, greenUrls: 0, greenToday: 0 }

function mergeColumnOrder(savedOrder, columns) {
  const validSaved = savedOrder.filter((col) => columns.includes(col))
  const missing = columns.filter((col) => !validSaved.includes(col))
  return [...validSaved, ...missing]
}

function parseClickedAt(clickedAt) {
  if (!clickedAt) {
    return null
  }

  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(clickedAt)
  const normalized = hasTimezone ? clickedAt : `${clickedAt}Z`
  const parsed = new Date(normalized)

  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function isSameLocalDay(dateA, dateB) {
  return (
    dateA.getFullYear() === dateB.getFullYear() &&
    dateA.getMonth() === dateB.getMonth() &&
    dateA.getDate() === dateB.getDate()
  )
}

function calculateRowStats(rows) {
  const today = new Date()
  const totalUrls = rows.filter((row) => row.data?.url).length
  const greenUrls = rows.filter((row) => row.clicked).length
  const greenToday = rows.filter((row) => {
    if (!row.clicked) {
      return false
    }
    const clickedAt = parseClickedAt(row.clicked_at)
    return clickedAt ? isSameLocalDay(clickedAt, today) : false
  }).length

  return { totalUrls, greenUrls, greenToday }
}

function normalizeStats(stats) {
  if (!stats) {
    return EMPTY_STATS
  }

  return {
    totalUrls: stats.total_urls || 0,
    greenUrls: stats.green_urls || 0,
    greenToday: stats.green_today || 0,
  }
}

function subtractStats(baseStats, removedStats) {
  return {
    totalUrls: Math.max(0, baseStats.totalUrls - removedStats.totalUrls),
    greenUrls: Math.max(0, baseStats.greenUrls - removedStats.greenUrls),
    greenToday: Math.max(0, baseStats.greenToday - removedStats.greenToday),
  }
}

function buildDeleteConfirmation({ currentStats, rowsToDelete, label, mode }) {
  const removedStats = calculateRowStats(rowsToDelete)
  const after = mode === 'archive' ? currentStats : subtractStats(currentStats, removedStats)
  const actionText = mode === 'archive'
    ? 'Clean from table only. Numbers will stay the same.'
    : 'Delete from database. Numbers will update.'

  return [
    `Remove ${label}?`,
    '',
    actionText,
    '',
    `Rows being removed: ${rowsToDelete.length}`,
    '',
    'Numbers will look like this:',
    `Total URLs: ${currentStats.totalUrls} -> ${after.totalUrls}`,
    `Green URLs: ${currentStats.greenUrls} -> ${after.greenUrls}`,
    `Green today: ${currentStats.greenToday} -> ${after.greenToday}`,
    '',
    mode === 'archive'
      ? 'These rows will disappear from the table, but stay counted in your totals.'
      : 'This permanently deletes the rows and cannot be undone.',
  ].join('\n')
}

function getDeleteModeFromUser() {
  const answer = window.prompt(
    [
      'How should these rows be removed?',
      '',
      '1 = Clean table only, numbers stay the same',
      '2 = Delete rows, numbers update',
      '',
      'Enter 1 or 2:',
    ].join('\n')
  )

  if (answer === null) {
    return null
  }

  const trimmed = answer.trim()
  if (trimmed === '1') {
    return 'archive'
  }
  if (trimmed === '2') {
    return 'delete'
  }

  window.alert('Invalid choice. Please enter 1 or 2.')
  return null
}

export default function Dashboard() {
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])
  const [stats, setStats] = useState(EMPTY_STATS)
  const [hidden, setHidden] = useState([])
  const [columnOrder, setColumnOrder] = useState([])
  const [sort, setSort] = useState(DEFAULT_SORT)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [filterOptions, setFilterOptions] = useState({ atsGroups: [] })
  const [selectedRowIds, setSelectedRowIds] = useState(new Set())
  const [columnsCollapsed, setColumnsCollapsed] = useState(true)

  const orderedColumns = useMemo(
    () => mergeColumnOrder(columnOrder, columns),
    [columnOrder, columns]
  )

  const savePreferences = async (nextHidden, nextOrder) => {
    await api.setPreferences({
      hiddenColumns: nextHidden,
      columnOrder: nextOrder,
    })
  }

  const loadRows = (nextSort = sort, nextFilters = filters) =>
    api.getRows({ ...nextSort, ...nextFilters }).then((d) => {
      setColumns(d.columns)
      setRows(d.rows)
      setStats(normalizeStats(d.stats))
      setFilterOptions({ atsGroups: d.filter_options?.ats_groups || [] })
      setColumnOrder((prev) => mergeColumnOrder(prev, d.columns))
      setSelectedRowIds(new Set())
    })

  useEffect(() => {
    Promise.all([
      api.getRows({ ...DEFAULT_SORT, ...DEFAULT_FILTERS }),
      api.getPreferences(),
    ]).then(([rowData, preferences]) => {
      const savedHidden = preferences.hidden_columns || []
      const savedOrder = preferences.column_order || []
      const nextOrder = mergeColumnOrder(savedOrder, rowData.columns)

      setColumns(rowData.columns)
      setRows(rowData.rows)
      setStats(normalizeStats(rowData.stats))
      setFilterOptions({ atsGroups: rowData.filter_options?.ats_groups || [] })
      setHidden(savedHidden)
      setColumnOrder(nextOrder)
      setSelectedRowIds(new Set())
    })
  }, [])

  const toggleColumn = async (col) => {
    const nextHidden = hidden.includes(col)
      ? hidden.filter((c) => c !== col)
      : [...hidden, col]
    setHidden(nextHidden)
    await savePreferences(nextHidden, columnOrder)
  }

  const moveColumn = async (col, direction) => {
    const currentOrder = mergeColumnOrder(columnOrder, columns)
    const index = currentOrder.indexOf(col)
    const nextIndex = index + direction

    if (index === -1 || nextIndex < 0 || nextIndex >= currentOrder.length) {
      return
    }

    const nextOrder = [...currentOrder]
    const [removed] = nextOrder.splice(index, 1)
    nextOrder.splice(nextIndex, 0, removed)

    setColumnOrder(nextOrder)
    await savePreferences(hidden, nextOrder)
  }

  const resetColumnOrder = async () => {
    const nextOrder = [...columns]
    setColumnOrder(nextOrder)
    await savePreferences(hidden, nextOrder)
  }

  const updateSort = async (sortBy, sortDir) => {
    const nextSort = { sortBy, sortDir }
    setSort(nextSort)
    await loadRows(nextSort, filters)
  }

  const updateAtsGroupFilter = async (atsGroup) => {
    const nextFilters = { ...filters, atsGroup }
    setFilters(nextFilters)
    await loadRows(sort, nextFilters)
  }

  const clearFilters = async () => {
    const nextFilters = DEFAULT_FILTERS
    setFilters(nextFilters)
    await loadRows(sort, nextFilters)
  }

  const toggleRowSelection = (rowId) => {
    setSelectedRowIds((prev) => {
      const next = new Set(prev)
      if (next.has(rowId)) {
        next.delete(rowId)
      } else {
        next.add(rowId)
      }
      return next
    })
  }

  const toggleAllRows = () => {
    setSelectedRowIds((prev) => {
      if (rows.length > 0 && prev.size === rows.length) {
        return new Set()
      }
      return new Set(rows.map((row) => row.id))
    })
  }

  const deleteRows = async (rowsToRemove, label) => {
    if (rowsToRemove.length === 0) {
      return
    }

    const mode = getDeleteModeFromUser()
    if (!mode) {
      return
    }

    const confirmed = window.confirm(
      buildDeleteConfirmation({
        currentStats: stats,
        rowsToDelete: rowsToRemove,
        label,
        mode,
      })
    )

    if (!confirmed) {
      return
    }

    await api.deleteRows(rowsToRemove.map((row) => row.id), mode)
    await loadRows(sort, filters)
  }

  const deleteSelectedRows = () => {
    const rowsToRemove = rows.filter((row) => selectedRowIds.has(row.id))
    deleteRows(rowsToRemove, `${rowsToRemove.length} selected row${rowsToRemove.length === 1 ? '' : 's'}`)
  }

  const deleteAllShownRows = () => {
    deleteRows(rows, `all ${rows.length} row${rows.length === 1 ? '' : 's'} currently shown`)
  }

  const handleClick = async (row) => {
    const url = row.data.url
    window.open(url, '_blank', 'noopener')
    const updated = await api.recordClick(row.id)
    setRows((prev) =>
      prev.map((r) =>
        r.id === row.id
          ? { ...r, clicked: updated.clicked, clicked_at: updated.clicked_at }
          : r
      )
    )
    await loadRows(sort, filters)
  }

  return (
    <div className="container">
        <CsvUpload onUploaded={() => loadRows()} />

        <div className="stats-grid">
          <div className="stat-card">
            <span>Total URLs counted</span>
            <strong>{stats.totalUrls}</strong>
          </div>
          <div className="stat-card">
            <span>Green URLs</span>
            <strong>{stats.greenUrls}</strong>
          </div>
          <div className="stat-card">
            <span>Green today</span>
            <strong>{stats.greenToday}</strong>
          </div>
        </div>

        <div className="table-controls">
          <div>
            <label htmlFor="sort-column">Sort database by</label>
            <select
              id="sort-column"
              value={sort.sortBy}
              onChange={(e) => updateSort(e.target.value, sort.sortDir)}
            >
              <option value="created_at">created_at</option>
              <option value="clicked_at">clicked_at</option>
              {columns.map((col) => (
                <option key={col} value={col}>
                  {col}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="sort-direction">Direction</label>
            <select
              id="sort-direction"
              value={sort.sortDir}
              onChange={(e) => updateSort(sort.sortBy, e.target.value)}
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </div>

          <div>
            <label htmlFor="ats-group-filter">Filter ats_group</label>
            <select
              id="ats-group-filter"
              value={filters.atsGroup}
              onChange={(e) => updateAtsGroupFilter(e.target.value)}
            >
              <option value="">All ATS groups</option>
              {filterOptions.atsGroups.map((group) => (
                <option key={group} value={group}>
                  {group}
                </option>
              ))}
            </select>
          </div>

          <div className="table-control-actions">
            <label>Rows shown</label>
            <span>{rows.length}</span>
            <button className="btn btn-grey" onClick={clearFilters}>
              Clear filters
            </button>
          </div>
        </div>

        <div className="delete-actions">
          <div>
            <strong>{selectedRowIds.size}</strong> selected
          </div>
          <button
            className="btn btn-danger"
            onClick={deleteSelectedRows}
            disabled={selectedRowIds.size === 0}
          >
            Remove selected
          </button>
          <button
            className="btn btn-danger-outline"
            onClick={deleteAllShownRows}
            disabled={rows.length === 0}
          >
            Remove all shown rows
          </button>
        </div>

        <div className="col-toggles">
          <div className="col-toggles-header">
            <button
              className="col-collapse-toggle"
              onClick={() => setColumnsCollapsed(!columnsCollapsed)}
            >
              {columnsCollapsed ? '▶' : '▼'} Show, hide, and rearrange columns
            </button>
            {!columnsCollapsed && (
              <button className="btn btn-grey" onClick={resetColumnOrder}>
                Reset order
              </button>
            )}
          </div>

          {!columnsCollapsed && orderedColumns.map((col, index) => (
            <div className="column-control" key={col}>
              <label>
                <input
                  type="checkbox"
                  checked={!hidden.includes(col)}
                  onChange={() => toggleColumn(col)}
                />{' '}
                {col}
              </label>
              <div className="column-move-actions">
                <button
                  type="button"
                  onClick={() => moveColumn(col, -1)}
                  disabled={index === 0}
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => moveColumn(col, 1)}
                  disabled={index === orderedColumns.length - 1}
                >
                  ↓
                </button>
              </div>
            </div>
          ))}
        </div>

        <DataTable
          columns={orderedColumns}
          rows={rows}
          hidden={hidden}
          sort={sort}
          selectedRowIds={selectedRowIds}
          onToggleRowSelection={toggleRowSelection}
          onToggleAllRows={toggleAllRows}
          onSortChange={updateSort}
          onUrlClick={handleClick}
        />
    </div>
  )
}
