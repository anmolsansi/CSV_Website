import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const STATUSES = ['opened', 'applied', 'follow_up', 'interview', 'rejected', 'offer', 'not_applying']

// ─── localStorage backup (kept for reference / fallback) ──────────────────────
// const STORAGE_KEY = 'csv_website_application_tracker_v1'
// function loadMeta() {
//   try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') }
//   catch { return {} }
// }
// function saveMeta(meta) { localStorage.setItem(STORAGE_KEY, JSON.stringify(meta)) }
// function rowToApplication(row, meta) {
//   const url = row.data?.url || ''
//   const saved = meta[url] || {}
//   return {
//     id: row.id, url,
//     company: saved.company ?? row.data?.company_guess ?? '',
//     title: saved.title ?? row.data?.title ?? '',
//     atsGroup: row.data?.ats_group ?? '',
//     searchBucket: row.data?.search_bucket ?? '',
//     resumeMatchScore: row.data?.resume_match_score ?? '',
//     clickedAt: row.clicked_at,
//     appliedAt: saved.appliedAt || '',
//     followUpAt: saved.followUpAt || '',
//     status: saved.status || 'opened',
//     notes: saved.notes || '',
//   }
// }
// ───────────────────────────────────────────────────────────────────────────────

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
  followUpToday: false,
  followUpOverdue: false,
  followUpNone: false,
  locationGroup: '',
  decision: '',
  sponsorshipStatus: '',
  hasError: false,
  jdMissing: false,
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

function scoreValue(value) {
  const score = Number(String(value || '').replace(/[%,$\s]/g, ''))
  return Number.isNaN(score) ? null : score
}

function calculateStats(apps) {
  const now = new Date()
  const today = startOfLocalDay(now)
  const last24 = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  return {
    totalOpened: apps.length,
    totalApplied: apps.filter((a) => a.applied_at || a.status === 'applied').length,
    openedToday: apps.filter((a) => parseDate(a.opened_at) >= today).length,
    appliedToday: apps.filter((a) => parseDate(a.applied_at) >= today).length,
    last24Hours: apps.filter((a) => parseDate(a.opened_at) >= last24).length,
    followUpsDue: apps.filter((a) => {
      const date = parseDate(a.follow_up_at)
      return date && date <= now
    }).length,
    interviews: apps.filter((a) => a.status === 'interview').length,
    rejected: apps.filter((a) => a.status === 'rejected').length,
  }
}

export default function Applications() {
  const [applications, setApplications] = useState([])
  const [filterOptions, setFilterOptions] = useState({ ats_groups: [] })
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [hiddenColumns, setHiddenColumns] = useState(['searchBucket'])
  const [sort, setSort] = useState({ field: 'opened_at', direction: 'desc' })
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())

  const refresh = () => {
    setLoading(true)
    api.getApplications({
      sort_by: sort.field === 'clickedAt' ? 'opened_at' : sort.field,
      sort_dir: sort.direction,
    }).then((data) => {
      setApplications(data.rows || [])
      setFilterOptions(data.filter_options || { ats_groups: [] })
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    refresh()
  }, [])

  const filtered = useMemo(() => {
    const from = filters.dateFrom ? new Date(filters.dateFrom) : null
    const to = filters.dateTo ? new Date(filters.dateTo) : null
    const minScore = filters.minScore === '' ? null : Number(filters.minScore)
    const maxScore = filters.maxScore === '' ? null : Number(filters.maxScore)
    const now = new Date()
    const todayStart = startOfLocalDay(now)
    const needle = filters.q.trim().toLowerCase()

    return applications.filter((app) => {
      const opened = parseDate(app.opened_at)
      const score = scoreValue(app.resume_match_score)
      if (filters.status && app.status !== filters.status) return false
      if (filters.company && !app.company?.toLowerCase().includes(filters.company.toLowerCase())) return false
      if (filters.atsGroup && app.ats_group !== filters.atsGroup) return false
      if (!inQuickRange(opened, filters.quickRange)) return false
      if (from && (!opened || opened < from)) return false
      if (to && (!opened || opened >= to)) return false
      if (minScore !== null && (score === null || score < minScore)) return false
      if (maxScore !== null && (score === null || score > maxScore)) return false
      if (filters.onlyOpenedNotApplied && (app.applied_at || app.status !== 'opened')) return false
      if (filters.followUpDue) {
        const followUp = parseDate(app.follow_up_at)
        if (!followUp || followUp > now) return false
      }
      if (filters.followUpToday) {
        const followUp = parseDate(app.follow_up_at)
        if (!followUp || followUp < todayStart || followUp >= new Date(todayStart.getTime() + 86400000)) return false
      }
      if (filters.followUpOverdue) {
        const followUp = parseDate(app.follow_up_at)
        if (!followUp || followUp >= now) return false
      }
      if (filters.followUpNone) {
        if (app.follow_up_at) return false
      }
      if (filters.hasError && !app.error) return false
      if (filters.jdMissing) {
        const len = Number(app.jd_text_length || 0)
        if (len > 0) return false
      }
      if (needle) {
        const haystack = [app.company, app.title, app.url, app.notes, app.ats_group].join(' ').toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return true
    })
  }, [applications, filters])

  const sorted = useMemo(() => {
    const copy = [...filtered]
    copy.sort((a, b) => {
      const aValue = ['opened_at', 'applied_at', 'follow_up_at'].includes(sort.field)
        ? parseDate(a[sort.field])?.getTime() || 0
        : sort.field === 'resumeMatchScore' || sort.field === 'resume_match_score'
          ? scoreValue(a.resume_match_score) ?? -1
          : String(a[sort.field] || '').toLowerCase()
      const bValue = ['opened_at', 'applied_at', 'follow_up_at'].includes(sort.field)
        ? parseDate(b[sort.field])?.getTime() || 0
        : sort.field === 'resumeMatchScore' || sort.field === 'resume_match_score'
          ? scoreValue(b.resume_match_score) ?? -1
          : String(b[sort.field] || '').toLowerCase()
      if (aValue < bValue) return sort.direction === 'asc' ? -1 : 1
      if (aValue > bValue) return sort.direction === 'asc' ? 1 : -1
      return 0
    })
    return copy
  }, [filtered, sort])

  const stats = useMemo(() => calculateStats(applications), [applications])

  const updateApp = async (itemId, payload) => {
    const updated = await api.updateApplication(itemId, payload)
    setApplications((prev) =>
      prev.map((app) => (app.id === itemId ? { ...app, ...updated } : app))
    )
  }

  const markApplied = (app) => {
    updateApp(app.id, { mark_applied: true })
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (sorted.length > 0 && prev.size === sorted.length) return new Set()
      return new Set(sorted.map((a) => a.id))
    })
  }

  const bulkMarkApplied = async () => {
    if (selectedIds.size === 0) return
    const confirmed = window.confirm(`Mark ${selectedIds.size} application(s) as applied?`)
    if (!confirmed) return
    const result = await api.bulkUpdateApplications([...selectedIds], { mark_applied: true })
    setSelectedIds(new Set())
    refresh()
  }

  const clearFilters = () => setFilters(DEFAULT_FILTERS)

  const [exportFormat, setExportFormat] = useState('csv')
  const [exportScope, setExportScope] = useState('all')

  const handleExport = async () => {
    const params = { format: exportFormat }
    if (exportScope === 'selected') {
      if (selectedIds.size === 0) { window.alert('No rows selected.'); return }
      params.rowIds = [...selectedIds]
    } else if (exportScope === 'filtered') {
      params.status = filters.status || undefined
      params.company = filters.company || undefined
      params.atsGroup = filters.atsGroup || undefined
      params.followUpDue = filters.followUpDue || undefined
      params.openedNotApplied = filters.onlyOpenedNotApplied || undefined
      params.q = filters.q || undefined
    } else if (exportScope === 'applied') {
      params.status = 'applied'
    } else if (exportScope === 'followups') {
      params.followUpDue = true
    }
    try {
      const res = await api.exportApplications(params)
      const ext = exportFormat === 'json' ? 'json' : 'csv'
      const blob = new Blob([res.data], { type: ext === 'json' ? 'application/json' : 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `applications_export.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      window.alert('Export failed.')
    }
  }

  const columns = [
    ['company', 'Company'],
    ['title', 'Title'],
    ['status', 'Status'],
    ['ats_group', 'ATS'],
    ['search_bucket', 'Bucket'],
    ['resume_match_score', 'Score'],
    ['opened_at', 'Opened At'],
    ['applied_at', 'Applied At'],
    ['follow_up_at', 'Follow-up'],
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

      <div className="export-bar">
        <label>Export</label>
        <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}>
          <option value="csv">CSV</option>
          <option value="json">JSON</option>
        </select>
        <select value={exportScope} onChange={(e) => setExportScope(e.target.value)}>
          <option value="all">All rows</option>
          <option value="filtered">Filtered rows</option>
          <option value="selected">Selected rows</option>
          <option value="applied">Applied only</option>
          <option value="followups">Follow-ups due</option>
        </select>
        <button className="btn btn-grey" onClick={handleExport}>Download</button>
      </div>

      <div className="table-controls">
        <div><label>Status</label><select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Company</label><input value={filters.company} onChange={(e) => setFilters({ ...filters, company: e.target.value })} placeholder="Company" /></div>
        <div><label>ATS group</label><select value={filters.atsGroup} onChange={(e) => setFilters({ ...filters, atsGroup: e.target.value })}><option value="">All</option>{filterOptions.ats_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Location</label><select value={filters.locationGroup} onChange={(e) => setFilters({ ...filters, locationGroup: e.target.value })}><option value="">All</option>{filterOptions.location_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Decision</label><select value={filters.decision} onChange={(e) => setFilters({ ...filters, decision: e.target.value })}><option value="">All</option>{filterOptions.decisions?.map((d) => <option key={d} value={d}>{d}</option>)}</select></div>
        <div><label>Sponsorship</label><select value={filters.sponsorshipStatus} onChange={(e) => setFilters({ ...filters, sponsorshipStatus: e.target.value })}><option value="">All</option>{filterOptions.sponsorship_statuses?.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Range</label><select value={filters.quickRange} onChange={(e) => setFilters({ ...filters, quickRange: e.target.value })}><option value="">All time</option><option value="last_24_hours">Last 24 hours</option><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_30_days">Last 30 days</option></select></div>
        <div><label>Date from</label><input type="datetime-local" value={filters.dateFrom} onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })} /></div>
        <div><label>Date to</label><input type="datetime-local" value={filters.dateTo} onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })} /></div>
        <div><label>Min score</label><input type="number" value={filters.minScore} onChange={(e) => setFilters({ ...filters, minScore: e.target.value })} /></div>
        <div><label>Max score</label><input type="number" value={filters.maxScore} onChange={(e) => setFilters({ ...filters, maxScore: e.target.value })} /></div>
        <div><label>Search</label><input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="Title, company, URL" /></div>
        <div className="checkbox-filter">
          <label><input type="checkbox" checked={filters.onlyOpenedNotApplied} onChange={(e) => setFilters({ ...filters, onlyOpenedNotApplied: e.target.checked })} /> Opened, not applied</label>
          <label><input type="checkbox" checked={filters.followUpDue} onChange={(e) => setFilters({ ...filters, followUpDue: e.target.checked })} /> Follow-up due</label>
          <label><input type="checkbox" checked={filters.followUpToday} onChange={(e) => setFilters({ ...filters, followUpToday: e.target.checked })} /> Follow-up today</label>
          <label><input type="checkbox" checked={filters.followUpOverdue} onChange={(e) => setFilters({ ...filters, followUpOverdue: e.target.checked })} /> Overdue</label>
          <label><input type="checkbox" checked={filters.followUpNone} onChange={(e) => setFilters({ ...filters, followUpNone: e.target.checked })} /> No follow-up</label>
          <label><input type="checkbox" checked={filters.hasError} onChange={(e) => setFilters({ ...filters, hasError: e.target.checked })} /> Has error</label>
          <label><input type="checkbox" checked={filters.jdMissing} onChange={(e) => setFilters({ ...filters, jdMissing: e.target.checked })} /> JD missing</label>
        </div>
        <div className="table-control-actions"><label>Rows shown</label><span>{sorted.length}</span><button className="btn btn-grey" onClick={clearFilters}>Clear filters</button></div>
      </div>

      <div className="col-toggles compact-toggles">
        <strong style={{ width: '100%' }}>Application columns</strong>
        {columns.map(([key, label]) => (
          <label key={key}><input type="checkbox" checked={!hiddenColumns.includes(key)} onChange={() => setHiddenColumns(hiddenColumns.includes(key) ? hiddenColumns.filter((c) => c !== key) : [...hiddenColumns, key])} /> {label}</label>
        ))}
      </div>

      <div className="delete-actions">
        <div>
          <strong>{selectedIds.size}</strong> selected
        </div>
        <button
          className="btn btn-green"
          onClick={bulkMarkApplied}
          disabled={selectedIds.size === 0}
        >
          Mark selected as applied
        </button>
      </div>

      <div className="table-wrap">
        {loading ? (
          <p style={{ padding: '1rem' }}>Loading applications...</p>
        ) : (
          <table>
            <thead><tr>
              <th className="row-select-cell">
                <input
                  type="checkbox"
                  checked={sorted.length > 0 && selectedIds.size === sorted.length}
                  onChange={toggleSelectAll}
                />
              </th>
              {columns.filter(([key]) => !hiddenColumns.includes(key)).map(([key, label]) => <th key={key}><button className="table-header-button" onClick={() => setSort({ field: key, direction: sort.field === key && sort.direction === 'asc' ? 'desc' : 'asc' })}>{label}{sort.field === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>)}<th>Actions</th></tr></thead>
            <tbody>
              {sorted.map((app) => {
                const followUpDate = parseDate(app.follow_up_at)
                const isOverdue = followUpDate && followUpDate < new Date()
                const isDueToday = followUpDate && (() => {
                  const today = startOfLocalDay()
                  return followUpDate >= today && followUpDate < new Date(today.getTime() + 86400000)
                })()
                return (
                <tr key={app.id} className={selectedIds.has(app.id) ? 'selected-row' : ''}>
                  <td className="row-select-cell">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(app.id)}
                      onChange={() => toggleSelect(app.id)}
                    />
                  </td>
                  {!hiddenColumns.includes('company') && <td><input className="inline-input" value={app.company || ''} onChange={(e) => updateApp(app.id, { company: e.target.value })} /></td>}
                  {!hiddenColumns.includes('title') && <td>{app.title}</td>}
                  {!hiddenColumns.includes('status') && <td><select value={app.status} onChange={(e) => updateApp(app.id, { status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></td>}
                  {!hiddenColumns.includes('ats_group') && <td>{app.ats_group}</td>}
                  {!hiddenColumns.includes('search_bucket') && <td>{app.search_bucket}</td>}
                  {!hiddenColumns.includes('resume_match_score') && <td>{app.resume_match_score}</td>}
                  {!hiddenColumns.includes('opened_at') && <td>{formatDateTime(app.opened_at)}</td>}
                  {!hiddenColumns.includes('applied_at') && <td><input type="datetime-local" value={localInputValue(app.applied_at)} onChange={(e) => updateApp(app.id, { applied_at: inputToIso(e.target.value), status: e.target.value ? 'applied' : app.status })} /></td>}
                  {!hiddenColumns.includes('follow_up_at') && (
                    <td>
                      <div className="follow-up-cell">
                        <input type="datetime-local" value={localInputValue(app.follow_up_at)} onChange={(e) => updateApp(app.id, { follow_up_at: inputToIso(e.target.value) })} />
                        <div className="follow-up-quick-btns">
                          <button className="btn btn-grey btn-sm" onClick={() => updateApp(app.id, { follow_up_at: new Date(Date.now() + 3 * 86400000).toISOString() })}>+3d</button>
                          <button className="btn btn-grey btn-sm" onClick={() => updateApp(app.id, { follow_up_at: new Date(Date.now() + 7 * 86400000).toISOString() })}>+7d</button>
                          <button className="btn btn-grey btn-sm" onClick={() => {
                            const now = new Date(); const day = now.getDay(); const daysUntilMon = (8 - day) % 7 || 7
                            updateApp(app.id, { follow_up_at: new Date(now.getTime() + daysUntilMon * 86400000).toISOString() })
                          }}>Mon</button>
                          {app.follow_up_at && <button className="btn btn-grey btn-sm" onClick={() => updateApp(app.id, { follow_up_at: '' })}>Clear</button>}
                        </div>
                        {isOverdue && <span className="follow-up-badge overdue">Overdue</span>}
                        {isDueToday && <span className="follow-up-badge due-today">Due today</span>}
                      </div>
                    </td>
                  )}
                  {!hiddenColumns.includes('notes') && <td><textarea value={app.notes || ''} onChange={(e) => updateApp(app.id, { notes: e.target.value })} /></td>}
                  {!hiddenColumns.includes('url') && <td><button className="btn btn-blue" onClick={() => window.open(app.url, '_blank', 'noopener')}>Open</button></td>}
                  <td><button className="btn btn-green" onClick={() => markApplied(app)}>Mark applied</button></td>
                </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {!loading && sorted.length === 0 && <p style={{ padding: '1rem' }}>No opened job links match these filters.</p>}
      </div>
    </div>
  )
}
