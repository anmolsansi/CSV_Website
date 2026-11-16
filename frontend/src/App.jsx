import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { api } from './api/client'
import { sessionCheckProblem } from './api/authAvailability'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Archive from './pages/Archive'
import Today from './pages/Today'
import Applications from './pages/Applications'
import AddApplication from './pages/AddApplication'
import Documents from './pages/Documents'
import Analytics from './pages/Analytics'
import Pipeline from './pages/Pipeline'
import Sessions from './pages/Sessions'
import SavedViews from './pages/SavedViews'
import ApplyPilotBatches from './pages/ApplyPilotBatches'
import Duplicates from './pages/Duplicates'
import CompanyHistory from './pages/CompanyHistory'
import ImportExternal from './pages/ImportExternal'
import Capture from './pages/Capture'
import Navigation from './components/Navigation'
import ActiveSessionBar from './components/ActiveSessionBar'
import BulkActionStatus from './components/BulkActionStatus'
import CommandPalette from './components/CommandPalette'
import DarkModeToggle from './components/DarkModeToggle'
import SkipToContent from './components/SkipToContent'
import ErrorBoundary from './components/ErrorBoundary'
import { ingestCaptureFragment, isSafeCaptureReturnPath } from './utils/captureDraft'

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
          <BulkActionStatus />
          <main id="main-content" tabIndex={-1}>
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard user={user} onLogout={onLogout} />} />
                <Route path="/archive" element={<Archive />} />
                <Route path="/today" element={<Today />} />
                <Route path="/applications" element={<Applications />} />
                <Route path="/applications/new" element={<AddApplication />} />
                <Route path="/documents" element={<Documents />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/pipeline" element={<Pipeline />} />
                <Route path="/sessions" element={<Sessions />} />
                <Route path="/saved-views" element={<SavedViews />} />
                <Route path="/applypilot" element={<ApplyPilotBatches />} />
                <Route path="/duplicates" element={<Duplicates />} />
                <Route path="/companies" element={<CompanyHistory />} />
                <Route path="/capture" element={<Capture />} />
                <Route path="/import" element={<ImportExternal />} />
              </Routes>
            </ErrorBoundary>
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
  const [sessionFailure, setSessionFailure] = useState(null)
  const [sessionCheckVersion, setSessionCheckVersion] = useState(0)
  const [retryClock, setRetryClock] = useState(Date.now())

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
    if (window.location.pathname === '/capture') ingestCaptureFragment()
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    api.me()
      .then((nextUser) => {
        if (!active) return
        setUser(nextUser)
        setSessionFailure(null)
      })
      .catch((error) => {
        if (!active) return
        const problem = sessionCheckProblem(error)
        if (problem) {
          const seconds = problem.kind === 'rate_limited' ? (problem.retryAfter ?? 60) : 0
          setSessionFailure({ ...problem, retryUntil: Date.now() + seconds * 1000 })
          setRetryClock(Date.now())
        } else {
          setUser(null)
          setSessionFailure(null)
        }
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [sessionCheckVersion])

  useEffect(() => {
    if (!sessionFailure || sessionFailure.kind !== 'rate_limited') return undefined
    const timer = window.setInterval(() => setRetryClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [sessionFailure])

  if (loading) return <div className="loading-screen"><div className="loading-spinner" /><span>Loading JobGrid...</span></div>
  if (sessionFailure) {
    const secondsLeft = Math.max(0, Math.ceil((sessionFailure.retryUntil - retryClock) / 1000))
    return (
      <div className="auth-page">
        <section className="auth-card" role="alert">
          <h1>JobGrid connection unavailable</h1>
          <p>{sessionFailure.message}</p>
          {secondsLeft > 0 && <p>Retry is available in {secondsLeft} seconds. No login attempt has been submitted.</p>}
          <button
            className="auth-primary-button"
            type="button"
            disabled={secondsLeft > 0}
            onClick={() => setSessionCheckVersion((previous) => previous + 1)}
          >
            Retry connection
          </button>
        </section>
      </div>
    )
  }
  if (!user) {
    const params = new URLSearchParams(window.location.search)
    const returnTo = window.location.pathname === '/capture'
      ? '/capture'
      : isSafeCaptureReturnPath(params.get('return_to'))
    return <Login returnTo={returnTo} />
  }
  return <AuthenticatedApp user={user} onLogout={() => setUser(null)} />
}
