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
import ApplyPilotBatches from './pages/ApplyPilotBatches'
import Duplicates from './pages/Duplicates'
import CompanyHistory from './pages/CompanyHistory'
import ImportExternal from './pages/ImportExternal'
import Navigation from './components/Navigation'
import ActiveSessionBar from './components/ActiveSessionBar'
import CommandPalette from './components/CommandPalette'
import DarkModeToggle from './components/DarkModeToggle'
import SkipToContent from './components/SkipToContent'

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
  const [cmdOpen, setCmdOpen] = useState(false)

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCmdOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <BrowserRouter>
      <ToastProvider>
        <div className="app-shell">
          <SkipToContent />
          <div className="topbar">
            <strong className="topbar-brand">JobGrid</strong>
            <Navigation />
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <DarkModeToggle />
              <button className="btn btn-grey btn-sm" onClick={() => setCmdOpen(true)} title="Command Palette (Cmd+K)">
                ⌘K
              </button>
              <span>{user.email}</span>
              <button className="btn btn-grey" onClick={() => api.logout().then(onLogout)}>Logout</button>
            </div>
          </div>
          <ActiveSessionBar />
          <main id="main-content" tabIndex={-1}>
            <Routes>
              <Route path="/" element={<Dashboard user={user} onLogout={onLogout} />} />
              <Route path="/applications" element={<Applications />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/pipeline" element={<Pipeline />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/saved-views" element={<SavedViews />} />
              <Route path="/applypilot" element={<ApplyPilotBatches />} />
              <Route path="/duplicates" element={<Duplicates />} />
              <Route path="/companies" element={<CompanyHistory />} />
              <Route path="/import" element={<ImportExternal />} />
            </Routes>
          </main>
        </div>
        <CommandPalette isOpen={cmdOpen} onClose={() => setCmdOpen(false)} />
      </ToastProvider>
    </BrowserRouter>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    try {
      const saved = localStorage.getItem('jobgrid-theme')
      const theme = saved || 'system'
      const resolved = theme === 'system'
        ? window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        : theme
      document.documentElement.setAttribute('data-theme', resolved)
    } catch {}
  }, [])

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
