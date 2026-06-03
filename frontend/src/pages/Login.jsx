import { api } from '../api/client'

const PROVIDERS = [
  { id: 'google', label: 'Continue with Google', icon: 'G' },
  { id: 'apple', label: 'Continue with Apple', icon: '' },
  { id: 'microsoft', label: 'Continue with Microsoft', icon: 'M' },
]

export default function Login() {
  const params = new URLSearchParams(window.location.search)
  const error = params.get('error')

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Log in or sign up</h1>

        <p className="auth-subtitle">
          Upload CSV files, track job URLs, and manage your saved rows.
        </p>

        {error && (
          <div className="auth-error">
            Login failed. Please try again or use a different provider.
          </div>
        )}

        <div className="oauth-list">
          {PROVIDERS.map((provider) => (
            <a
              key={provider.id}
              className="oauth-button"
              href={api.loginUrl(provider.id)}
            >
              <span className={`oauth-icon ${provider.id}`}>{provider.icon}</span>
              <span>{provider.label}</span>
            </a>
          ))}

          <button className="oauth-button oauth-button-disabled" type="button" disabled>
            <span className="oauth-icon phone">☎</span>
            <span>Continue with phone</span>
          </button>
        </div>

        <div className="auth-divider">
          <span></span>
          <p>OR</p>
          <span></span>
        </div>

        <input
          className="auth-input"
          type="email"
          placeholder="Email address"
          disabled
        />

        <button className="auth-primary-button" type="button" disabled>
          Continue
        </button>

        <p className="auth-note">
          OAuth login is active now. Email and phone login can be added next.
        </p>
      </div>
    </div>
  )
}
