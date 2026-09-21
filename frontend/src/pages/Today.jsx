import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, formatApiError } from '../api/client'
import { useToast } from '../App'

function localInputToIso(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

function localDateKey(value, timeZone) {
  if (!value) return null
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(value))
  const get = (type) => parts.find((part) => part.type === type)?.value || ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

function formatDue(value, timeZone) {
  if (!value) return 'No due time'
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function groupItems(items, asOf, timeZone) {
  const todayKey = localDateKey(asOf, timeZone)
  return items.reduce((groups, item) => {
    if (!item.due_at) groups.undated.push(item)
    else if (localDateKey(item.due_at, timeZone) < todayKey) groups.overdue.push(item)
    else groups.dueToday.push(item)
    return groups
  }, { overdue: [], dueToday: [], undated: [] })
}

function TodayDialog({ title, children, onClose }) {
  const ref = useRef(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (!node.open) node.showModal()
    return () => {
      if (node.open) node.close()
    }
  }, [])

  return (
    <dialog
      ref={ref}
      aria-labelledby="today-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      style={{ width: 'min(520px, 92vw)', border: 0, borderRadius: 12, padding: 0 }}
    >
      <div style={{ padding: 20 }}>
        <div className="page-header-row" style={{ marginBottom: 16 }}>
          <h3 id="today-dialog-title" style={{ margin: 0 }}>{title}</h3>
          <button className="btn btn-grey btn-sm" onClick={onClose} aria-label="Close dialog">Close</button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

export default function Today() {
  const navigate = useNavigate()
  const toast = useToast()
  const [queue, setQueue] = useState({ items: [], counts: {}, as_of: null, timezone: 'UTC', next_cursor: null })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [pendingKeys, setPendingKeys] = useState(new Set())
  const [conflicts, setConflicts] = useState({})
  const [description, setDescription] = useState('')
  const [manualDue, setManualDue] = useState('')
  const [manualError, setManualError] = useState('')
  const [manualPending, setManualPending] = useState(false)
  const [dialog, setDialog] = useState(null)
  const [dialogValue, setDialogValue] = useState('')
  const [dialogError, setDialogError] = useState('')
  const returnFocusRef = useRef(null)

  const loadToday = useCallback(async ({ cursor = null, append = false } = {}) => {
    setLoadError('')
    if (!append) setLoading(true)
    try {
      const data = await api.getToday({ limit: 100, ...(cursor ? { cursor } : {}) })
      setQueue((prev) => ({
        ...data,
        items: append ? [...prev.items, ...(data.items || [])] : (data.items || []),
      }))
      return data
    } catch (error) {
      setLoadError(formatApiError(error, 'Could not load Today. Please retry.').message)
      return null
    } finally {
      if (!append) setLoading(false)
    }
  }, [])

  useEffect(() => { loadToday() }, [loadToday])

  useEffect(() => {
    const handleFocus = () => { loadToday() }
    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [loadToday])

  const grouped = useMemo(
    () => groupItems(queue.items, queue.as_of || new Date().toISOString(), queue.timezone || 'UTC'),
    [queue.items, queue.as_of, queue.timezone]
  )

  const setPending = (key, pending) => {
    setPendingKeys((prev) => {
      const next = new Set(prev)
      if (pending) next.add(key)
      else next.delete(key)
      return next
    })
  }

  const recordConflict = (key, error) => {
    if (error?.response?.status !== 409) return false
    setConflicts((prev) => ({
      ...prev,
      [key]: formatApiError(error, 'This action changed. Refresh before retrying.').message,
    }))
    return true
  }

  const mutateItem = async (item, operation) => {
    if (pendingKeys.has(item.action_key)) return
    setPending(item.action_key, true)
    setConflicts((prev) => ({ ...prev, [item.action_key]: '' }))
    try {
      await operation()
      await loadToday()
    } catch (error) {
      if (!recordConflict(item.action_key, error)) {
        toast(formatApiError(error, 'Could not update this Today action.').message, 'error')
      }
    } finally {
      setPending(item.action_key, false)
    }
  }

  const createManual = async (event) => {
    event.preventDefault()
    setManualError('')
    const trimmed = description.trim()
    if (!trimmed) {
      setManualError('Description is required.')
      return
    }
    if (trimmed.length > 500) {
      setManualError('Description must be 500 characters or fewer.')
      return
    }
    const dueAt = manualDue ? localInputToIso(manualDue) : null
    if (manualDue && !dueAt) {
      setManualError('Enter a valid due date and time.')
      return
    }
    if (manualPending) return
    setManualPending(true)
    try {
      await api.createWorkItem({ description: trimmed, due_at: dueAt, priority: 1 })
      setDescription('')
      setManualDue('')
      toast('Added to Today.', 'success')
      await loadToday()
    } catch (error) {
      setManualError(formatApiError(error, 'Could not add the action. Your draft was kept.').message)
    } finally {
      setManualPending(false)
    }
  }

  const closeDialog = () => {
    setDialog(null)
    setDialogError('')
    requestAnimationFrame(() => returnFocusRef.current?.focus())
  }

  const openDialog = (kind, item, event) => {
    returnFocusRef.current = event.currentTarget
    setDialog({ kind, item })
    setDialogValue('')
    setDialogError('')
  }

  const submitDialog = async (event) => {
    event.preventDefault()
    const { kind, item } = dialog
    const iso = localInputToIso(dialogValue)
    if (!iso) {
      setDialogError('Choose a valid future date and time.')
      return
    }
    if (new Date(iso) <= new Date()) {
      setDialogError('Choose a future date and time.')
      return
    }
    setDialogError('')
    setPending(item.action_key, true)
    try {
      if (kind === 'snooze') {
        await api.snoozeTodayAction({
          action_key: item.action_key,
          until: iso,
          version: item.snooze_version,
        })
      } else {
        await api.resolveTodayFollowUp({
          action_key: item.action_key,
          resolution: 'reschedule',
          follow_up_at: iso,
        })
      }
      closeDialog()
      await loadToday()
    } catch (error) {
      if (recordConflict(item.action_key, error)) {
        setDialogError('This action changed. Close this dialog, refresh, and retry.')
      } else {
        setDialogError(formatApiError(error, 'Could not save the change. Your draft was kept.').message)
      }
    } finally {
      setPending(item.action_key, false)
    }
  }

  const complete = (item) => mutateItem(item, () => (
    item.type === 'manual'
      ? api.updateWorkItem(item.id, { version: item.version, state: 'done' })
      : api.resolveTodayFollowUp({ action_key: item.action_key, resolution: 'clear' })
  ))

  const openDetails = (item) => {
    const q = [item.company, item.role].filter(Boolean).join(' ')
    if (item.track_id) navigate(`/applications${q ? `?q=${encodeURIComponent(q)}` : ''}`)
    else navigate(`/${q ? `?q=${encodeURIComponent(q)}` : ''}`)
  }

  const renderGroup = (title, items) => (
    <section aria-labelledby={`today-${title.toLowerCase().replace(/\s+/g, '-')}`} style={{ marginTop: 24 }}>
      <div className="page-header-row" style={{ marginBottom: 8 }}>
        <h3 id={`today-${title.toLowerCase().replace(/\s+/g, '-')}`} style={{ margin: 0 }}>{title}</h3>
        <span>{items.length}</span>
      </div>
      {items.length === 0 ? <p style={{ color: '#6b7280' }}>No actions in this group.</p> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Action</th><th>Company / role</th><th>Origin</th><th>Due</th><th>Controls</th></tr></thead>
            <tbody>
              {items.map((item) => {
                const pending = pendingKeys.has(item.action_key)
                return (
                  <tr key={item.action_key}>
                    <td><strong>{item.description}</strong></td>
                    <td>{item.company || '—'}{item.role ? <><br /><span style={{ color: '#6b7280' }}>{item.role}</span></> : null}</td>
                    <td>{item.origin_label || item.type}</td>
                    <td>{formatDue(item.due_at, queue.timezone || 'UTC')}</td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        <button className="btn btn-green btn-sm" disabled={pending} onClick={() => complete(item)}>
                          {pending ? 'Saving...' : 'Complete'}
                        </button>
                        <button className="btn btn-grey btn-sm" disabled={pending} onClick={(event) => openDialog('snooze', item, event)}>Snooze</button>
                        {item.type === 'followup' && (
                          <button className="btn btn-grey btn-sm" disabled={pending} onClick={(event) => openDialog('reschedule', item, event)}>Reschedule</button>
                        )}
                        {(item.row_id || item.track_id) && <button className="btn btn-blue btn-sm" onClick={() => openDetails(item)}>Open details</button>}
                      </div>
                      {conflicts[item.action_key] && (
                        <p className="error-msg" role="alert" style={{ marginTop: 8 }}>
                          {conflicts[item.action_key]} <button className="btn btn-grey btn-sm" onClick={() => loadToday()}>Refresh</button>
                        </p>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )

  if (loading) {
    return <div className="container"><div className="empty-state"><div className="loading-spinner" /><p>Loading Today...</p></div></div>
  }

  if (loadError && queue.items.length === 0) {
    return (
      <div className="container">
        <div className="empty-state" role="alert">
          <h2>Today could not load</h2>
          <p>{loadError}</p>
          <button className="btn btn-blue" onClick={() => loadToday()}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Today</h2>
          <p>Your next useful actions in {queue.timezone || 'your account timezone'}.</p>
        </div>
        <button className="btn btn-blue" onClick={() => loadToday()}>Refresh</button>
      </div>

      {loadError && <div className="error-msg" role="alert">{loadError} <button className="btn btn-grey btn-sm" onClick={() => loadToday()}>Retry</button></div>}

      <div className="stats-grid app-stats-grid">
        <div className="stat-card"><span>Overdue</span><strong>{queue.counts?.overdue ?? grouped.overdue.length}</strong></div>
        <div className="stat-card"><span>Due today</span><strong>{queue.counts?.due_today ?? grouped.dueToday.length}</strong></div>
        <div className="stat-card"><span>Undated</span><strong>{queue.counts?.undated ?? grouped.undated.length}</strong></div>
      </div>

      <form className="table-controls" onSubmit={createManual} style={{ marginTop: 20 }}>
        <div>
          <label htmlFor="today-description">New action</label>
          <input id="today-description" value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} placeholder="e.g. Tailor resume for Acme" />
        </div>
        <div>
          <label htmlFor="today-due">Due (device timezone)</label>
          <input id="today-due" type="datetime-local" value={manualDue} onChange={(event) => setManualDue(event.target.value)} />
        </div>
        <div className="table-control-actions">
          <label>&nbsp;</label>
          <button className="btn btn-green" type="submit" disabled={manualPending}>{manualPending ? 'Adding...' : 'Add action'}</button>
        </div>
        {manualError && <div className="error-msg" role="alert">{manualError}</div>}
      </form>

      {queue.items.length === 0 ? (
        <div className="empty-state">
          <h3>Nothing needs attention today</h3>
          <p>Add a manual action above, or add matching jobs from a Saved View.</p>
        </div>
      ) : (
        <>
          {renderGroup('Overdue', grouped.overdue)}
          {renderGroup('Due today', grouped.dueToday)}
          {renderGroup('Undated', grouped.undated)}
          {queue.next_cursor && (
            <div style={{ marginTop: 16 }}>
              <button className="btn btn-grey" onClick={() => loadToday({ cursor: queue.next_cursor, append: true })}>Load more</button>
            </div>
          )}
        </>
      )}

      {dialog && (
        <TodayDialog title={dialog.kind === 'snooze' ? 'Snooze action' : 'Reschedule follow-up'} onClose={closeDialog}>
          <form onSubmit={submitDialog}>
            <label htmlFor="today-dialog-date">{dialog.kind === 'snooze' ? 'Snooze until' : 'New follow-up time'}</label>
            <input
              id="today-dialog-date"
              type="datetime-local"
              value={dialogValue}
              onChange={(event) => setDialogValue(event.target.value)}
              autoFocus
            />
            {dialogError && <p className="error-msg" role="alert">{dialogError}</p>}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-blue" type="submit" disabled={pendingKeys.has(dialog.item.action_key)}>
                {pendingKeys.has(dialog.item.action_key) ? 'Saving...' : 'Save'}
              </button>
              <button className="btn btn-grey" type="button" onClick={closeDialog}>Cancel</button>
            </div>
          </form>
        </TodayDialog>
      )}
    </div>
  )
}
