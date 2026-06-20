import { useEffect, useState } from 'react'
import { api } from '../api/client'

function BarChart({ data, labelKey, countKey, maxItems = 10 }) {
  if (!data || data.length === 0) return <p style={{ color: '#9ca3af', fontSize: 13 }}>No data</p>
  const max = Math.max(...data.map((d) => d[countKey]))
  return (
    <div className="chart-bars">
      {data.slice(0, maxItems).map((d, i) => (
        <div className="chart-bar-row" key={i}>
          <span className="chart-bar-label">{d[labelKey]}</span>
          <div className="chart-bar-track">
            <div className="chart-bar-fill" style={{ width: `${(d[countKey] / max) * 100}%` }} />
          </div>
          <span className="chart-bar-count">{d[countKey]}</span>
        </div>
      ))}
    </div>
  )
}

function FunnelChart({ stages }) {
  if (!stages || stages.length === 0) return null
  const max = stages[0].count || 1
  return (
    <div className="funnel-chart">
      {stages.map((stage, i) => (
        <div className="funnel-stage" key={i}>
          <div className="funnel-bar" style={{ width: `${(stage.count / max) * 100}%` }}>
            <span className="funnel-label">{stage.name}</span>
            <span className="funnel-count">{stage.count}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function GoalProgress({ goals, today }) {
  if (!goals || !today) return null
  const items = [
    { label: 'Open jobs', goal: goals.open_per_day, actual: today.opened },
    { label: 'Apply', goal: goals.apply_per_day, actual: today.applied },
    { label: 'Follow-ups', goal: goals.followup_per_day, actual: today.followups },
    { label: 'ApplyPilot', goal: goals.applypilot_per_day, actual: today.exports },
  ]
  return (
    <div className="goal-progress">
      {items.map((item) => {
        const pct = Math.min(100, Math.round((item.actual / item.goal) * 100))
        return (
          <div className="goal-item" key={item.label}>
            <div className="goal-header">
              <span className="goal-label">{item.label}</span>
              <span className="goal-value">{item.actual}/{item.goal}</span>
            </div>
            <div className="goal-bar-track">
              <div className="goal-bar-fill" style={{ width: `${pct}%`, background: pct >= 100 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626' }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [funnel, setFunnel] = useState(null)
  const [atsPerf, setAtsPerf] = useState([])
  const [bucketPerf, setBucketPerf] = useState([])
  const [goalData, setGoalData] = useState(null)
  const [weekly, setWeekly] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showGoals, setShowGoals] = useState(false)
  const [goals, setGoals] = useState({ open_per_day: 30, apply_per_day: 10, followup_per_day: 5, applypilot_per_day: 5 })

  const refresh = () => {
    setLoading(true)
    Promise.all([
      api.getAnalytics(),
      api.getFunnelAnalytics(),
      api.getAtsPerformance(),
      api.getBucketPerformance(),
      api.getGoalProgress(),
      api.getWeeklyReport(),
    ]).then(([analytics, f, ats, buckets, g, w]) => {
      setData(analytics)
      setFunnel(f)
      setAtsPerf(ats)
      setBucketPerf(buckets)
      setGoalData(g)
      setWeekly(w)
      if (g?.goals) setGoals(g.goals)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const saveGoals = async () => {
    await api.updateGoals(goals)
    setShowGoals(false)
    const g = await api.getGoalProgress()
    setGoalData(g)
  }

  if (loading) return <div className="container"><div className="empty-state"><div className="loading-spinner" /><p>Loading analytics...</p></div></div>
  if (!data) return <div className="container"><div className="empty-state"><h3>Failed to load analytics</h3><p>Please try refreshing.</p></div></div>

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Analytics</h2>
          <p>Job search metrics and progress over time.</p>
        </div>
        <div>
          <button className="btn btn-grey" style={{ marginRight: 8 }} onClick={() => setShowGoals(!showGoals)}>Goals</button>
          <button className="btn btn-blue" onClick={refresh}>Refresh</button>
        </div>
      </div>

      {showGoals && (
        <div className="table-controls" style={{ marginBottom: 16 }}>
          <div><label>Open/day</label><input type="number" value={goals.open_per_day} onChange={(e) => setGoals({ ...goals, open_per_day: Number(e.target.value) })} /></div>
          <div><label>Apply/day</label><input type="number" value={goals.apply_per_day} onChange={(e) => setGoals({ ...goals, apply_per_day: Number(e.target.value) })} /></div>
          <div><label>Follow-ups/day</label><input type="number" value={goals.followup_per_day} onChange={(e) => setGoals({ ...goals, followup_per_day: Number(e.target.value) })} /></div>
          <div><label>ApplyPilot/day</label><input type="number" value={goals.applypilot_per_day} onChange={(e) => setGoals({ ...goals, applypilot_per_day: Number(e.target.value) })} /></div>
          <div><button className="btn btn-green" onClick={saveGoals}>Save goals</button></div>
        </div>
      )}

      <div className="stats-grid app-stats-grid">
        <div className="stat-card"><span>Total URLs uploaded</span><strong>{data.total_urls}</strong></div>
        <div className="stat-card"><span>Total opened</span><strong>{data.total_opened}</strong></div>
        <div className="stat-card"><span>Total applied</span><strong>{data.total_applied}</strong></div>
        <div className="stat-card"><span>Applied today</span><strong>{data.applied_today}</strong></div>
        <div className="stat-card"><span>Applied last 7 days</span><strong>{data.applied_7d}</strong></div>
        <div className="stat-card"><span>Opened not applied</span><strong>{data.opened_not_applied}</strong></div>
        <div className="stat-card"><span>Follow-ups due</span><strong>{data.follow_ups_due}</strong></div>
        <div className="stat-card"><span>Interviews</span><strong>{data.interviews}</strong></div>
        <div className="stat-card"><span>Rejections</span><strong>{data.rejected}</strong></div>
        <div className="stat-card"><span>Offers</span><strong>{data.offers}</strong></div>
        <div className="stat-card"><span>Avg match score (applied)</span><strong>{data.avg_applied_score}%</strong></div>
      </div>

      {goalData && (
        <div className="chart-section" style={{ marginBottom: 16 }}>
          <h3>Today's Progress</h3>
          <GoalProgress goals={goalData.goals} today={goalData.today} />
        </div>
      )}

      <div className="analytics-charts">
        <div className="chart-section">
          <h3>Application Funnel</h3>
          <FunnelChart stages={funnel?.stages} />
          {funnel?.rates && (
            <div className="funnel-rates">
              <span>Open rate: {funnel.rates.open_rate}%</span>
              <span>Application rate: {funnel.rates.application_rate}%</span>
              <span>Interview rate: {funnel.rates.interview_rate}%</span>
              <span>Rejection rate: {funnel.rates.rejection_rate}%</span>
            </div>
          )}
        </div>

        <div className="chart-section">
          <h3>Applications by Status</h3>
          <BarChart data={data.by_status} labelKey="name" countKey="count" />
        </div>

        <div className="chart-section">
          <h3>ATS Performance</h3>
          {atsPerf.length > 0 ? (
            <table style={{ fontSize: 12 }}>
              <thead><tr><th>ATS</th><th>Total</th><th>Applied</th><th>Interviews</th><th>Avg Score</th></tr></thead>
              <tbody>{atsPerf.map((a) => <tr key={a.name}><td>{a.name}</td><td>{a.total}</td><td>{a.applied}</td><td>{a.interviews}</td><td>{a.avg_score}%</td></tr>)}</tbody>
            </table>
          ) : <p style={{ color: '#9ca3af', fontSize: 13 }}>No data</p>}
        </div>

        <div className="chart-section">
          <h3>Search Bucket Performance</h3>
          {bucketPerf.length > 0 ? (
            <table style={{ fontSize: 12 }}>
              <thead><tr><th>Bucket</th><th>Total</th><th>Applied</th><th>Opened not applied</th><th>Avg Score</th></tr></thead>
              <tbody>{bucketPerf.map((b) => <tr key={b.name}><td>{b.name}</td><td>{b.total}</td><td>{b.applied}</td><td>{b.opened_not_applied}</td><td>{b.avg_score}%</td></tr>)}</tbody>
            </table>
          ) : <p style={{ color: '#9ca3af', fontSize: 13 }}>No data</p>}
        </div>

        <div className="chart-section">
          <h3>Daily Applications (last 30 days)</h3>
          <BarChart data={data.daily_applied} labelKey="date" countKey="count" />
        </div>

        <div className="chart-section">
          <h3>Top Companies Opened</h3>
          <BarChart data={data.top_companies_opened} labelKey="name" countKey="count" />
        </div>

        <div className="chart-section">
          <h3>Top Companies Applied</h3>
          <BarChart data={data.top_companies_applied} labelKey="name" countKey="count" />
        </div>

        {weekly && (
          <div className="chart-section">
            <h3>This Week's Summary</h3>
            <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 8 }}>
              <div className="stat-card"><span>Uploaded</span><strong>{weekly.uploaded}</strong></div>
              <div className="stat-card"><span>Opened</span><strong>{weekly.opened}</strong></div>
              <div className="stat-card"><span>Applied</span><strong>{weekly.applied}</strong></div>
              <div className="stat-card"><span>Interviews</span><strong>{weekly.interviews}</strong></div>
              <div className="stat-card"><span>Follow-ups done</span><strong>{weekly.followups_completed}</strong></div>
            </div>
            {weekly.top_companies?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <strong style={{ fontSize: 13 }}>Top companies this week:</strong>
                {weekly.top_companies.map((c) => <div key={c.name} style={{ fontSize: 12, color: '#374151' }}>{c.name} ({c.count})</div>)}
              </div>
            )}
            {weekly.upcoming_followups?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <strong style={{ fontSize: 13 }}>Upcoming follow-ups:</strong>
                {weekly.upcoming_followups.map((f) => <div key={f.id} style={{ fontSize: 12, color: '#374151' }}>{f.company} - {f.title} ({new Date(f.follow_up_at).toLocaleDateString()})</div>)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
