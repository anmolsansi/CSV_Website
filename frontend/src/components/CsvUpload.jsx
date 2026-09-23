import { useRef, useState } from 'react'
import { api } from '../api/client'
import { defaultImportMapping, readImportHeaders } from '../api/imports'
import ImportPreview from './ImportPreview'

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

function ClassicUploadResult({ result }) {
  const [expanded, setExpanded] = useState(false)
  const missingOptionalColumns = result.missing_optional_columns || result.missing_expected_columns || []
  const missingRequiredColumns = result.missing_required_columns || []
  const unknownExtraColumns = result.unknown_extra_columns || []

  return (
    <div className="upload-result" role="region" aria-label="Classic upload result details">
      <div className="upload-result-header">
        <strong>{result.filename}</strong>
        <span className="upload-result-summary">{result.inserted} inserted</span>
        <button type="button" className="btn btn-grey btn-sm" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
          {expanded ? 'Less' : 'Details'}
        </button>
      </div>
      {expanded && (
        <div className="upload-result-details">
          <table className="upload-detail-table">
            <tbody>
              <tr><td>Total rows received</td><td>{result.total_rows_received}</td></tr>
              <tr><td>Inserted</td><td className="positive">{result.inserted}</td></tr>
              <tr><td>Duplicates in same upload</td><td>{result.duplicate_in_upload}</td></tr>
              <tr><td>Duplicates from history</td><td>{result.duplicate_from_history}</td></tr>
              <tr><td>Rows skipped (URL missing)</td><td>{result.rows_missing_url}</td></tr>
              {missingRequiredColumns.length > 0 && <tr><td>Missing required columns</td><td className="negative">{missingRequiredColumns.join(', ')}</td></tr>}
              {missingOptionalColumns.length > 0 && <tr><td>Optional columns not included</td><td>{missingOptionalColumns.join(', ')}</td></tr>}
              {unknownExtraColumns.length > 0 && <tr><td>Unknown extra columns</td><td>{unknownExtraColumns.join(', ')}</td></tr>}
            </tbody>
          </table>
          {result.invalid_rows_csv && (
            <button type="button" className="btn btn-grey btn-sm" onClick={() => downloadInvalidRows(result.invalid_rows_csv, result.filename)}>
              Download skipped rows as CSV
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default function CsvUpload({ onUploaded }) {
  const inputRef = useRef()
  const [file, setFile] = useState(null)
  const [headers, setHeaders] = useState([])
  const [mapping, setMapping] = useState({})
  const [preparing, setPreparing] = useState(false)
  const [classicUploading, setClassicUploading] = useState(false)
  const [classicResult, setClassicResult] = useState(null)
  const [error, setError] = useState('')

  const reset = () => {
    setFile(null)
    setHeaders([])
    setMapping({})
    setClassicResult(null)
    setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleChange = async (event) => {
    const nextFile = event.target.files?.[0]
    if (!nextFile) return
    setPreparing(true)
    setClassicResult(null)
    setError('')
    try {
      const nextHeaders = await readImportHeaders(nextFile)
      setFile(nextFile)
      setHeaders(nextHeaders)
      setMapping(defaultImportMapping(nextHeaders))
    } catch (readError) {
      setFile(null)
      setHeaders([])
      setMapping({})
      setError(readError.message || 'Import file could not be read.')
      if (inputRef.current) inputRef.current.value = ''
    } finally {
      setPreparing(false)
    }
  }

  const useClassicImport = async () => {
    if (!file || !file.name.toLowerCase().endsWith('.csv')) return
    setClassicUploading(true)
    setError('')
    try {
      const result = await api.uploadCsv(file)
      setClassicResult(result)
      setFile(null)
      setHeaders([])
      setMapping({})
      if (inputRef.current) inputRef.current.value = ''
      onUploaded()
    } catch (requestError) {
      const detail = requestError.response?.data?.detail
      if (typeof detail === 'object' && detail?.error) setError(detail.error)
      else setError(typeof detail === 'string' ? detail : 'Classic upload failed')
    } finally {
      setClassicUploading(false)
    }
  }

  return (
    <div className="csv-upload">
      {!file && (
        <div className="csv-upload-input">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.json"
            onChange={handleChange}
            disabled={preparing || classicUploading}
            aria-label="Upload CSV file"
          />
          {preparing && <span className="upload-spinner" role="progressbar" aria-label="Reading import headers">Reading headers…</span>}
          <a className="btn btn-grey btn-sm upload-template-link" href="/jobgrid_sample.csv" download>Download CSV template</a>
        </div>
      )}

      {error && <div className="upload-error" role="alert">{error}</div>}

      {file && (
        <>
          <ImportPreview
            file={file}
            headers={headers}
            initialMapping={mapping}
            onCancel={reset}
            onCommitted={() => onUploaded()}
          />
          {file.name.toLowerCase().endsWith('.csv') && (
            <div className="upload-result-hint">
              Need the previous behavior while the mapped importer is being rolled out?{' '}
              <button type="button" className="btn btn-grey btn-sm" onClick={useClassicImport} disabled={classicUploading}>
                {classicUploading ? 'Uploading…' : 'Use classic CSV import'}
              </button>
            </div>
          )}
        </>
      )}

      {classicResult && <ClassicUploadResult result={classicResult} />}
    </div>
  )
}
