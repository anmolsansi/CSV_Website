import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatApiError } from '../api/client'
import {
  clearCaptureDraft,
  createCaptureBookmarklet,
  loadCaptureDraft,
  saveCaptureDraft,
  validateCaptureUrl,
} from '../utils/captureDraft'

const EMPTY_FORM = {
  job_url: '',
  title: '',
  company: '',
  notes: '',
  source: 'manual',
}

function newRequestKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `capture-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function validateForm(form) {
  const errors = {}
  const urlError = validateCaptureUrl(form.job_url)
  if (urlError) errors.job_url = urlError
  if (!form.title.trim()) errors.title = 'Title is required.'
  else if (form.title.length > 300) errors.title = 'Title must be 300 characters or fewer.'
  if (!form.company.trim()) errors.company = 'Company is required.'
  else if (form.company.length > 300) errors.company = 'Company must be 300 characters or fewer.'
  if (form.notes.length > 20000) errors.notes = 'Notes must be 20,000 characters or fewer.'
  return errors
}

export default function Capture() {
  const [form, setForm] = useState(() => loadCaptureDraft() || EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState({})
  const [matches, setMatches] = useState({ state: 'idle', items: [], companyHistoryCount: 0, error: '' })
  const [status, setStatus] = useState({ state: 'idle', message: '' })
  const [result, setResult] = useState(null)
  const requestKeyRef = useRef(newRequestKey())

  const bookmarklet = useMemo(() => createCaptureBookmarklet(window.location.origin), [])

  useEffect(() => {
    saveCaptureDraft(form)
  }, [form])

  useEffect(() => {
    const urlError = validateCaptureUrl(form.job_url)
    if (urlError) {
      setMatches({ state: 'idle', items: [], companyHistoryCount: 0, error: '' })
      return undefined
    }
    const timer = window.setTimeout(async () => {
      setMatches((current) => ({ ...current, state: 'loading', error: '' }))
      try {
        const data = await api.findApplicationMatches({
          url: form.job_url.trim(),
          company: form.company.trim() || null,
          title: form.title.trim() || null,
        })
        setMatches({
          state: 'loaded',
          items: data.matches || [],
          companyHistoryCount: data.company_history_count || 0,
          error: '',
        })
      } catch (error) {
        setMatches({
          state: 'error',
          items: [],
          companyHistoryCount: 0,
          error: formatApiError(error, 'Could not check prior application history.').message,
        })
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [form.job_url, form.company, form.title])

  const updateField = (field) => (event) => {
    const value = event.target.value
    setForm((current) => ({ ...current, [field]: value }))
    setFieldErrors((current) => ({ ...current, [field]: undefined }))
    setStatus({ state: 'idle', message: '' })
    if (result) {
      setResult(null)
      requestKeyRef.current = newRequestKey()
    }
  }

  const submit = async (event) => {
    event.preventDefault()
    const errors = validateForm(form)
    setFieldErrors(errors)
    if (Object.keys(errors).length) {
      setStatus({ state: 'error', message: 'Fix the highlighted fields before saving.' })
      return
    }

    saveCaptureDraft(form)
    setStatus({ state: 'pending', message: 'Saving job…' })
    try {
      const data = await api.captureJob(
        {
          job_url: form.job_url.trim(),
          title: form.title.trim(),
          company: form.company.trim(),
          source: form.source,
          ...(form.notes ? { notes: form.notes } : {}),
        },
        requestKeyRef.current
      )
      setResult(data)
      setStatus({
        state: 'success',
        message: data.created ? 'Job saved.' : 'This job was already saved. Existing row returned.',
      })
      clearCaptureDraft()
    } catch (error) {
      const formatted = formatApiError(error, 'Could not save this job. Your edits are still here.')
      const nextFields = {}
      for (const item of formatted.fields || []) {
        if (['job_url', 'title', 'company', 'notes'].includes(item.field)) nextFields[item.field] = item.message
      }
      setFieldErrors((current) => ({ ...current, ...nextFields }))
      setStatus({ state: 'error', message: `${formatted.message} Your edits are still here.` })
    }
  }

  const copyBookmarklet = async () => {
    try {
      await navigator.clipboard.writeText(bookmarklet)
      setStatus({ state: 'success', message: 'Bookmarklet copied. Create a browser bookmark and paste it into the URL field.' })
    } catch {
      window.prompt('Copy this bookmarklet:', bookmarklet)
    }
  }

  return (
    <div className="container capture-page">
      <div className="page-header-row">
        <div>
          <h2>Capture a job</h2>
          <p>Save one job without creating a CSV. Capturing does not mark it visited or applied.</p>
        </div>
      </div>

      <div className="capture-layout">
        <form className="capture-card" onSubmit={submit} aria-label="Capture job">
          <div className="capture-field">
            <label htmlFor="capture-url">Job URL</label>
            <input id="capture-url" value={form.job_url} onChange={updateField('job_url')} maxLength={2048} autoFocus />
            {fieldErrors.job_url && <span className="error-msg" role="alert">{fieldErrors.job_url}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="capture-title">Title</label>
            <input id="capture-title" value={form.title} onChange={updateField('title')} maxLength={300} />
            {fieldErrors.title && <span className="error-msg" role="alert">{fieldErrors.title}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="capture-company">Company</label>
            <input id="capture-company" value={form.company} onChange={updateField('company')} maxLength={300} />
            {fieldErrors.company && <span className="error-msg" role="alert">{fieldErrors.company}</span>}
          </div>
          <div className="capture-field">
            <label htmlFor="capture-notes">Notes <span className="capture-muted">(optional)</span></label>
            <textarea id="capture-notes" value={form.notes} onChange={updateField('notes')} maxLength={20000} rows={5} />
            {fieldErrors.notes && <span className="error-msg" role="alert">{fieldErrors.notes}</span>}
          </div>

          <button className="btn btn-blue" type="submit" disabled={status.state === 'pending'}>
            {status.state === 'pending' ? 'Saving…' : 'Save job'}
          </button>
          {status.message && (
            <p className={status.state === 'error' ? 'error-msg' : 'capture-status'} role={status.state === 'error' ? 'alert' : 'status'}>
              {status.message}
            </p>
          )}
        </form>

        <aside className="capture-card" aria-label="Prior application context">
          <h3>Prior application context</h3>
          {matches.state === 'idle' && <p className="capture-muted">Enter a valid job URL to check your existing application history.</p>}
          {matches.state === 'loading' && <p role="status">Checking your history…</p>}
          {matches.state === 'error' && <p className="error-msg" role="alert">{matches.error}</p>}
          {matches.state === 'loaded' && matches.items.length === 0 && (
            <p data-testid="capture-no-matches">No matching application history found.</p>
          )}
          {matches.state === 'loaded' && matches.items.length > 0 && (
            <div data-testid="capture-match-list">
              <p><strong>{matches.items.length}</strong> possible prior application match(es).</p>
              {matches.items.map((match) => (
                <div className="capture-match" key={`${match.track_id}-${match.confidence}`} data-testid={`capture-match-${match.confidence}`}>
                  <strong>{match.company || 'Unknown company'} · {match.title || 'Untitled role'}</strong>
                  <span>{match.confidence} match · {match.status || 'unknown status'}</span>
                  {match.track_id && (
                    <Link to={`/companies?company=${encodeURIComponent(match.company || form.company)}&track_id=${match.track_id}#application-${match.track_id}`}>
                      View application history
                    </Link>
                  )}
                </div>
              ))}
              {matches.companyHistoryCount > 0 && <p className="capture-muted">{matches.companyHistoryCount} applied role(s) found for this company.</p>}
            </div>
          )}
        </aside>
      </div>

      {result && (
        <section className="capture-card capture-result" aria-live="polite" data-testid="capture-result">
          <h3>{result.created ? 'Saved' : 'Already saved'}</h3>
          <p>Row #{result.row_id} is available in Job Links. Capture itself did not count as a visit or application.</p>
          <div className="capture-actions">
            <Link className="btn btn-grey" to="/">View saved row in Job Links</Link>
            {result.matches?.[0]?.track_id && (
              <Link
                className="btn btn-grey"
                to={`/companies?company=${encodeURIComponent(result.matches[0].company || form.company)}&track_id=${result.matches[0].track_id}#application-${result.matches[0].track_id}`}
              >
                View application history
              </Link>
            )}
          </div>
        </section>
      )}

      <section className="capture-card bookmarklet-card" aria-labelledby="bookmarklet-heading">
        <h3 id="bookmarklet-heading">One-click bookmarklet</h3>
        <p>
          The bookmarklet reads the current page URL and page title only when you click it, then opens JobGrid with an editable draft.
          It runs in the browser where you invoke it. JobGrid cannot force the page to open in Chrome or another installed browser.
        </p>
        <a data-testid="capture-bookmarklet" className="btn btn-green" href={bookmarklet}>Capture in JobGrid</a>
        <button className="btn btn-grey" type="button" onClick={copyBookmarklet}>Copy bookmarklet</button>
        <p className="capture-muted">
          If your browser blocks the popup, the bookmarklet shows the JobGrid capture link in a copy prompt so you can paste it manually.
          The source URL is carried in the URL fragment, not a server query string.
        </p>
      </section>
    </div>
  )
}
