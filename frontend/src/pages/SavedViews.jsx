import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function SavedViews() {
  const [views, setViews] = useState([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [viewType, setViewType] = useState('job_links')
  const [filterJson, setFilterJson] = useState('{}')
  const [error, setError] = useState('')

  const refresh = () => {
    setLoading(true)
    api.getViews()
      .then(setViews)
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const saveView = async () => {
    setError('')
    if (!name.trim()) { setError('Name is required'); return }
    let filters
    try { filters = JSON.parse(filterJson) }
    catch { setError('Invalid JSON in filters'); return }
    await api.saveView({ name: name.trim(), view_type: viewType, filters })
    setName('')
    setFilterJson('{}')
    refresh()
  }

  const deleteView = async (id) => {
    if (!window.confirm('Delete this saved view?')) return
    await api.deleteView(id)
    refresh()
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Saved Views</h2>
          <p>Save and recall filter combinations for quick access.</p>
        </div>
      </div>

      <div className="saved-view-form">
        <div className="table-controls">
          <div><label>View name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. High score remote jobs" /></div>
          <div><label>Page</label><select value={viewType} onChange={(e) => setViewType(e.target.value)}>
            <option value="job_links">Job Links</option>
            <option value="applications">Applications</option>
            <option value="pipeline">Pipeline</option>
          </select></div>
          <div><label>Filters (JSON)</label><textarea className="filter-json-input" value={filterJson} onChange={(e) => setFilterJson(e.target.value)} rows={3} /></div>
          <div><button className="btn btn-green" onClick={saveView}>Save view</button></div>
          {error && <div className="error-msg">{error}</div>}
        </div>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" />
          <p>Loading saved views...</p>
        </div>
      ) : views.length === 0 ? (
        <div className="empty-state">
          <h3>No saved views yet</h3>
          <p>Save filter combinations above to quickly access your most-used searches.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Page</th><th>Filters</th><th>Created</th><th>Actions</th></tr></thead>
            <tbody>
              {views.map((v) => (
                <tr key={v.id}>
                  <td>{v.name}</td>
                  <td>{v.view_type}</td>
                  <td><code style={{ fontSize: 12 }}>{JSON.stringify(v.filters)}</code></td>
                  <td>{new Date(v.created_at).toLocaleDateString()}</td>
                  <td><button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => deleteView(v.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
