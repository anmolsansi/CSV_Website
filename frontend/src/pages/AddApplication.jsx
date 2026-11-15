import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatApiError } from '../api/client'
import { validateCaptureUrl } from '../utils/captureDraft'

const EMPTY = {
  url: '',
  company: '',
  title: '',
  appliedAt: '',
  followUpAt: '',
  notes: '',
}

function newKey() {
  return window.crypto.randomUUID()
}

function toUtc(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

function checkForm(form) {
  const errors = {}
  const urlError = validateCaptureUrl(form.url)
  if (urlError) errors.url = urlError
  if (!form.company.trim()) errors.company = 'Company is required.'
  else if (form.company.length > 300) errors.company = 'Company must be 300 characters or fewer.'
  if (!form.title.trim()) errors.title = 'Role title is required.'
  else if (form.title.length > 300) errors.title = 'Role title must be 300 characters or fewer.'
  if (!toUtc(form.appliedAt)) errors.applied_at = 'Enter the date and time you actually applied.'
  else if (new Date(form.appliedAt).getTime() > Date.now() + 300000) errors.applied_at = 'Application date cannot be in the future.'
  if (form.followUpAt && !toUtc(form.followUpAt)) errors.follow_up_at = 'Enter a valid follow-up date and time.'
  if (form.notes.length > 20000) errors.notes = 'Notes must be 20,000 characters or fewer.'
  return errors
}

export default function AddApplication() {
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [matches, setMatches] = useState({ state: 'idle', items: [], count: 0, error: '' })
  const [acknowledged, setAcknowledged] = useState(false)
  const [review, setReview] = useState(null)
  const [outcome, setOutcome] = useState({ state: 'idle', message: '' })
  const [saved, setSaved] = useState(null)
  const requestKeyRef = useRef(newKey())
  const savingRef = useRef(false)
  const timezoneName = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time'

  useEffect(() => {
    const validation = validateCaptureUrl(form.url)
    if (validation || !form.company.trim() || !form.title.trim()) {
      setMatches({ state: 'idle', items: [], count: 0, error: '' })
      return undefined
    }
    let cancelled = false
    setMatches({ state: 'loading', items: [], count: 0, error: '' })
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.findApplicationMatches({
          url: form.url,
          company: form.company.trim(),
          title: form.title.trim(),
        })
        if (!cancelled) setMatches({
          state: 'loaded', items: found.matches || [],
          count: found.company_history_count || 0, error: '',
        })
      } catch (error) {
        if (!cancelled) setMatches({
          state: 'error', items: [], count: 0,
          error: formatApiError(error, 'Could not check existing applications.').message,
        })
      }
    }, 300)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [form.url, form.company, form.title])

  const change = (name) => (event) => {
    const value = event.target.value
    setForm((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name === 'appliedAt' ? 'applied_at' : name === 'followUpAt' ? 'follow_up_at' : name]: undefined }))
    setAcknowledged(false)
    setReview(null)
    setSaved(null)
    setOutcome({ state: 'idle', message: '' })
    requestKeyRef.current = newKey()
  }

  const hasDirectMatch = matches.items.some((item) => item.confidence === 'exact' || item.confidence === 'canonical')
  const hasPossibleMatch = matches.items.some((item) => item.confidence === 'possible')

  const prepareReview = (event) => {
    event.preventDefault()
    if (savingRef.current || saved) return
    const invalid = checkForm(form)
    setErrors(invalid)
    if (Object.keys(invalid).length) {
      setOutcome({ state: 'error', message: 'Correct the highlighted fields before reviewing.' })
      return
    }
    if (matches.state !== 'loaded') {
      setOutcome({ state: 'error', message: 'Check existing application history before recording this submission.' })
      return
    }
    if (hasDirectMatch) {
      setOutcome({ state: 'error', message: 'This application may already exist. Open the existing history instead.' })
      return
    }
    if (hasPossibleMatch && !acknowledged) {
      setOutcome({ state: 'error', message: 'Review the similar application and confirm this is a separate submission.' })
      return
    }
    setReview({
      url: form.url.trim(),
      company: form.company.trim(),
      title: form.title.trim(),
      applied_at: toUtc(form.appliedAt),
      confirmed: true,
      ...(form.notes.trim() ? { notes: form.notes } : {}),
      ...(form.followUpAt ? { follow_up_at: toUtc(form.followUpAt) } : {}),
      ...(acknowledged ? { acknowledge_possible_match: true } : {}),
    })
    setOutcome({ state: 'idle', message: '' })
  }

  const confirmSave = async () => {
    if (!review || savingRef.current || saved) return
    savingRef.current = true
    setOutcome({ state: 'pending', message: 'Saving confirmed application…' })
    try {
      const result = await api.createManualApplication(review, requestKeyRef.current)
      setSaved(result)
      setOutcome({
        state: 'success',
        message: result.replayed ? 'Previous save confirmed.' : 'Application recorded in your history.',
      })
    } catch (error) {
      const info = formatApiError(error, 'Could not confirm this application. Check history before retrying.')
      if (!error?.response || error.response.status >= 500) {
        setOutcome({
          state: 'unknown',
          message: 'Save result unknown. The server may have recorded it. Check My Applications before retrying this exact request.',
        })
      } else {
        const mapped = {}
        for (const field of info.fields) {
          if (field.field) mapped[field.field] = field.message
        }
        setErrors((current) => ({ ...current, ...mapped }))
        const list = error.response.data?.detail?.matches
        if (Array.isArray(list) && list.length) {
          setMatches({ state: 'loaded', items: list, count: 0, error: '' })
        }
        setOutcome({ state: 'error', message: info.message })
        setReview(null)
      }
    } finally {
      savingRef.current = false
    }
  }

  return (
    <div className="container capture-page">
      <div className="page-header-row">
        <div>
          <h2>Add application</h2>
          <p>Record a job application you already submitted, even if it was never in a CSV. JobGrid will not submit anything to the employer.</p>
        </div>
        <Link className="btn btn-grey" to="/applications?tab=applied">My Applications</Link>
      </div>

      <div className="capture-layout">
        <form className="capture-card" onSubmit={prepareReview} aria-label="Add application">
          <h3>Submitted job</h3>
          <div className="capture-field">
            <label htmlFor="manual-url">Job URL</label>
            <input id="manual-url" type="url" value={form.url} onChange={change('url')} maxLength={2048} disabled={!!review || !!saved} autoFocus />
            {errors.url && <span className="error-msg" role="alert">{errors.url}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="manual-company">Company</label>
            <input id="manual-company" value={form.company} onChange={change('company')} maxLength={300} disabled={!!review || !!saved} />
            {errors.company && <span className="error-msg" role="alert">{errors.company}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="manual-title">Job title</label>
            <input id="manual-title" value={form.title} onChange={change('title')} maxLength={300} disabled={!!review || !!saved} />
            {errors.title && <span className="error-msg" role="alert">{errors.title}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="manual-applied-date">Date and time applied ({timezoneName})</label>
            <input id="manual-applied-date" type="datetime-local" value={form.appliedAt} onChange={change('appliedAt')} disabled={!!review || !!saved} />
            {errors.applied_at && <span className="error-msg" role="alert">{errors.applied_at}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="manual-followup">Follow-up date and time (optional)</label>
            <input id="manual-followup" type="datetime-local" value={form.followUpAt} onChange={change('followUpAt')} disabled={!!review || !!saved} />
            {errors.follow_up_at && <span className="error-msg" role="alert">{errors.follow_up_at}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="manual-notes">Notes (optional)</label>
            <textarea id="manual-notes" value={form.notes} onChange={change('notes')} rows={4} maxLength={20000} disabled={!!review || !!saved} />
            {errors.notes && <span className="error-msg" role="alert">{errors.notes}</span>}
          </div>
          {hasPossibleMatch && !hasDirectMatch && (
            <label className="manual-apply-acknowledge">
              <input
                type="checkbox" checked={acknowledged}
                onChange={(event) => { setAcknowledged(event.target.checked); setOutcome({ state: 'idle', message: '' }); requestKeyRef.current = newKey() }}
                disabled={!!review || !!saved}
              />
              I reviewed the similar application. This is a different job submission.
            </label>
          )}
          {!review && !saved && (
            <button type="submit" className="btn btn-blue" disabled={matches.state === 'loading'}>
              Review application details
            </button>
          )}
        </form>

        <aside className="capture-card" aria-label="Prior application context">
          <h3>Prior application check</h3>
          {matches.state === 'idle' && <p className="capture-muted">Enter the job URL, company, and title to check existing submissions.</p>}
          {matches.state === 'loading' && <p role="status">Checking your history…</p>}
          {matches.state === 'error' && <p className="error-msg" role="alert">{matches.error} Retry after editing a field.</p>}
          {matches.state === 'loaded' && matches.items.length === 0 && (
            <p>No matching confirmed applications were found. This does not guarantee a submission never existed.</p>
          )}
          {matches.state === 'loaded' && matches.items.length > 0 && (
            <div data-testid="manual-apply-matches">
              <p><strong>{matches.items.length}</strong> existing application match(es). Exact or canonical matches must be reviewed instead of saved twice.</p>
              {matches.items.map((item) => (
                <div key={item.track_id} className="capture-match">
                  <strong>{item.company || 'Unknown company'} · {item.title || 'Untitled job'}</strong>
                  <span>{item.confidence} match · {item.status}</span>
                  <Link to={`/applications?tab=applied&track_id=${item.track_id}`}>View existing application</Link>
                </div>
              ))}
            </div>
          )}
          {matches.count > 0 && <p className="capture-muted">{matches.count} prior submissions at this company.</p>}
        </aside>
      </div>

      {review && !saved && (
        <section className="capture-card manual-apply-review" aria-label="Confirm submitted application" data-testid="manual-apply-review">
          <h3>Confirm a completed job submission</h3>
          <p>Only save after you have actually submitted this job application.</p>
          <dl>
            <dt>Company</dt><dd>{review.company}</dd>
            <dt>Job title</dt><dd>{review.title}</dd>
            <dt>Job URL</dt><dd>{review.url}</dd>
            <dt>Applied at</dt><dd>{new Date(review.applied_at).toLocaleString()}</dd>
          </dl>
          <div className="capture-actions">
            <button type="button" className="btn btn-blue" onClick={confirmSave} disabled={outcome.state === 'pending'}>
              {outcome.state === 'pending' ? 'Saving…' : outcome.state === 'unknown' ? 'Retry same save' : 'Confirm I applied and save'}
            </button>
            {outcome.state !== 'unknown' && (
              <button type="button" className="btn btn-grey" onClick={() => { setReview(null); setOutcome({ state: 'idle', message: '' }) }} disabled={outcome.state === 'pending'}>
                Edit details
              </button>
            )}
          </div>
        </section>
      )}

      {outcome.message && <p role={outcome.state === 'error' ? 'alert' : 'status'} className={outcome.state === 'error' ? 'error-msg' : 'capture-status'}>{outcome.message}</p>}
      {outcome.state === 'unknown' && <Link className="btn btn-grey" to="/applications?tab=applied">Check My Applications</Link>}
      {saved && (
        <section className="capture-card capture-result" role="status" data-testid="manual-apply-success">
          <h3>Application saved</h3>
          <p>Your confirmed application is now part of your lifetime history.</p>
          <Link className="btn btn-blue" to={`/applications?tab=applied&track_id=${saved.application_id}`}>View saved application</Link>
        </section>
      )}
    </div>
  )
}
