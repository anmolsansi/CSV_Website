import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export default function SavedViews() {
  const [views, setViews] = useState([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [viewType, setViewType] = useState('job_links')
  const [filterJson, setFilterJson] = useState('{}')
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const navigate = useNavigate()

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
    if (editingId) {
      await api.saveView({ name: name.trim(), view_type: viewType, filters })
      setEditingId(null)
    } else {
      await api.saveView({ name: name.trim(), view_type: viewType, filters })
    }
    setName('')
    setFilterJson('{}')
    refresh()
  }

  const deleteView = async (id) => {
    if (!window.confirm('Delete this saved view?')) return
    await api.deleteView(id)
    refresh()
  }

  const applyView = (view) => {
    const filterParams = encodeURIComponent(JSON.stringify(view.filters))
    if (view.view_type === 'job_links') {
      navigate(`/?view=${view.id}`)
    } else if (view.view_type === 'applications') {
      navigate(`/applications?view=${view.id}`)
    } else if (view.view_type === 'pipeline') {
      navigate(`/pipeline?view=${view.id}`)
    }
  }

  const editView = (view) => {
    setEditingId(view.id)
    setName(view.name)
    setViewType(view.view_type)
    setFilterJson(JSON.stringify(view.filters, null, 2))
  }

  const duplicateView = async (id) => {
    await api.duplicateView(id)
    refresh()
  }

  const togglePin = async (id) => {
    await api.pinView(id)
    refresh()
  }

  const createDefaults = async () => {
    const result = await api.createDefaultViews()
    alert(`Created ${result.created} default views`)
    refresh()
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Saved Views</h2>
          <p>Save and recall filter combinations for quick access.</p>
        </div>
        <button className="btn btn-blue" onClick={createDefaults}>Create default views</button>
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
          <div>
            <button className="btn btn-green" onClick={saveView}>{editingId ? 'Update view' : 'Save view'}</button>
            {editingId && <button className="btn btn-grey" style={{ marginLeft: 8 }} onClick={() => { setEditingId(null); setName(''); setFilterJson('{}') }}>Cancel</button>}
          </div>
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
          <p>Save filter combinations above to quickly access your most-used searches. Or click "Create default views" for pre-built filters.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Page</th><th>Filters</th><th>Pinned</th><th>Created</th><th>Actions</th></tr></thead>
            <tbody>
              {views.map((v) => (
                <tr key={v.id} className={v.is_pinned ? 'selected-row' : ''}>
                  <td>{v.name}</td>
                  <td>{v.view_type}</td>
                  <td><code style={{ fontSize: 12 }}>{JSON.stringify(v.filters)}</code></td>
                  <td>{v.is_pinned ? 'Yes' : ''}</td>
                  <td>{new Date(v.created_at).toLocaleDateString()}</td>
                  <td>
                    <button className="btn btn-blue" style={{ padding: '4px 8px', fontSize: 12, marginRight: 4 }} onClick={() => applyView(v)}>Apply</button>
                    <button className="btn btn-grey" style={{ padding: '4px 8px', fontSize: 12, marginRight: 4 }} onClick={() => editView(v)}>Edit</button>
                    <button className="btn btn-grey" style={{ padding: '4px 8px', fontSize: 12, marginRight: 4 }} onClick={() => duplicateView(v.id)}>Duplicate</button>
                    <button className="btn btn-grey" style={{ padding: '4px 8px', fontSize: 12, marginRight: 4 }} onClick={() => togglePin(v.id)}>{v.is_pinned ? 'Unpin' : 'Pin'}</button>
                    <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => deleteView(v.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
