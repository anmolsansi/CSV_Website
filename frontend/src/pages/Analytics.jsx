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

function SectionSpinner() {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px 0', color: '#6b7280', fontSize: 13 }}>
    <div className="loading-spinner" style={{ width: 20, height: 20 }} />
    <span>Loading...</span>
  </div>
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [funnel, setFunnel] = useState(null)
  const [atsPerf, setAtsPerf] = useState([])
  const [bucketPerf, setBucketPerf] = useState([])
  const [goalData, setGoalData] = useState(null)
  const [weekly, setWeekly] = useState(null)
  const [loadingData, setLoadingData] = useState(true)
  const [loadingFunnel, setLoadingFunnel] = useState(true)
  const [loadingAts, setLoadingAts] = useState(true)
  const [loadingBucket, setLoadingBucket] = useState(true)
  const [loadingGoals, setLoadingGoals] = useState(true)
  const [loadingWeekly, setLoadingWeekly] = useState(true)
  const [showGoals, setShowGoals] = useState(false)
  const [goals, setGoals] = useState({ open_per_day: 30, apply_per_day: 10, followup_per_day: 5, applypilot_per_day: 5 })

  const anyLoading = loadingData || loadingFunnel || loadingAts || loadingBucket || loadingGoals || loadingWeekly

  useEffect(() => {
    setLoadingData(true)
    api.getAnalytics().then((d) => {
      setData(d)
    }).catch(() => {}).finally(() => setLoadingData(false))
  }, [])

  useEffect(() => {
    setLoadingFunnel(true)
    api.getFunnelAnalytics().then((f) => {
      setFunnel(f)
    }).catch(() => {}).finally(() => setLoadingFunnel(false))
  }, [])

  useEffect(() => {
    setLoadingAts(true)
    api.getAtsPerformance().then((ats) => {
      setAtsPerf(ats)
    }).catch(() => {}).finally(() => setLoadingAts(false))
  }, [])

  useEffect(() => {
    setLoadingBucket(true)
    api.getBucketPerformance().then((buckets) => {
      setBucketPerf(buckets)
    }).catch(() => {}).finally(() => setLoadingBucket(false))
  }, [])

  useEffect(() => {
    setLoadingGoals(true)
    api.getGoalProgress().then((g) => {
      setGoalData(g)
      if (g?.goals) setGoals(g.goals)
    }).catch(() => {}).finally(() => setLoadingGoals(false))
  }, [])

  useEffect(() => {
    setLoadingWeekly(true)
    api.getWeeklyReport().then((w) => {
      setWeekly(w)
    }).catch(() => {}).finally(() => setLoadingWeekly(false))
  }, [])

  const refresh = () => {
    setLoadingData(true)
    setLoadingFunnel(true)
    setLoadingAts(true)
    setLoadingBucket(true)
    setLoadingGoals(true)
    setLoadingWeekly(true)
    Promise.allSettled([
      api.getAnalytics().then((d) => { setData(d) }),
      api.getFunnelAnalytics().then((f) => { setFunnel(f) }),
      api.getAtsPerformance().then((ats) => { setAtsPerf(ats) }),
      api.getBucketPerformance().then((buckets) => { setBucketPerf(buckets) }),
      api.getGoalProgress().then((g) => { setGoalData(g); if (g?.goals) setGoals(g.goals) }),
      api.getWeeklyReport().then((w) => { setWeekly(w) }),
    ]).finally(() => {
      setLoadingData(false)
      setLoadingFunnel(false)
      setLoadingAts(false)
      setLoadingBucket(false)
      setLoadingGoals(false)
      setLoadingWeekly(false)
    })
  }

  const saveGoals = async () => {
    await api.updateGoals(goals)
    setShowGoals(false)
    setLoadingGoals(true)
    const g = await api.getGoalProgress()
    setGoalData(g)
    setLoadingGoals(false)
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Analytics</h2>
          <p>Job search metrics and progress over time.</p>
        </div>
        <div>
          <button className="btn btn-grey" style={{ marginRight: 8 }} onClick={() => setShowGoals(!showGoals)}>Goals</button>
          <button className="btn btn-blue" onClick={refresh} disabled={anyLoading}>Refresh</button>
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

      {!loadingData && data ? (
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
      ) : loadingData ? (
        <div className="stats-grid app-stats-grid">
          {Array.from({ length: 11 }).map((_, i) => (
            <div className="stat-card" key={i}><SectionSpinner /></div>
          ))}
        </div>
      ) : null}

      {!loadingGoals && goalData ? (
        <div className="chart-section" style={{ marginBottom: 16 }}>
          <h3>Today's Progress</h3>
          <GoalProgress goals={goalData.goals} today={goalData.today} />
        </div>
      ) : loadingGoals ? (
        <div className="chart-section" style={{ marginBottom: 16 }}><h3>Today's Progress</h3><SectionSpinner /></div>
      ) : null}

      <div className="analytics-charts">
        {!loadingFunnel ? (
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
        ) : (
          <div className="chart-section"><h3>Application Funnel</h3><SectionSpinner /></div>
        )}

        {!loadingData && data ? (
          <div className="chart-section">
            <h3>Applications by Status</h3>
            <BarChart data={data.by_status} labelKey="name" countKey="count" />
          </div>
        ) : loadingData ? (
          <div className="chart-section"><h3>Applications by Status</h3><SectionSpinner /></div>
        ) : null}

        {!loadingAts ? (
          <div className="chart-section">
            <h3>ATS Performance</h3>
            {atsPerf.length > 0 ? (
              <table style={{ fontSize: 12 }}>
                <thead><tr><th>ATS</th><th>Total</th><th>Applied</th><th>Interviews</th><th>Avg Score</th></tr></thead>
                <tbody>{atsPerf.map((a) => <tr key={a.name}><td>{a.name}</td><td>{a.total}</td><td>{a.applied}</td><td>{a.interviews}</td><td>{a.avg_score}%</td></tr>)}</tbody>
              </table>
            ) : <p style={{ color: '#9ca3af', fontSize: 13 }}>No data</p>}
          </div>
        ) : (
          <div className="chart-section"><h3>ATS Performance</h3><SectionSpinner /></div>
        )}

        {!loadingBucket ? (
          <div className="chart-section">
            <h3>Search Bucket Performance</h3>
            {bucketPerf.length > 0 ? (
              <table style={{ fontSize: 12 }}>
                <thead><tr><th>Bucket</th><th>Total</th><th>Applied</th><th>Opened not applied</th><th>Avg Score</th></tr></thead>
                <tbody>{bucketPerf.map((b) => <tr key={b.name}><td>{b.name}</td><td>{b.total}</td><td>{b.applied}</td><td>{b.opened_not_applied}</td><td>{b.avg_score}%</td></tr>)}</tbody>
              </table>
            ) : <p style={{ color: '#9ca3af', fontSize: 13 }}>No data</p>}
          </div>
        ) : (
          <div className="chart-section"><h3>Search Bucket Performance</h3><SectionSpinner /></div>
        )}

        {!loadingData && data ? (
          <div className="chart-section">
            <h3>Daily Applications (last 30 days)</h3>
            <BarChart data={data.daily_applied} labelKey="date" countKey="count" />
          </div>
        ) : loadingData ? (
          <div className="chart-section"><h3>Daily Applications (last 30 days)</h3><SectionSpinner /></div>
        ) : null}

        {!loadingData && data ? (
          <div className="chart-section">
            <h3>Top Companies Opened</h3>
            <BarChart data={data.top_companies_opened} labelKey="name" countKey="count" />
          </div>
        ) : loadingData ? (
          <div className="chart-section"><h3>Top Companies Opened</h3><SectionSpinner /></div>
        ) : null}

        {!loadingData && data ? (
          <div className="chart-section">
            <h3>Top Companies Applied</h3>
            <BarChart data={data.top_companies_applied} labelKey="name" countKey="count" />
          </div>
        ) : loadingData ? (
          <div className="chart-section"><h3>Top Companies Applied</h3><SectionSpinner /></div>
        ) : null}

        {!loadingData && data?.by_fit_category?.length > 0 ? (
          <div className="chart-section">
            <h3>Fit Category Breakdown</h3>
            <BarChart data={data.by_fit_category} labelKey="name" countKey="count" />
          </div>
        ) : null}

        {!loadingData && data?.by_seniority?.length > 0 ? (
          <div className="chart-section">
            <h3>Seniority Level Breakdown</h3>
            <BarChart data={data.by_seniority} labelKey="name" countKey="count" />
          </div>
        ) : null}

        {!loadingData && data?.by_work_model?.length > 0 ? (
          <div className="chart-section">
            <h3>Work Model Breakdown</h3>
            <BarChart data={data.by_work_model} labelKey="name" countKey="count" />
          </div>
        ) : null}

        {!loadingData && data?.by_role_family?.length > 0 ? (
          <div className="chart-section">
            <h3>Role Family Breakdown</h3>
            <BarChart data={data.by_role_family} labelKey="name" countKey="count" />
          </div>
        ) : null}

        {!loadingWeekly ? (
          weekly ? (
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
          ) : null
        ) : (
          <div className="chart-section"><h3>This Week's Summary</h3><SectionSpinner /></div>
        )}
      </div>
    </div>
  )
}
