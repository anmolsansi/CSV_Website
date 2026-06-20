import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

export default function ApplyPilotBatches() {
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [importFile, setImportFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const toast = useToast()

  const refresh = () => {
    setLoading(true)
    api.getApplyPilotBatches()
      .then(setBatches)
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const downloadBatch = async (batch) => {
    try {
      const res = await api.downloadApplyPilotBatch(batch.id)
      const blob = new Blob([res.data], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${batch.name || 'batch'}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('Batch downloaded', 'success')
    } catch {
      toast('Download failed', 'error')
    }
  }

  const deleteBatch = async (id) => {
    if (!window.confirm('Delete this batch?')) return
    await api.deleteApplyPilotBatch(id)
    refresh()
  }

  const handleImport = async () => {
    if (!importFile) return
    setImporting(true)
    try {
      const text = await importFile.text()
      const results = JSON.parse(text)
      const result = await api.importApplyPilotResults(results)
      toast(`Imported: ${result.updated} applications updated`, 'success')
      setImportFile(null)
      refresh()
    } catch (err) {
      toast(`Import failed: ${err.message}`, 'error')
    } finally {
      setImporting(false)
    }
  }

  const statusColors = {
    downloaded: { bg: '#dbeafe', color: '#1e40af' },
    sent: { bg: '#fef3c7', color: '#92400e' },
    completed: { bg: '#d1fae5', color: '#065f46' },
    failed: { bg: '#fee2e2', color: '#991b1b' },
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>ApplyPilot Batches</h2>
          <p>Track job application batches sent to ApplyPilot.</p>
        </div>
      </div>

      <div className="table-controls">
        <div>
          <label>Import results</label>
          <input type="file" accept=".json" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
        </div>
        <div>
          <button className="btn btn-blue" onClick={handleImport} disabled={!importFile || importing}>
            {importing ? 'Importing...' : 'Import Results'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" />
          <p>Loading batches...</p>
        </div>
      ) : batches.length === 0 ? (
        <div className="empty-state">
          <h3>No batches yet</h3>
          <p>Select jobs on the Dashboard and click "Send to ApplyPilot" to create your first batch.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Created</th><th>Jobs</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {batches.map((b) => {
                const style = statusColors[b.status] || statusColors.downloaded
                return (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td>{new Date(b.created_at).toLocaleString()}</td>
                    <td>{b.job_count}</td>
                    <td><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600, background: style.bg, color: style.color }}>{b.status}</span></td>
                    <td>
                      <button className="btn btn-blue" style={{ padding: '4px 8px', fontSize: 12, marginRight: 4 }} onClick={() => downloadBatch(b)}>Download</button>
                      <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => deleteBatch(b.id)}>Delete</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
