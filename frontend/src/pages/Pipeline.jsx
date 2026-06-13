import { useEffect, useState } from 'react'
import { api } from '../api/client'

const STATUSES = ['opened', 'applied', 'follow_up', 'interview', 'rejected', 'offer', 'not_applying']

function parseDate(value) {
  if (!value) return null
  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasTimezone ? value : `${value}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatDateTime(value) {
  const date = parseDate(value)
  return date ? date.toLocaleString() : ''
}

export default function Pipeline() {
  const [applications, setApplications] = useState([])
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    setLoading(true)
    api.getApplications({ sort_by: 'opened_at', sort_dir: 'desc' })
      .then((data) => setApplications(data.rows || []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const grouped = STATUSES.reduce((acc, status) => {
    acc[status] = applications.filter((a) => a.status === status)
    return acc
  }, {})

  const updateStatus = async (appId, newStatus) => {
    await api.updateApplication(appId, { status: newStatus })
    setApplications((prev) => prev.map((a) => a.id === appId ? { ...a, status: newStatus } : a))
  }

  if (loading) return <div className="container"><p>Loading pipeline...</p></div>

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Pipeline</h2>
          <p>Jobs grouped by application status.</p>
        </div>
        <button className="btn btn-blue" onClick={refresh}>Refresh</button>
      </div>

      <div className="pipeline-board">
        {STATUSES.map((status) => (
          <div className="pipeline-column" key={status}>
            <div className="pipeline-column-header">
              {status.replace('_', ' ')} ({(grouped[status] || []).length})
            </div>
            <div className="pipeline-column-body">
              {(grouped[status] || []).map((app) => (
                <div className="pipeline-card" key={app.id}>
                  <div className="pipeline-card-company">{app.company || 'Unknown'}</div>
                  <div className="pipeline-card-title">{app.title || 'Untitled'}</div>
                  {app.resume_match_score && <div className="pipeline-card-score">Score: {app.resume_match_score}</div>}
                  {app.ats_group && <div className="pipeline-card-meta">ATS: {app.ats_group}</div>}
                  {app.applied_at && <div className="pipeline-card-meta">Applied: {formatDateTime(app.applied_at)}</div>}
                  {app.follow_up_at && <div className="pipeline-card-meta">Follow-up: {formatDateTime(app.follow_up_at)}</div>}
                  {app.notes && <div className="pipeline-card-notes">{app.notes.slice(0, 80)}{app.notes.length > 80 ? '...' : ''}</div>}
                  <div className="pipeline-card-actions">
                    <select value={app.status} onChange={(e) => updateStatus(app.id, e.target.value)}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
                    </select>
                    <button className="btn btn-blue" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => window.open(app.url, '_blank', 'noopener')}>Open</button>
                  </div>
                </div>
              ))}
              {(grouped[status] || []).length === 0 && <p style={{ color: '#9ca3af', fontSize: 13, padding: 8 }}>No items</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
