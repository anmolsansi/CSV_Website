import { useEffect, useState } from 'react'
import { api } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Applications from './pages/Applications'

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('links')

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="container">Loading...</div>
  if (!user) return <Login />

  return (
    <div>
      <div className="topbar">
        <strong>CSV URL Tracker</strong>
        <div>
          <button
            className={`tab-btn ${activeTab === 'links' ? 'tab-btn-active' : ''}`}
            onClick={() => setActiveTab('links')}
          >
            Job Links
          </button>
          <button
            className={`tab-btn ${activeTab === 'applications' ? 'tab-btn-active' : ''}`}
            onClick={() => setActiveTab('applications')}
          >
            Applications
          </button>
          <span style={{ marginLeft: 12, marginRight: 12 }}>{user.email}</span>
          <button
            className="btn btn-grey"
            onClick={() => api.logout().then(() => setUser(null))}
          >
            Logout
          </button>
        </div>
      </div>

      {activeTab === 'links' ? (
        <Dashboard user={user} onLogout={() => setUser(null)} showTopbar={false} />
      ) : (
        <Applications />
      )}
    </div>
  )
}
