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

  const sendToApplications = async () => {
    if (selectedRowIds.size === 0) return
    const ids = [...selectedRowIds]
    const result = await api.bulkCreateApplicationsFromRows(ids)
    window.alert(
      `Sent to Applications:\n\nCreated: ${result.created}\nUpdated: ${result.updated}\nSkipped: ${result.skipped}`
    )
    await loadRows(sort, filters)
  }

  const openSelected = async () => {
    if (selectedRowIds.size === 0) return
    const toOpen = rows.filter((r) => selectedRowIds.has(r.id))
    let blocked = 0
    for (const row of toOpen) {
      const win = window.open(row.data.url, '_blank', 'noopener')
      if (!win) { blocked++; continue }
      api.recordClick(row.id).catch(() => {})
      api.createApplicationFromRow(row.id).catch(() => {})
    }
    if (blocked > 0) window.alert(`Browser blocked ${blocked} popup(s). Please allow popups for this site.`)
    await loadRows(sort, filters)
  }

  const openNext5 = async () => {
    const unclicked = rows.filter((r) => !r.clicked).slice(0, 5)
    if (unclicked.length === 0) { window.alert('No unclicked rows remaining.'); return }
    let blocked = 0
    for (const row of unclicked) {
      const win = window.open(row.data.url, '_blank', 'noopener')
      if (!win) { blocked++; continue }
      api.recordClick(row.id).catch(() => {})
      api.createApplicationFromRow(row.id).catch(() => {})
    }
    if (blocked > 0) window.alert(`Browser blocked ${blocked} popup(s). Please allow popups for this site.`)
    await loadRows(sort, filters)
  }

  const sendNext5ToApplications = async () => {
    const unclicked = rows.filter((r) => !r.clicked).slice(0, 5)
    if (unclicked.length === 0) { window.alert('No unclicked rows remaining.'); return }
    const result = await api.bulkCreateApplicationsFromRows(unclicked.map((r) => r.id))
    window.alert(
      `Sent next ${unclicked.length} to Applications:\n\nCreated: ${result.created}\nUpdated: ${result.updated}\nSkipped: ${result.skipped}`
    )
    await loadRows(sort, filters)
  }

  const exportApplyPilot = () => {
    if (selectedRowIds.size === 0) return
    if (selectedRowIds.size > 5) {
      window.alert('ApplyPilot V1 supports max 5 jobs per batch. Please select 5 or fewer.')
      return
    }
    const toExport = rows.filter((r) => selectedRowIds.has(r.id))
    const payload = toExport.map((r) => ({
      job_id: r.data.job_id_guess || '',
      company: r.data.company_guess || '',
      title: r.data.title || '',
      url: r.data.url || '',
      ats_group: r.data.ats_group || '',
      search_bucket: r.data.search_bucket || '',
      resume_match_score: r.data.resume_match_score || '',
      jd_text: r.data.jd_text || '',
      sponsorship_status: r.data.sponsorship_status || '',
      location_group: r.data.location_group || '',
      posted_age_days: r.data.posted_age_days || '',
    }))
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'applypilot_batch.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const [exportFormat, setExportFormat] = useState('csv')
  const [exportScope, setExportScope] = useState('all')

  const handleExport = async () => {
    const params = { format: exportFormat }
    if (exportScope === 'selected') {
      if (selectedRowIds.size === 0) { window.alert('No rows selected.'); return }
      params.rowIds = [...selectedRowIds]
    } else if (exportScope === 'filtered') {
      params.atsGroup = filters.atsGroup || undefined
    }
    try {
      const res = await api.exportDashboard(params)
      const ext = exportFormat === 'json' ? 'json' : 'csv'
      const blob = new Blob([res.data], { type: ext === 'json' ? 'application/json' : 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dashboard_export.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      window.alert('Export failed.')
    }
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
    api.createApplicationFromRow(row.id).catch(() => {})
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

        <div className="export-bar">
          <label>Export</label>
          <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
          <select value={exportScope} onChange={(e) => setExportScope(e.target.value)}>
            <option value="all">All rows</option>
            <option value="filtered">Filtered rows</option>
            <option value="selected">Selected rows</option>
          </select>
          <button className="btn btn-grey" onClick={handleExport}>Download</button>
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
            className="btn btn-blue"
            onClick={openSelected}
            disabled={selectedRowIds.size === 0}
          >
            Open selected
          </button>
          <button
            className="btn btn-blue"
            onClick={openNext5}
          >
            Open next 5
          </button>
          <button
            className="btn btn-blue"
            onClick={sendToApplications}
            disabled={selectedRowIds.size === 0}
          >
            Send selected to Applications
          </button>
          <button
            className="btn btn-blue"
            onClick={sendNext5ToApplications}
          >
            Send next 5 to Applications
          </button>
          <button
            className="btn btn-green"
            onClick={exportApplyPilot}
            disabled={selectedRowIds.size === 0}
          >
            Send 5 to ApplyPilot
          </button>
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
