import { useEffect, useState } from 'react'
import { api } from '../api/client'

const DEV_LOGIN_ENABLED = import.meta.env.VITE_ENABLE_DEV_LOGIN === 'true'
const EMAIL_PASSWORD_ENABLED = import.meta.env.VITE_ENABLE_EMAIL_PASSWORD_AUTH === 'true'

const PROVIDERS = [
  { id: 'google', label: 'Continue with Google', icon: 'G' },
  { id: 'apple', label: 'Continue with Apple', icon: '' },
  { id: 'microsoft', label: 'Continue with Microsoft', icon: 'M' },
]

export default function Login({ returnTo = null }) {
  const query = new URLSearchParams(window.location.search)
  const link = new URLSearchParams(window.location.hash.slice(1))
  const oauthError = query.get('error')
  const emailAction = link.get('email_action')
  const [linkToken] = useState(link.get('token') || '')
  const [mode, setMode] = useState(
    EMAIL_PASSWORD_ENABLED && linkToken && emailAction === 'verify'
      ? 'verify'
      : EMAIL_PASSWORD_ENABLED && linkToken && emailAction === 'reset'
        ? 'reset'
        : 'login'
  )
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [devLoginError, setDevLoginError] = useState('')
  const [devLoginLoading, setDevLoginLoading] = useState(false)

  useEffect(() => {
    // One-time tokens live in the fragment, not in server/CDN request logs.
    if (linkToken) window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }, [linkToken])

  const chooseMode = (next) => {
    setMode(next)
    setFormError('')
    setNotice('')
    setPassword('')
    setConfirmPassword('')
  }

  const completeLogin = () => {
    window.location.assign(returnTo === '/capture' ? '/capture' : '/')
  }

  const submitEmail = async (event) => {
    event.preventDefault()
    setFormError('')
    setNotice('')
    if ((mode === 'register' || mode === 'reset') && password !== confirmPassword) {
      setFormError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'login') {
        await api.emailLogin(email, password)
        completeLogin()
      } else if (mode === 'register') {
        const result = await api.emailRegister(email, password)
        chooseMode('login')
        setNotice(result.message)
      } else if (mode === 'forgot') {
        const result = await api.emailForgotPassword(email)
        chooseMode('login')
        setNotice(result.message)
      } else if (mode === 'verify') {
        await api.emailVerify(linkToken)
        completeLogin()
      } else if (mode === 'reset') {
        await api.emailResetPassword(linkToken, password)
        completeLogin()
      }
    } catch (error) {
      const detail = error?.response?.data?.detail
      const message = typeof detail === 'string' ? detail : detail?.message
      if (error?.response?.status === 429) {
        const retry = Number(error.response.headers?.['retry-after'])
        setFormError(Number.isFinite(retry) && retry > 0
          ? 'Too many attempts. Try again in ' + Math.ceil(retry / 60) + ' minute(s).'
          : 'Too many attempts. Please try again later.')
      } else {
        setFormError(message || 'Unable to continue. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleDevLogin = async () => {
    setDevLoginError('')
    setDevLoginLoading(true)
    try {
      await api.devLogin()
      completeLogin()
    } catch {
      setDevLoginError('Local test login is not available. Start the backend with TEST_AUTH=true.')
      setDevLoginLoading(false)
    }
  }

  const actionName = {
    login: 'Sign in',
    register: 'Create account',
    forgot: 'Send reset link',
    verify: 'Verify my email',
    reset: 'Set new password',
  }[mode]

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Log in or sign up</h1>
        <p className="auth-subtitle">
          Upload CSV files, track job URLs, and manage your saved rows.
        </p>

        {oauthError && <div className="auth-error">Login failed. Please try again or use another method.</div>}
        {devLoginError && <div className="auth-error">{devLoginError}</div>}

        {EMAIL_PASSWORD_ENABLED && (
          <div className="auth-email-section">
            <h2>{mode === 'login' ? 'Use your email' : actionName}</h2>
            {formError && <div className="auth-error" role="alert">{formError}</div>}
            {notice && <p className="auth-email-notice" role="status">{notice}</p>}
            {mode === 'verify' && <p>Confirm your email to finish creating your account.</p>}
            {mode === 'reset' && <p>Choose a new password for your account.</p>}
            <form className="auth-email-form" onSubmit={submitEmail}>
              {['login', 'register', 'forgot'].includes(mode) && (
                <label htmlFor="auth-email">
                  Email address
                  <input
                    id="auth-email"
                    className="auth-input"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    maxLength={320}
                    required
                  />
                </label>
              )}
              {['login', 'register', 'reset'].includes(mode) && (
                <label htmlFor="auth-password">
                  {mode === 'reset' ? 'New password' : 'Password'}
                  <input
                    id="auth-password"
                    className="auth-input"
                    type="password"
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={mode === 'login' ? 'Your password' : 'At least 15 characters'}
                    minLength={15}
                    maxLength={128}
                    required
                  />
                </label>
              )}
              {['register', 'reset'].includes(mode) && (
                <label htmlFor="auth-confirm">
                  Confirm password
                  <input
                    id="auth-confirm"
                    className="auth-input"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    minLength={15}
                    maxLength={128}
                    required
                  />
                </label>
              )}
              <button className="auth-primary-button" type="submit" disabled={submitting}>
                {submitting ? 'Working...' : actionName}
              </button>
            </form>
            <div className="auth-email-links">
              {mode === 'login' && (
                <>
                  <button type="button" onClick={() => chooseMode('register')}>Create an account</button>
                  <button type="button" onClick={() => chooseMode('forgot')}>Forgot password?</button>
                </>
              )}
              {mode !== 'login' && (
                <button type="button" onClick={() => chooseMode('login')}>Back to sign in</button>
              )}
            </div>
            {mode === 'register' && <p className="auth-note">We’ll email you a verification link. Already used Google? Choose Forgot password to set a password for the same account.</p>}
          </div>
        )}

        <div className="auth-divider">
          <span></span><p>OR</p><span></span>
        </div>
        <div className="oauth-list">
          {PROVIDERS.map((provider) => (
            <a key={provider.id} className="oauth-button" href={api.loginUrl(provider.id, returnTo)}>
              <span className={'oauth-icon ' + provider.id}>{provider.icon}</span>
              <span>{provider.label}</span>
            </a>
          ))}
          <button className="oauth-button oauth-button-disabled" type="button" disabled>
            <span className="oauth-icon phone">☎</span>
            <span>Continue with phone</span>
          </button>
          {DEV_LOGIN_ENABLED && (
            <button className="oauth-button" type="button" onClick={handleDevLogin} disabled={devLoginLoading}>
              <span className="oauth-icon">D</span>
              <span>{devLoginLoading ? 'Signing in...' : 'Continue as local test user'}</span>
            </button>
          )}
        </div>
        <p className="auth-note">
          {EMAIL_PASSWORD_ENABLED
            ? 'Email sign-in and supported social providers use the same JobGrid account.'
            : 'OAuth login is active now. Email and phone login can be added next.'}
          {DEV_LOGIN_ENABLED && ' Local test login is enabled for this environment.'}
        </p>
      </div>
    </div>
  )
}
