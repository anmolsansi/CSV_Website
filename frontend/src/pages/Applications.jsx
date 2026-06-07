import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const STORAGE_KEY = 'csv_website_application_tracker_v1'
const STATUSES = ['opened', 'applied', 'follow_up', 'interview', 'rejected', 'offer', 'not_applying']
const DEFAULT_FILTERS = {
  status: '',
  company: '',
  atsGroup: '',
  quickRange: '',
  dateFrom: '',
  dateTo: '',
  minScore: '',
  maxScore: '',
  onlyOpenedNotApplied: false,
  followUpDue: false,
  q: '',
}

function parseDate(value) {
  if (!value) return null
  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasTimezone ? value : `${value}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatDateTime(value) {
  const date = parseDate(value)
  return date ? date.toLocaleString() : ''
}

function localInputValue(value) {
  const date = parseDate(value)
  if (!date) return ''
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function inputToIso(value) {
  return value ? new Date(value).toISOString() : ''
}

function startOfLocalDay(date = new Date()) {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  return d
}

function inQuickRange(date, range) {
  if (!range) return true
  if (!date) return false
  const now = new Date()
  if (range === 'last_24_hours') return date >= new Date(now.getTime() - 24 * 60 * 60 * 1000)
  if (range === 'today') return date >= startOfLocalDay(now)
  if (range === 'yesterday') {
    const today = startOfLocalDay(now)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    return date >= yesterday && date < today
  }
  if (range === 'last_7_days') return date >= new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  if (range === 'last_30_days') return date >= new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  return true
}

function loadMeta() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveMeta(meta) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(meta))
}

function scoreValue(value) {
  const score = Number(String(value || '').replace(/[%,$\s]/g, ''))
  return Number.isNaN(score) ? null : score
}

function rowToApplication(row, meta) {
  const url = row.data?.url || ''
  const saved = meta[url] || {}
  return {
    id: row.id,
    url,
    company: saved.company ?? row.data?.company_guess ?? '',
    title: saved.title ?? row.data?.title ?? '',
    atsGroup: row.data?.ats_group ?? '',
    searchBucket: row.data?.search_bucket ?? '',
    resumeMatchScore: row.data?.resume_match_score ?? '',
    clickedAt: row.clicked_at,
    appliedAt: saved.appliedAt || '',
    followUpAt: saved.followUpAt || '',
    status: saved.status || 'opened',
    notes: saved.notes || '',
  }
}

function calculateStats(apps) {
  const now = new Date()
  const today = startOfLocalDay(now)
  const last24 = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  return {
    totalOpened: apps.length,
    totalApplied: apps.filter((a) => a.appliedAt || a.status === 'applied').length,
    openedToday: apps.filter((a) => parseDate(a.clickedAt) >= today).length,
    appliedToday: apps.filter((a) => parseDate(a.appliedAt) >= today).length,
    last24Hours: apps.filter((a) => parseDate(a.clickedAt) >= last24).length,
    followUpsDue: apps.filter((a) => {
      const date = parseDate(a.followUpAt)
      return date && date <= now
    }).length,
    interviews: apps.filter((a) => a.status === 'interview').length,
    rejected: apps.filter((a) => a.status === 'rejected').length,
  }
}

export default function Applications() {
  const [rows, setRows] = useState([])
  const [meta, setMeta] = useState(() => loadMeta())
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [hiddenColumns, setHiddenColumns] = useState(['searchBucket'])
  const [sort, setSort] = useState({ field: 'clickedAt', direction: 'desc' })

  const refresh = () => {
    api.getRows({ sortBy: 'clicked_at', sortDir: 'desc' }).then((data) => {
      setRows((data.rows || []).filter((row) => row.clicked))
    })
  }

  useEffect(() => {
    refresh()
  }, [])

  const applications = useMemo(
    () => rows.map((row) => rowToApplication(row, meta)),
    [rows, meta]
  )

  const filterOptions = useMemo(() => ({
    atsGroups: [...new Set(applications.map((a) => a.atsGroup).filter(Boolean))].sort(),
    companies: [...new Set(applications.map((a) => a.company).filter(Boolean))].sort(),
  }), [applications])

  const filtered = useMemo(() => {
    const from = filters.dateFrom ? new Date(filters.dateFrom) : null
    const to = filters.dateTo ? new Date(filters.dateTo) : null
    const minScore = filters.minScore === '' ? null : Number(filters.minScore)
    const maxScore = filters.maxScore === '' ? null : Number(filters.maxScore)
    const now = new Date()
    const needle = filters.q.trim().toLowerCase()

    return applications.filter((app) => {
      const clicked = parseDate(app.clickedAt)
      const score = scoreValue(app.resumeMatchScore)
      if (filters.status && app.status !== filters.status) return false
      if (filters.company && !app.company.toLowerCase().includes(filters.company.toLowerCase())) return false
      if (filters.atsGroup && app.atsGroup !== filters.atsGroup) return false
      if (!inQuickRange(clicked, filters.quickRange)) return false
      if (from && (!clicked || clicked < from)) return false
      if (to && (!clicked || clicked >= to)) return false
      if (minScore !== null && (score === null || score < minScore)) return false
      if (maxScore !== null && (score === null || score > maxScore)) return false
      if (filters.onlyOpenedNotApplied && (app.appliedAt || app.status !== 'opened')) return false
      if (filters.followUpDue) {
        const followUp = parseDate(app.followUpAt)
        if (!followUp || followUp > now) return false
      }
      if (needle) {
        const haystack = [app.company, app.title, app.url, app.notes, app.atsGroup].join(' ').toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return true
    })
  }, [applications, filters])

  const sorted = useMemo(() => {
    const copy = [...filtered]
    copy.sort((a, b) => {
      const aValue = ['clickedAt', 'appliedAt', 'followUpAt'].includes(sort.field)
        ? parseDate(a[sort.field])?.getTime() || 0
        : sort.field === 'resumeMatchScore'
          ? scoreValue(a.resumeMatchScore) ?? -1
          : String(a[sort.field] || '').toLowerCase()
      const bValue = ['clickedAt', 'appliedAt', 'followUpAt'].includes(sort.field)
        ? parseDate(b[sort.field])?.getTime() || 0
        : sort.field === 'resumeMatchScore'
          ? scoreValue(b.resumeMatchScore) ?? -1
          : String(b[sort.field] || '').toLowerCase()
      if (aValue < bValue) return sort.direction === 'asc' ? -1 : 1
      if (aValue > bValue) return sort.direction === 'asc' ? 1 : -1
      return 0
    })
    return copy
  }, [filtered, sort])

  const stats = useMemo(() => calculateStats(applications), [applications])

  const updateMeta = (url, patch) => {
    const next = { ...meta, [url]: { ...(meta[url] || {}), ...patch } }
    setMeta(next)
    saveMeta(next)
  }

  const markApplied = (app) => {
    updateMeta(app.url, { status: 'applied', appliedAt: new Date().toISOString() })
  }

  const clearFilters = () => setFilters(DEFAULT_FILTERS)

  const columns = [
    ['company', 'Company'],
    ['title', 'Title'],
    ['status', 'Status'],
    ['atsGroup', 'ATS'],
    ['searchBucket', 'Bucket'],
    ['resumeMatchScore', 'Score'],
    ['clickedAt', 'Opened At'],
    ['appliedAt', 'Applied At'],
    ['followUpAt', 'Follow-up'],
    ['notes', 'Notes'],
    ['url', 'URL'],
  ]

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Applications</h2>
          <p>Track opened jobs, applied dates, follow-ups, notes, and statuses.</p>
        </div>
        <button className="btn btn-blue" onClick={refresh}>Refresh</button>
      </div>

      <div className="stats-grid app-stats-grid">
        <div className="stat-card"><span>Total opened</span><strong>{stats.totalOpened}</strong></div>
        <div className="stat-card"><span>Total applied</span><strong>{stats.totalApplied}</strong></div>
        <div className="stat-card"><span>Opened today</span><strong>{stats.openedToday}</strong></div>
        <div className="stat-card"><span>Applied today</span><strong>{stats.appliedToday}</strong></div>
        <div className="stat-card"><span>Last 24 hours</span><strong>{stats.last24Hours}</strong></div>
        <div className="stat-card"><span>Follow-ups due</span><strong>{stats.followUpsDue}</strong></div>
        <div className="stat-card"><span>Interviews</span><strong>{stats.interviews}</strong></div>
        <div className="stat-card"><span>Rejected</span><strong>{stats.rejected}</strong></div>
      </div>

      <div className="table-controls">
        <div><label>Status</label><select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Company</label><input value={filters.company} onChange={(e) => setFilters({ ...filters, company: e.target.value })} placeholder="Company" /></div>
        <div><label>ATS group</label><select value={filters.atsGroup} onChange={(e) => setFilters({ ...filters, atsGroup: e.target.value })}><option value="">All</option>{filterOptions.atsGroups.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Range</label><select value={filters.quickRange} onChange={(e) => setFilters({ ...filters, quickRange: e.target.value })}><option value="">All time</option><option value="last_24_hours">Last 24 hours</option><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_30_days">Last 30 days</option></select></div>
        <div><label>Date from</label><input type="datetime-local" value={filters.dateFrom} onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })} /></div>
        <div><label>Date to</label><input type="datetime-local" value={filters.dateTo} onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })} /></div>
        <div><label>Min score</label><input type="number" value={filters.minScore} onChange={(e) => setFilters({ ...filters, minScore: e.target.value })} /></div>
        <div><label>Max score</label><input type="number" value={filters.maxScore} onChange={(e) => setFilters({ ...filters, maxScore: e.target.value })} /></div>
        <div><label>Search</label><input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="Title, company, URL" /></div>
        <div className="checkbox-filter"><label><input type="checkbox" checked={filters.onlyOpenedNotApplied} onChange={(e) => setFilters({ ...filters, onlyOpenedNotApplied: e.target.checked })} /> Opened, not applied</label><label><input type="checkbox" checked={filters.followUpDue} onChange={(e) => setFilters({ ...filters, followUpDue: e.target.checked })} /> Follow-up due</label></div>
        <div className="table-control-actions"><label>Rows shown</label><span>{sorted.length}</span><button className="btn btn-grey" onClick={clearFilters}>Clear filters</button></div>
      </div>

      <div className="col-toggles compact-toggles">
        <strong style={{ width: '100%' }}>Application columns</strong>
        {columns.map(([key, label]) => (
          <label key={key}><input type="checkbox" checked={!hiddenColumns.includes(key)} onChange={() => setHiddenColumns(hiddenColumns.includes(key) ? hiddenColumns.filter((c) => c !== key) : [...hiddenColumns, key])} /> {label}</label>
        ))}
      </div>

      <div className="table-wrap">
        <table>
          <thead><tr>{columns.filter(([key]) => !hiddenColumns.includes(key)).map(([key, label]) => <th key={key}><button className="table-header-button" onClick={() => setSort({ field: key, direction: sort.field === key && sort.direction === 'asc' ? 'desc' : 'asc' })}>{label}{sort.field === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>)}<th>Actions</th></tr></thead>
          <tbody>
            {sorted.map((app) => (
              <tr key={app.id}>
                {!hiddenColumns.includes('company') && <td><input className="inline-input" value={app.company} onChange={(e) => updateMeta(app.url, { company: e.target.value })} /></td>}
                {!hiddenColumns.includes('title') && <td>{app.title}</td>}
                {!hiddenColumns.includes('status') && <td><select value={app.status} onChange={(e) => updateMeta(app.url, { status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></td>}
                {!hiddenColumns.includes('atsGroup') && <td>{app.atsGroup}</td>}
                {!hiddenColumns.includes('searchBucket') && <td>{app.searchBucket}</td>}
                {!hiddenColumns.includes('resumeMatchScore') && <td>{app.resumeMatchScore}</td>}
                {!hiddenColumns.includes('clickedAt') && <td>{formatDateTime(app.clickedAt)}</td>}
                {!hiddenColumns.includes('appliedAt') && <td><input type="datetime-local" value={localInputValue(app.appliedAt)} onChange={(e) => updateMeta(app.url, { appliedAt: inputToIso(e.target.value), status: e.target.value ? 'applied' : app.status })} /></td>}
                {!hiddenColumns.includes('followUpAt') && <td><input type="datetime-local" value={localInputValue(app.followUpAt)} onChange={(e) => updateMeta(app.url, { followUpAt: inputToIso(e.target.value) })} /></td>}
                {!hiddenColumns.includes('notes') && <td><textarea value={app.notes} onChange={(e) => updateMeta(app.url, { notes: e.target.value })} /></td>}
                {!hiddenColumns.includes('url') && <td><button className="btn btn-blue" onClick={() => window.open(app.url, '_blank', 'noopener')}>Open</button></td>}
                <td><button className="btn btn-green" onClick={() => markApplied(app)}>Mark applied</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && <p style={{ padding: '1rem' }}>No opened job links match these filters.</p>}
      </div>
    </div>
  )
}
