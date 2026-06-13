import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

const STATUSES = ['opened', 'applied', 'follow_up', 'interview', 'rejected', 'offer', 'not_applying']

const DEFAULT_FILTERS = {
  status: '',
  company: '',
  atsGroup: '',
  locationGroup: '',
  decision: '',
  sponsorshipStatus: '',
  quickRange: '',
  dateFrom: '',
  dateTo: '',
  minScore: '',
  maxScore: '',
  q: '',
  onlyOpenedNotApplied: false,
  followUpDue: false,
  followUpToday: false,
  followUpOverdue: false,
  followUpNone: false,
  hasError: false,
  jdMissing: false,
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

export default function Applications() {
  const [applications, setApplications] = useState([])
  const [filterOptions, setFilterOptions] = useState({ ats_groups: [], location_groups: [], decisions: [], sponsorship_statuses: [] })
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [hiddenColumns, setHiddenColumns] = useState(['searchBucket'])
  const [sort, setSort] = useState({ field: 'opened_at', direction: 'desc' })
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pageSize] = useState(50)
  const toast = useToast()

  const buildParams = (overrides = {}) => {
    const f = { ...filters, ...overrides }
    const params = {
      sort_by: sort.field === 'clickedAt' ? 'opened_at' : sort.field,
      sort_dir: sort.direction,
      page,
      page_size: pageSize,
    }
    if (f.status) params.status = f.status
    if (f.company) params.company = f.company
    if (f.atsGroup) params.ats_group = f.atsGroup
    if (f.locationGroup) params.location_group = f.locationGroup
    if (f.decision) params.decision = f.decision
    if (f.sponsorshipStatus) params.sponsorship_status = f.sponsorshipStatus
    if (f.quickRange) params.quick_range = f.quickRange
    if (f.dateFrom) params.date_from = f.dateFrom
    if (f.dateTo) params.date_to = f.dateTo
    if (f.minScore !== '') params.min_score = Number(f.minScore)
    if (f.maxScore !== '') params.max_score = Number(f.maxScore)
    if (f.q) params.q = f.q
    if (f.onlyOpenedNotApplied) params.opened_not_applied = true
    if (f.followUpDue) params.follow_up_due = true
    if (f.followUpToday) params.follow_up_today = true
    if (f.followUpOverdue) params.follow_up_overdue = true
    if (f.followUpNone) params.follow_up_none = true
    if (f.hasError) params.has_error = true
    if (f.jdMissing) params.jd_missing = true
    return params
  }

  const refresh = (overrides = {}) => {
    setLoading(true)
    api.getApplications(buildParams(overrides)).then((data) => {
      setApplications(data.rows || [])
      setFilterOptions(data.filter_options || { ats_groups: [] })
      setTotal(data.total || 0)
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    setPage(1)
  }, [filters, sort])

  useEffect(() => {
    refresh()
  }, [page])

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  const handleFilterCommit = () => {
    setPage(1)
    refresh({ page: 1 })
  }

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
      if (applications.length > 0 && prev.size === applications.length) return new Set()
      return new Set(applications.map((a) => a.id))
    })
  }

  const bulkMarkApplied = async () => {
    if (selectedIds.size === 0) return
    const confirmed = window.confirm(`Mark ${selectedIds.size} application(s) as applied?`)
    if (!confirmed) return
    await api.bulkUpdateApplications([...selectedIds], { mark_applied: true })
    toast(`Marked ${selectedIds.size} as applied`, 'success')
    setSelectedIds(new Set())
    refresh()
  }

  const clearFilters = () => { setFilters(DEFAULT_FILTERS); setPage(1); setTimeout(() => refresh({ page: 1 }), 0) }

  const [exportFormat, setExportFormat] = useState('csv')
  const [exportScope, setExportScope] = useState('all')

  const handleSort = (field) => {
    const newDir = sort.field === field && sort.direction === 'asc' ? 'desc' : 'asc'
    setSort({ field, direction: newDir })
    setPage(1)
    setTimeout(() => refresh({ sort_by: field, sort_dir: newDir, page: 1 }), 0)
  }

  const handleExport = async () => {
    const params = { format: exportFormat }
    if (exportScope === 'selected') {
      if (selectedIds.size === 0) { toast('No rows selected', 'warning'); return }
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
      toast('Export downloaded', 'success')
    } catch (err) {
      toast('Export failed', 'error')
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
        <div className="stat-card"><span>Total opened</span><strong>{total}</strong></div>
        <div className="stat-card"><span>Shown</span><strong>{applications.length}</strong></div>
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
        <div><label>Status</label><select value={filters.status} onChange={(e) => { handleFilterChange('status', e.target.value); handleFilterCommit() }}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Company</label><input value={filters.company} onChange={(e) => handleFilterChange('company', e.target.value)} onBlur={handleFilterCommit} placeholder="Company" /></div>
        <div><label>ATS group</label><select value={filters.atsGroup} onChange={(e) => { handleFilterChange('atsGroup', e.target.value); handleFilterCommit() }}><option value="">All</option>{filterOptions.ats_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Location</label><select value={filters.locationGroup} onChange={(e) => { handleFilterChange('locationGroup', e.target.value); handleFilterCommit() }}><option value="">All</option>{filterOptions.location_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Decision</label><select value={filters.decision} onChange={(e) => { handleFilterChange('decision', e.target.value); handleFilterCommit() }}><option value="">All</option>{filterOptions.decisions?.map((d) => <option key={d} value={d}>{d}</option>)}</select></div>
        <div><label>Sponsorship</label><select value={filters.sponsorshipStatus} onChange={(e) => { handleFilterChange('sponsorshipStatus', e.target.value); handleFilterCommit() }}><option value="">All</option>{filterOptions.sponsorship_statuses?.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Range</label><select value={filters.quickRange} onChange={(e) => { handleFilterChange('quickRange', e.target.value); handleFilterCommit() }}><option value="">All time</option><option value="last_24_hours">Last 24 hours</option><option value="last_7_days">Last 7 days</option><option value="last_30_days">Last 30 days</option></select></div>
        <div><label>Date from</label><input type="datetime-local" value={filters.dateFrom} onChange={(e) => handleFilterChange('dateFrom', e.target.value)} onBlur={handleFilterCommit} /></div>
        <div><label>Date to</label><input type="datetime-local" value={filters.dateTo} onChange={(e) => handleFilterChange('dateTo', e.target.value)} onBlur={handleFilterCommit} /></div>
        <div><label>Min score</label><input type="number" value={filters.minScore} onChange={(e) => handleFilterChange('minScore', e.target.value)} onBlur={handleFilterCommit} /></div>
        <div><label>Max score</label><input type="number" value={filters.maxScore} onChange={(e) => handleFilterChange('maxScore', e.target.value)} onBlur={handleFilterCommit} /></div>
        <div><label>Search</label><input value={filters.q} onChange={(e) => handleFilterChange('q', e.target.value)} onBlur={handleFilterCommit} placeholder="Title, company, URL" /></div>
        <div className="checkbox-filter">
          <label><input type="checkbox" checked={filters.onlyOpenedNotApplied} onChange={(e) => { handleFilterChange('onlyOpenedNotApplied', e.target.checked); handleFilterCommit() }} /> Opened, not applied</label>
          <label><input type="checkbox" checked={filters.followUpDue} onChange={(e) => { handleFilterChange('followUpDue', e.target.checked); handleFilterCommit() }} /> Follow-up due</label>
          <label><input type="checkbox" checked={filters.followUpToday} onChange={(e) => { handleFilterChange('followUpToday', e.target.checked); handleFilterCommit() }} /> Follow-up today</label>
          <label><input type="checkbox" checked={filters.followUpOverdue} onChange={(e) => { handleFilterChange('followUpOverdue', e.target.checked); handleFilterCommit() }} /> Overdue</label>
          <label><input type="checkbox" checked={filters.followUpNone} onChange={(e) => { handleFilterChange('followUpNone', e.target.checked); handleFilterCommit() }} /> No follow-up</label>
          <label><input type="checkbox" checked={filters.hasError} onChange={(e) => { handleFilterChange('hasError', e.target.checked); handleFilterCommit() }} /> Has error</label>
          <label><input type="checkbox" checked={filters.jdMissing} onChange={(e) => { handleFilterChange('jdMissing', e.target.checked); handleFilterCommit() }} /> JD missing</label>
        </div>
        <div className="table-control-actions"><label>Rows shown</label><span>{applications.length} of {total}</span><button className="btn btn-grey" onClick={clearFilters}>Clear filters</button></div>
      </div>

      <div className="col-toggles compact-toggles">
        <strong style={{ width: '100%' }}>Application columns</strong>
        {columns.map(([key, label]) => (
          <label key={key}><input type="checkbox" checked={!hiddenColumns.includes(key)} onChange={() => setHiddenColumns(hiddenColumns.includes(key) ? hiddenColumns.filter((c) => c !== key) : [...hiddenColumns, key])} /> {label}</label>
        ))}
      </div>

      {selectedIds.size > 0 && (
        <div className="sticky-toolbar">
          <span className="toolbar-count"><strong>{selectedIds.size}</strong> selected</span>
          <button className="btn btn-green" onClick={bulkMarkApplied}>Mark applied</button>
          <button className="btn btn-grey" onClick={() => setSelectedIds(new Set())}>Clear selection</button>
        </div>
      )}

      <div className="delete-actions">
        <div><strong>{selectedIds.size}</strong> selected</div>
        <button className="btn btn-green" onClick={bulkMarkApplied} disabled={selectedIds.size === 0}>Mark selected as applied</button>
      </div>

      <div className="table-wrap">
        {loading ? (
          <div className="empty-state">
            <div className="loading-spinner" />
            <p>Loading applications...</p>
          </div>
        ) : applications.length === 0 ? (
          <div className="empty-state">
            <h3>No applications yet</h3>
            <p>Open job links from the Dashboard to start tracking applications.</p>
          </div>
        ) : (
          <table>
            <thead><tr>
              <th className="row-select-cell">
                <input
                  type="checkbox"
                  checked={applications.length > 0 && selectedIds.size === applications.length}
                  onChange={toggleSelectAll}
                />
              </th>
              {columns.filter(([key]) => !hiddenColumns.includes(key)).map(([key, label]) => <th key={key}><button className="table-header-button" onClick={() => handleSort(key)}>{label}{sort.field === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>)}<th>Actions</th></tr></thead>
            <tbody>
              {applications.map((app) => {
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
      </div>

      {total > pageSize && (
        <div className="pagination">
          <button className="btn btn-grey" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {Math.ceil(total / pageSize)}</span>
          <button className="btn btn-grey" disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  )
}
