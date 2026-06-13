import { useEffect, useState } from 'react'
import { api } from '../api/client'

function formatDateTime(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

function timeAgo(startedAt) {
  if (!startedAt) return ''
  const start = new Date(startedAt)
  const now = new Date()
  const diff = Math.floor((now - start) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function Sessions() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [activeId, setActiveId] = useState(null)

  const refresh = () => {
    setLoading(true)
    api.getSessions()
      .then((data) => {
        setSessions(data)
        const active = data.find((s) => !s.ended_at)
        setActiveId(active ? active.id : null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const startSession = async () => {
    const result = await api.startSession({ name: name.trim() || 'Job search session', notes: notes.trim() || null })
    setName('')
    setNotes('')
    setActiveId(result.id)
    refresh()
  }

  const endSession = async (id) => {
    await api.updateSession(id, { end: true })
    if (activeId === id) setActiveId(null)
    refresh()
  }

  const addNotes = async (id, currentNotes) => {
    const newNotes = window.prompt('Edit notes:', currentNotes || '')
    if (newNotes === null) return
    await api.updateSession(id, { notes: newNotes })
    refresh()
  }

  const deleteSession = async (id) => {
    if (!window.confirm('Delete this session?')) return
    await api.deleteSession(id)
    if (activeId === id) setActiveId(null)
    refresh()
  }

  const activeSession = sessions.find((s) => s.id === activeId)

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Sessions</h2>
          <p>Track job-search sessions with notes and durations.</p>
        </div>
      </div>

      <div className="table-controls">
        <div><label>Session name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Morning applications" /></div>
        <div><label>Notes</label><input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" /></div>
        <div>
          {activeId ? (
            <button className="btn btn-danger" onClick={() => endSession(activeId)}>End active session</button>
          ) : (
            <button className="btn btn-green" onClick={startSession}>Start session</button>
          )}
        </div>
      </div>

      {activeSession && (
        <div className="active-session-banner">
          <strong>Active session:</strong> {activeSession.name} (started {timeAgo(activeSession.started_at)})
        </div>
      )}

      {loading ? <p>Loading...</p> : (
        sessions.length === 0 ? <p style={{ color: '#9ca3af' }}>No sessions yet. Start one above.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Started</th><th>Ended</th><th>Duration</th><th>Notes</th><th>Actions</th></tr></thead>
              <tbody>
                {sessions.map((s) => {
                  const duration = s.ended_at
                    ? `${Math.round((new Date(s.ended_at) - new Date(s.started_at)) / 60000)}m`
                    : timeAgo(s.started_at)
                  return (
                    <tr key={s.id} className={s.id === activeId ? 'selected-row' : ''}>
                      <td>{s.name}</td>
                      <td>{formatDateTime(s.started_at)}</td>
                      <td>{s.ended_at ? formatDateTime(s.ended_at) : <span style={{ color: '#16a34a' }}>Active</span>}</td>
                      <td>{duration}</td>
                      <td>{s.notes || '-'}</td>
                      <td>
                        <button className="btn btn-grey" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => addNotes(s.id, s.notes)}>Notes</button>
                        {!s.ended_at && <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12, marginLeft: 4 }} onClick={() => endSession(s.id)}>End</button>}
                        <button className="btn btn-danger-outline" style={{ padding: '4px 8px', fontSize: 12, marginLeft: 4 }} onClick={() => deleteSession(s.id)}>Delete</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
