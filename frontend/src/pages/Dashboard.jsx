import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import CsvUpload from '../components/CsvUpload'
import DataTable from '../components/DataTable'

const DEFAULT_SORT = { sortBy: 'created_at', sortDir: 'desc' }

function mergeColumnOrder(savedOrder, columns) {
  const validSaved = savedOrder.filter((col) => columns.includes(col))
  const missing = columns.filter((col) => !validSaved.includes(col))
  return [...validSaved, ...missing]
}

export default function Dashboard({ user, onLogout }) {
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])
  const [hidden, setHidden] = useState([])
  const [columnOrder, setColumnOrder] = useState([])
  const [sort, setSort] = useState(DEFAULT_SORT)

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

  const loadRows = (nextSort = sort) =>
    api.getRows(nextSort).then((d) => {
      setColumns(d.columns)
      setRows(d.rows)
      setColumnOrder((prev) => mergeColumnOrder(prev, d.columns))
    })

  useEffect(() => {
    Promise.all([api.getRows(DEFAULT_SORT), api.getPreferences()]).then(
      ([rowData, preferences]) => {
        const savedHidden = preferences.hidden_columns || []
        const savedOrder = preferences.column_order || []
        const nextOrder = mergeColumnOrder(savedOrder, rowData.columns)

        setColumns(rowData.columns)
        setRows(rowData.rows)
        setHidden(savedHidden)
        setColumnOrder(nextOrder)
      }
    )
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
    await loadRows(nextSort)
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
  }

  return (
    <div>
      <div className="topbar">
        <strong>CSV URL Tracker</strong>
        <div>
          <span style={{ marginRight: 12 }}>{user.email}</span>
          <button
            className="btn btn-grey"
            onClick={() => api.logout().then(onLogout)}
          >
            Logout
          </button>
        </div>
      </div>
      <div className="container">
        <CsvUpload onUploaded={() => loadRows()} />

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
        </div>

        <div className="col-toggles">
          <div className="col-toggles-header">
            <strong>Show, hide, and rearrange columns</strong>
            <button className="btn btn-grey" onClick={resetColumnOrder}>
              Reset order
            </button>
          </div>

          {orderedColumns.map((col, index) => (
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
          onSortChange={updateSort}
          onUrlClick={handleClick}
        />
      </div>
    </div>
  )
}
