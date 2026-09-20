import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const RETENTION_ERROR = 'Enter 0 to keep automatic archive off, or a whole number from 7 to 3650.'

function validateRetention(value) {
  if (value === '') return RETENTION_ERROR
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || (parsed !== 0 && (parsed < 7 || parsed > 3650))) {
    return RETENTION_ERROR
  }
  return ''
}

function formatCleanupTime(value) {
  if (!value) return 'No successful cleanup recorded'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unavailable' : parsed.toLocaleString()
}

export default function RetentionSettings() {
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState('0')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [savedMessage, setSavedMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const saveButtonRef = useRef(null)

  const loadProfile = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const next = await api.getProfileRetention()
      setProfile(next)
      setDraft(String(next.archive_after_days ?? 0))
    } catch {
      setLoadError('Retention settings are unavailable. Try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProfile()
  }, [])

  const validationError = validateRetention(draft)
  const parsedDraft = validationError ? null : Number(draft)
  const hasChanges = profile && parsedDraft !== profile.archive_after_days

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (saving || validationError || !hasChanges) return

    setSaving(true)
    setSaveError('')
    setSavedMessage('')
    try {
      const next = await api.updateProfileRetention(parsedDraft)
      setProfile(next)
      setDraft(String(next.archive_after_days))
      setSavedMessage('Retention policy saved.')
    } catch {
      setSaveError('Could not save the retention policy. Your draft is still here.')
    } finally {
      setSaving(false)
      requestAnimationFrame(() => saveButtonRef.current?.focus())
    }
  }

  if (loading) {
    return (
      <section className="chart-section" aria-label="Retention and maintenance">
        <h3>Retention & maintenance</h3>
        <p role="status">Loading retention settings…</p>
      </section>
    )
  }

  if (loadError) {
    return (
      <section className="chart-section" aria-label="Retention and maintenance">
        <h3>Retention & maintenance</h3>
        <p className="error-msg" role="alert">{loadError}</p>
        <button className="btn btn-grey btn-sm" type="button" onClick={loadProfile}>Retry</button>
      </section>
    )
  }

  const healthStatus = profile?.maintenance?.status || 'unavailable'
  const healthText = healthStatus === 'healthy'
    ? 'Healthy'
    : healthStatus === 'disabled'
      ? 'Disabled'
      : 'Unavailable'
  const previewLabel = hasChanges ? 'Eligible under saved policy' : 'Eligible now'

  return (
    <section className="chart-section" aria-label="Retention and maintenance" style={{ marginBottom: '1rem' }}>
      <h3>Retention & maintenance</h3>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: '12px' }}>
          <div>
            <label htmlFor="archive-after-days">Archive visited jobs after (days)</label>
            <input
              id="archive-after-days"
              type="number"
              min="0"
              max="3650"
              step="1"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value)
                setSavedMessage('')
                setSaveError('')
              }}
              aria-describedby="retention-help retention-validation"
              style={{ display: 'block', marginTop: '4px' }}
            />
          </div>
          <button
            ref={saveButtonRef}
            className="btn btn-grey"
            type="submit"
            disabled={saving || Boolean(validationError) || !hasChanges}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
        <p id="retention-help" style={{ marginBottom: 0 }}>
          Use 0 to keep your account policy off. Saving a policy does not turn on the operator maintenance worker.
        </p>
        {validationError && <p id="retention-validation" className="error-msg" role="alert">{validationError}</p>}
        {saveError && <p className="error-msg" role="alert">{saveError}</p>}
        {savedMessage && <p role="status">{savedMessage}</p>}
      </form>

      <div style={{ marginTop: '12px', display: 'grid', gap: '6px' }}>
        <div><strong>{previewLabel}:</strong> {profile.eligible_row_count} visited job{profile.eligible_row_count === 1 ? '' : 's'}</div>
        <div><strong>Maintenance:</strong> {healthText}</div>
        <div><strong>Last successful cleanup:</strong> {formatCleanupTime(profile.maintenance?.last_successful_cleanup_at)}</div>
        {healthStatus === 'unavailable' && (
          <p className="error-msg" role="status">
            Maintenance health is unavailable. This does not mean there are zero eligible jobs.
          </p>
        )}
        <div><strong>Permanent purge:</strong> Unavailable</div>
        <p style={{ margin: 0 }}>{profile.recovery_message}</p>
      </div>
    </section>
  )
}
