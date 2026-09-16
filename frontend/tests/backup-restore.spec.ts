import { test, expect } from '@playwright/test'

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

  const applicationsRefresh = page.waitForResponse(response =>
    response.request().method() === 'GET' && response.url().includes('/crm/applications?')
  )
  const companiesRefresh = page.waitForResponse(response =>
    response.request().method() === 'GET' && response.url().includes('/crm/companies?')
  )
  await page.getByRole('button', { name: 'Retry restore', exact: true }).click()
  const [applicationsResponse, companiesResponse] = await Promise.all([applicationsRefresh, companiesRefresh])
  expect(applicationsResponse.ok()).toBeTruthy()
  expect(companiesResponse.ok()).toBeTruthy()
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
