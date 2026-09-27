import { randomUUID } from 'node:crypto'
import { test, expect, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function resetAndLogin(request: APIRequestContext) {
  const reset = await request.post(`${API_URL}/test/reset`)
  expect(reset.ok()).toBeTruthy()
  const seeded = await request.post(`${API_URL}/test/seed`)
  expect(seeded.ok()).toBeTruthy()
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()
}

async function createApplication(request: APIRequestContext) {
  const rows = await request.get(`${API_URL}/rows`, {
    params: { page: 1, page_size: 1, sort_by: 'created_at', sort_dir: 'asc' },
  })
  expect(rows.ok()).toBeTruthy()
  const row = (await rows.json()).rows[0]
  expect(row).toBeTruthy()

  const created = await request.post(`${API_URL}/crm/from-row/${row.id}`)
  expect(created.ok()).toBeTruthy()
  return await created.json()
}

function localHour(date: Date, timeZone: string) {
  const hour = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date).find((part) => part.type === 'hour')?.value
  return Number(hour)
}

function safeTestTimezone(now = new Date()) {
  const candidates = [
    'Pacific/Honolulu',
    'America/Los_Angeles',
    'America/Chicago',
    'America/New_York',
    'Europe/London',
    'Europe/Berlin',
    'Asia/Kolkata',
    'Asia/Singapore',
    'Asia/Tokyo',
    'Australia/Sydney',
  ]
  return candidates.find((zone) => {
    const hour = localHour(now, zone)
    return Number.isFinite(hour) && hour >= 7 && hour <= 18
  }) || 'UTC'
}

async function createInterview(
  request: APIRequestContext,
  trackId: number,
  startsAt: Date,
  timezone: string,
  label: string,
) {
  const response = await request.post(`${API_URL}/crm/tracks/${trackId}/interviews`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      starts_at: startsAt.toISOString(),
      ends_at: new Date(startsAt.getTime() + 45 * 60 * 1000).toISOString(),
      timezone,
      kind: 'video',
      round_label: label,
    },
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
}

test('mixed Today Load more reaches every interview page and keeps navigation working', async ({ page, request }) => {
  await resetAndLogin(request)
  const application = await createApplication(request)
  const timezone = safeTestTimezone()

  const timezoneResponse = await request.patch(`${API_URL}/crm/profile/timezone`, {
    data: { timezone },
  })
  expect(timezoneResponse.ok()).toBeTruthy()

  const now = Date.now()
  for (const [offsetHours, label] of [[1, 'C04 First'], [2, 'C04 Second'], [3, 'C04 Third']] as const) {
    await createInterview(
      request,
      application.id,
      new Date(now + offsetHours * 60 * 60 * 1000),
      timezone,
      label,
    )
  }

  // Keep the production UI and real backend response path. Only reduce the
  // requested page size so this browser fixture can exercise continuation
  // without manufacturing more than 100 records.
  await page.route('**/crm/today**', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (route.request().method() === 'GET' && requestUrl.pathname === '/crm/today') {
      requestUrl.searchParams.set('limit', '2')
      await route.continue({ url: requestUrl.toString() })
      return
    }
    await route.continue()
  })

  await page.goto('/today')

  const interviewRows = page.locator('tr').filter({ hasText: 'Interview preparation' })
  await expect(interviewRows).toHaveCount(2, { timeout: 15000 })
  await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible()

  const dueTodayCard = page.locator('.stat-card').filter({ hasText: 'Due today' })
  await expect(dueTodayCard).toContainText('3')

  await page.getByRole('button', { name: 'Load more' }).click()
  await expect(interviewRows).toHaveCount(3, { timeout: 15000 })
  await expect(page.getByRole('button', { name: 'Load more' })).toHaveCount(0)
  await expect(dueTodayCard).toContainText('3')

  await interviewRows.first().getByRole('button', { name: 'Open details' }).click()
  await expect(page).toHaveURL(new RegExp(`/applications\\?track_id=${application.id}$`))
})
