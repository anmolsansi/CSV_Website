import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'

const PANEL_STYLE = {
  flexBasis: '100%',
  borderTop: '1px solid #e5e7eb',
  marginTop: 4,
  paddingTop: 12,
  display: 'grid',
  gap: 10,
}

const SUMMARY_STYLE = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
  gap: 8,
}

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail?.message) return detail.message
  if (detail?.code) return String(detail.code).replaceAll('_', ' ')
  return fallback
}

function isLegacyWarning(warning) {
  return warning?.code === 'incomplete_legacy_backup' || warning?.code === 'legacy_section_absent'
}

function sanitizeWarnings(warnings = []) {
  return warnings.map((warning) => ({
    code: warning?.code || 'warning',
    ...(warning?.section ? { section: warning.section } : {}),
  }))
}

function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function CountGrid({ counts }) {
  const entries = Object.entries(counts || {})
  if (!entries.length) return null

  return (
    <div style={SUMMARY_STYLE} aria-label="Restore section counts">
      {entries.map(([section, values]) => (
        <div key={section} style={{ border: '1px solid #e5e7eb', borderRadius: 6, padding: 8 }}>
          <strong style={{ display: 'block', fontSize: 12 }}>{section.replaceAll('_', ' ')}</strong>
          <span style={{ fontSize: 12, color: '#4b5563' }}>
            {values.created ?? 0} create · {values.skipped ?? values.existing ?? 0} skip · {values.conflicts ?? 0} conflict
          </span>
        </div>
      ))}
    </div>
  )
}

export default function BackupRestore({ onRestored, toast }) {
  const inputRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [status, setStatus] = useState('idle')
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [failedPhase, setFailedPhase] = useState(null)
  const [refreshWarning, setRefreshWarning] = useState(false)
  const [exporting, setExporting] = useState(false)

  const current = result || preview
  const warnings = current?.warnings || []
  const hasLegacyWarning = useMemo(() => warnings.some(isLegacyWarning), [warnings])
  const busy = status === 'validating' || status === 'restoring' || exporting

  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setResult(null)
    setError('')
    setFailedPhase(null)
    setRefreshWarning(false)
    setStatus('idle')
    if (inputRef.current) inputRef.current.value = ''
  }

  const exportV2 = async (bundle = true) => {
    if (busy) return
    setExporting(true)
    try {
      const response = await (bundle ? api.exportBackupBundle() : api.exportBackupV2())
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `jobgrid_backup_v2_${new Date().toISOString().slice(0, 10)}.${bundle ? 'zip' : 'json'}`
      anchor.click()
      URL.revokeObjectURL(url)
      toast?.(bundle ? 'Complete backup exported: records and files' : 'Records exported; document files are excluded', 'success')
    } catch (exportError) {
      toast?.(getErrorMessage(exportError, 'Could not export the backup. Please retry.'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const chooseFile = async (event) => {
    const file = event.target.files?.[0] || null
    setSelectedFile(file)
    setPreview(null)
    setResult(null)
    setError('')
    setFailedPhase(null)
    setRefreshWarning(false)
    if (!file) {
      setStatus('idle')
      return
    }

    setStatus('validating')
    try {
      const nextPreview = await api.previewBackup(file)
      if (!nextPreview?.verified) throw new Error('Backup verification did not complete.')
      setPreview(nextPreview)
      setStatus('ready')
    } catch (previewError) {
      setError(getErrorMessage(previewError, previewError?.message || 'Backup validation failed. Choose a valid backup file and retry.'))
      setFailedPhase('verify')
      setStatus('error')
    }
  }

  const restore = async () => {
    if (!selectedFile || !preview || status === 'restoring') return
    setError('')
    setFailedPhase(null)
    setRefreshWarning(false)
    setStatus('restoring')
    try {
      const nextResult = await api.restoreBackup(selectedFile)
      setResult(nextResult)
      setStatus('completed')
      toast?.('Backup restore completed', 'success')
      if (onRestored) {
        try {
          await onRestored(nextResult)
        } catch {
          setRefreshWarning(true)
          toast?.('Restore completed, but the Dashboard could not refresh. Reload the page to see restored data.', 'warning')
        }
      }
    } catch (restoreError) {
      setError(getErrorMessage(restoreError, 'Restore failed. No success was recorded. You can retry with the selected file.'))
      setFailedPhase('restore')
      setStatus('error')
    }
  }

  const downloadSummary = () => {
    if (!result) return
    downloadJson(`jobgrid_restore_summary_${new Date().toISOString().slice(0, 10)}.json`, {
      generated_at: new Date().toISOString(),
      backup_id: result.backup_id,
      mode: result.mode,
      verified: result.verified,
      counts: result.counts,
      warnings: sanitizeWarnings(result.warnings),
    })
  }

  return (
    <>
      <button className="btn btn-grey" type="button" onClick={() => exportV2(true)} disabled={busy}>
        {exporting ? 'Exporting backup…' : 'Export complete backup'}
      </button>
      <button className="btn btn-grey" type="button" onClick={() => exportV2(false)} disabled={busy}>
        Export records only (no files)
      </button>
      <label className="btn btn-grey" style={{ cursor: busy ? 'not-allowed' : 'pointer' }}>
        Restore backup file
        <input
          ref={inputRef}
          data-testid="backup-file-input"
          type="file"
          accept="application/json,application/zip,.json,.zip"
          onChange={chooseFile}
          disabled={busy}
          style={{ display: 'none' }}
        />
      </label>

      {selectedFile && (
        <section style={PANEL_STYLE} aria-label="Backup restore preview">
          <div>
            <strong>{selectedFile.name}</strong>
            <span style={{ marginLeft: 8, color: '#6b7280', fontSize: 12 }}>
              {(selectedFile.size / 1024).toFixed(1)} KB · kept only in this browser session
            </span>
          </div>

          {status === 'validating' && <div role="status">Uploading and validating backup. Nothing is being restored yet.</div>}
          {status === 'restoring' && <div role="status">Restoring missing records in one transaction…</div>}

          {status === 'error' && (
            <div role="alert" style={{ color: '#991b1b' }}>
              <strong>{failedPhase === 'verify' ? 'Backup could not be verified.' : 'Restore failed.'}</strong> {error}
            </div>
          )}

          {preview && (
            <>
              <div role="note">
                {current?.document_bytes_included
                  ? 'ZIP backup includes document files.'
                  : 'Records-only backup: document files are not included.'}
              </div>
              <div style={{ fontSize: 13 }}>
                <strong>Merge policy:</strong> JobGrid creates missing records only. Existing destination records win on conflicts and are not overwritten.
              </div>
              <CountGrid counts={current?.counts} />

              {hasLegacyWarning && (
                <div role="alert" style={{ border: '1px solid #f59e0b', borderRadius: 6, padding: 8, background: '#fffbeb' }}>
                  <strong>Legacy backup warning.</strong> This file does not contain complete history. Missing dates, relationships, visit history, and omitted sections cannot be reconstructed or described as restored.
                </div>
              )}

              {warnings.length > 0 && (
                <div>
                  <strong>Warnings ({warnings.length})</strong>
                  <ul style={{ margin: '4px 0 0 18px' }}>
                    {warnings.map((warning, index) => (
                      <li key={`${warning.code}-${warning.section || 'general'}-${index}`}>
                        {warning.code}{warning.section ? ` · ${warning.section}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {status === 'ready' && (
            <button className="btn btn-green" type="button" onClick={restore}>
              Restore backup
            </button>
          )}
          {status === 'restoring' && <button className="btn btn-green" type="button" disabled>Restoring…</button>}
          {status === 'error' && failedPhase === 'restore' && preview && (
            <button className="btn btn-green" type="button" onClick={restore}>Retry restore</button>
          )}

          {status === 'completed' && (
            <div role="status" style={{ color: warnings.length ? '#92400e' : '#166534' }}>
              <strong>{warnings.length ? 'Restore completed with warnings.' : 'Restore completed.'}</strong> Restored data was committed and the Dashboard refresh was requested.
            </div>
          )}
          {refreshWarning && <div role="alert">Reload the page to refresh restored rows.</div>}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {result && <button className="btn btn-grey" type="button" onClick={downloadSummary}>Download restore summary</button>}
            {!busy && <button className="btn btn-grey" type="button" onClick={clearSelection}>Clear file</button>}
          </div>
        </section>
      )}
    </>
  )
}
