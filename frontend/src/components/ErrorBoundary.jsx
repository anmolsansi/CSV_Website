import { Component } from 'react'
import { logReactFailure } from '../api/diagnostics'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch() {
    logReactFailure()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <h2>Something went wrong</h2>
          <p style={{ color: '#666', marginTop: 8 }}>An unexpected error occurred. Reload the page to try again.</p>
          <button className="btn btn-blue" style={{ marginTop: 16 }} onClick={() => { this.setState({ hasError: false }); window.location.reload() }}>
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
