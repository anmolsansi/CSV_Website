import { useCallback, useEffect, useRef, useState } from 'react'
import { api, formatApiError } from '../api/client'

const STATE_LABELS = {
  unknown: 'Status unknown',
  available: 'Link reachable',
  unavailable: 'Link unavailable',
  closed: 'Closed by you',
}

function formatTimestamp(value, timeZone) {
  if (!value) return 'Never'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timeZone || 'UTC',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

export default function JobAvailability({ rowId = null, trackId = null, onChanged = null }) {
  const [availability, setAvailability] = useState(null)
  const [deadlineDraft, setDeadlineDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const pollTimers = useRef([])

  const isTrack = Boolean(trackId)
  const sourceId = isTrack ? trackId : rowId

  const getAvailability = useCallback(() => {
    if (!sourceId) return Promise.resolve(null)
    return isTrack
      ? api.getTrackAvailability(sourceId)
      : api.getJobAvailability(sourceId)
  }, [isTrack, sourceId])

  const updateAvailability = useCallback((payload) => (
    isTrack
      ? api.updateTrackAvailability(sourceId, payload)
      : api.updateJobAvailability(sourceId, payload)
  ), [isTrack, sourceId])

  const checkAvailability = useCallback(() => (
    isTrack
      ? api.checkTrackAvailability(sourceId)
      : api.checkJobAvailability(sourceId)
  ), [isTrack, sourceId])

  const applyLoaded = useCallback((data, { preserveDraft = false } = {}) => {
    if (!data) return
    setAvailability(data)
    if (!preserveDraft) setDeadlineDraft(data.deadline_local_date || '')
    if (onChanged) onChanged(data)
  }, [onChanged])

  const load = useCallback(async ({ preserveDraft = false, silent = false } = {}) => {
    if (!sourceId) return
    if (!silent) setLoading(true)
    try {
      const data = await getAvailability()
      applyLoaded(data, { preserveDraft })
      setError('')
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not load deadline and freshness information.',
      ).message)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [applyLoaded, getAvailability, sourceId])

  useEffect(() => {
    setAvailability(null)
    setDeadlineDraft('')
    setMessage('')
    setError('')
    load()
    return () => {
      pollTimers.current.forEach((timer) => window.clearTimeout(timer))
      pollTimers.current = []
    }
  }, [load])

  const saveDeadline = async () => {
    if (!availability || pending) return
    setPending(true)
    setError('')
    setMessage('')
    try {
      const data = await updateAvailability({
        version: availability.version,
        deadline_at: deadlineDraft || null,
      })
      applyLoaded(data)
      setMessage(deadlineDraft ? 'Deadline saved.' : 'Deadline cleared.')
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not save the deadline. Your draft was kept.',
      ).message)
    } finally {
      setPending(false)
    }
  }

  const changeManualState = async (nextState) => {
    if (!availability || pending) return
    const closing = nextState === 'closed'
    const confirmed = window.confirm(
      closing
        ? 'Mark this job closed? Only your explicit confirmation can close it.'
        : 'Reopen this job as status unknown? A link check will never reopen it automatically.',
    )
    if (!confirmed) return

    setPending(true)
    setError('')
    setMessage('')
    try {
      const data = await updateAvailability({
        version: availability.version,
        state: nextState,
        confirm_state_change: true,
      })
      applyLoaded(data)
      setMessage(closing ? 'Marked closed by you.' : 'Reopened as status unknown.')
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        closing ? 'Could not mark the job closed.' : 'Could not reopen the job.',
      ).message)
    } finally {
      setPending(false)
    }
  }

  const runCheck = async () => {
    if (!availability?.checks_enabled || pending) return
    setPending(true)
    setError('')
    setMessage('')
    try {
      const result = await checkAvailability()
      if (result?.availability) applyLoaded(result.availability)
      setMessage('Link check queued. The result will never mark a job closed automatically.')
      pollTimers.current.forEach((timer) => window.clearTimeout(timer))
      pollTimers.current = [700, 1800, 3500].map((delay) => (
        window.setTimeout(() => load({ silent: true }), delay)
      ))
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not check this link. Manual freshness controls are still available.',
      ).message)
    } finally {
      setPending(false)
    }
  }

  if (!sourceId) return null

  if (loading && !availability) {
    return (
      <div className="drawer-section" data-testid="job-availability">
        <h4>Deadline & freshness</h4>
        <p role="status">Loading deadline and freshness...</p>
      </div>
    )
  }

  if (!availability) {
    return (
      <div className="drawer-section" data-testid="job-availability">
        <h4>Deadline & freshness</h4>
        <p className="error-msg" role="alert">{error || 'Deadline information is unavailable.'}</p>
        <button className="btn btn-grey btn-sm" type="button" onClick={() => load()}>Retry</button>
      </div>
    )
  }

  const timezoneName = availability.timezone || 'UTC'
  const persistedDeadline = availability.deadline_local_date || ''
  const deadlineChanged = deadlineDraft !== persistedDeadline
  const stateLabel = STATE_LABELS[availability.state] || 'Status unknown'

  return (
    <div className="drawer-section" data-testid="job-availability">
      <h4>Deadline & freshness</h4>

      <div className="drawer-field">
        <span className="drawer-field-label">Availability</span>
        <span className="drawer-field-value" data-testid="availability-label">{stateLabel}</span>
      </div>
      <div className="drawer-field">
        <span className="drawer-field-label">Last checked</span>
        <span className="drawer-field-value">{formatTimestamp(availability.last_checked_at, timezoneName)}</span>
      </div>
      <div className="drawer-field">
        <span className="drawer-field-label">Evidence</span>
        <span className="drawer-field-value">{availability.check_reason || 'No link-check evidence yet'}</span>
      </div>
      <div className="drawer-field">
        <span className="drawer-field-label">Deadline source</span>
        <span className="drawer-field-value">{availability.deadline_source || 'Not set'}</span>
      </div>

      <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
        <label htmlFor={`availability-deadline-${isTrack ? 'track' : 'row'}-${sourceId}`}>
          Deadline date ({timezoneName})
        </label>
        <input
          id={`availability-deadline-${isTrack ? 'track' : 'row'}-${sourceId}`}
          type="date"
          value={deadlineDraft}
          disabled={pending}
          onChange={(event) => {
            setDeadlineDraft(event.target.value)
            setError('')
            setMessage('')
          }}
        />
        <small data-testid="deadline-timezone-note">
          Date-only deadlines are stored at the end of the selected day in {timezoneName}.
        </small>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button
            className="btn btn-blue btn-sm"
            type="button"
            disabled={pending || !deadlineChanged}
            onClick={saveDeadline}
          >
            {pending ? 'Saving...' : 'Save deadline'}
          </button>
          {availability.state === 'closed' ? (
            <button
              className="btn btn-grey btn-sm"
              type="button"
              disabled={pending}
              onClick={() => changeManualState('unknown')}
            >
              Reopen
            </button>
          ) : (
            <button
              className="btn btn-grey btn-sm"
              type="button"
              disabled={pending}
              onClick={() => changeManualState('closed')}
            >
              Mark closed
            </button>
          )}
          {availability.checks_enabled && (
            <button
              className="btn btn-grey btn-sm"
              type="button"
              disabled={pending || availability.check_status === 'pending' || availability.check_status === 'running'}
              onClick={runCheck}
            >
              {availability.check_status === 'pending' || availability.check_status === 'running'
                ? 'Check pending'
                : 'Check link'}
            </button>
          )}
        </div>
      </div>

      {!availability.checks_enabled && (
        <p data-testid="manual-freshness-fallback" style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
          Automatic link checks are off. You can still edit the deadline and close or reopen this job manually.
        </p>
      )}
      {message && <p role="status" style={{ marginTop: 8 }}>{message}</p>}
      {error && (
        <p className="error-msg" role="alert" style={{ marginTop: 8 }}>
          {error}
          {' '}
          <button className="btn btn-grey btn-sm" type="button" onClick={() => load({ preserveDraft: true })}>
            Refresh
          </button>
        </p>
      )}
    </div>
  )
}
