import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

const DEFAULT_FILTERS = {
  q: '',
  atsGroup: '',
  locationGroup: '',
  searchBucket: '',
  decision: '',
  sponsorshipStatus: '',
  openedOnly: false,
  hasError: false,
  jdMissing: false,
}

function expectedVersions(rows) {
  return rows.reduce((out, row) => {
    out[row.id] = row.version
    return out
  }, {})
}

function archivedLabel(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
}

export default function Archive() {
  const toast = useToast()
  const [rows, setRows] = useState([])
  const [filterOptions, setFilterOptions] = useState({})
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [sortBy, setSortBy] = useState('archived_at')
  const [sortDir, setSortDir] = useState('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [totalCount, setTotalCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pendingAction, setPendingAction] = useState('')

  const query = useMemo(() => ({
    ...filters,
    archiveScope: 'archived',
    sortBy,
    sortDir,
    page,
    pageSize,
  }), [filters, sortBy, sortDir, page, pageSize])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.getRows(query)
      setRows(result.rows || [])
      setFilterOptions(result.filter_options || {})
      setTotalCount(result.total_count || 0)
      setHasNext(Boolean(result.has_next))
      setSelected(new Set())
    } catch {
      setError('Could not load Archive. Retry after checking your connection.')
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const handler = () => load()
    window.addEventListener('jobgrid:bulk-changed', handler)
    return () => window.removeEventListener('jobgrid:bulk-changed', handler)
  }, [load])

  const selectedRows = rows.filter((row) => selected.has(row.id))
  const allShownSelected = rows.length > 0 && rows.every((row) => selected.has(row.id))

  const setFilter = (key, value) => {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  const toggleRow = (id) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    setSelected(allShownSelected ? new Set() : new Set(rows.map((row) => row.id)))
  }

  const restoreSelected = async () => {
    if (!selectedRows.length || pendingAction) return
    setPendingAction('restore')
    try {
      const result = await api.restoreRows(
        selectedRows.map((row) => row.id),
        expectedVersions(selectedRows),
        'all_or_nothing'
      )
      toast(`Restored ${result.restored} archived row${result.restored === 1 ? '' : 's'}.`, 'success')
      await load()
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail
      toast(detail?.fields?.[0]?.message || 'Restore failed. Reload before retrying.', 'error')
    } finally {
      setPendingAction('')
    }
  }

  const permanentlyDeleteSelected = async () => {
    if (!selectedRows.length || pendingAction) return
    setPendingAction('delete-preview')
    try {
      const ids = selectedRows.map((row) => row.id)
      const versions = expectedVersions(selectedRows)
      const preview = await api.previewPermanentDelete(ids, versions)
      const confirmed = window.confirm([
        `Permanently delete ${preview.eligible_count} archived source row${preview.eligible_count === 1 ? '' : 's'}?`,
        '',
        preview.warning,
        '',
        'This action is not Undo. It cannot be reversed from JobGrid after deletion.',
      ].join('\n'))
      if (!confirmed) return
      setPendingAction('delete')
      const result = await api.deleteRows(ids, 'delete', {
        expectedVersions: versions,
        confirmationToken: preview.confirmation_token,
      })
      toast(`Permanently deleted ${result.deleted} archived source row${result.deleted === 1 ? '' : 's'}.`, 'success')
      await load()
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail
      toast(detail?.fields?.[0]?.message || 'Permanent deletion was not completed.', 'error')
    } finally {
      setPendingAction('')
    }
  }

  return (
    <div className="page-container" data-testid="archive-page">
      <div className="page-header">
        <div>
          <h1>Archive</h1>
          <p>Recover source rows after cleanup. Immediate Undo may expire, but archived rows stay here until you explicitly restore or permanently delete them.</p>
        </div>
      </div>

      <section className="card" aria-label="Archive filters">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            aria-label="Search archived jobs"
            placeholder="Search company, title, or URL"
            value={filters.q}
            onChange={(event) => setFilter('q', event.target.value)}
          />
          <select aria-label="ATS group" value={filters.atsGroup} onChange={(event) => setFilter('atsGroup', event.target.value)}>
            <option value="">All ATS groups</option>
            {(filterOptions.ats_groups || []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select aria-label="Location group" value={filters.locationGroup} onChange={(event) => setFilter('locationGroup', event.target.value)}>
            <option value="">All locations</option>
            {(filterOptions.location_groups || []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select aria-label="Decision" value={filters.decision} onChange={(event) => setFilter('decision', event.target.value)}>
            <option value="">All decisions</option>
            {(filterOptions.decisions || []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select aria-label="Sponsorship status" value={filters.sponsorshipStatus} onChange={(event) => setFilter('sponsorshipStatus', event.target.value)}>
            <option value="">All sponsorship states</option>
            {(filterOptions.sponsorship_statuses || []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <label><input type="checkbox" checked={filters.openedOnly} onChange={(event) => setFilter('openedOnly', event.target.checked)} /> Opened only</label>
          <label><input type="checkbox" checked={filters.hasError} onChange={(event) => setFilter('hasError', event.target.checked)} /> Errors</label>
          <label><input type="checkbox" checked={filters.jdMissing} onChange={(event) => setFilter('jdMissing', event.target.checked)} /> JD missing</label>
          <button className="btn btn-grey btn-sm" type="button" onClick={() => { setFilters(DEFAULT_FILTERS); setPage(1) }}>Clear filters</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 10 }}>
          <label>Sort
            <select value={sortBy} onChange={(event) => { setSortBy(event.target.value); setPage(1) }}>
              <option value="archived_at">Archived time</option>
              <option value="created_at">Created time</option>
              <option value="title">Title</option>
              <option value="company_guess">Company</option>
              <option value="clicked_at">Opened time</option>
            </select>
          </label>
          <select aria-label="Sort direction" value={sortDir} onChange={(event) => { setSortDir(event.target.value); setPage(1) }}>
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
          <label>Rows per page
            <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }}>
              {[25, 50, 100, 250, 500].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section className="card" aria-label="Archive actions" style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>{selected.size} selected of {totalCount} archived rows</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" type="button" disabled={!selected.size || Boolean(pendingAction)} onClick={restoreSelected}>
              {pendingAction === 'restore' ? 'Restoring…' : 'Restore selected'}
            </button>
            <button className="btn btn-danger" type="button" disabled={!selected.size || Boolean(pendingAction)} onClick={permanentlyDeleteSelected}>
              {pendingAction.startsWith('delete') ? 'Checking…' : 'Permanently delete selected'}
            </button>
          </div>
        </div>
      </section>

      {error && <div className="card" role="alert" style={{ marginTop: 12 }}>{error} <button className="btn btn-grey btn-sm" onClick={load}>Retry</button></div>}
      {loading ? (
        <div className="card" style={{ marginTop: 12 }} role="status">Loading Archive…</div>
      ) : rows.length === 0 ? (
        <div className="card" style={{ marginTop: 12 }}>No archived rows match these filters.</div>
      ) : (
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th><input aria-label="Select all archived rows on this page" type="checkbox" checked={allShownSelected} onChange={toggleAll} /></th>
                <th>Archived</th>
                <th>Company</th>
                <th>Title</th>
                <th>ATS</th>
                <th>Status</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-testid={`archive-row-${row.id}`}>
                  <td><input aria-label={`Select archived row ${row.id}`} type="checkbox" checked={selected.has(row.id)} onChange={() => toggleRow(row.id)} /></td>
                  <td>{archivedLabel(row.archived_at)}</td>
                  <td>{row.data?.company_guess || '—'}</td>
                  <td>{row.data?.title || '—'}</td>
                  <td>{row.data?.ats_group || '—'}</td>
                  <td>{row.app_status || '—'}</td>
                  <td>{row.data?.url ? <a href={row.data.url} target="_blank" rel="noreferrer">Open source</a> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
        <button className="btn btn-grey" type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button>
        <span>Page {page}</span>
        <button className="btn btn-grey" type="button" disabled={!hasNext || loading} onClick={() => setPage((value) => value + 1)}>Next</button>
      </div>
    </div>
  )
}
