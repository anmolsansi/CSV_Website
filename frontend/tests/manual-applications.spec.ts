import { test, expect } from '@playwright/test'

const API_URL = 'http://localhost:8000'

function localDate(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

async function fillApplication(page: import('@playwright/test').Page, url: string, company: string) {
  await page.getByLabel('Job URL').fill(url)
  await page.getByLabel('Company').fill(company)
  await page.getByLabel('Job title').fill('Backend Engineer')
  await page.getByLabel(/Date and time applied/).fill(localDate(new Date(Date.now() - 86400000)))
  await expect(page.getByText('No matching confirmed applications were found')).toBeVisible()
}

test.describe('AL-13–AL-17: explicit manual Add Application', () => {
  test.beforeAll(async ({ request }) => {
    expect((await request.post(`${API_URL}/test/reset`)).ok()).toBeTruthy()
    expect((await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    })).ok()).toBeTruthy()
  })

  test('can review, explicitly confirm and find submission in lifetime history', async ({ page, request }) => {
    await page.goto('/applications?tab=applied')
    await page.getByRole('link', { name: 'Add application' }).click()
    await expect(page).toHaveURL(/\/applications\/new/)
    const url = `https://jobs.example.test/manual-ui/${Date.now()}-one`
    await fillApplication(page, url, 'AL3 Unique Employer One')
    await page.getByRole('button', { name: 'Review application details' }).click()
    await expect(page.getByTestId('manual-apply-review')).toContainText('AL3 Unique Employer One')
    await expect(page.getByTestId('manual-apply-success')).toHaveCount(0)
    await page.getByRole('button', { name: 'Confirm I applied and save' }).click()
    await expect(page.getByTestId('manual-apply-success')).toBeVisible()
    await page.getByRole('link', { name: 'View saved application' }).click()
    await expect(page).toHaveURL(/\/applications\?tab=applied/)
    const listing = await request.get(`${API_URL}/crm/applications`, { params: { applied_only: 'true', q: 'AL3 Unique Employer One' } })
    expect(listing.ok()).toBeTruthy()
    const records = (await listing.json()).rows
    expect(records.some((row: { url: string }) => row.url === url)).toBe(true)
  })

  test('exact URL already applied shows prior history instead of saving again', async ({ page, request }) => {
    const url = `https://jobs.example.test/manual-ui/${Date.now()}-duplicate`
    const posted = await request.post(`${API_URL}/crm/applications`, {
      data: {
        url, company: 'AL3 Duplicate Employer', title: 'Backend Engineer',
        applied_at: new Date(Date.now() - 86400000).toISOString(), confirmed: true,
      },
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    })
    expect(posted.status()).toBe(201)
    await page.goto('/applications/new')
    await page.getByLabel('Job URL').fill(url)
    await page.getByLabel('Company').fill('AL3 Duplicate Employer')
    await page.getByLabel('Job title').fill('Backend Engineer')
    await page.getByLabel(/Date and time applied/).fill(localDate(new Date(Date.now() - 86400000)))
    await expect(page.getByTestId('manual-apply-matches')).toContainText('exact match')
    await page.getByRole('button', { name: 'Review application details' }).click()
    await expect(page.getByRole('alert')).toContainText('already exist')
    await expect(page.getByTestId('manual-apply-review')).toHaveCount(0)
  })

  test('ambiguous response keeps request UUID for deliberate retry', async ({ page }) => {
    const url = `https://jobs.example.test/manual-ui/${Date.now()}-retry`
    await page.goto('/applications/new')
    await fillApplication(page, url, 'AL3 Unique Employer Retry')
    await page.getByRole('button', { name: 'Review application details' }).click()
    const keys: string[] = []
    let failOnce = true
    await page.route('**/crm/applications', async (route) => {
      if (route.request().method() !== 'POST') return route.continue()
      keys.push(route.request().headers()['idempotency-key'])
      if (failOnce) {
        failOnce = false
        await route.fulfill({
          status: 503, contentType: 'application/json',
          body: JSON.stringify({ detail: { code: 'server_error' } }),
        })
        return
      }
      await route.continue()
    })
    await page.getByRole('button', { name: 'Confirm I applied and save' }).click()
    await expect(page.getByText('Save result unknown.', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Retry same save' }).click()
    await expect(page.getByTestId('manual-apply-success')).toBeVisible()
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  test('client rejects missing application date without sending a submission', async ({ page }) => {
    await page.goto('/applications/new')
    const url = `https://jobs.example.test/manual-ui/${Date.now()}-bad-date`
    await page.getByLabel('Job URL').fill(url)
    await page.getByLabel('Company').fill('AL3 Unique Employer Invalid')
    await page.getByLabel('Job title').fill('Backend Engineer')
    await expect(page.getByText('No matching confirmed applications were found')).toBeVisible()
    await page.getByRole('button', { name: 'Review application details' }).click()
    await expect(page.locator('#manual-applied-date + .error-msg')).toContainText('date and time')
    await expect(page.getByTestId('manual-apply-review')).toHaveCount(0)
  })
})
