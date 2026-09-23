import { useMemo, useRef, useState } from 'react'
import {
  IMPORT_TARGET_FIELDS,
  commitImportPreview,
  createImportCommitKey,
  createImportPreview,
  downloadRejectedImportRows,
  importError,
} from '../api/imports'

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function ErrorSummary({ errors }) {
  if (!errors?.length) return null
  return (
    <div className="upload-result-details" role="region" aria-label="Import error summary">
      <strong>Preview errors</strong>
      <ul>
        {errors.slice(0, 20).map((item, index) => (
          <li key={`${item.row}-${item.column}-${item.code}-${index}`}>
            Row {item.row}, {item.column}: {item.code}
          </li>
        ))}
      </ul>
      {errors.length > 20 && <p className="muted">Showing the first 20 errors. Download rejected rows for source values.</p>}
    </div>
  )
}

export default function ImportPreview({ file, headers, initialMapping, onCancel, onCommitted }) {
  const [mapping, setMapping] = useState(initialMapping)
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const [regenerateRequired, setRegenerateRequired] = useState(false)
  const [commitResult, setCommitResult] = useState(null)
  const [mode, setMode] = useState('insert_only')
  const [invalidPolicy, setInvalidPolicy] = useState('reject')
  const [possibleDuplicatePolicy, setPossibleDuplicatePolicy] = useState('skip')
  const [replaceEmpty, setReplaceEmpty] = useState(false)
  const [updateFields, setUpdateFields] = useState([])
  const commitKeyRef = useRef(createImportCommitKey())

  const mappedTargets = useMemo(() => Object.values(mapping), [mapping])
  const unmappedCount = headers.length - Object.keys(mapping).length
  const urlMapped = mappedTargets.includes('url')
  const updateCandidates = useMemo(
    () => [...new Set(mappedTargets.filter((field) => field !== 'url'))],
    [mappedTargets],
  )

  const expectedCounts = useMemo(() => {
    const counts = preview?.counts || {}
    const exact = counts.exact_duplicate || 0
    const possible = counts.possible_duplicate || 0
    return {
      create: (counts.create || 0) + (possibleDuplicatePolicy === 'create' ? possible : 0),
      update: mode === 'update_selected' ? exact : 0,
      skip:
        (mode === 'update_selected' ? 0 : exact) +
        (possibleDuplicatePolicy === 'create' ? 0 : possible),
      invalid: counts.invalid || 0,
    }
  }, [preview, mode, possibleDuplicatePolicy])

  const resetPreview = () => {
    setPreview(null)
    setCommitResult(null)
    setRegenerateRequired(false)
    setError('')
    commitKeyRef.current = createImportCommitKey()
  }

  const changeMapping = (index, target) => {
    setMapping((current) => {
      const next = { ...current }
      if (target) next[String(index)] = target
      else delete next[String(index)]
      return next
    })
    resetPreview()
  }

  const generatePreview = async () => {
    if (!urlMapped) {
      setError('Map exactly one source column to the required url field before previewing.')
      return
    }
    setPreviewing(true)
    setError('')
    setRegenerateRequired(false)
    try {
      const next = await createImportPreview(file, mapping)
      setPreview(next)
      setCommitResult(null)
      commitKeyRef.current = createImportCommitKey()
    } catch (requestError) {
      setError(importError(requestError, 'Preview could not be generated.').message)
    } finally {
      setPreviewing(false)
    }
  }

  const toggleUpdateField = (field) => {
    setUpdateFields((current) => (
      current.includes(field) ? current.filter((item) => item !== field) : [...current, field]
    ))
  }

  const commit = async () => {
    if (!preview || regenerateRequired || commitResult) return
    if (invalidPolicy === 'reject' && expectedCounts.invalid > 0) {
      setError('This preview contains invalid rows. Review the report, then deliberately choose Skip invalid rows to continue.')
      return
    }
    if (mode === 'update_selected' && updateFields.length === 0) {
      setError('Choose at least one mapped field to update, or use insert-only mode.')
      return
    }

    setCommitting(true)
    setError('')
    try {
      const result = await commitImportPreview(preview.preview_id, {
        version: preview.version,
        idempotency_key: commitKeyRef.current,
        mode,
        update_fields: mode === 'update_selected' ? updateFields : [],
        invalid_policy: invalidPolicy,
        replace_empty: mode === 'update_selected' ? replaceEmpty : false,
        possible_duplicate_policy: possibleDuplicatePolicy,
      })
      setCommitResult(result)
      onCommitted(result)
    } catch (requestError) {
      const parsed = importError(requestError, 'Commit could not be completed.')
      const status = requestError?.response?.status
      if (
        status === 410 ||
        ['import_preview_expired', 'commit_result_expired', 'destination_changed', 'preview_changed', 'version_conflict']
          .includes(parsed.code)
      ) {
        setRegenerateRequired(true)
        setError(`${parsed.message} Regenerate the preview before committing.`)
      } else if (!requestError?.response) {
        setError('The commit response was lost. Retry Commit to safely replay the same request without creating duplicates.')
      } else {
        setError(parsed.message)
      }
    } finally {
      setCommitting(false)
    }
  }

  const downloadRejected = async () => {
    if (!preview) return
    setDownloading(true)
    setError('')
    try {
      const response = await downloadRejectedImportRows(preview.preview_id)
      saveBlob(response.data, `${file.name.replace(/\.[^.]+$/, '') || 'import'}_rejected.csv`)
    } catch (requestError) {
      const parsed = importError(requestError, 'Rejected rows could not be downloaded.')
      if (requestError?.response?.status === 410) setRegenerateRequired(true)
      setError(parsed.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="upload-result" role="region" aria-label="Import mapping and preview">
      <div className="upload-result-header">
        <strong>{file.name}</strong>
        <span className="upload-result-summary">Map → Review → Commit</span>
        <button type="button" className="btn btn-grey btn-sm" onClick={onCancel} disabled={previewing || committing}>
          Choose another file
        </button>
      </div>

      {error && <div className="upload-error" role="alert">{error}</div>}

      <section aria-labelledby="import-map-heading">
        <h4 id="import-map-heading">1. Map columns</h4>
        <p className="muted">Source labels are shown with their zero-based position. The URL target is required.</p>
        <div className="table-scroll">
          <table className="upload-detail-table">
            <thead>
              <tr><th>Source</th><th>JobGrid field</th></tr>
            </thead>
            <tbody>
              {headers.map((label, index) => {
                const selected = mapping[String(index)] || ''
                const usedElsewhere = new Set(
                  Object.entries(mapping)
                    .filter(([sourceIndex]) => sourceIndex !== String(index))
                    .map(([, target]) => target),
                )
                return (
                  <tr key={`${index}-${label}`}>
                    <td>#{index} {label || '(blank label)'}</td>
                    <td>
                      <label className="sr-only" htmlFor={`import-map-${index}`}>Map source column {index} {label}</label>
                      <select
                        id={`import-map-${index}`}
                        value={selected}
                        onChange={(event) => changeMapping(index, event.target.value)}
                        disabled={previewing || committing}
                      >
                        <option value="">Do not import</option>
                        {IMPORT_TARGET_FIELDS.map((field) => (
                          <option key={field} value={field} disabled={usedElsewhere.has(field)}>{field}{field === 'url' ? ' (required)' : ''}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {unmappedCount > 0 && <p className="upload-result-hint">{unmappedCount} source column{unmappedCount === 1 ? '' : 's'} will be ignored.</p>}
        {!urlMapped && <p className="upload-error">A source column must map to <code>url</code>.</p>}
        <button type="button" className="btn btn-primary btn-sm" onClick={generatePreview} disabled={!urlMapped || previewing || committing}>
          {previewing ? 'Generating preview…' : preview ? 'Review changes again' : 'Review import'}
        </button>
      </section>

      {preview && (
        <section aria-labelledby="import-review-heading">
          <h4 id="import-review-heading">2. Review changes</h4>
          <p className="muted">Previewing does not create or update destination rows.</p>
          <table className="upload-detail-table">
            <tbody>
              <tr><td>Will create</td><td className="positive">{expectedCounts.create}</td></tr>
              <tr><td>Update candidates</td><td>{expectedCounts.update}</td></tr>
              <tr><td>Will skip</td><td>{expectedCounts.skip}</td></tr>
              <tr><td>Invalid</td><td className={expectedCounts.invalid ? 'negative' : ''}>{expectedCounts.invalid}</td></tr>
              <tr><td>Preview expires</td><td>{new Date(preview.expires_at).toLocaleString()}</td></tr>
            </tbody>
          </table>
          <ErrorSummary errors={preview.errors} />
          {expectedCounts.invalid > 0 && (
            <button type="button" className="btn btn-grey btn-sm" onClick={downloadRejected} disabled={downloading}>
              {downloading ? 'Preparing rejected rows…' : 'Download rejected rows'}
            </button>
          )}

          <fieldset disabled={committing || Boolean(commitResult)}>
            <legend>Commit behavior</legend>
            <label>
              <input type="radio" name="import-mode" value="insert_only" checked={mode === 'insert_only'} onChange={() => { setMode('insert_only'); setUpdateFields([]); setReplaceEmpty(false) }} />
              Insert only. Never update an existing exact URL.
            </label>
            <label>
              <input type="radio" name="import-mode" value="update_selected" checked={mode === 'update_selected'} onChange={() => setMode('update_selected')} />
              Update selected source fields on exact URL matches.
            </label>

            {mode === 'update_selected' && (
              <div>
                <p><strong>Fields allowed to update</strong></p>
                {updateCandidates.length === 0 ? (
                  <p className="muted">Map at least one field besides URL to enable updates.</p>
                ) : updateCandidates.map((field) => (
                  <label key={field}>
                    <input type="checkbox" checked={updateFields.includes(field)} onChange={() => toggleUpdateField(field)} /> {field}
                  </label>
                ))}
                <label>
                  <input type="checkbox" checked={replaceEmpty} onChange={(event) => setReplaceEmpty(event.target.checked)} />
                  Deliberately replace selected fields with empty values from the import.
                </label>
              </div>
            )}

            <label htmlFor="invalid-policy">Invalid rows</label>
            <select id="invalid-policy" value={invalidPolicy} onChange={(event) => setInvalidPolicy(event.target.value)}>
              <option value="reject">Reject the entire commit (default)</option>
              <option value="skip">Skip invalid rows after review</option>
            </select>

            <label htmlFor="possible-duplicate-policy">Possible duplicates</label>
            <select id="possible-duplicate-policy" value={possibleDuplicatePolicy} onChange={(event) => setPossibleDuplicatePolicy(event.target.value)}>
              <option value="skip">Skip possible duplicates (default)</option>
              <option value="create">Create them as new rows</option>
            </select>
          </fieldset>

          {regenerateRequired ? (
            <button type="button" className="btn btn-primary btn-sm" onClick={generatePreview} disabled={previewing}>
              {previewing ? 'Regenerating…' : 'Regenerate preview'}
            </button>
          ) : !commitResult ? (
            <button type="button" className="btn btn-primary btn-sm" onClick={commit} disabled={committing || (mode === 'update_selected' && updateFields.length === 0)}>
              {committing ? 'Committing…' : 'Commit reviewed import'}
            </button>
          ) : null}
        </section>
      )}

      {commitResult && (
        <section aria-live="polite" aria-label="Import commit result">
          <h4>Import committed</h4>
          <p>
            {commitResult.counts.created} created, {commitResult.counts.updated} updated, {commitResult.counts.skipped} skipped, {commitResult.counts.invalid} invalid.
          </p>
        </section>
      )}
    </div>
  )
}
