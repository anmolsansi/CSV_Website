import { useEffect, useMemo, useRef, useState } from 'react'
import { api, apiFieldErrors, formatApiError } from '../api/client'

const EVIDENCE_KINDS = [
  ['confirmation_url', 'Confirmation URL'],
  ['confirmation_text', 'Confirmation text'],
  ['note', 'Note'],
]

const KIND_LABELS = {
  application_created: 'Application recorded',
  application_imported: 'Application imported',
  status_changed: 'Status changed',
  applied_date_corrected: 'Applied date corrected',
  evidence_added: 'Evidence added',
  evidence_edited: 'Evidence edited',
  evidence_deleted: 'Evidence deleted',
  confirmation_url: 'Confirmation URL',
  confirmation_text: 'Confirmation text',
  note: 'Note',
}

function formatDate(value) {
  if (!value) return 'Unknown'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unknown' : parsed.toLocaleString()
}

function localInputValue(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const offset = parsed.getTimezoneOffset() * 60000
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16)
}

function inputToIso(value) {
  return value ? new Date(value).toISOString() : ''
}

function errorStatus(error) {
  return error?.response?.status || 0
}

function itemKey(item) {
  return `${item.type}:${item.id}`
}

function eventDate(item) {
  if (item.type === 'evidence') return item.occurred_at || null
  return item.occurred_at || item.timestamp || null
}

function recordedAt(item) {
  return item.recorded_at || item.created_at || null
}

function timelineDescription(item) {
  if (item.type === 'evidence') {
    if (item.is_deleted) return 'Evidence deleted. Its body is hidden from normal reads.'
    return item.body || ''
  }
  const payload = item.payload || {}
  if (item.kind === 'status_changed') {
    return `${payload.from || 'Unknown'} → ${payload.to || 'Unknown'}${payload.reason ? ` · ${payload.reason}` : ''}`
  }
  if (item.kind === 'applied_date_corrected') {
    const previous = payload.previous_applied_at || payload.from || 'Unknown'
    const next = payload.applied_at || payload.new_applied_at || payload.to || 'Unknown'
    return `${formatDate(previous)} → ${formatDate(next)}${payload.reason ? ` · ${payload.reason}` : ''}`
  }
  return payload.reason || ''
}

export default function ApplicationTimeline({ application, onApplicationChanged }) {
  const [items, setItems] = useState([])
  const [nextBefore, setNextBefore] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [createDraft, setCreateDraft] = useState({ kind: 'confirmation_text', body: '', occurred_at: '' })
  const [createErrors, setCreateErrors] = useState({})
  const [createPending, setCreatePending] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editBody, setEditBody] = useState('')
  const [editError, setEditError] = useState('')
  const [editPending, setEditPending] = useState(false)
  const [conflictMessage, setConflictMessage] = useState('')
  const [appliedDate, setAppliedDate] = useState(localInputValue(application.applied_at))
  const [appliedReason, setAppliedReason] = useState('')
  const [appliedPending, setAppliedPending] = useState(false)
  const [appliedError, setAppliedError] = useState('')
  const [statusReason, setStatusReason] = useState('')
  const [statusPending, setStatusPending] = useState(false)
  const [statusError, setStatusError] = useState('')
  const editButtonRefs = useRef({})

  const loadTimeline = async ({ before = null, append = false } = {}) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    setLoadError('')
    try {
      const data = await api.getApplicationTimeline(application.id, {
        ...(before ? { before } : {}),
        limit: 50,
      })
      const received = data.items || []
      setItems((current) => append ? [...received, ...current] : received)
      setNextBefore(data.next_before || null)
      setConflictMessage('')
    } catch (error) {
      setLoadError(formatApiError(error, 'Could not load application history. Please retry.').message)
    } finally {
      if (append) setLoadingMore(false)
      else setLoading(false)
    }
  }

  useEffect(() => {
    setItems([])
    setNextBefore(null)
    setCreateDraft({ kind: 'confirmation_text', body: '', occurred_at: '' })
    setEditingId(null)
    setAppliedDate(localInputValue(application.applied_at))
    setAppliedReason('')
    setStatusReason('')
    setConflictMessage('')
    loadTimeline()
  }, [application.id])

  const latestStatusEvent = useMemo(
    () => [...items].reverse().find((item) => item.type === 'lifecycle' && item.kind === 'status_changed' && item.payload?.from),
    [items]
  )

  const submitEvidence = async (event) => {
    event.preventDefault()
    if (createPending) return
    const localErrors = {}
    const body = createDraft.body.trim()
    if (!body) localErrors.body = 'Evidence is required.'
    if (createDraft.kind === 'confirmation_url') {
      try {
        const parsed = new URL(body)
        if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
          localErrors.body = 'Use a credential-free HTTP(S) URL.'
        }
      } catch {
        localErrors.body = 'Use a valid HTTP(S) URL.'
      }
    }
    if (Object.keys(localErrors).length) {
      setCreateErrors(localErrors)
      return
    }

    setCreatePending(true)
    setCreateErrors({})
    try {
      await api.createApplicationEvidence(application.id, {
        kind: createDraft.kind,
        body,
        ...(createDraft.occurred_at ? { occurred_at: inputToIso(createDraft.occurred_at) } : {}),
      })
      setCreateDraft({ kind: createDraft.kind, body: '', occurred_at: '' })
      await loadTimeline()
    } catch (error) {
      setCreateErrors(apiFieldErrors(error, formatApiError(error, 'Could not save evidence.').message))
    } finally {
      setCreatePending(false)
    }
  }

  const startEdit = (item) => {
    setEditingId(item.id)
    setEditBody(item.body || '')
    setEditError('')
    setConflictMessage('')
  }

  const cancelEdit = (id) => {
    setEditingId(null)
    setEditBody('')
    setEditError('')
    requestAnimationFrame(() => editButtonRefs.current[id]?.focus())
  }

  const saveEdit = async (item) => {
    if (editPending) return
    if (!editBody.trim()) {
      setEditError('Evidence is required.')
      return
    }
    setEditPending(true)
    setEditError('')
    setConflictMessage('')
    try {
      await api.updateApplicationEvidence(application.id, item.id, {
        version: item.version,
        body: editBody,
      })
      setEditingId(null)
      setEditBody('')
      await loadTimeline()
      requestAnimationFrame(() => editButtonRefs.current[item.id]?.focus())
    } catch (error) {
      if (errorStatus(error) === 409) {
        setConflictMessage('This evidence changed after you opened it. Your draft is preserved. Reload history before retrying.')
      } else {
        setEditError(formatApiError(error, 'Could not update evidence.').message)
      }
    } finally {
      setEditPending(false)
    }
  }

  const removeEvidence = async (item) => {
    if (!window.confirm('Delete this evidence? The body disappears from normal reads immediately and may remain in recovery data for up to 30 days.')) return
    setConflictMessage('')
    try {
      await api.deleteApplicationEvidence(application.id, item.id)
      if (editingId === item.id) {
        setEditingId(null)
        setEditBody('')
      }
      await loadTimeline()
    } catch (error) {
      if (errorStatus(error) === 409) {
        setConflictMessage('This evidence changed before deletion. Reload history and review the latest version.')
      } else {
        setLoadError(formatApiError(error, 'Could not delete evidence.').message)
      }
    }
  }

  const submitAppliedCorrection = async (event) => {
    event.preventDefault()
    if (appliedPending) return
    if (!appliedDate || !appliedReason.trim()) {
      setAppliedError('Choose the corrected date and explain why it is changing.')
      return
    }
    if (inputToIso(appliedDate) === application.applied_at) {
      setAppliedError('Choose a date different from the current applied date.')
      return
    }
    setAppliedPending(true)
    setAppliedError('')
    setConflictMessage('')
    try {
      const updated = await api.correctApplicationAppliedDate(application.id, {
        applied_at: inputToIso(appliedDate),
        reason: appliedReason.trim(),
      })
      setAppliedReason('')
      onApplicationChanged?.(updated)
      await loadTimeline()
    } catch (error) {
      if (errorStatus(error) === 409) {
        setConflictMessage('The application changed before this correction could be saved. Your correction draft is preserved. Reload history and retry.')
      } else {
        setAppliedError(formatApiError(error, 'Could not correct the applied date.').message)
      }
    } finally {
      setAppliedPending(false)
    }
  }

  const submitStatusCorrection = async (event) => {
    event.preventDefault()
    if (!latestStatusEvent || statusPending) return
    if (!statusReason.trim()) {
      setStatusError('Explain why the latest status should be corrected.')
      return
    }
    setStatusPending(true)
    setStatusError('')
    setConflictMessage('')
    try {
      const updated = await api.correctApplicationStatus(application.id, {
        expected_event_id: latestStatusEvent.id,
        restore_status: latestStatusEvent.payload.from,
        reason: statusReason.trim(),
      })
      setStatusReason('')
      onApplicationChanged?.(updated)
      await loadTimeline()
    } catch (error) {
      if (errorStatus(error) === 409) {
        setConflictMessage('A newer status change exists. Nothing was overwritten. Your reason is preserved. Reload history before retrying.')
      } else {
        setStatusError(formatApiError(error, 'Could not correct the latest status.').message)
      }
    } finally {
      setStatusPending(false)
    }
  }

  const oldAppliedDay = application.applied_at ? new Date(application.applied_at).toLocaleDateString() : 'Unknown'
  const newAppliedDay = appliedDate ? new Date(inputToIso(appliedDate)).toLocaleDateString() : 'Unknown'

  return (
    <section aria-label={`History and evidence for ${application.company || application.title || 'application'}`} data-testid="application-timeline" style={{ padding: 16, background: '#f8fafc', borderTop: '1px solid #e5e7eb' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>History & evidence</h3>
          <p style={{ margin: '4px 0 0', color: '#6b7280' }}>Evidence is your recorded assertion. JobGrid does not verify that a confirmation proves submission.</p>
        </div>
        <button className="btn btn-grey btn-sm" onClick={() => loadTimeline()} disabled={loading}>Reload history</button>
      </div>

      {conflictMessage && (
        <div className="error-msg" role="alert" data-testid="timeline-conflict">
          {conflictMessage} <button className="btn btn-grey btn-sm" onClick={() => loadTimeline()}>Reload history</button>
        </div>
      )}

      {loading ? (
        <div className="empty-state"><div className="loading-spinner" /><p>Loading history...</p></div>
      ) : loadError ? (
        <div className="error-msg" role="alert">{loadError} <button className="btn btn-grey btn-sm" onClick={() => loadTimeline()}>Retry</button></div>
      ) : items.length === 0 ? (
        <div className="empty-state" data-testid="timeline-empty"><p>No recorded history yet.</p></div>
      ) : (
        <ol style={{ listStyle: 'none', padding: 0, margin: '0 0 12px', display: 'grid', gap: 8 }}>
          {items.map((item) => {
            const occurrence = eventDate(item)
            const recorded = recordedAt(item)
            return (
              <li key={itemKey(item)} data-testid={`timeline-item-${item.type}-${item.id}`} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <strong>{KIND_LABELS[item.kind] || item.kind}</strong>
                  <span style={{ color: '#6b7280', fontSize: 12 }}>
                    {item.source || 'legacy'} · <span data-testid="timeline-event-date">{occurrence ? formatDate(occurrence) : 'Unknown'}</span>
                    {recorded && <span title={`Recorded at ${formatDate(recorded)}`} aria-label={`Recorded at ${formatDate(recorded)}`} style={{ marginLeft: 8, cursor: 'help' }}>Recorded</span>}
                  </span>
                </div>
                {item.source === 'import' && <p style={{ margin: '6px 0 0', color: '#6b7280', fontSize: 12 }}>Imported record time is not assumed to be the application date.</p>}
                {timelineDescription(item) && <p data-testid="timeline-body" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{timelineDescription(item)}</p>}
                {item.type === 'evidence' && !item.is_deleted && (
                  <div style={{ marginTop: 8 }}>
                    {editingId === item.id ? (
                      <div>
                        <label htmlFor={`evidence-edit-${item.id}`}>Edit evidence</label>
                        <textarea id={`evidence-edit-${item.id}`} value={editBody} onChange={(e) => setEditBody(e.target.value)} disabled={editPending} style={{ width: '100%', minHeight: 72 }} />
                        {editError && <p className="error-msg" role="alert">{editError}</p>}
                        <button className="btn btn-blue btn-sm" onClick={() => saveEdit(item)} disabled={editPending}>{editPending ? 'Saving...' : 'Save edit'}</button>
                        <button className="btn btn-grey btn-sm" onClick={() => cancelEdit(item.id)} disabled={editPending} style={{ marginLeft: 6 }}>Cancel</button>
                      </div>
                    ) : (
                      <>
                        <button ref={(node) => { editButtonRefs.current[item.id] = node }} className="btn btn-grey btn-sm" onClick={() => startEdit(item)}>Edit evidence</button>
                        <button className="btn btn-grey btn-sm" onClick={() => removeEvidence(item)} style={{ marginLeft: 6 }}>Delete evidence</button>
                      </>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {nextBefore && !loading && (
        <button className="btn btn-grey btn-sm" onClick={() => loadTimeline({ before: nextBefore, append: true })} disabled={loadingMore}>
          {loadingMore ? 'Loading...' : 'Load more history'}
        </button>
      )}

      <form onSubmit={submitEvidence} style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid #e5e7eb' }}>
        <h4>Add evidence</h4>
        <div style={{ display: 'grid', gap: 8, maxWidth: 720 }}>
          <label>Type
            <select value={createDraft.kind} onChange={(e) => setCreateDraft((current) => ({ ...current, kind: e.target.value }))} disabled={createPending}>
              {EVIDENCE_KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Evidence
            <textarea value={createDraft.body} onChange={(e) => { setCreateDraft((current) => ({ ...current, body: e.target.value })); setCreateErrors({}) }} disabled={createPending} placeholder={createDraft.kind === 'confirmation_url' ? 'https://...' : 'Record the evidence as plain text'} style={{ width: '100%', minHeight: 72 }} />
          </label>
          {createErrors.body && <p className="error-msg" role="alert">{createErrors.body}</p>}
          <label>Event date (optional)
            <input type="datetime-local" value={createDraft.occurred_at} onChange={(e) => setCreateDraft((current) => ({ ...current, occurred_at: e.target.value }))} disabled={createPending} />
          </label>
          {createErrors.occurred_at && <p className="error-msg" role="alert">{createErrors.occurred_at}</p>}
          {createErrors.non_field && <p className="error-msg" role="alert">{createErrors.non_field}</p>}
          <button className="btn btn-blue" type="submit" disabled={createPending}>{createPending ? 'Saving evidence...' : 'Add evidence'}</button>
        </div>
      </form>

      {application.applied_at && (
        <form onSubmit={submitAppliedCorrection} style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid #e5e7eb' }}>
          <h4>Correct applied date</h4>
          <p style={{ color: '#6b7280' }}>Corrections append history. They do not erase the original application event.</p>
          <div style={{ display: 'grid', gap: 8, maxWidth: 720 }}>
            <label>Corrected applied date
              <input type="datetime-local" value={appliedDate} onChange={(e) => setAppliedDate(e.target.value)} disabled={appliedPending} />
            </label>
            <label>Reason
              <textarea value={appliedReason} onChange={(e) => setAppliedReason(e.target.value)} maxLength={500} disabled={appliedPending} />
            </label>
            <p data-testid="applied-date-preview" style={{ margin: 0, color: '#6b7280' }}>Daily application metrics will move from {oldAppliedDay} to {newAppliedDay}. First-applied history remains recorded.</p>
            {appliedError && <p className="error-msg" role="alert">{appliedError}</p>}
            <button className="btn btn-grey" type="submit" disabled={appliedPending}>{appliedPending ? 'Correcting...' : 'Correct applied date'}</button>
          </div>
        </form>
      )}

      {latestStatusEvent && (
        <form onSubmit={submitStatusCorrection} style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid #e5e7eb' }}>
          <h4>Correct latest status</h4>
          <p data-testid="status-correction-preview">Preview: {latestStatusEvent.payload.to || application.status} → {latestStatusEvent.payload.from}. A compensating event will be added.</p>
          <div style={{ display: 'grid', gap: 8, maxWidth: 720 }}>
            <label>Reason
              <textarea value={statusReason} onChange={(e) => setStatusReason(e.target.value)} maxLength={500} disabled={statusPending} />
            </label>
            {statusError && <p className="error-msg" role="alert">{statusError}</p>}
            <button className="btn btn-grey" type="submit" disabled={statusPending}>{statusPending ? 'Correcting...' : 'Correct latest status'}</button>
          </div>
        </form>
      )}
    </section>
  )
}
