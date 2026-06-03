import { useEffect, useState } from 'react'
import { api } from '../api/client'
import CsvUpload from '../components/CsvUpload'
import DataTable from '../components/DataTable'

export default function Dashboard({ user, onLogout }) {
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])
  const [hidden, setHidden] = useState([])

  const loadRows = () =>
    api.getRows().then((d) => {
      setColumns(d.columns)
      setRows(d.rows)
    })

  useEffect(() => {
    loadRows()
    api.getPreferences().then((p) => setHidden(p.hidden_columns))
  }, [])

  const toggleColumn = async (col) => {
    const next = hidden.includes(col)
      ? hidden.filter((c) => c !== col)
      : [...hidden, col]
    setHidden(next)
    await api.setPreferences(next)
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
        <CsvUpload onUploaded={loadRows} />
        <div className="col-toggles">
          <strong style={{ width: '100%' }}>Show / hide columns</strong>
          {columns.map((col) => (
            <label key={col}>
              <input
                type="checkbox"
                checked={!hidden.includes(col)}
                onChange={() => toggleColumn(col)}
              />{' '}
              {col}
            </label>
          ))}
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          hidden={hidden}
          onUrlClick={handleClick}
        />
      </div>
    </div>
  )
}
