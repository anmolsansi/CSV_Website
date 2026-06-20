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
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(false)

  const search = async () => {
    if (!company.trim()) return
    setLoading(true)
    try {
      const data = await api.getCompanyHistory(company.trim())
      setHistory(data)
    } catch {
      setHistory(null)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      setCompany(searchInput)
      search()
    }
  }

  useEffect(() => {
    if (company) search()
  }, [company])

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Company History</h2>
          <p>View all roles and status history for a company</p>
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
        <button className="btn btn-blue" onClick={() => { setCompany(searchInput); search() }}>Search</button>
      </div>

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
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{role.title}</div>
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
          <h3>Search for a company</h3>
          <p>Enter a company name above to see all roles and application history.</p>
        </div>
      )}
    </div>
  )
}
