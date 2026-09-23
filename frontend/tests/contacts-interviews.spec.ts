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
  const initial = await created.json()
  const company = `F8 Browser ${randomUUID().slice(0, 8)}`
  const updated = await request.patch(`${API_URL}/crm/applications/${initial.id}`, {
    data: { company },
  })
  expect(updated.ok()).toBeTruthy()
  return await updated.json()
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

async function createContactAndInterviews(request: APIRequestContext, trackId: number) {
  const timezone = safeTestTimezone()
  const timezoneResponse = await request.patch(`${API_URL}/crm/profile/timezone`, {
    data: { timezone },
  })
  expect(timezoneResponse.ok()).toBeTruthy()

  const contactResponse = await request.post(`${API_URL}/crm/contacts`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      name: 'Casey Recruiter',
      email: 'casey.recruiter@example.test',
      company_display: 'F8 Recruiting',
      notes: 'Private referral context',
    },
  })
  expect(contactResponse.ok()).toBeTruthy()
  const contact = await contactResponse.json()

  const link = await request.post(`${API_URL}/crm/tracks/${trackId}/contacts`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      contact_id: contact.id,
      role: 'recruiter',
      referral_source: 'Warm introduction',
    },
  })
  expect(link.ok()).toBeTruthy()

  const now = Date.now()
  const startsAt = new Date(now + 2 * 60 * 60 * 1000)
  const endsAt = new Date(now + 3 * 60 * 60 * 1000)
  const firstResponse = await request.post(`${API_URL}/crm/tracks/${trackId}/interviews`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      contact_id: contact.id,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      timezone,
      kind: 'video',
      meeting_url: 'https://meet.example.test/f8-round',
      round_label: 'Technical',
      preparation_notes: 'Review system design tradeoffs',
      notes: 'Private interview note',
    },
  })
  expect(firstResponse.ok()).toBeTruthy()
  const first = await firstResponse.json()

  const overlappingResponse = await request.post(`${API_URL}/crm/tracks/${trackId}/interviews`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      contact_id: contact.id,
      starts_at: new Date(now + 2.5 * 60 * 60 * 1000).toISOString(),
      ends_at: new Date(now + 3.5 * 60 * 60 * 1000).toISOString(),
      timezone,
      kind: 'video',
      round_label: 'Panel',
    },
  })
  expect(overlappingResponse.ok()).toBeTruthy()
  const overlapping = await overlappingResponse.json()
  expect(overlapping.overlap_interview_ids).toContain(first.id)

  return { contact, first, overlapping, timezone }
}

test.describe('JG-055 people and interview workspace', () => {
  test('people_interviews_company_history_calendar_and_today', async ({ page, request }) => {
    await resetAndLogin(request)
    const application = await createApplication(request)
    const { first, timezone } = await createContactAndInterviews(request, application.id)

    await page.goto(`/applications?track_id=${application.id}`)
    const workspace = page.getByTestId('application-f8-workspace')
    await expect(workspace).toBeVisible({ timeout: 15000 })

    const people = workspace.getByTestId('application-people')
    await expect(people.getByText('Casey Recruiter', { exact: true })).toBeVisible()
    await expect(people.getByText('casey.recruiter@example.test', { exact: true })).toBeVisible()
    await expect(people.getByText('Source: Warm introduction', { exact: true })).toBeVisible()

    const interviews = workspace.getByTestId('application-interviews')
    await expect(interviews.getByText('Technical', { exact: true })).toBeVisible()
    await expect(interviews.getByText('Panel', { exact: true })).toBeVisible()
    await expect(interviews.getByText(`(${timezone})`, { exact: false }).first()).toBeVisible()
    await expect(interviews.getByText(/Warning: overlaps 1 other scheduled interview/).first()).toBeVisible()
    await expect(interviews.getByText('Prep: Review system design tradeoffs', { exact: true })).toBeVisible()

    const firstRow = interviews.getByTestId(`application-interview-${first.id}`)
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      firstRow.getByRole('button', { name: 'Download calendar event' }).click(),
    ])
    expect(download.suggestedFilename()).toBe(`jobgrid_interview_${first.id}.ics`)
    await expect(page.getByText('Calendar file downloaded. No invitation was sent.', { exact: true })).toBeVisible()

    await page.goto(`/companies?company=${encodeURIComponent(application.company)}&track_id=${application.id}`)
    const companyWorkspace = page.getByTestId('application-f8-workspace')
    await expect(companyWorkspace).toBeVisible({ timeout: 15000 })
    await expect(companyWorkspace.getByText('Casey Recruiter', { exact: true })).toBeVisible()
    await expect(companyWorkspace.getByText('Technical', { exact: true })).toBeVisible()

    await page.goto('/today')
    const prepRow = page.locator('tr').filter({ hasText: 'Prepare for Technical interview' })
    await expect(prepRow).toBeVisible({ timeout: 15000 })
    await expect(prepRow.getByText('Interview preparation', { exact: true })).toBeVisible()
    await expect(prepRow.getByRole('button', { name: 'Snooze' })).toBeVisible()
    await expect(prepRow.getByRole('button', { name: 'Complete' })).toHaveCount(0)

    await prepRow.getByRole('button', { name: 'Open details' }).click()
    await expect(page).toHaveURL(new RegExp(`/applications\\?track_id=${application.id}$`))
    await expect(page.getByTestId('application-f8-workspace')).toBeVisible({ timeout: 15000 })
  })
})
