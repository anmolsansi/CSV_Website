import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import RetryCountdown from './components/RetryCountdown.jsx'
import { readRetryAfter } from './api/authAvailability.js'
import { installBrowserDiagnostics } from './api/diagnostics.js'
import { recoveryDeadline, secondsUntil } from './utils/retryCountdown.js'
import './styles.css'

installBrowserDiagnostics()

function BackendStartupGate() {
  const [attempt, setAttempt] = useState(0)
  const [startedAt, setStartedAt] = useState(() => window.__jobgridBootstrapHealth?.startedAt ?? Date.now())
  const [startup, setStartup] = useState({ kind: 'checking' })
  const [clock, setClock] = useState(Date.now())

  useEffect(() => {
    let active = true
    setStartup({ kind: 'checking' })
    const bootstrap = window.__jobgridBootstrapHealth
    const probe = attempt === 0 ? bootstrap?.initial : bootstrap?.check()
    if (!probe) {
      const now = Date.now()
      setClock(now)
      setStartup({ kind: 'unavailable', status: null, retryUntil: recoveryDeadline(startedAt) })
      return () => { active = false }
    }

    Promise.resolve(probe).then((result) => {
      if (!active) return
      if (result?.ok) {
        setStartup({ kind: 'ready' })
        return
      }
      const retryAfter = readRetryAfter({ 'retry-after': result?.retryAfter })
      const status = Number.isInteger(result?.status) ? result.status : null
      console.warn('[JobGrid diagnostic]', {
        event: 'backend_health_failure',
        status,
        kind: status === 429 ? 'rate_limited' : status === null ? 'unverified' : 'not_healthy',
        retryAfterSeconds: retryAfter,
      })
      const now = Date.now()
      setClock(now)
      setStartup({ kind: 'unavailable', status, retryUntil: recoveryDeadline(startedAt, now, retryAfter) })
    })
    return () => { active = false }
  }, [attempt, startedAt])

  useEffect(() => {
    if (startup.kind === 'ready') return undefined
    // The clock is display-only. It never schedules a health request.
    const interval = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [startup.kind])

  if (startup.kind === 'ready') return <App />

  const retryDeadline = startup.retryUntil ?? recoveryDeadline(startedAt)
  const secondsRemaining = secondsUntil(retryDeadline, clock)

  return (
    <div className="auth-page" data-testid="backend-startup">
      <section className="auth-card">
        {startup.kind === 'checking' ? (
          <>
            <h1>Starting JobGrid</h1>
            <p role="status">Checking the Render backend before loading your session. A Free service may take about a minute to wake up.</p>
            <RetryCountdown label="Startup countdown:" seconds={secondsRemaining} />
            <div className="loading-spinner" aria-hidden="true" />
          </>
        ) : (
          <>
            <h1>JobGrid backend not ready</h1>
            <p role="alert">
              {startup.status === 429
                ? 'The hosting service is limiting requests to JobGrid. Your session has not been checked.'
                : startup.status === null
                  ? 'JobGrid could not confirm the backend is healthy. It may be starting, unreachable, or blocking the cross-origin response.'
                  : 'The backend health check returned an error. JobGrid has not attempted to check your session.'}
            </p>
            {startup.status !== null && <p>Health response: HTTP {startup.status}.</p>}
            <RetryCountdown label={secondsRemaining > 0 ? 'Retry available in:' : 'Ready to retry:'} seconds={secondsRemaining} />
            <button
              className="auth-primary-button"
              type="button"
              disabled={secondsRemaining > 0}
              onClick={() => {
                const now = Date.now()
                setStartedAt(now)
                setClock(now)
                setAttempt((previous) => previous + 1)
              }}
            >
              Retry backend connection
            </button>
          </>
        )}
      </section>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BackendStartupGate />
  </React.StrictMode>
)
