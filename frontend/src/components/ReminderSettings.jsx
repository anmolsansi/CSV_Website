import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../api/client'
import { useToast } from '../App'

function statusLabel(item) {
  if (item.status === 'unknown') return 'Uncertain, may already have been sent'
  if (item.status === 'pending') return 'Pending'
  if (item.status === 'sending') return 'Sending'
  if (item.status === 'failed') return 'Failed'
  if (item.status === 'cancelled') return 'Cancelled'
  if (item.channel === 'in_app' && item.unread) return 'Delivered, unread'
  if (item.channel === 'in_app') return 'Delivered, read'
  return 'Sent'
}

export default function ReminderSettings() {
  const toast = useToast()
  const [preference, setPreference] = useState(null)
  const [draft, setDraft] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingId, setPendingId] = useState(null)
  const [retryConfirmId, setRetryConfirmId] = useState(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const [prefs, reminders] = await Promise.all([
        api.getReminderPreferences(),
        api.getReminders({ limit: 50 }),
      ])
      setPreference(prefs)
      setDraft({
        enabled: prefs.enabled,
        channel: prefs.channel,
        local_time: prefs.local_time,
        quiet_start: prefs.quiet_start,
        quiet_end: prefs.quiet_end,
      })
      setHistory(reminders.items || [])
    } catch (requestError) {
      setError(formatApiError(requestError, 'Could not load reminder settings.').message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const save = async (event) => {
    event.preventDefault()
    if (!preference || !draft || saving) return
    setSaving(true)
    setError('')
    try {
      const updated = await api.updateReminderPreferences({
        version: preference.version,
        ...draft,
      })
      setPreference(updated)
      setDraft({
        enabled: updated.enabled,
        channel: updated.channel,
        local_time: updated.local_time,
        quiet_start: updated.quiet_start,
        quiet_end: updated.quiet_end,
      })
      const reminders = await api.getReminders({ limit: 50 })
      setHistory(reminders.items || [])
      toast(updated.enabled ? 'Reminders enabled.' : 'Reminders disabled.', 'success')
    } catch (requestError) {
      setError(formatApiError(requestError, 'Could not save reminder settings.').message)
    } finally {
      setSaving(false)
    }
  }

  const retryUnknown = async (item) => {
    if (pendingId) return
    if (retryConfirmId !== item.id) {
      setRetryConfirmId(item.id)
      return
    }
    setPendingId(item.id)
    try {
      await api.retryReminder(item.id, item.version)
      setRetryConfirmId(null)
      await load()
      toast('Uncertain reminder queued for an explicit retry.', 'success')
    } catch (requestError) {
      toast(formatApiError(requestError, 'Could not retry reminder.').message, 'error')
    } finally {
      setPendingId(null)
    }
  }

  const markRead = async (item) => {
    if (pendingId) return
    setPendingId(item.id)
    try {
      await api.markReminderRead(item.id, item.version)
      await load()
    } catch (requestError) {
      toast(formatApiError(requestError, 'Could not mark reminder read.').message, 'error')
    } finally {
      setPendingId(null)
    }
  }

  if (loading) return <section aria-label="Reminders"><p>Loading reminder settings...</p></section>
  if (error && !draft) {
    return <section aria-label="Reminders" className="empty-state" role="alert"><p>{error}</p><button className="btn btn-grey" onClick={load}>Retry</button></section>
  }

  return (
    <section aria-labelledby="reminder-settings-heading" style={{ marginTop: 24 }}>
      <div className="page-header-row"><div><h3 id="reminder-settings-heading">Reminders</h3><p>Opt in to one reminder per follow-up due date using {preference?.timezone || 'your account timezone'}.</p></div></div>
      {error && <p className="error-msg" role="alert">{error}</p>}
      <form className="table-controls" onSubmit={save}>
        <div>
          <label htmlFor="reminder-enabled">Delivery</label>
          <label><input id="reminder-enabled" type="checkbox" checked={Boolean(draft?.enabled)} onChange={(e) => setDraft((v) => ({ ...v, enabled: e.target.checked }))} /> Enable reminders</label>
        </div>
        <div>
          <label htmlFor="reminder-channel">Channel</label>
          <select id="reminder-channel" value={draft?.channel || 'in_app'} onChange={(e) => setDraft((v) => ({ ...v, channel: e.target.value }))}>
            <option value="in_app">In-app</option>
            <option value="email" disabled={!preference?.email_available}>Email</option>
          </select>
          {!preference?.email_available && <small>Email unavailable: {preference?.email_unavailable_reason || 'not configured'}.</small>}
        </div>
        <div><label htmlFor="reminder-local-time">Local time</label><input id="reminder-local-time" type="time" value={draft?.local_time || '09:00'} onChange={(e) => setDraft((v) => ({ ...v, local_time: e.target.value }))} /></div>
        <div><label htmlFor="reminder-quiet-start">Quiet starts</label><input id="reminder-quiet-start" type="time" value={draft?.quiet_start || '21:00'} onChange={(e) => setDraft((v) => ({ ...v, quiet_start: e.target.value }))} /></div>
        <div><label htmlFor="reminder-quiet-end">Quiet ends</label><input id="reminder-quiet-end" type="time" value={draft?.quiet_end || '08:00'} onChange={(e) => setDraft((v) => ({ ...v, quiet_end: e.target.value }))} /></div>
        <div className="table-control-actions"><label>&nbsp;</label><button className="btn btn-blue" type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save reminders'}</button></div>
      </form>

      <h4 style={{ marginTop: 20 }}>Delivery history</h4>
      {history.length === 0 ? <p>No reminder deliveries yet.</p> : (
        <div className="table-wrap"><table><thead><tr><th>Application</th><th>Channel</th><th>Status</th><th>Scheduled</th><th>Action</th></tr></thead><tbody>
          {history.map((item) => <tr key={item.id}>
            <td>{item.company || 'Application'}{item.role ? <><br /><span style={{ color: '#6b7280' }}>{item.role}</span></> : null}</td>
            <td>{item.channel === 'in_app' ? 'In-app' : 'Email'}</td>
            <td>{statusLabel(item)}{item.last_error_code ? <><br /><small>{item.last_error_code}</small></> : null}</td>
            <td>{new Date(item.scheduled_at).toLocaleString()}</td>
            <td>
              {item.unread && <button className="btn btn-grey btn-sm" disabled={pendingId === item.id} onClick={() => markRead(item)}>Mark read</button>}
              {item.status === 'unknown' && <button className="btn btn-grey btn-sm" disabled={pendingId === item.id} onClick={() => retryUnknown(item)}>{retryConfirmId === item.id ? 'Retry anyway, duplicate possible' : 'Retry'}</button>}
              {retryConfirmId === item.id && <p className="error-msg">The provider may already have accepted this message. Retrying can create a duplicate.</p>}
            </td>
          </tr>)}
        </tbody></table></div>
      )}
    </section>
  )
}
