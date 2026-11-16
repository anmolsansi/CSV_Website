import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { installBrowserDiagnostics } from './api/diagnostics.js'
import './styles.css'

installBrowserDiagnostics()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
