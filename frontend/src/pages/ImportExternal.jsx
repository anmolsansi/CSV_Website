import { useState, useRef } from 'react'
import { api } from '../api/client'
import { useToast } from '../App'

export default function ImportExternal() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef()
  const toast = useToast()

  const handleFile = (e) => {
    const f = e.target.files[0]
    if (!f) return
    setFile(f)
    setResult(null)
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result)
        const items = Array.isArray(data) ? data : data.applications || data.rows || []
        setPreview(items.slice(0, 10))
      } catch {
        toast('Invalid JSON file', 'error')
      }
    }
    reader.readAsText(f)
  }

  const handleImport = async () => {
    if (!file) return
    setImporting(true)
    try {
      const reader = new FileReader()
      reader.onload = async (ev) => {
        const data = JSON.parse(ev.target.result)
        const items = Array.isArray(data) ? data : data.applications || data.rows || []
        const res = await api.importExternalApplications(items)
        setResult(res)
        toast(`Imported ${res.created} applications`, 'success')
      }
      reader.readAsText(file)
    } catch (err) {
      toast('Import failed: ' + err.message, 'error')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="container">
      <div className="page-header-row">
        <div>
          <h2>Import External Applications</h2>
          <p>Import applications from JSON files (e.g., from another tool or spreadsheet export)</p>
        </div>
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 14, color: '#374151', marginBottom: 8 }}>
            Expected format: JSON array with objects containing <code>url</code>, <code>company</code>, <code>title</code>, <code>status</code>, <code>applied_at</code>, <code>follow_up_at</code>, <code>notes</code>.
          </p>
          <pre style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6, padding: 12, fontSize: 12, overflow: 'auto', maxHeight: 200 }}>
{`[
  {
    "url": "https://company.com/careers/role-123",
    "company": "Acme Corp",
    "title": "Software Engineer",
    "status": "applied",
    "applied_at": "2026-06-01",
    "notes": "Applied via referral"
  }
]`}
          </pre>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
          <input ref={inputRef} type="file" accept=".json" onChange={handleFile} style={{ display: 'none' }} />
          <button className="btn btn-blue" onClick={() => inputRef.current?.click()}>Choose JSON file</button>
          {file && <span style={{ fontSize: 13, color: '#374151' }}>{file.name}</span>}
        </div>

        {preview && (
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ fontSize: 13, marginBottom: 8 }}>Preview ({preview.length} of {preview.length} rows):</h4>
            <div style={{ overflow: 'auto', maxHeight: 300 }}>
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th>Company</th><th>Title</th><th>Status</th><th>Applied</th><th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((item, i) => (
                    <tr key={i}>
                      <td>{item.company || '-'}</td>
                      <td>{item.title || '-'}</td>
                      <td>{item.status || 'opened'}</td>
                      <td>{item.applied_at || '-'}</td>
                      <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.url || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn btn-green" onClick={handleImport} disabled={!file || importing}>
            {importing ? 'Importing...' : 'Import Applications'}
          </button>
          {result && <span style={{ fontSize: 13, color: '#16a34a', fontWeight: 600 }}>Imported {result.created} applications</span>}
        </div>
      </div>
    </div>
  )
}
