import { useRef, useState } from 'react'
import { api, formatApiError } from '../api/client'
import { useToast } from '../App'

function extractImportItems(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.applications)) return data.applications
  if (data && Array.isArray(data.rows)) return data.rows
  throw new Error('JSON must be an array or contain an applications/rows array.')
}

export default function ImportExternal() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [parsedItems, setParsedItems] = useState(null)
  const [rowCount, setRowCount] = useState(0)
  const [reading, setReading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [fileError, setFileError] = useState('')
  const [importError, setImportError] = useState(null)
  const inputRef = useRef()
  const fileSelectionRef = useRef(0)
  const toast = useToast()

  const handleFile = async (e) => {
    const f = e.target.files?.[0] || null
    const selectionId = ++fileSelectionRef.current

    setFile(f)
    setPreview(null)
    setParsedItems(null)
    setRowCount(0)
    setResult(null)
    setFileError('')
    setImportError(null)

    if (!f) return

    setReading(true)
    try {
      const text = await f.text()
      if (selectionId !== fileSelectionRef.current) return
      const items = extractImportItems(JSON.parse(text))
      setParsedItems(items)
      setRowCount(items.length)
      setPreview(items.slice(0, 10))
    } catch (error) {
      if (selectionId !== fileSelectionRef.current) return
      setParsedItems(null)
      setPreview(null)
      setRowCount(0)
      const message = error instanceof SyntaxError
        ? 'Invalid JSON file. Choose a valid JSON export and try again.'
        : (error?.message || 'Could not read this file. Choose another file and try again.')
      setFileError(message)
      toast(message, 'error')
    } finally {
      if (selectionId === fileSelectionRef.current) setReading(false)
    }
  }

  const handleImport = async () => {
    if (!parsedItems || parsedItems.length === 0 || importing || reading) return

    setImporting(true)
    setResult(null)
    setImportError(null)
    try {
      const res = await api.importExternalApplications(parsedItems)
      setResult(res)
      toast(`Imported ${res.created} applications`, 'success')
    } catch (error) {
      const formatted = formatApiError(error, 'Import failed. Correct the highlighted data and retry.')
      setImportError(formatted)
      toast(formatted.message, 'error')
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
          <button className="btn btn-blue" type="button" onClick={() => inputRef.current?.click()} disabled={reading || importing}>
            {reading ? 'Reading...' : 'Choose JSON file'}
          </button>
          {file && <span style={{ fontSize: 13, color: '#374151' }}>{file.name}</span>}
        </div>

        {fileError && <p className="error-msg" role="alert">{fileError}</p>}

        {preview && (
          <div style={{ marginBottom: 16 }}>
            {rowCount === 0 ? (
              <p role="status">No application rows were found in this file.</p>
            ) : (
              <>
                <h4 style={{ fontSize: 13, marginBottom: 8 }}>Preview ({preview.length} of {rowCount} rows):</h4>
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
              </>
            )}
          </div>
        )}

        {importError && (
          <div className="error-msg" role="alert">
            {importError.fields.length === 1 ? (
              importError.fields[0].message
            ) : (
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {importError.fields.map((item, index) => (
                  <li key={`${item.field}-${index}`}>
                    {item.field !== 'non_field' ? `${item.field}: ` : ''}{item.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className="btn btn-green"
            type="button"
            onClick={handleImport}
            disabled={!parsedItems || parsedItems.length === 0 || importing || reading}
          >
            {importing ? 'Importing...' : 'Import Applications'}
          </button>
          {result && <span style={{ fontSize: 13, color: '#16a34a', fontWeight: 600 }}>Imported {result.created} applications</span>}
        </div>
      </div>
    </div>
  )
}
