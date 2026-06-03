import { api } from '../api/client'

const PROVIDERS = [
  { id: 'google', label: 'Continue with Google' },
  { id: 'microsoft', label: 'Continue with Microsoft' },
  { id: 'apple', label: 'Continue with Apple' },
]

export default function Login() {
  return (
    <div className="login-card">
      <h2>CSV URL Tracker</h2>
      <p>Sign up or log in to upload and track your CSVs.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {PROVIDERS.map((p) => (
          <a key={p.id} className="btn btn-blue" href={api.loginUrl(p.id)}>
            {p.label}
          </a>
        ))}
      </div>
      <p style={{ fontSize: 12, color: '#6b7280', marginTop: 16 }}>
        First sign-in creates your account automatically. Logging in with a
        different provider that shares your email links to the same account.
      </p>
    </div>
  )
}
