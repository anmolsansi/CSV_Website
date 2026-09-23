import { useEffect, useState } from 'react'
import { api, formatApiError } from '../api/client'
import ApplicationWorkspace from '../components/ApplicationWorkspace'

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
  const initialParams = new URLSearchParams(window.location.search)
  const initialCompany = initialParams.get('company') || ''
  const focusTrackId = Number(initialParams.get('track_id') || 0)
  const [company, setCompany] = useState(initialCompany)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [directory, setDirectory] = useState(null)
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [aliases, setAliases] = useState(null)
  const [aliasDraft, setAliasDraft] = useState('')
  const [aliasLoading, setAliasLoading] = useState(false)
  const [aliasPending, setAliasPending] = useState(false)
  const [aliasError, setAliasError] = useState('')
  const [aliasMessage, setAliasMessage] = useState('')
  const [aliasRetry, setAliasRetry] = useState(0)
  const [expandedTrackId, setExpandedTrackId] = useState(focusTrackId || null)

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

  useEffect(() => {
    if (!company) {
      setAliases(null)
      return undefined
    }
    let active = true
    setAliasLoading(true)
    setAliasError('')
    api.getCompanyAliases(company)
      .then((data) => {
        if (active) setAliases(data)
      })
      .catch((requestError) => {
        if (active) {
          setAliasError(formatApiError(requestError, 'Could not load company aliases. Please retry.').message)
        }
      })
      .finally(() => {
        if (active) setAliasLoading(false)
      })
    return () => { active = false }
  }, [company, retry, aliasRetry])

  useEffect(() => {
    if (!history || !focusTrackId) return
    const element = document.getElementById(`application-${focusTrackId}`)
    if (element) {
      element.scrollIntoView({ block: 'center' })
      element.focus({ preventScroll: true })
      setExpandedTrackId(focusTrackId)
    }
  }, [history, focusTrackId])

  const search = () => {
    setQuery(searchInput.trim())
    setPage(1)
    setCompany('')
    setHistory(null)
    setExpandedTrackId(null)
  }
  const handleKeyDown = (e) => { if (e.key === 'Enter') search() }

  const refreshCompanyContext = () => {
    setRetry((value) => value + 1)
    setAliasRetry((value) => value + 1)
  }

  const addAlias = async () => {
    const proposed = aliasDraft.trim()
    if (!company || !proposed || aliasPending) return
    setAliasPending(true)
    setAliasError('')
    setAliasMessage('')
    try {
      const proposedHistory = await api.getCompanyHistory(proposed)
      const currentCount = history?.total || 0
      const proposedCount = proposedHistory?.total || 0
      const confirmed = window.confirm(
        `Group "${proposed}" with "${company}"? This affects company-history grouping for ${currentCount} current and ${proposedCount} proposed-label roles. Applications, statuses, dates, and notes will not be changed.`
      )
      if (!confirmed) return

      const result = await api.createCompanyAlias(company, proposed)
      setAliasDraft('')
      setAliasMessage(
        result.created
          ? `Alias added. ${result.group_history_count} remembered roles are now in this company group.`
          : 'That alias was already in this company group.'
      )
      refreshCompanyContext()
    } catch (requestError) {
      setAliasError(formatApiError(requestError, 'Could not add that alias. Your label is still here so you can retry.').message)
    } finally {
      setAliasPending(false)
    }
  }

  const removeAlias = async (alias) => {
    if (aliasPending) return
    const confirmed = window.confirm(
      `Remove alias "${alias.display_name}"? This changes grouping for ${alias.history_count} remembered roles. Applications and their history will remain unchanged.`
    )
    if (!confirmed) return

    setAliasPending(true)
    setAliasError('')
    setAliasMessage('')
    try {
      await api.deleteCompanyAlias(alias.id)
      setAliasMessage(`Removed alias "${alias.display_name}". Application history was not deleted.`)
      refreshCompanyContext()
    } catch (requestError) {
      setAliasError(formatApiError(requestError, 'Could not remove that alias. Please refresh and retry.').message)
    } finally {
      setAliasPending(false)
    }
  }

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
              <button className="btn btn-grey" key={item.company} onClick={() => { setCompany(item.company); setExpandedTrackId(null) }}>
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

          <section aria-label="Company aliases" style={{ marginBottom: 20, padding: 14, border: '1px solid #e5e7eb', borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Company aliases</h3>
            <p style={{ fontSize: 13, color: '#6b7280' }}>
              Group explicit company-name variants. This changes history grouping only and never merges or deletes applications.
            </p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <label htmlFor="company-alias-input">Alias label</label>
              <input
                id="company-alias-input"
                value={aliasDraft}
                onChange={(event) => setAliasDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') addAlias()
                }}
                placeholder="e.g. Acme Corporation"
                maxLength={320}
                disabled={aliasPending}
                style={{ minWidth: 240, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
              />
              <button className="btn btn-blue" onClick={addAlias} disabled={aliasPending || !aliasDraft.trim()}>
                {aliasPending ? 'Saving…' : 'Add alias'}
              </button>
            </div>
            {aliasLoading && <p role="status">Loading aliases…</p>}
            {aliasMessage && <p role="status">{aliasMessage}</p>}
            {aliasError && (
              <div role="alert">
                {aliasError}{' '}
                <button className="btn btn-grey btn-sm" onClick={() => setAliasRetry((value) => value + 1)}>Refresh aliases</button>
              </div>
            )}
            {aliases && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  Grouped history: {aliases.group_history_count} remembered roles
                </div>
                {(aliases.aliases || [])
                  .filter((alias) => alias.display_name.trim().toLowerCase() !== company.trim().toLowerCase())
                  .map((alias) => (
                    <div key={alias.id} data-testid="company-alias-row" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                      <span><strong>{alias.display_name}</strong> · {alias.history_count} roles</span>
                      <button className="btn btn-grey btn-sm" disabled={aliasPending} onClick={() => removeAlias(alias)}>Remove alias</button>
                    </div>
                  ))}
              </div>
            )}
          </section>

          {history.roles.length === 0 ? (
            <div className="empty-state">
              <h3>No roles found for "{history.company}"</h3>
              <p>No applications or job tracks match this company name.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {history.roles.map((role) => {
                const style = STATUS_COLORS[role.status] || STATUS_COLORS.opened
                const expanded = expandedTrackId === role.track_id
                return (
                  <div key={role.track_id}>
                    <div
                      id={`application-${role.track_id}`}
                      tabIndex={-1}
                      style={{
                        background: '#fff',
                        border: focusTrackId === role.track_id ? '2px solid #2563eb' : '1px solid #e5e7eb',
                        borderRadius: 8,
                        padding: 14,
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: 12,
                        alignItems: 'center',
                      }}
                    >
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
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <span style={{ padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: style.bg, color: style.color, textTransform: 'capitalize' }}>
                          {role.status}
                        </span>
                        <button
                          className="btn btn-grey btn-sm"
                          type="button"
                          aria-expanded={expanded}
                          onClick={() => setExpandedTrackId((current) => current === role.track_id ? null : role.track_id)}
                        >
                          {expanded ? 'Hide people & interviews' : 'People & interviews'}
                        </button>
                      </div>
                    </div>
                    {expanded && (
                      <div style={{ marginTop: 8 }}>
                        <ApplicationWorkspace application={{ id: role.track_id, company: history.company, title: role.title }} />
                      </div>
                    )}
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
