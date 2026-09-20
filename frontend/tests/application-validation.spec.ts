import { test, expect, type Page } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function prepareApplication(page: Page) {
  await page.request.post(`${API_URL}/test/reset`)
  await page.request.post(`${API_URL}/test/seed`)
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()

  const rowsResponse = await page.request.get(`${API_URL}/rows`, {
    params: { sort_by: 'created_at', sort_dir: 'desc', page: 1, page_size: 1 },
  })
  expect(rowsResponse.ok()).toBeTruthy()
  const rows = (await rowsResponse.json()).rows || []
  expect(rows.length).toBeGreaterThan(0)

  const create = await page.request.post(`${API_URL}/crm/from-row/${rows[0].id}`)
  expect(create.ok()).toBeTruthy()
  const application = await create.json()

  const applied = await page.request.patch(`${API_URL}/crm/applications/${application.id}`, {
    data: { status: 'applied' },
  })
  expect(applied.ok()).toBeTruthy()
  return await applied.json()
}

async function openImport(page: Page) {
  await page.request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  await page.goto('/import')
  await expect(page.getByRole('heading', { name: 'Import External Applications' })).toBeVisible()
}

function validImportRows(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    url: `https://example.test/jobs/jg017-${index + 1}`,
    company: `JG017 Company ${index + 1}`,
    title: 'Software Engineer',
    status: 'opened',
  }))
}

test.describe('JG-017 application validation feedback', () => {
  test('application-validation.spec.ts: invalid date has visible field message and preserves persisted value', async ({ page }) => {
    const application = await prepareApplication(page)

    await page.goto('/applications')
    const row = page.locator('tbody tr').first()
    await expect(row).toBeVisible()

    const appliedInput = row.locator('input[type="datetime-local"]').first()
    const persistedValue = await appliedInput.inputValue()
    expect(persistedValue).not.toBe('')

    await appliedInput.fill('')
    await appliedInput.press('Enter')

    const fieldError = row.getByRole('alert').filter({ hasText: 'Applied date cannot be cleared' })
    await expect(fieldError).toBeVisible()
    await expect(appliedInput).toBeFocused()
    await expect(appliedInput).toHaveValue('')

    const storedResponse = await page.request.get(`${API_URL}/crm/applications`)
    expect(storedResponse.ok()).toBeTruthy()
    const storedRows = (await storedResponse.json()).rows || []
    const stored = storedRows.find((item: any) => item.id === application.id)
    expect(stored?.status).toBe('applied')
    expect(stored?.applied_at).toBeTruthy()

    await page.reload()
    const reloadedAppliedInput = page.locator('tbody tr').first().locator('input[type="datetime-local"]').first()
    await expect(reloadedAppliedInput).toHaveValue(persistedValue)
  })

  test('file_reader_and_network_failure: failures are recoverable without unhandled rejection', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))

    await page.addInitScript(() => {
      const originalText = File.prototype.text
      File.prototype.text = function () {
        if (this.name === 'reader-fail.json') {
          return Promise.reject(new Error('synthetic file read failure'))
        }
        return originalText.call(this)
      }
    })

    await openImport(page)
    const fileInput = page.locator('input[type="file"]')
    const importButton = page.getByRole('button', { name: 'Import Applications' })

    await fileInput.setInputFiles({
      name: 'reader-fail.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(validImportRows(1))),
    })

    await expect(page.getByRole('alert')).toContainText('synthetic file read failure')
    await expect(importButton).toBeDisabled()
    expect(pageErrors).toEqual([])

    await page.route('**/crm/import/external', (route) => route.abort('failed'))
    await fileInput.setInputFiles({
      name: 'network-fail.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(validImportRows(2))),
    })

    await expect(page.getByText('Preview (2 of 2 rows):')).toBeVisible()
    await expect(importButton).toBeEnabled()
    await importButton.click()

    await expect(page.getByRole('alert')).toContainText('Network error')
    await expect(page.getByText('Preview (2 of 2 rows):')).toBeVisible()
    await expect(importButton).toBeEnabled()
    expect(pageErrors).toEqual([])
  })

  test('pending_request_button_disabled', async ({ page }) => {
    await openImport(page)

    let releaseRequest: (() => void) | undefined
    const requestGate = new Promise<void>((resolve) => { releaseRequest = resolve })

    await page.route('**/crm/import/external', async (route) => {
      await requestGate
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ created: 1, skipped: 0 }),
      })
    })

    const fileInput = page.locator('input[type="file"]')
    const importButton = page.getByRole('button', { name: 'Import Applications' })

    await fileInput.setInputFiles({
      name: 'pending.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(validImportRows(1))),
    })
    await expect(importButton).toBeEnabled()

    await importButton.click()
    await expect(page.getByRole('button', { name: 'Importing...' })).toBeDisabled()

    releaseRequest?.()

    await expect(page.getByText('Imported 1 applications')).toBeVisible()
    await expect(importButton).toBeEnabled()
  })

  test('preview_10_of_25_and_invalid_replacement_file', async ({ page }) => {
    await openImport(page)

    const fileInput = page.locator('input[type="file"]')
    const importButton = page.getByRole('button', { name: 'Import Applications' })

    await fileInput.setInputFiles({
      name: 'twenty-five.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(validImportRows(25))),
    })

    await expect(page.getByText('Preview (10 of 25 rows):')).toBeVisible()
    await expect(page.locator('tbody tr')).toHaveCount(10)
    await expect(importButton).toBeEnabled()

    await fileInput.setInputFiles({
      name: 'invalid-replacement.json',
      mimeType: 'application/json',
      buffer: Buffer.from('{"applications": ['),
    })

    await expect(page.getByRole('alert')).toContainText('Invalid JSON file')
    await expect(page.getByText('Preview (10 of 25 rows):')).toHaveCount(0)
    await expect(page.locator('table')).toHaveCount(0)
    await expect(importButton).toBeDisabled()
  })

  test('company draft submits with Enter and refreshes from persisted server state', async ({ page }) => {
    const application = await prepareApplication(page)
    const company = `JG017 Enter ${Date.now()}`

    await page.goto('/applications')
    const row = page.locator('tbody tr').first()
    const companyInput = row.locator('input.inline-input')

    await companyInput.fill(company)
    await companyInput.press('Enter')

    await expect(companyInput).toHaveValue(company)

    await expect.poll(async () => {
      const response = await page.request.get(`${API_URL}/crm/applications`)
      const rows = (await response.json()).rows || []
      return rows.find((item: any) => item.id === application.id)?.company
    }).toBe(company)

    await page.reload()
    await expect(page.locator('tbody tr').first().locator('input.inline-input')).toHaveValue(company)
  })
})
