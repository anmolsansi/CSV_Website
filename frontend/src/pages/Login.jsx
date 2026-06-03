import { api } from '../api/client'

export default function Login() {
  return (
    <div className="login-card">
      <h2>CSV URL Tracker</h2>
      <p>Sign in to upload and track your CSVs.</p>
      <a className="btn btn-blue" href={api.loginGoogleUrl()}>
        Sign in with Google
      </a>
    </div>
  )
}
