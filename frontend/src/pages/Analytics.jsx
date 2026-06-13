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

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    setLoading(true)
    api.getAnalytics()
      .then(setData)
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  if (loading) return <div className="container"><div className="empty-state"><div className="loading-spinner" /><p>Loading analytics...</p></div></div>
  if (!data) return <div className="container"><div className="empty-state"><h3>Failed to load analytics</h3><p>Please try refreshing.</p></div></div>

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Analytics</h2>
          <p>Job search metrics and progress over time.</p>
        </div>
        <button className="btn btn-blue" onClick={refresh}>Refresh</button>
      </div>

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

      <div className="analytics-charts">
        <div className="chart-section">
          <h3>Applications by Status</h3>
          <BarChart data={data.by_status} labelKey="name" countKey="count" />
        </div>

        <div className="chart-section">
          <h3>By ATS Group</h3>
          <BarChart data={data.by_ats_group} labelKey="name" countKey="count" />
        </div>

        <div className="chart-section">
          <h3>By Search Bucket</h3>
          <BarChart data={data.by_search_bucket} labelKey="name" countKey="count" />
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
      </div>
    </div>
  )
}
