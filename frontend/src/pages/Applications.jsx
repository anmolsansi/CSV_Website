import { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

const STATUSES = ['opened', 'applied', 'follow_up', 'interview', 'rejected', 'offer', 'not_applying']

const DEFAULT_FILTERS = {
  status: '',
  company: '',
  atsGroup: '',
  searchBucket: '',
  quickRange: '',
  dateFrom: '',
  dateTo: '',
  minScore: '',
  maxScore: '',
  openedNotApplied: false,
  followUpDue: false,
  followUpToday: false,
  followUpOverdue: false,
  followUpNone: false,
  hasError: false,
  jdMissing: false,
}
const DEFAULT_PAGINATION = { page: 1, pageSize: 50, totalCount: 0, hasNext: false }

function formatDateTime(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

function localInputValue(value) {
  if (!value) return ''
  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasTimezone ? value : `${value}Z`)
  if (Number.isNaN(parsed.getTime())) return ''
  const offset = parsed.getTimezoneOffset() * 60000
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16)
}

function inputToIso(value) {
  return value ? new Date(value).toISOString() : ''
}

function buildApiParams(filters, sort, pagination) {
  return {
    sort_by: sort.field === 'clickedAt' ? 'opened_at' : sort.field,
    sort_dir: sort.direction,
    page: pagination.page,
    page_size: pagination.pageSize,
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.company ? { company: filters.company } : {}),
    ...(filters.atsGroup ? { ats_group: filters.atsGroup } : {}),
    ...(filters.searchBucket ? { search_bucket: filters.searchBucket } : {}),
    ...(filters.quickRange ? { quick_range: filters.quickRange } : {}),
    ...(filters.dateFrom ? { date_from: new Date(filters.dateFrom).toISOString() } : {}),
    ...(filters.dateTo ? { date_to: new Date(filters.dateTo).toISOString() } : {}),
    ...(filters.minScore ? { min_score: Number(filters.minScore) } : {}),
    ...(filters.maxScore ? { max_score: Number(filters.maxScore) } : {}),
    ...(filters.followUpDue ? { follow_up_due: true } : {}),
    ...(filters.followUpToday ? { follow_up_today: true } : {}),
    ...(filters.followUpOverdue ? { follow_up_overdue: true } : {}),
    ...(filters.followUpNone ? { follow_up_none: true } : {}),
    ...(filters.openedNotApplied ? { opened_not_applied: true } : {}),
    ...(filters.hasError ? { has_error: true } : {}),
    ...(filters.jdMissing ? { jd_missing: true } : {}),
    ...(filters.locationGroup ? { location_group: filters.locationGroup } : {}),
    ...(filters.decision ? { decision: filters.decision } : {}),
    ...(filters.sponsorshipStatus ? { sponsorship_status: filters.sponsorshipStatus } : {}),
    ...(filters.q ? { q: filters.q } : {}),
  }
}

export default function Applications() {
  const [applications, setApplications] = useState([])
  const [filterOptions, setFilterOptions] = useState({ ats_groups: [], location_groups: [], decisions: [], sponsorship_statuses: [] })
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [hiddenColumns, setHiddenColumns] = useState(['searchBucket'])
  const [sort, setSort] = useState({ field: 'opened_at', direction: 'desc' })
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [pagination, setPagination] = useState(DEFAULT_PAGINATION)
  const toast = useToast()

  const refresh = (nextFilters = filters, nextSort = sort, nextPage = pagination.page) => {
    setLoading(true)
    const params = buildApiParams(nextFilters, nextSort, { ...pagination, page: nextPage })
    api.getApplications(params).then((data) => {
      setApplications(data.rows || [])
      setFilterOptions(data.filter_options || { ats_groups: [] })
      setPagination({ page: data.page || nextPage, pageSize: data.page_size || 50, totalCount: data.total_count || (data.rows || []).length, hasNext: data.has_next || false })
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    refresh()
  }, [])

  const updateFilter = (key, value) => {
    const nextFilters = { ...filters, [key]: value }
    setFilters(nextFilters)
    refresh(nextFilters, sort, 1)
  }

  const updateSort = (field) => {
    const direction = sort.field === field && sort.direction === 'asc' ? 'desc' : 'asc'
    const nextSort = { field, direction }
    setSort(nextSort)
    refresh(filters, nextSort, 1)
  }

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS)
    refresh(DEFAULT_FILTERS, sort, 1)
  }

  const goToPage = (newPage) => {
    refresh(filters, sort, newPage)
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
      params.openedNotApplied = filters.openedNotApplied || undefined
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

  const handleKeyDown = useCallback((e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
      return
    }
    switch (e.key.toLowerCase()) {
      case 'a':
        e.preventDefault()
        if (selectedIds.size > 0) bulkMarkApplied()
        break
      case 'o':
        e.preventDefault()
        if (selectedIds.size > 0) {
          applications.filter((a) => selectedIds.has(a.id)).forEach((app) => window.open(app.url, '_blank', 'noopener'))
        }
        break
      default:
        break
    }
  }, [selectedIds.size, applications, bulkMarkApplied])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

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
        <button className="btn btn-blue" onClick={() => refresh()}>Refresh</button>
      </div>

      <div className="stats-grid app-stats-grid">
        <div className="stat-card"><span>Total</span><strong>{pagination.totalCount}</strong></div>
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
        <div><label>Status</label><select value={filters.status} onChange={(e) => updateFilter('status', e.target.value)}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Company</label><input value={filters.company} onChange={(e) => updateFilter('company', e.target.value)} placeholder="Company" /></div>
        <div><label>ATS group</label><select value={filters.atsGroup} onChange={(e) => updateFilter('atsGroup', e.target.value)}><option value="">All</option>{filterOptions.ats_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Location</label><select value={filters.locationGroup} onChange={(e) => updateFilter('locationGroup', e.target.value)}><option value="">All</option>{filterOptions.location_groups?.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
        <div><label>Decision</label><select value={filters.decision} onChange={(e) => updateFilter('decision', e.target.value)}><option value="">All</option>{filterOptions.decisions?.map((d) => <option key={d} value={d}>{d}</option>)}</select></div>
        <div><label>Sponsorship</label><select value={filters.sponsorshipStatus} onChange={(e) => updateFilter('sponsorshipStatus', e.target.value)}><option value="">All</option>{filterOptions.sponsorship_statuses?.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
        <div><label>Range</label><select value={filters.quickRange} onChange={(e) => updateFilter('quickRange', e.target.value)}><option value="">All time</option><option value="last_24_hours">Last 24 hours</option><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="last_7_days">Last 7 days</option><option value="last_30_days">Last 30 days</option></select></div>
        <div><label>Date from</label><input type="datetime-local" value={filters.dateFrom} onChange={(e) => updateFilter('dateFrom', e.target.value)} /></div>
        <div><label>Date to</label><input type="datetime-local" value={filters.dateTo} onChange={(e) => updateFilter('dateTo', e.target.value)} /></div>
        <div><label>Min score</label><input type="number" value={filters.minScore} onChange={(e) => updateFilter('minScore', e.target.value)} /></div>
        <div><label>Max score</label><input type="number" value={filters.maxScore} onChange={(e) => updateFilter('maxScore', e.target.value)} /></div>
        <div><label>Search</label><input value={filters.q} onChange={(e) => updateFilter('q', e.target.value)} placeholder="Title, company, URL" /></div>
        <div className="checkbox-filter">
          <label><input type="checkbox" checked={filters.openedNotApplied} onChange={(e) => updateFilter('openedNotApplied', e.target.checked)} /> Opened, not applied</label>
          <label><input type="checkbox" checked={filters.followUpDue} onChange={(e) => updateFilter('followUpDue', e.target.checked)} /> Follow-up due</label>
          <label><input type="checkbox" checked={filters.followUpToday} onChange={(e) => updateFilter('followUpToday', e.target.checked)} /> Follow-up today</label>
          <label><input type="checkbox" checked={filters.followUpOverdue} onChange={(e) => updateFilter('followUpOverdue', e.target.checked)} /> Overdue</label>
          <label><input type="checkbox" checked={filters.followUpNone} onChange={(e) => updateFilter('followUpNone', e.target.checked)} /> No follow-up</label>
          <label><input type="checkbox" checked={filters.hasError} onChange={(e) => updateFilter('hasError', e.target.checked)} /> Has error</label>
          <label><input type="checkbox" checked={filters.jdMissing} onChange={(e) => updateFilter('jdMissing', e.target.checked)} /> JD missing</label>
        </div>
        <div className="table-control-actions">
          <label>Rows shown</label>
          <span>{applications.length} of {pagination.totalCount}</span>
          <button className="btn btn-grey" onClick={clearFilters}>Clear filters</button>
        </div>
      </div>

      {pagination.totalCount > pagination.pageSize && (
        <div className="pagination-controls">
          <button className="btn btn-grey btn-sm" disabled={pagination.page <= 1} onClick={() => goToPage(1)}>First</button>
          <button className="btn btn-grey btn-sm" disabled={pagination.page <= 1} onClick={() => goToPage(pagination.page - 1)}>Prev</button>
          <span className="pagination-info">Page {pagination.page} of {Math.ceil(pagination.totalCount / pagination.pageSize)}</span>
          <button className="btn btn-grey btn-sm" disabled={!pagination.hasNext} onClick={() => goToPage(pagination.page + 1)}>Next</button>
          <button className="btn btn-grey btn-sm" disabled={!pagination.hasNext} onClick={() => goToPage(Math.ceil(pagination.totalCount / pagination.pageSize))}>Last</button>
        </div>
      )}

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
              {columns.filter(([key]) => !hiddenColumns.includes(key)).map(([key, label]) => <th key={key}><button className="table-header-button" onClick={() => updateSort(key)}>{label}{sort.field === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>)}<th>Actions</th></tr></thead>
            <tbody>
              {applications.map((app) => (
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
                      </div>
                    </td>
                  )}
                  {!hiddenColumns.includes('notes') && <td><textarea value={app.notes || ''} onChange={(e) => updateApp(app.id, { notes: e.target.value })} /></td>}
                  {!hiddenColumns.includes('url') && <td><button className="btn btn-blue" onClick={() => window.open(app.url, '_blank', 'noopener')}>Open</button></td>}
                  <td><button className="btn btn-green" onClick={() => markApplied(app)}>Mark applied</button></td>
                </tr>
              ))}
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
