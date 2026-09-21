import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { api, apiFieldErrors, formatApiError } from '../api/client'
import { applicationNavigationState, applicationStateQuery, queryValidationMessage, serializeApplicationQuery } from '../api/queryParams'
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
  locationGroup: '',
  decision: '',
  sponsorshipStatus: '',
  q: '',
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

export default function Applications() {
  const initialNavigation = useMemo(
    () => applicationNavigationState(window.location.search, { ...DEFAULT_FILTERS, sortBy: 'opened_at', sortDir: 'desc', page: 1, pageSize: 50 }),
    []
  )
  const initialFilters = { ...DEFAULT_FILTERS, ...initialNavigation.filters }
  const [applications, setApplications] = useState([])
  const [filterOptions, setFilterOptions] = useState({ ats_groups: [], location_groups: [], decisions: [], sponsorship_statuses: [] })
  const [filters, setFilters] = useState(initialFilters)
  const [hiddenColumns, setHiddenColumns] = useState(['searchBucket'])
  const [sort, setSort] = useState(initialNavigation.sort)
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [pagination, setPagination] = useState({ ...DEFAULT_PAGINATION, page: initialNavigation.page, pageSize: initialNavigation.pageSize })
  const settledQueryRef = useRef(null)
  const requestSequenceRef = useRef(0)
  const [queryError, setQueryError] = useState(() => queryValidationMessage(initialNavigation))
  const [drafts, setDrafts] = useState({})
  const [fieldErrors, setFieldErrors] = useState({})
  const [focusTarget, setFocusTarget] = useState(null)
  const [pendingRows, setPendingRows] = useState(new Set())
  const [bulkPending, setBulkPending] = useState(false)
  const pendingMutationRef = useRef(new Set())
  const fieldRefs = useRef({})
  const toast = useToast()

  const refresh = (nextFilters = filters, nextSort = sort, nextPage = pagination.page) => {
    const requestId = ++requestSequenceRef.current
    const query = applicationStateQuery(nextSort, nextFilters, nextPage, pagination.pageSize)
    setLoading(true)
    return api.getApplications(query).then((data) => {
      if (requestId !== requestSequenceRef.current) return
      setApplications(data.rows || [])
      setFilterOptions(data.filter_options || { ats_groups: [] })
      setPagination({ page: data.page || nextPage, pageSize: data.page_size || 50, totalCount: data.total_count || (data.rows || []).length, hasNext: data.has_next || false })
      settledQueryRef.current = query
    }).catch(() => {
      if (requestId === requestSequenceRef.current) toast('Could not load applications. Please retry.', 'error')
    }).finally(() => {
      if (requestId === requestSequenceRef.current) setLoading(false)
    })
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    if (!focusTarget || pendingRows.has(focusTarget.itemId)) return
    const node = fieldRefs.current[`${focusTarget.itemId}:${focusTarget.field}`]
    if (!node) return
    node.focus()
    setFocusTarget(null)
  }, [focusTarget, pendingRows, fieldErrors])

  const addApplicationToToday = async (app) => {
    if (pendingMutationRef.current.has(app.id)) return
    pendingMutationRef.current.add(app.id)
    setPendingRow(app.id, true)
    try {
      await api.createWorkItem({
        description: `Review ${app.company || 'company'} — ${app.title || 'role'}`,
        track_id: app.id,
        ...(app.csv_row_id ? { row_id: app.csv_row_id } : {}),
        priority: 1,
      })
      toast('Added to Today.', 'success')
    } catch (error) {
      toast(formatApiError(error, 'Could not add this application to Today.').message, 'error')
    } finally {
      pendingMutationRef.current.delete(app.id)
      setPendingRow(app.id, false)
    }
  }

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

  const draftKey = (itemId, field) => `${itemId}:${field}`

  const draftValue = (app, field, fallback) => {
    const key = draftKey(app.id, field)
    return Object.prototype.hasOwnProperty.call(drafts, key) ? drafts[key] : fallback
  }

  const setDraftValue = (itemId, field, value) => {
    const key = draftKey(itemId, field)
    setDrafts((prev) => ({ ...prev, [key]: value }))
    setFieldErrors((prev) => {
      if (!prev[itemId]?.[field]) return prev
      const nextRow = { ...prev[itemId] }
      delete nextRow[field]
      const next = { ...prev }
      if (Object.keys(nextRow).length === 0) delete next[itemId]
      else next[itemId] = nextRow
      return next
    })
  }

  const clearDraftFields = (itemId, fields) => {
    setDrafts((prev) => {
      const next = { ...prev }
      fields.forEach((field) => delete next[draftKey(itemId, field)])
      return next
    })
  }

  const setPendingRow = (itemId, pending) => {
    setPendingRows((prev) => {
      const next = new Set(prev)
      if (pending) next.add(itemId)
      else next.delete(itemId)
      return next
    })
  }

  const updateApp = async (itemId, payload, { draftFields = Object.keys(payload) } = {}) => {
    if (pendingMutationRef.current.has(itemId)) return null

    pendingMutationRef.current.add(itemId)
    setPendingRow(itemId, true)
    setFieldErrors((prev) => {
      if (!prev[itemId]) return prev
      const next = { ...prev }
      delete next[itemId]
      return next
    })

    try {
      const updated = await api.updateApplication(itemId, payload)
      setApplications((prev) =>
        prev.map((app) => (app.id === itemId ? { ...app, ...updated } : app))
      )
      clearDraftFields(itemId, draftFields)
      await refresh()
      return updated
    } catch (error) {
      const formatted = formatApiError(error, 'Could not save this application. Correct the highlighted fields and retry.')
      setFieldErrors((prev) => ({ ...prev, [itemId]: apiFieldErrors(error, formatted.message) }))
      const firstInvalid = formatted.fields.find((item) => item.field && item.field !== 'non_field')
      if (firstInvalid) setFocusTarget({ itemId, field: firstInvalid.field })
      toast(formatted.message, 'error')
      return null
    } finally {
      pendingMutationRef.current.delete(itemId)
      setPendingRow(itemId, false)
    }
  }

  const markApplied = async (app) => {
    await updateApp(app.id, { mark_applied: true }, { draftFields: [] })
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
    if (selectedIds.size === 0 || bulkPending) return
    const confirmed = window.confirm(`Mark ${selectedIds.size} application(s) as applied?`)
    if (!confirmed) return

    setBulkPending(true)
    try {
      await api.bulkUpdateApplications([...selectedIds], { mark_applied: true })
      toast(`Marked ${selectedIds.size} as applied`, 'success')
      setSelectedIds(new Set())
      await refresh()
    } catch (error) {
      toast(formatApiError(error, 'Could not update the selected applications. Please retry.').message, 'error')
    } finally {
      setBulkPending(false)
    }
  }

  const [exportFormat, setExportFormat] = useState('csv')
  const [exportScope, setExportScope] = useState('all')

  const handleExport = async () => {
    if (loading || !settledQueryRef.current) {
      toast('Wait for the current filters to finish loading before exporting.', 'warning')
      return
    }
    const querySnapshot = applicationStateQuery(sort, filters, pagination.page, pagination.pageSize)
    const currentSignature = JSON.stringify(serializeApplicationQuery(querySnapshot, { includePagination: false, includeFalse: true }))
    const settledSignature = JSON.stringify(serializeApplicationQuery(settledQueryRef.current, { includePagination: false, includeFalse: true }))
    if (currentSignature !== settledSignature) {
      toast('Filters changed before the matching results settled. Retry after loading finishes.', 'warning')
      return
    }
    const params = { ...querySnapshot, format: exportFormat, scope: exportScope }
    if (exportScope === 'selected') {
      if (selectedIds.size === 0) { toast('No rows selected', 'warning'); return }
      params.rowIds = [...selectedIds]
    } else if (exportScope === 'applied') {
      params.scope = 'filtered'
      Object.assign(params, { ...DEFAULT_FILTERS, status: 'applied' })
    } else if (exportScope === 'followups') {
      params.scope = 'filtered'
      Object.assign(params, { ...DEFAULT_FILTERS, followUpDue: true })
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
    } catch {
      toast('Export failed. No file was downloaded. Please retry.', 'error')
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

  const clearNavigationError = () => {
    window.history.replaceState({}, '', window.location.pathname)
    setQueryError('')
    setSort({ field: 'opened_at', direction: 'desc' })
    setFilters(DEFAULT_FILTERS)
    setPagination(DEFAULT_PAGINATION)
    refresh(DEFAULT_FILTERS, { field: 'opened_at', direction: 'desc' }, 1)
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
      {queryError && <div className="error-msg" role="alert">{queryError} <button className="btn btn-grey btn-sm" onClick={clearNavigationError}>Clear saved-view filters</button></div>}
      <div className="page-header-row">
        <div>
          <h2>Applications</h2>
          <p>Track opened jobs, applied dates, follow-ups, notes, and statuses.</p>
        </div>
        <button className="btn btn-blue" onClick={() => refresh()}>Refresh</button>
      </div>

      <div className="stats-grid app-stats-grid">
        <div className="stat-card"><span>Total</span><strong>{pagination.totalCount}</strong></div>
        <div className="stat-card"><span>Page</span><strong>{pagination.page}</strong></div>
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
        <button className="btn btn-grey" onClick={handleExport} disabled={loading}>Download</button>
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
          <button className="btn btn-green" onClick={bulkMarkApplied} disabled={bulkPending}>{bulkPending ? 'Saving...' : 'Mark applied'}</button>
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
                  {!hiddenColumns.includes('company') && (
                    <td>
                      <input
                        className="inline-input"
                        ref={(node) => { fieldRefs.current[draftKey(app.id, 'company')] = node }}
                        value={draftValue(app, 'company', app.company || '')}
                        aria-invalid={Boolean(fieldErrors[app.id]?.company)}
                        aria-describedby={fieldErrors[app.id]?.company ? `app-${app.id}-company-error` : undefined}
                        disabled={pendingRows.has(app.id)}
                        onChange={(e) => setDraftValue(app.id, 'company', e.target.value)}
                        onBlur={(e) => {
                          if (e.target.value !== (app.company || '')) updateApp(app.id, { company: e.target.value }, { draftFields: ['company'] })
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            if (e.currentTarget.value !== (app.company || '')) updateApp(app.id, { company: e.currentTarget.value }, { draftFields: ['company'] })
                          }
                        }}
                      />
                      {fieldErrors[app.id]?.company && <p id={`app-${app.id}-company-error`} className="error-msg" role="alert">{fieldErrors[app.id].company}</p>}
                    </td>
                  )}
                  {!hiddenColumns.includes('title') && <td>{app.title}</td>}
                  {!hiddenColumns.includes('status') && (
                    <td>
                      <select
                        ref={(node) => { fieldRefs.current[draftKey(app.id, 'status')] = node }}
                        value={draftValue(app, 'status', app.status)}
                        aria-invalid={Boolean(fieldErrors[app.id]?.status)}
                        aria-describedby={fieldErrors[app.id]?.status ? `app-${app.id}-status-error` : undefined}
                        disabled={pendingRows.has(app.id)}
                        onChange={(e) => {
                          const value = e.target.value
                          setDraftValue(app.id, 'status', value)
                          updateApp(app.id, { status: value }, { draftFields: ['status'] })
                        }}
                      >
                        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                      {fieldErrors[app.id]?.status && <p id={`app-${app.id}-status-error`} className="error-msg" role="alert">{fieldErrors[app.id].status}</p>}
                    </td>
                  )}
                  {!hiddenColumns.includes('ats_group') && <td>{app.ats_group}</td>}
                  {!hiddenColumns.includes('search_bucket') && <td>{app.search_bucket}</td>}
                  {!hiddenColumns.includes('resume_match_score') && <td>{app.resume_match_score}</td>}
                  {!hiddenColumns.includes('opened_at') && <td>{formatDateTime(app.opened_at)}</td>}
                  {!hiddenColumns.includes('applied_at') && (
                    <td>
                      <input
                        type="datetime-local"
                        ref={(node) => { fieldRefs.current[draftKey(app.id, 'applied_at')] = node }}
                        value={draftValue(app, 'applied_at', localInputValue(app.applied_at))}
                        aria-invalid={Boolean(fieldErrors[app.id]?.applied_at)}
                        aria-describedby={fieldErrors[app.id]?.applied_at ? `app-${app.id}-applied-error` : undefined}
                        disabled={pendingRows.has(app.id)}
                        onChange={(e) => setDraftValue(app.id, 'applied_at', e.target.value)}
                        onBlur={(e) => {
                          const value = e.target.value
                          if (value !== localInputValue(app.applied_at)) {
                            updateApp(app.id, { applied_at: inputToIso(value), status: value ? 'applied' : app.status }, { draftFields: ['applied_at'] })
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            const value = e.currentTarget.value
                            if (value !== localInputValue(app.applied_at)) {
                              updateApp(app.id, { applied_at: inputToIso(value), status: value ? 'applied' : app.status }, { draftFields: ['applied_at'] })
                            }
                          }
                        }}
                      />
                      {fieldErrors[app.id]?.applied_at && <p id={`app-${app.id}-applied-error`} className="error-msg" role="alert">{fieldErrors[app.id].applied_at}</p>}
                    </td>
                  )}
                  {!hiddenColumns.includes('follow_up_at') && (
                    <td>
                      <div className="follow-up-cell">
                        <input
                          type="datetime-local"
                          ref={(node) => { fieldRefs.current[draftKey(app.id, 'follow_up_at')] = node }}
                          value={draftValue(app, 'follow_up_at', localInputValue(app.follow_up_at))}
                          aria-invalid={Boolean(fieldErrors[app.id]?.follow_up_at)}
                          aria-describedby={fieldErrors[app.id]?.follow_up_at ? `app-${app.id}-followup-error` : undefined}
                          disabled={pendingRows.has(app.id)}
                          onChange={(e) => setDraftValue(app.id, 'follow_up_at', e.target.value)}
                          onBlur={(e) => {
                            const value = e.target.value
                            if (value !== localInputValue(app.follow_up_at)) updateApp(app.id, { follow_up_at: inputToIso(value) }, { draftFields: ['follow_up_at'] })
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              const value = e.currentTarget.value
                              if (value !== localInputValue(app.follow_up_at)) updateApp(app.id, { follow_up_at: inputToIso(value) }, { draftFields: ['follow_up_at'] })
                            }
                          }}
                        />
                        {fieldErrors[app.id]?.follow_up_at && <p id={`app-${app.id}-followup-error`} className="error-msg" role="alert">{fieldErrors[app.id].follow_up_at}</p>}
                        <div className="follow-up-quick-btns">
                          <button className="btn btn-grey btn-sm" disabled={pendingRows.has(app.id)} onClick={() => updateApp(app.id, { follow_up_at: new Date(Date.now() + 3 * 86400000).toISOString() }, { draftFields: ['follow_up_at'] })}>+3d</button>
                          <button className="btn btn-grey btn-sm" disabled={pendingRows.has(app.id)} onClick={() => updateApp(app.id, { follow_up_at: new Date(Date.now() + 7 * 86400000).toISOString() }, { draftFields: ['follow_up_at'] })}>+7d</button>
                          <button className="btn btn-grey btn-sm" disabled={pendingRows.has(app.id)} onClick={() => {
                            const now = new Date(); const day = now.getDay(); const daysUntilMon = (8 - day) % 7 || 7
                            updateApp(app.id, { follow_up_at: new Date(now.getTime() + daysUntilMon * 86400000).toISOString() }, { draftFields: ['follow_up_at'] })
                          }}>Mon</button>
                          {app.follow_up_at && <button className="btn btn-grey btn-sm" disabled={pendingRows.has(app.id)} onClick={() => updateApp(app.id, { follow_up_at: '' }, { draftFields: ['follow_up_at'] })}>Clear</button>}
                        </div>
                      </div>
                    </td>
                  )}
                  {!hiddenColumns.includes('notes') && (
                    <td>
                      <textarea
                        ref={(node) => { fieldRefs.current[draftKey(app.id, 'notes')] = node }}
                        value={draftValue(app, 'notes', app.notes || '')}
                        aria-invalid={Boolean(fieldErrors[app.id]?.notes)}
                        aria-describedby={fieldErrors[app.id]?.notes ? `app-${app.id}-notes-error` : undefined}
                        disabled={pendingRows.has(app.id)}
                        onChange={(e) => setDraftValue(app.id, 'notes', e.target.value)}
                        onBlur={(e) => {
                          if (e.target.value !== (app.notes || '')) updateApp(app.id, { notes: e.target.value }, { draftFields: ['notes'] })
                        }}
                      />
                      {fieldErrors[app.id]?.notes && <p id={`app-${app.id}-notes-error`} className="error-msg" role="alert">{fieldErrors[app.id].notes}</p>}
                    </td>
                  )}
                  {!hiddenColumns.includes('url') && <td><button className="btn btn-blue" onClick={() => window.open(app.url, '_blank', 'noopener')}>Open</button></td>}
                  <td>
                    <button className="btn btn-green" disabled={pendingRows.has(app.id)} onClick={() => markApplied(app)}>
                      {pendingRows.has(app.id) ? 'Saving...' : 'Mark applied'}
                    </button>
                    <button className="btn btn-grey" style={{ marginLeft: 6 }} disabled={pendingRows.has(app.id)} onClick={() => addApplicationToToday(app)}>
                      Add to Today
                    </button>
                    {fieldErrors[app.id]?.non_field && <p className="error-msg" role="alert">{fieldErrors[app.id].non_field}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
