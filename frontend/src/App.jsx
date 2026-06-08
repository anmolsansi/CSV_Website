import { useEffect, useState } from 'react'
import { api } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'

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
  return <Dashboard user={user} onLogout={() => setUser(null)} />
}
