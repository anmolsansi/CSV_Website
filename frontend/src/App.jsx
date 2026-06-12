import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { api } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Applications from './pages/Applications'
import Analytics from './pages/Analytics'
import Pipeline from './pages/Pipeline'
import Sessions from './pages/Sessions'
import SavedViews from './pages/SavedViews'
import Navigation from './components/Navigation'

function AuthenticatedApp({ user, onLogout }) {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <div className="topbar">
          <strong>CSV URL Tracker</strong>
          <Navigation />
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
        <Routes>
          <Route path="/" element={<Dashboard user={user} onLogout={onLogout} />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/saved-views" element={<SavedViews />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="container">Loading...</div>
  if (!user) return <Login />
  return <AuthenticatedApp user={user} onLogout={() => setUser(null)} />
}
