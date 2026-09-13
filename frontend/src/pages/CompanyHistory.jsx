import { useEffect, useState } from 'react'
import { api } from '../api/client'

const STATUS_COLORS = {
  opened: { bg: '#dbeafe', color: '#1e40af' },
  applied: { bg: '#d1fae5', color: '#065f46' },
  follow_up: { bg: '#fef3c7', color: '#92400e' },
  interview: { bg: '#ede9fe', color: '#5b21b6' },
  rejected: { bg: '#fee2e2', color: '#991b1b' },
  offer: { bg: '#d1fae5', color: '#065f46' },
  not_applying: { bg: '#f3f4f6', color: '#374151' },
}

export default function CompanyHistory() {
  const [company, setCompany] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [directory, setDirectory] = useState(null)
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api.getCompanies({ q: query, page }).then((data) => {
      if (active) setDirectory(data)
    }).catch(() => {
      if (active) setError('Could not load remembered companies. Please retry.')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query, page, retry])

  useEffect(() => {
    if (!company) return
    let active = true
    setHistory(null)
    setError('')
    api.getCompanyHistory(company).then((data) => {
      if (active) setHistory(data)
    }).catch(() => {
      if (active) setError('Could not load company history. Please retry.')
    })
    return () => { active = false }
  }, [company, retry])

  const search = () => {
    setQuery(searchInput.trim())
    setPage(1)
    setCompany('')
    setHistory(null)
  }
  const handleKeyDown = (e) => { if (e.key === 'Enter') search() }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Company History</h2>
          <p>Your saved jobs and companies, remembered across visits. Mark jobs applied after submitting.</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search company name..."
          style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
        />
        <button className="btn btn-blue" onClick={search}>Search</button>
      </div>

      {error && <div role="alert">{error} <button className="btn btn-grey" onClick={() => setRetry((value) => value + 1)}>Retry</button></div>}
      {!loading && directory && (
        <section aria-label="Remembered companies">
          <h3>{directory.total_count} remembered companies</h3>
          {directory.companies.length === 0 && <p>No companies found. Select jobs on the Dashboard and mark them applied to remember them here.</p>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
            {directory.companies.map((item) => (
              <button className="btn btn-grey" key={item.company} onClick={() => setCompany(item.company)}>
                {item.company} · {item.total} jobs · {item.applied} applied
              </button>
            ))}
          </div>
          <button className="btn btn-grey" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous companies</button>
          <span> Page {page} </span>
          <button className="btn btn-grey" disabled={!directory.has_next} onClick={() => setPage(page + 1)}>Next companies</button>
        </section>
      )}
      {company && !history && !error && <p role="status">Loading company history…</p>}
      {loading && (
        <div className="empty-state"><div className="loading-spinner" /><p>Loading...</p></div>
      )}

      {!loading && history && (
        <>
          <div className="stats-grid" style={{ marginBottom: 16 }}>
            <div className="stat-card"><span>Total roles</span><strong>{history.total}</strong></div>
            <div className="stat-card"><span>Applied</span><strong>{history.applied}</strong></div>
            <div className="stat-card"><span>Interviews</span><strong>{history.interviews}</strong></div>
            <div className="stat-card"><span>Rejected</span><strong>{history.rejected}</strong></div>
          </div>

          {history.roles.length === 0 ? (
            <div className="empty-state">
              <h3>No roles found for "{history.company}"</h3>
              <p>No applications or job tracks match this company name.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {history.roles.map((role) => {
                const style = STATUS_COLORS[role.status] || STATUS_COLORS.opened
                return (
                  <div key={role.track_id} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{role.title || role.url}</div>
                      {/^(https?):\/\//i.test(role.url) && <a href={role.url} target="_blank" rel="noopener noreferrer">View job</a>}
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                        {role.ats_group && <span style={{ marginRight: 8 }}>{role.ats_group}</span>}
                        {role.opened_at && <span style={{ marginRight: 8 }}>Opened: {new Date(role.opened_at).toLocaleDateString()}</span>}
                        {role.applied_at && <span style={{ marginRight: 8 }}>Applied: {new Date(role.applied_at).toLocaleDateString()}</span>}
                        {role.follow_up_at && <span>Follow-up: {new Date(role.follow_up_at).toLocaleDateString()}</span>}
                      </div>
                      {role.notes && <div style={{ fontSize: 12, color: '#374151', marginTop: 4, fontStyle: 'italic' }}>{role.notes}</div>}
                    </div>
                    <span style={{ padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: style.bg, color: style.color, textTransform: 'capitalize' }}>
                      {role.status}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {!loading && !history && (
        <div className="empty-state">
          <h3>Select a remembered company</h3>
          <p>Choose a company above to see its saved roles and application dates.</p>
        </div>
      )}
    </div>
  )
}
