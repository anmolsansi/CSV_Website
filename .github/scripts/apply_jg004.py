from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    target.write_text(text.replace(old, new, 1))


client_old = """  // CRM - Backup
  exportBackup: () => client.get('/crm/backup/export', { responseType: 'blob' }),
  importBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import', fd).then((r) => r.data)
  },
"""
client_new = """  // CRM - Backup
  exportBackup: () => client.get('/crm/backup/export', { responseType: 'blob' }),
  exportBackupV2: () => client.get('/crm/backup/export', { params: { version: '2' }, responseType: 'blob' }),
  previewBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import?mode=verify_only', fd).then((r) => r.data)
  },
  restoreBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import?mode=merge_missing', fd).then((r) => r.data)
  },
  importBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import', fd).then((r) => r.data)
  },
"""
replace_once('frontend/src/api/client.js', client_old, client_new)

component = r'''import { useMemo, useRef, useState } from 'react'
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
            {values.created} create · {values.skipped} skip · {values.conflicts} conflict
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

  const exportV2 = async () => {
    if (busy) return
    setExporting(true)
    try {
      const response = await api.exportBackupV2()
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `jobgrid_backup_v2_${new Date().toISOString().slice(0, 10)}.json`
      anchor.click()
      URL.revokeObjectURL(url)
      toast?.('Complete v2 backup exported', 'success')
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
      <button className="btn btn-grey" type="button" onClick={exportV2} disabled={busy}>
        {exporting ? 'Exporting backup…' : 'Export complete backup'}
      </button>
      <label className="btn btn-grey" style={{ cursor: busy ? 'not-allowed' : 'pointer' }}>
        Restore backup file
        <input
          ref={inputRef}
          data-testid="backup-file-input"
          type="file"
          accept="application/json,.json"
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
'''
Path('frontend/src/components/BackupRestore.jsx').write_text(component)

dashboard_import = "import RowDrawer from '../components/RowDrawer'\n"
replace_once('frontend/src/pages/Dashboard.jsx', dashboard_import, dashboard_import + "import BackupRestore from '../components/BackupRestore'\n")

backup_handler = """  const handleBackupExport = async () => {
    try {
      const res = await api.exportBackup()
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `jobgrid_backup_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('Backup exported', 'success')
    } catch {
      toast('Export failed', 'error')
    }
  }

"""
replace_once('frontend/src/pages/Dashboard.jsx', backup_handler, '')

backup_button = """          <button className=\"btn btn-grey\" onClick={handleBackupExport}>Export Backup</button>
          <span style={{ borderLeft: '1px solid #d1d5db', height: 20, margin: '0 4px' }} />
"""
backup_controls = """          <BackupRestore onRestored={() => loadRows(sort, filters, 1)} toast={toast} />
          <span style={{ borderLeft: '1px solid #d1d5db', height: 20, margin: '0 4px' }} />
"""
replace_once('frontend/src/pages/Dashboard.jsx', backup_button, backup_controls)

spec = r'''import { test, expect } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function selectBackup(page: any, content: string | Buffer, name = 'backup.json') {
  await page.getByTestId('backup-file-input').setInputFiles({
    name,
    mimeType: 'application/json',
    buffer: Buffer.isBuffer(content) ? content : Buffer.from(content),
  })
}

test('invalid backup shows validation failure and no restore action', async ({ page }) => {
  await page.goto('/')
  await selectBackup(page, '{"version":')
  await expect(page.getByRole('alert')).toContainText('Backup could not be verified')
  await expect(page.getByRole('button', { name: 'Restore backup', exact: true })).toHaveCount(0)
})

test('legacy backup warning never claims omitted history is restored', async ({ page }) => {
  await page.route('**/crm/backup/import?mode=verify_only', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      backup_id: 'legacy-test',
      mode: 'verify_only',
      verified: true,
      counts: { csv_rows: { created: 1, skipped: 0, conflicts: 0 } },
      warnings: [{ code: 'incomplete_legacy_backup' }, { code: 'legacy_section_absent', section: 'url_history' }],
    }),
  }))
  await page.goto('/')
  await selectBackup(page, JSON.stringify({ version: '1.0', csv_rows: [] }), 'legacy.json')
  await expect(page.getByText('Legacy backup warning.', { exact: false })).toBeVisible()
  await expect(page.getByText(/cannot be reconstructed or described as restored/i)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Restore backup', exact: true })).toBeVisible()
})

test('restore failure keeps the selected file and allows retry', async ({ page }) => {
  let restoreAttempts = 0
  await page.route('**/crm/backup/import?mode=verify_only', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      backup_id: 'retry-test', mode: 'verify_only', verified: true,
      counts: { job_tracks: { created: 1, skipped: 0, conflicts: 0 } }, warnings: [],
    }),
  }))
  await page.route('**/crm/backup/import?mode=merge_missing', route => {
    restoreAttempts += 1
    if (restoreAttempts === 1) {
      return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'restore_failed', message: 'Injected restore failure.' } }) })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backup_id: 'retry-test', mode: 'merge_missing', verified: true,
        counts: { job_tracks: { created: 1, skipped: 0, conflicts: 0 } }, warnings: [],
      }),
    })
  })

  await page.goto('/')
  await selectBackup(page, '{}', 'retry.json')
  await page.getByRole('button', { name: 'Restore backup', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Injected restore failure')
  await expect(page.getByText('retry.json', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Retry restore', exact: true }).click()
  await expect(page.getByText('Restore completed.', { exact: false })).toBeVisible()
  expect(restoreAttempts).toBe(2)
})

test('v2 restore recovers an applied job and company after reload', async ({ page, context }) => {
  const suffix = Date.now()
  const sourceEmail = `jg004-source-${suffix}@jobgrid.dev`
  const destinationEmail = `jg004-destination-${suffix}@jobgrid.dev`
  const company = `Recoverable Company ${suffix}`
  const url = `https://example.test/jg004/${suffix}`

  const sourceLogin = await context.request.post(`${API_URL}/auth/dev-login`, { data: { email: sourceEmail } })
  expect(sourceLogin.ok()).toBeTruthy()
  const csv = `url,title,company_guess\n${url},Recoverable Engineer,${company}\n`
  const upload = await context.request.post(`${API_URL}/upload`, {
    multipart: { file: { name: 'jg004.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) } },
  })
  expect(upload.ok()).toBeTruthy()
  const sourceRows = await context.request.get(`${API_URL}/rows`, { params: { q: company, page_size: 10 } })
  expect(sourceRows.ok()).toBeTruthy()
  const row = (await sourceRows.json()).rows[0]
  const applied = await context.request.post(`${API_URL}/crm/from-rows/bulk`, { data: { row_ids: [row.id], status: 'applied' } })
  expect(applied.ok()).toBeTruthy()

  const backupResponse = await context.request.get(`${API_URL}/crm/backup/export?version=2`)
  expect(backupResponse.ok()).toBeTruthy()
  const backupBuffer = await backupResponse.body()

  const destinationLogin = await context.request.post(`${API_URL}/auth/dev-login`, { data: { email: destinationEmail } })
  expect(destinationLogin.ok()).toBeTruthy()
  await page.goto('/')
  await selectBackup(page, backupBuffer, 'roundtrip-v2.json')
  await expect(page.getByRole('button', { name: 'Restore backup', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Restore backup', exact: true }).click()
  await expect(page.getByText('Restore completed.', { exact: false })).toBeVisible()

  await page.reload()
  const restoredApps = await context.request.get(`${API_URL}/crm/applications`, { params: { q: company } })
  expect(restoredApps.ok()).toBeTruthy()
  const appRows = (await restoredApps.json()).rows
  expect(appRows).toHaveLength(1)
  expect(appRows[0].company).toBe(company)
  expect(appRows[0].status).toBe('applied')
  expect(appRows[0].applied_at).toBeTruthy()

  await page.goto('/companies')
  await expect(page.getByRole('button', { name: `${company} · 1 jobs · 1 applied`, exact: true })).toBeVisible()
  await page.getByRole('button', { name: `${company} · 1 jobs · 1 applied`, exact: true }).click()
  await expect(page.getByText(/^Applied:/)).toBeVisible()
})
'''
Path('frontend/tests/backup-restore.spec.ts').write_text(spec)

readme_anchor = """## Open top 5 unopened
"""
readme_section = """## Portable backup and restore

The Dashboard keeps ordinary CSV/JSON data export separate from portable account backup.
Use **Export complete backup** to download the v2 backup that includes all nine durable
backup sections. To restore, choose **Restore backup file**. JobGrid uploads the file for
`verify_only` preflight first and shows section-level create/skip/conflict counts plus safe
warning codes. Nothing is written until you click **Restore backup**.

Restore uses `merge_missing`: missing records are created, but an existing destination
record wins on a natural-key conflict and is not overwritten by older backup values. A
failed restore keeps the selected browser file so you can retry. A successful restore
refreshes Dashboard data and can download a summary containing only backup metadata,
counts, and warning codes, not job descriptions, notes, or other private records.

V1 files remain accepted for compatibility, but they are incomplete. The UI explicitly
warns that omitted history, dates, relationships, and sections cannot be reconstructed or
described as restored. The selected file is held only in browser memory for the current
page session. Portable backup is separate from database disaster-recovery scripts under
`scripts/backup.sh` and `scripts/restore.sh`.

"""
replace_once('README.md', readme_anchor, readme_section + readme_anchor)

build_old = """- JG-004 still owns the dedicated restore preview/interface. JG-003 does not claim that UI as shipped.
"""
build_new = """- JG-004 adds the dedicated restore preview/interface on the Dashboard, using this backend contract without changing restore semantics.
"""
replace_once('docs/JOBGRID_BUILD_GUIDE.md', build_old, build_new)

build_anchor = """## Why v2 exists
"""
build_section = """## JG-004 restore interface

`frontend/src/components/BackupRestore.jsx` owns the portable-backup UI and
`frontend/src/api/client.js` owns its transport calls. The Dashboard keeps ordinary data
export separate from backup actions.

The UI flow is deliberate:

1. **Export complete backup** requests `GET /crm/backup/export?version=2`.
2. Choosing a JSON file immediately calls `POST /crm/backup/import?mode=verify_only`.
3. Parse/schema/checksum errors are shown as failures and no Restore button is rendered.
4. A verified preview shows section `created`/`skipped`/`conflicts` counts, merge policy,
   and safe warning codes. Legacy warnings state that missing history cannot be recovered.
5. The separate **Restore backup** action calls `mode=merge_missing`; duplicate clicks are
   disabled while the request is active.
6. A failed import keeps the selected file and verified preview so **Retry restore** is
   possible. HTTP failure never renders a completed state.
7. Successful restore refreshes Dashboard rows. If refresh fails, restore success remains
   truthful and the UI asks the user to reload rather than implying the transaction failed.
8. **Download restore summary** emits only `backup_id`, mode, verified flag, section counts,
   timestamp, and warning codes/sections. It never embeds restored records or private text.

The browser holds the selected `File` object only in component memory. Choosing a different
file clears stale preview/result state. Reloading or clearing the file discards it.

Focused interface verification:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/backup-restore.spec.ts --project=chromium
```

`backup-restore.spec.ts` covers invalid-file gating, explicit legacy limitations,
retry-after-import-failure with selection preserved, and a real v2 applied-job round trip
that verifies company/status/date after reload. The existing application-memory regression
remains part of the affected browser suite.

"""
replace_once('docs/JOBGRID_BUILD_GUIDE.md', build_anchor, build_section + build_anchor)

print('JG-004 implementation files patched successfully')
