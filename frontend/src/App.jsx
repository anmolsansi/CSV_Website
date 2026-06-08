import { useEffect, useState } from 'react'
import { api } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Applications from './pages/Applications'
import Analytics from './pages/Analytics'

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('links')

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="container">Loading...</div>
  if (!user) return <Login />

  return (
    <div>
      <div className="topbar">
        <strong>CSV URL Tracker</strong>
        <div>
          <button className={`tab-btn ${tab === 'links' ? 'tab-btn-active' : ''}`} onClick={() => setTab('links')}>Job Links</button>
          <button className={`tab-btn ${tab === 'apps' ? 'tab-btn-active' : ''}`} onClick={() => setTab('apps')}>Applications</button>
          <button className={`tab-btn ${tab === 'analytics' ? 'tab-btn-active' : ''}`} onClick={() => setTab('analytics')}>Analytics</button>
          <span style={{ marginLeft: 12, marginRight: 12 }}>{user.email}</span>
          <button className="btn btn-grey" onClick={() => api.logout().then(() => setUser(null))}>Logout</button>
        </div>
      </div>
      {tab === 'links' && <Dashboard user={user} onLogout={() => setUser(null)} />}
      {tab === 'apps' && <Applications />}
      {tab === 'analytics' && <Analytics />}
    </div>
  )
}
