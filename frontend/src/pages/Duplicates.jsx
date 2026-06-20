import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

const REASON_LABELS = {
  same_url: { label: 'Same URL', color: '#dc2626' },
  same_canonical_key: { label: 'Same canonical key', color: '#d97706' },
  same_company_title: { label: 'Same company + title', color: '#2563eb' },
  same_job_id: { label: 'Same job ID', color: '#7c3aed' },
  unknown: { label: 'Unknown', color: '#6b7280' },
}

export default function Duplicates() {
  const [dupes, setDupes] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedPrimary, setSelectedPrimary] = useState(null)
  const [selectedDupes, setSelectedDupes] = useState(new Set())
  const toast = useToast()

  const load = () => {
    setLoading(true)
    api.getDuplicates().then(setDupes).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const toggleSelect = (id) => {
    setSelectedDupes((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const resolve = async (rowId, action) => {
    await api.resolveDuplicate(rowId, action)
    toast(`Resolved as ${action}`, 'success')
    load()
  }

  const mergeToPrimary = async () => {
    if (!selectedPrimary || selectedDupes.size === 0) return
    await api.mergeDuplicates(selectedPrimary, [...selectedDupes])
    toast(`Merged ${selectedDupes.size} duplicates`, 'success')
    setSelectedPrimary(null)
    setSelectedDupes(new Set())
    load()
  }

  const grouped = {}
  dupes.forEach((d) => {
    const key = d.reason || 'unknown'
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(d)
  })

  if (loading) return <div className="container"><div className="empty-state"><div className="loading-spinner" /><p>Loading duplicates...</p></div></div>

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Duplicates Review</h2>
          <p>{dupes.length} duplicate(s) detected across all uploads</p>
        </div>
        {selectedPrimary && selectedDupes.size > 0 && (
          <button className="btn btn-blue" onClick={mergeToPrimary}>
            Merge {selectedDupes.size} into selected primary
          </button>
        )}
      </div>

      {dupes.length === 0 ? (
        <div className="empty-state">
          <h3>No duplicates found</h3>
          <p>All your job listings appear unique.</p>
        </div>
      ) : (
        Object.entries(grouped).map(([reason, items]) => {
          const meta = REASON_LABELS[reason] || REASON_LABELS.unknown
          return (
            <div key={reason} style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 14, color: meta.color, marginBottom: 8 }}>
                {meta.label} ({items.length})
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {items.map((d) => (
                  <div key={d.id} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{d.company || 'Unknown'} — {d.title || 'Untitled'}</div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                        <a href={d.url} target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>{d.url}</a>
                      </div>
                      {d.original_url && (
                        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                          Original: {d.original_company} — <a href={d.original_url} target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>{d.original_url}</a>
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <input type="radio" name={`primary-${d.id}`} checked={selectedPrimary === d.id} onChange={() => setSelectedPrimary(d.id)} />
                        Primary
                      </label>
                      <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <input type="checkbox" checked={selectedDupes.has(d.id)} onChange={() => toggleSelect(d.id)} />
                        Select
                      </label>
                      <button className="btn btn-grey btn-sm" onClick={() => resolve(d.id, 'keep_both')}>Keep both</button>
                      <button className="btn btn-grey btn-sm" onClick={() => resolve(d.id, 'mark_duplicate')}>Mark dup</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
