import { test, expect, type Page } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function resetAndLogin(page: Page) {
  await page.request.post(`${API_URL}/test/reset`)
  await page.request.post(`${API_URL}/test/seed`)
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()
  await page.goto('/')
  await expect(page.getByLabel('Upload CSV file')).toBeVisible()
}

async function chooseRenamedCsv(page: Page, suffix: string) {
  await page.getByLabel('Upload CSV file').setInputFiles({
    name: `mapped-${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from(`Link,Role,Company\nhttps://example.test/jobs/${suffix},Platform Engineer,Example ${suffix}\n`),
  })
  await page.getByLabel('Map source column 0 Link').selectOption('url')
  await page.getByLabel('Map source column 1 Role').selectOption('title')
  await page.getByLabel('Map source column 2 Company').selectOption('company_guess')
}

async function review(page: Page) {
  await page.getByRole('button', { name: 'Review import' }).click()
  await expect(page.getByRole('heading', { name: '2. Review changes' })).toBeVisible()
}

test.describe('JG-059 deliberate import mapping', () => {
  test('renamed_headers_preview_commit', async ({ page }) => {
    await resetAndLogin(page)
    await chooseRenamedCsv(page, 'renamed-commit')
    await review(page)

    await expect(page.getByText('Will create').locator('..').locator('td').nth(1)).toHaveText('1')
    await expect(page.getByText('Invalid').locator('..').locator('td').nth(1)).toHaveText('0')

    await page.getByRole('button', { name: 'Commit reviewed import' }).click()
    await expect(page.getByRole('heading', { name: 'Import committed' })).toBeVisible()
    await expect(page.getByText('1 created, 0 updated, 0 skipped, 0 invalid.')).toBeVisible()

    const rows = await page.request.get(`${API_URL}/rows`, { params: { search: 'renamed-commit', page: 1, page_size: 20 } })
    expect(rows.ok()).toBeTruthy()
    const payload = await rows.json()
    expect(payload.rows.some((row: any) => row.data?.url === 'https://example.test/jobs/renamed-commit')).toBeTruthy()
  })

  test('preview_only_no_rows_written', async ({ page }) => {
    await resetAndLogin(page)
    await chooseRenamedCsv(page, 'preview-only')
    await review(page)

    const rows = await page.request.get(`${API_URL}/rows`, { params: { search: 'preview-only', page: 1, page_size: 20 } })
    expect(rows.ok()).toBeTruthy()
    const payload = await rows.json()
    expect(payload.rows.some((row: any) => row.data?.url === 'https://example.test/jobs/preview-only')).toBeFalsy()
  })

  test('explicit_title_update_preserves_user_fields', async ({ page }) => {
    await resetAndLogin(page)
    const url = 'https://example.test/jobs/update-title-only'
    const seed = await page.request.post(`${API_URL}/upload`, {
      multipart: {
        file: {
          name: 'seed.csv',
          mimeType: 'text/csv',
          buffer: Buffer.from(`url,title,company_guess\n${url},Old Title,Example Co\n`),
        },
      },
    })
    expect(seed.ok()).toBeTruthy()

    const beforeRows = await page.request.get(`${API_URL}/rows`, { params: { search: 'update-title-only', page: 1, page_size: 20 } })
    const before = (await beforeRows.json()).rows.find((row: any) => row.data?.url === url)
    expect(before).toBeTruthy()
    const clicked = await page.request.post(`${API_URL}/rows/${before.id}/click`)
    expect(clicked.ok()).toBeTruthy()
    const application = await page.request.post(`${API_URL}/crm/from-row/${before.id}`)
    expect(application.ok()).toBeTruthy()
    const app = await application.json()
    const notePatch = await page.request.patch(`${API_URL}/crm/applications/${app.id}`, {
      data: { notes: 'Keep this private note', status: 'applied' },
    })
    expect(notePatch.ok()).toBeTruthy()

    await page.reload()
    await page.getByLabel('Upload CSV file').setInputFiles({
      name: 'update.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`url,title,company_guess\n${url},New Title,Replacement Co\n`),
    })
    await review(page)
    await page.getByRole('radio', { name: /Update selected source fields/ }).check()
    await page.getByLabel('title', { exact: true }).check()
    await page.getByRole('button', { name: 'Commit reviewed import' }).click()
    await expect(page.getByRole('heading', { name: 'Import committed' })).toBeVisible()

    const afterRows = await page.request.get(`${API_URL}/rows`, { params: { search: 'update-title-only', page: 1, page_size: 20 } })
    const after = (await afterRows.json()).rows.find((row: any) => row.data?.url === url)
    expect(after.data.title).toBe('New Title')
    expect(after.data.company_guess).toBe('Example Co')
    expect(after.clicked).toBe(true)

    const applications = await page.request.get(`${API_URL}/crm/applications`)
    const stored = (await applications.json()).rows.find((row: any) => row.id === app.id)
    expect(stored.notes).toBe('Keep this private note')
    expect(stored.status).toBe('applied')
  })

  test('expired_preview_requires_regenerate', async ({ page }) => {
    await resetAndLogin(page)
    await chooseRenamedCsv(page, 'expired-preview')
    await review(page)

    await page.route('**/crm/imports/*/commit', async (route) => {
      await route.fulfill({
        status: 410,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            code: 'import_preview_expired',
            fields: [{ field: '__root__', message: 'Import preview has expired. Create a new preview.' }],
          },
        }),
      })
    })

    await page.getByRole('button', { name: 'Commit reviewed import' }).click()
    await expect(page.getByRole('alert')).toContainText('Regenerate the preview before committing')
    await expect(page.getByRole('button', { name: 'Regenerate preview' })).toBeVisible()
  })

  test('lost_response_retry_no_duplicates', async ({ page }) => {
    await resetAndLogin(page)
    await chooseRenamedCsv(page, 'lost-response')
    await review(page)

    let attempts = 0
    const keys: string[] = []
    await page.route('**/crm/imports/*/commit', async (route) => {
      attempts += 1
      const payload = route.request().postDataJSON()
      keys.push(payload.idempotency_key)
      if (attempts === 1) {
        await route.fetch()
        await route.abort('failed')
        return
      }
      await route.continue()
    })

    await page.getByRole('button', { name: 'Commit reviewed import' }).click()
    await expect(page.getByRole('alert')).toContainText('Retry Commit')
    await page.getByRole('button', { name: 'Commit reviewed import' }).click()
    await expect(page.getByRole('heading', { name: 'Import committed' })).toBeVisible()

    expect(attempts).toBe(2)
    expect(keys[0]).toBe(keys[1])
    const rows = await page.request.get(`${API_URL}/rows`, { params: { search: 'lost-response', page: 1, page_size: 20 } })
    const payload = await rows.json()
    expect(payload.rows.filter((row: any) => row.data?.url === 'https://example.test/jobs/lost-response')).toHaveLength(1)
  })
})
