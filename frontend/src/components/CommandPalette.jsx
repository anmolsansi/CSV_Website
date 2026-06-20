import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const ACTIONS = [
  { id: 'nav-dashboard', label: 'Go to Job Links', shortcut: 'G J', category: 'Navigation', action: 'navigate', path: '/' },
  { id: 'nav-applications', label: 'Go to Applications', shortcut: 'G A', category: 'Navigation', action: 'navigate', path: '/applications' },
  { id: 'nav-analytics', label: 'Go to Analytics', shortcut: 'G N', category: 'Navigation', action: 'navigate', path: '/analytics' },
  { id: 'nav-pipeline', label: 'Go to Pipeline', shortcut: 'G P', category: 'Navigation', action: 'navigate', path: '/pipeline' },
  { id: 'nav-sessions', label: 'Go to Sessions', shortcut: 'G S', category: 'Navigation', action: 'navigate', path: '/sessions' },
  { id: 'nav-saved-views', label: 'Go to Saved Views', shortcut: 'G V', category: 'Navigation', action: 'navigate', path: '/saved-views' },
  { id: 'nav-applypilot', label: 'Go to ApplyPilot', shortcut: 'G L', category: 'Navigation', action: 'navigate', path: '/applypilot' },
  { id: 'nav-duplicates', label: 'Go to Duplicates', shortcut: 'G D', category: 'Navigation', action: 'navigate', path: '/duplicates' },
  { id: 'nav-companies', label: 'Go to Company History', shortcut: 'G C', category: 'Navigation', action: 'navigate', path: '/companies' },
  { id: 'nav-import', label: 'Go to Import', shortcut: 'G I', category: 'Navigation', action: 'navigate', path: '/import' },
  { id: 'backup-export', label: 'Export Backup', category: 'Data', action: 'backup-export' },
  { id: 'backup-import', label: 'Go to Import Backup', category: 'Data', action: 'navigate', path: '/import' },
  { id: 'refresh', label: 'Refresh current page', shortcut: 'R', category: 'Actions', action: 'refresh' },
]

export default function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef(null)

  const filtered = ACTIONS.filter((a) =>
    a.label.toLowerCase().includes(query.toLowerCase()) ||
    a.category.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  const execute = useCallback((action) => {
    if (action.action === 'navigate') {
      navigate(action.path)
    } else if (action.action === 'refresh') {
      window.location.reload()
    } else if (action.action === 'backup-export') {
      api.exportBackup().then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `jobgrid_backup_${new Date().toISOString().slice(0, 10)}.json`
        a.click()
        URL.revokeObjectURL(url)
      })
    }
    onClose()
  }, [navigate, onClose])

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[selectedIndex]) execute(filtered[selectedIndex])
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 500 }} onClick={onClose} />
      <div style={{
        position: 'fixed', top: '20%', left: '50%', transform: 'translateX(-50%)',
        width: 480, maxWidth: '90vw', background: '#fff', borderRadius: 12,
        boxShadow: '0 8px 32px rgba(0,0,0,0.2)', zIndex: 501, overflow: 'hidden',
      }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb' }}>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command..."
            style={{ width: '100%', border: 'none', outline: 'none', fontSize: 16, padding: '4px 0' }}
          />
        </div>
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {filtered.length === 0 && (
            <div style={{ padding: 16, textAlign: 'center', color: '#6b7280', fontSize: 13 }}>No matching commands</div>
          )}
          {filtered.map((action, i) => (
            <div
              key={action.id}
              onClick={() => execute(action)}
              style={{
                padding: '10px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                background: i === selectedIndex ? '#f3f4f6' : 'transparent',
                fontSize: 14,
              }}
            >
              <span>{action.label}</span>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {action.shortcut && (
                  <span style={{ fontSize: 11, color: '#9ca3af', fontFamily: 'monospace' }}>
                    {action.shortcut.split(' ').map((k) => <kbd key={k} style={{ padding: '2px 4px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: 3, fontSize: 11 }}>{k}</kbd>)}
                  </span>
                )}
                <span style={{ fontSize: 11, color: '#9ca3af' }}>{action.category}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
