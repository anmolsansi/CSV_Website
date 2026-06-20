import { useEffect, useState } from 'react'
import { api } from '../api/client'

function timeAgo(startedAt) {
  if (!startedAt) return ''
  const start = new Date(startedAt)
  const now = new Date()
  const diff = Math.floor((now - start) / 1000)
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString()
}

export default function ActiveSessionBar() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    api.getActiveSession()
      .then((data) => { setSession(data); setLoading(false) })
      .catch(() => { setSession(null); setLoading(false) })
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [])

  const endSession = async () => {
    if (!session) return
    if (!window.confirm('End the active session?')) return
    await api.updateSession(session.id, { end: true })
    setSession(null)
  }

  if (loading || !session) return null

  const stats = session.stats || {}

  return (
    <div className="global-session-bar">
      <strong>Active session: {session.name}</strong>
      <span>Started: {formatTime(session.started_at)} ({timeAgo(session.started_at)} ago)</span>
      <span className="session-stat">Opened: <strong>{stats.urls_opened || 0}</strong></span>
      <span className="session-stat">Sent: <strong>{stats.sent_to_applications || 0}</strong></span>
      <span className="session-stat">Applied: <strong>{stats.applications_marked_applied || 0}</strong></span>
      <button className="btn btn-danger btn-sm" onClick={endSession}>End session</button>
    </div>
  )
}
