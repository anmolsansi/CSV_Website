import { useRef, useState } from 'react'
import { api } from '../api/client'

function downloadInvalidRows(csvContent, filename) {
  if (!csvContent) return
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `invalid_rows_${filename}`
  a.click()
  URL.revokeObjectURL(url)
}

function UploadResult({ result }) {
  const [expanded, setExpanded] = useState(false)

  const hasIssues =
    result.duplicate_in_upload > 0 ||
    result.duplicate_from_history > 0 ||
    result.rows_missing_url > 0 ||
    result.missing_expected_columns.length > 0

  return (
    <div className="upload-result" role="region" aria-label="Upload result details">
      <div className="upload-result-header">
        <strong>{result.filename}</strong>
        <span className="upload-result-summary">
          {result.inserted} inserted
          {result.duplicate_in_upload > 0 && (
            <span className="upload-dup">{result.duplicate_in_upload} dup in file</span>
          )}
          {result.duplicate_from_history > 0 && (
            <span className="upload-dup">{result.duplicate_from_history} already existed</span>
          )}
          {result.rows_missing_url > 0 && (
            <span className="upload-warn">{result.rows_missing_url} missing URL</span>
          )}
        </span>
        <button
          className="btn btn-grey btn-sm"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          {expanded ? 'Less' : 'Details'}
        </button>
      </div>

      {expanded && (
        <div className="upload-result-details">
          <table className="upload-detail-table">
            <tbody>
              <tr><td>Batch ID</td><td className="mono">{result.batch_id.slice(0, 8)}...</td></tr>
              <tr><td>Total rows received</td><td>{result.total_rows_received}</td></tr>
              <tr><td>Unique URLs received</td><td>{result.unique_urls_received}</td></tr>
              <tr><td>Inserted</td><td className="positive">{result.inserted}</td></tr>
              <tr><td>Duplicates in same upload</td><td>{result.duplicate_in_upload}</td></tr>
              <tr><td>Duplicates from history</td><td>{result.duplicate_from_history}</td></tr>
              <tr><td>Rows skipped (URL missing)</td><td className={result.rows_missing_url > 0 ? 'negative' : ''}>{result.rows_missing_url}</td></tr>
              <tr><td>Columns detected</td><td>{result.columns_detected.length}</td></tr>
              {result.missing_expected_columns.length > 0 && (
                <tr>
                  <td>Missing expected columns</td>
                  <td className="negative">{result.missing_expected_columns.join(', ')}</td>
                </tr>
              )}
              {result.unknown_extra_columns.length > 0 && (
                <tr>
                  <td>Unknown extra columns</td>
                  <td className="muted">{result.unknown_extra_columns.join(', ')}</td>
                </tr>
              )}
            </tbody>
          </table>
          {result.invalid_rows_csv && (
            <button
              className="btn btn-grey btn-sm"
              onClick={() => downloadInvalidRows(result.invalid_rows_csv, result.filename)}
            >
              Download skipped rows as CSV
            </button>
          )}
        </div>
      )}

      {!expanded && hasIssues && (
        <span className="upload-result-hint">Click Details for breakdown</span>
      )}
    </div>
  )
}

export default function CsvUpload({ onUploaded }) {
  const inputRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const handleChange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setResult(null)
    setError('')
    try {
      const res = await api.uploadCsv(file)
      setResult(res)
      onUploaded()
    } catch (err) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'object' && detail?.error) {
        setError(detail.error)
      } else {
        setError(typeof detail === 'string' ? detail : 'Upload failed')
      }
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="csv-upload">
      <div className="csv-upload-input">
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          onChange={handleChange}
          disabled={uploading}
          aria-label="Upload CSV file"
        />
        {uploading && (
          <span className="upload-spinner" role="progressbar" aria-label="Uploading file">
            Uploading...
          </span>
        )}
      </div>
      {error && <div className="upload-error" role="alert">{error}</div>}
      {result && (
        <div aria-live="polite">
          <UploadResult result={result} />
        </div>
      )}
    </div>
  )
}
