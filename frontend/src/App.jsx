import { createContext, useCallback, useContext, useEffect, useState } from 'react'
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

const ToastContext = createContext(null)

export function useToast() {
  return useContext(ToastContext)
}

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3000)
  }, [])
  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>{t.message}</div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function AuthenticatedApp({ user, onLogout }) {
  return (
    <BrowserRouter>
      <ToastProvider>
        <div className="app-shell">
          <div className="topbar">
            <strong className="topbar-brand">JobGrid</strong>
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
      </ToastProvider>
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

  if (loading) return <div className="loading-screen"><div className="loading-spinner" /><span>Loading JobGrid...</span></div>
  if (!user) return <Login />
  return <AuthenticatedApp user={user} onLogout={() => setUser(null)} />
}
