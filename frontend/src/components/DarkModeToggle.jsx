import { useState, useEffect, useCallback } from 'react'

const THEMES = ['light', 'dark', 'system']

function getSystemPreference() {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolveTheme(theme) {
  return theme === 'system' ? getSystemPreference() : theme
}

function applyTheme(theme) {
  const resolved = resolveTheme(theme)
  document.documentElement.setAttribute('data-theme', resolved)
}

export default function DarkModeToggle() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('jobgrid-theme') || 'system'
    } catch {
      return 'system'
    }
  })

  useEffect(() => {
    applyTheme(theme)
    try { localStorage.setItem('jobgrid-theme', theme) } catch {}
  }, [theme])

  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => applyTheme('system')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  const cycleTheme = useCallback(() => {
    setTheme((prev) => {
      const idx = THEMES.indexOf(prev)
      return THEMES[(idx + 1) % THEMES.length]
    })
  }, [])

  const icon = theme === 'dark' ? '🌙' : theme === 'light' ? '☀️' : '🖥️'
  const label = theme === 'dark' ? 'Dark mode' : theme === 'light' ? 'Light mode' : 'System theme'

  return (
    <button
      className="btn btn-grey btn-sm"
      onClick={cycleTheme}
      title={`Current: ${label}. Click to switch.`}
      aria-label={label}
    >
      {icon}
    </button>
  )
}
