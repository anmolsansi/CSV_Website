import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, formatApiError } from '../api/client'
import { contactApi } from '../api/contacts'
import { useToast } from '../App'

const EMPTY_DRAFT = {
  contact_id: '',
  starts_at: '',
  ends_at: '',
  timezone: '',
  kind: 'video',
  meeting_url: '',
  location: '',
  round_label: '',
  preparation_notes: '',
  notes: '',
}

function formatInZone(iso, timeZone) {
  if (!iso || !timeZone) return ''
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone,
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZoneName: 'short',
    }).format(new Date(iso))
  } catch {
    return ''
  }
}

function zoneParts(date, timeZone) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  })
  return Object.fromEntries(formatter.formatToParts(date).filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]))
}

export function zonedLocalToIso(value, timeZone) {
  if (!value || !timeZone) return ''
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/)
  if (!match) return ''
  const [, year, month, day, hour, minute] = match
  const desired = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), 0)
  let instant = new Date(desired)
  for (let index = 0; index < 3; index += 1) {
    const parts = zoneParts(instant, timeZone)
    const represented = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second))
    const delta = desired - represented
    if (delta === 0) break
    instant = new Date(instant.getTime() + delta)
  }
  return instant.toISOString()
}

function cleanDraft(draft) {
  return {
    contact_id: draft.contact_id ? Number(draft.contact_id) : null,
    starts_at: zonedLocalToIso(draft.starts_at, draft.timezone),
    ends_at: zonedLocalToIso(draft.ends_at, draft.timezone),
    timezone: draft.timezone,
    kind: draft.kind,
    meeting_url: draft.meeting_url || null,
    location: draft.location || null,
    round_label: draft.round_label || null,
    preparation_notes: draft.preparation_notes || null,
    notes: draft.notes || null,
  }
}

async function downloadCalendar(interview) {
  const blob = await contactApi.downloadInterviewCalendar(interview.id)
  const url = URL.createObjectURL(blob)
  try {
    const link = window.document.createElement('a')
    link.href = url
    link.download = `jobgrid_interview_${interview.id}.ics`
    window.document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export default function ApplicationInterviews({ application }) {
  const toast = useToast()
  const [interviews, setInterviews] = useState([])
  const [contacts, setContacts] = useState([])
  const [accountTimezone, setAccountTimezone] = useState('UTC')
  const [draft, setDraft] = useState(EMPTY_DRAFT)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [interviewData, contactData, profile] = await Promise.all([
        contactApi.getInterviews(application.id),
        contactApi.listContacts(),
        api.getProfileTimezone(),
      ])
      const timezone = profile.timezone || 'UTC'
      setInterviews(interviewData.interviews || [])
      setContacts(contactData.contacts || [])
      setAccountTimezone(timezone)
      setDraft((current) => ({ ...current, timezone: current.timezone || timezone }))
    } catch (requestError) {
      setError(formatApiError(requestError, 'Could not load interviews for this application.').message)
    } finally {
      setLoading(false)
    }
  }, [application.id])

  useEffect(() => { refresh() }, [refresh])

  const startIso = useMemo(() => {
    try { return zonedLocalToIso(draft.starts_at, draft.timezone) } catch { return '' }
  }, [draft.starts_at, draft.timezone])
  const endIso = useMemo(() => {
    try { return zonedLocalToIso(draft.ends_at, draft.timezone) } catch { return '' }
  }, [draft.ends_at, draft.timezone])

  const create = async (event) => {
    event.preventDefault()
    if (!startIso || !endIso || !draft.timezone || pending) return
    setPending(true)
    setError('')
    try {
      const created = await contactApi.createInterview(application.id, cleanDraft(draft))
      setDraft({ ...EMPTY_DRAFT, timezone: accountTimezone })
      if ((created.overlap_interview_ids || []).length > 0) {
        toast('Interview saved. It overlaps another scheduled interview.', 'warning')
      } else {
        toast('Interview saved.', 'success')
      }
      await refresh()
    } catch (requestError) {
      // Keep all private preparation notes and form values on failure.
      const message = formatApiError(requestError, 'Could not save the interview. Your draft was kept.').message
      setError(message)
      toast(message, 'error')
    } finally {
      setPending(false)
    }
  }

  const cancel = async (interview) => {
    if (pending || interview.status === 'cancelled') return
    setPending(true)
    setError('')
    try {
      await contactApi.updateInterview(interview.id, { version: interview.version, status: 'cancelled' })
      toast('Interview cancelled. Its pending Today preparation action is removed.', 'success')
      await refresh()
    } catch (requestError) {
      const message = formatApiError(requestError, 'Could not cancel the interview. Reload and retry.').message
      setError(message)
      toast(message, 'error')
    } finally {
      setPending(false)
    }
  }

  const download = async (interview) => {
    try {
      await downloadCalendar(interview)
      toast('Calendar file downloaded. No invitation was sent.', 'success')
    } catch (requestError) {
      const message = formatApiError(requestError, 'Could not download the calendar event.').message
      setError(message)
      toast(message, 'error')
    }
  }

  return (
    <section className="document-panel" aria-label="Application interviews" data-testid="application-interviews">
      <div className="document-panel-header">
        <div>
          <h3>Interviews</h3>
          <p className="muted-text">Schedule rounds in the interview timezone. Calendar export downloads one event only and never sends an invitation.</p>
        </div>
        <button type="button" className="btn btn-grey btn-sm" onClick={refresh} disabled={pending}>Refresh</button>
      </div>

      {loading ? <p role="status">Loading interviews…</p> : (
        <>
          {interviews.length === 0 ? (
            <p className="muted-text">No interviews scheduled yet.</p>
          ) : (
            <div className="document-link-list">
              {interviews.map((interview) => (
                <div className="document-link-row" key={interview.id} data-testid={`application-interview-${interview.id}`}>
                  <div>
                    <strong>{interview.round_label || `${interview.kind} interview`}</strong>
                    <div className="document-meta">
                      <span>{interview.status}</span>
                      <span>{formatInZone(`${interview.starts_at}Z`, interview.timezone)} ({interview.timezone})</span>
                      {accountTimezone !== interview.timezone && <span>Your timezone: {formatInZone(`${interview.starts_at}Z`, accountTimezone)}</span>}
                      {interview.contact?.name && <span>With {interview.contact.name}</span>}
                    </div>
                    {(interview.overlap_interview_ids || []).length > 0 && (
                      <p className="error-msg" role="status">Warning: overlaps {interview.overlap_interview_ids.length} other scheduled interview(s).</p>
                    )}
                    {interview.preparation_notes && <p className="muted-text">Prep: {interview.preparation_notes}</p>}
                  </div>
                  <div className="document-actions">
                    <button type="button" className="btn btn-grey btn-sm" onClick={() => download(interview)}>Download calendar event</button>
                    {interview.status === 'scheduled' && <button type="button" className="btn btn-grey btn-sm" disabled={pending} onClick={() => cancel(interview)}>Cancel interview</button>}
                  </div>
                </div>
              ))}
            </div>
          )}

          <form className="document-attach-form" onSubmit={create}>
            <label>
              Round
              <input maxLength={100} value={draft.round_label} onChange={(event) => setDraft((current) => ({ ...current, round_label: event.target.value }))} placeholder="Technical, hiring manager…" />
            </label>
            <label>
              Interviewer
              <select value={draft.contact_id} onChange={(event) => setDraft((current) => ({ ...current, contact_id: event.target.value }))}>
                <option value="">No linked person</option>
                {contacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.name}</option>)}
              </select>
            </label>
            <label>
              Timezone
              <input required maxLength={64} value={draft.timezone} onChange={(event) => setDraft((current) => ({ ...current, timezone: event.target.value }))} placeholder="America/Chicago" />
            </label>
            <label>
              Starts
              <input required type="datetime-local" value={draft.starts_at} onChange={(event) => setDraft((current) => ({ ...current, starts_at: event.target.value }))} />
            </label>
            <label>
              Ends
              <input required type="datetime-local" value={draft.ends_at} onChange={(event) => setDraft((current) => ({ ...current, ends_at: event.target.value }))} />
            </label>
            <label>
              Type
              <select value={draft.kind} onChange={(event) => setDraft((current) => ({ ...current, kind: event.target.value }))}>
                <option value="phone">Phone</option><option value="video">Video</option><option value="onsite">Onsite</option><option value="other">Other</option>
              </select>
            </label>
            <label>Meeting URL<input type="url" maxLength={2048} value={draft.meeting_url} onChange={(event) => setDraft((current) => ({ ...current, meeting_url: event.target.value }))} placeholder="https://…" /></label>
            <label>Location<input maxLength={500} value={draft.location} onChange={(event) => setDraft((current) => ({ ...current, location: event.target.value }))} /></label>
            <label>Private preparation notes<textarea maxLength={20000} value={draft.preparation_notes} onChange={(event) => setDraft((current) => ({ ...current, preparation_notes: event.target.value }))} /></label>
            <label>Private interview notes<textarea maxLength={20000} value={draft.notes} onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))} /></label>

            {startIso && (
              <div role="status" className="muted-text" data-testid="interview-timezone-preview">
                <div>Chosen timezone: {formatInZone(startIso, draft.timezone)}</div>
                <div>Your timezone: {formatInZone(startIso, accountTimezone)}</div>
              </div>
            )}
            <button className="btn btn-blue" type="submit" disabled={pending || !startIso || !endIso}>{pending ? 'Saving…' : 'Schedule interview'}</button>
          </form>
        </>
      )}

      {error && <p className="error-msg" role="alert">{error}</p>}
    </section>
  )
}
