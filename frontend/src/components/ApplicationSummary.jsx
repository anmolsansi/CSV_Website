const CARDS = [
  {
    key: 'total_applied',
    label: 'Lifetime applied',
    description: 'First-applied lifecycle events across your account, all time. This is independent of filters and may differ from dated tracks in legacy records.',
  },
  {
    key: 'interviews',
    label: 'Current interviews',
    description: 'Tracked roles currently at the interview stage, across your account.',
  },
  {
    key: 'offers',
    label: 'Current offers',
    description: 'Tracked roles currently at the offer stage, across your account.',
  },
  {
    key: 'follow_ups_due',
    label: 'Follow-ups due',
    description: 'Tracked jobs with a follow-up date at or before the current UTC time, across your account.',
  },
]

export default function ApplicationSummary({ summary, loading, error, onRetry }) {
  return (
    <section aria-label="Account-wide application summary">
      <div className="application-summary-heading">
        <h3>Account overview</h3>
        <span>All-time and current-stage account metrics. Not affected by table filters.</span>
      </div>
      {error && (
        <div role="alert" className="application-summary-error">
          <span>{error}</span>
          <button className="btn btn-grey btn-sm" type="button" onClick={onRetry}>Retry overview</button>
        </div>
      )}
      <div className="stats-grid app-stats-grid">
        {CARDS.map(({ key, label, description }) => (
          <div className="stat-card" key={key} title={description}>
            <span>{label}</span>
            <strong aria-label={label} aria-busy={loading}>
              {loading ? '…' : summary && Number.isFinite(summary[key]) ? summary[key] : '—'}
            </strong>
            <small className="application-stat-note">{description}</small>
          </div>
        ))}
      </div>
    </section>
  )
}
