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

async function createApplication(request: APIRequestContext, rowPage = 1) {
  const rows = await request.get(`${API_URL}/rows`, {
    params: { page: rowPage, page_size: 1, sort_by: 'created_at', sort_dir: 'asc' },
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

async function createContact(request: APIRequestContext) {
  const response = await request.post(`${API_URL}/crm/contacts`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      name: 'Casey Recruiter',
      email: 'casey.recruiter@example.test',
      company_display: 'F8 Recruiting',
      notes: 'Private referral context',
    },
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
}

async function linkRecruiter(request: APIRequestContext, trackId: number, contactId: number) {
  const response = await request.post(`${API_URL}/crm/tracks/${trackId}/contacts`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      contact_id: contactId,
      role: 'recruiter',
      referral_source: 'Warm introduction',
    },
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
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

async function createInterviewFixture(request: APIRequestContext, trackId: number) {
  const timezone = safeTestTimezone()
  const timezoneResponse = await request.patch(`${API_URL}/crm/profile/timezone`, {
    data: { timezone },
  })
  expect(timezoneResponse.ok()).toBeTruthy()

  const contact = await createContact(request)
  await linkRecruiter(request, trackId, contact.id)

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

async function restoreTimezone(request: APIRequestContext) {
  const restored = await request.patch(`${API_URL}/crm/profile/timezone`, {
    data: { timezone: 'UTC' },
  })
  expect(restored.ok()).toBeTruthy()
  const profile = await request.get(`${API_URL}/crm/profile/timezone`)
  expect(profile.ok()).toBeTruthy()
  expect((await profile.json()).timezone).toBe('UTC')
}

test.describe('JG-055 people and interview workspace', () => {
  test('recruiter_reused_across_applications', async ({ page, request }) => {
    await resetAndLogin(request)

    const firstApplication = await createApplication(request, 1)
    const secondApplication = await createApplication(request, 2)
    expect(secondApplication.id).not.toBe(firstApplication.id)

    const contact = await createContact(request)
    const firstLink = await linkRecruiter(request, firstApplication.id, contact.id)
    const secondLink = await linkRecruiter(request, secondApplication.id, contact.id)

    expect(firstLink.contact.id).toBe(contact.id)
    expect(secondLink.contact.id).toBe(contact.id)
    expect(secondLink.id).not.toBe(firstLink.id)

    await page.goto(`/applications?track_id=${firstApplication.id}`)
    const firstWorkspace = page.getByTestId('application-f8-workspace')
    await expect(firstWorkspace).toBeVisible({ timeout: 15000 })
    const firstPerson = firstWorkspace.getByTestId(`application-person-${firstLink.id}`)
    await expect(firstPerson.getByText('Casey Recruiter', { exact: true })).toBeVisible()
    await expect(firstPerson.getByText('casey.recruiter@example.test', { exact: true })).toBeVisible()

    await page.goto(`/applications?track_id=${secondApplication.id}`)
    const secondWorkspace = page.getByTestId('application-f8-workspace')
    await expect(secondWorkspace).toBeVisible({ timeout: 15000 })
    const secondPerson = secondWorkspace.getByTestId(`application-person-${secondLink.id}`)
    await expect(secondPerson.getByText('Casey Recruiter', { exact: true })).toBeVisible()
    await expect(secondPerson.getByText('Source: Warm introduction', { exact: true })).toBeVisible()

    await page.goto(`/companies?company=${encodeURIComponent(firstApplication.company)}&track_id=${firstApplication.id}`)
    const companyWorkspace = page.getByTestId('application-f8-workspace')
    await expect(companyWorkspace).toBeVisible({ timeout: 15000 })
    await expect(companyWorkspace.getByTestId(`application-person-${firstLink.id}`).getByText('Casey Recruiter', { exact: true })).toBeVisible()
  })

  test('interview_timezone_preview_matches_server', async ({ page, request }) => {
    await resetAndLogin(request)
    const application = await createApplication(request)

    await page.goto(`/applications?track_id=${application.id}`)
    const interviews = page.getByTestId('application-interviews')
    await expect(interviews).toBeVisible({ timeout: 15000 })

    await interviews.getByLabel('Timezone').fill('Asia/Kolkata')
    await interviews.getByLabel('Starts').fill('2026-10-05T21:30')
    await interviews.getByLabel('Ends').fill('2026-10-05T22:30')
    await interviews.getByLabel('Round').fill('Timezone round')

    const preview = interviews.getByTestId('interview-timezone-preview')
    await expect(preview).toContainText('Chosen timezone:')
    await expect(preview).toContainText('9:30')

    await interviews.getByRole('button', { name: 'Schedule interview' }).click()
    await expect(interviews.getByText('Timezone round', { exact: true })).toBeVisible({ timeout: 15000 })

    const serverResponse = await request.get(`${API_URL}/crm/tracks/${application.id}/interviews`)
    expect(serverResponse.ok()).toBeTruthy()
    const serverInterview = (await serverResponse.json()).interviews.find((item: { round_label?: string }) => item.round_label === 'Timezone round')
    expect(serverInterview).toBeTruthy()
    expect(serverInterview.timezone).toBe('Asia/Kolkata')
    expect(serverInterview.starts_at).toContain('2026-10-05T16:00:00')

    const row = interviews.getByTestId(`application-interview-${serverInterview.id}`)
    await expect(row).toContainText('9:30')
    await expect(row).toContainText('(Asia/Kolkata)')
  })

  test('calendar_download_not_sent_message', async ({ page, request }) => {
    await resetAndLogin(request)
    const application = await createApplication(request)

    try {
      const { first, timezone } = await createInterviewFixture(request, application.id)
      await page.goto(`/applications?track_id=${application.id}`)
      const interviews = page.getByTestId('application-interviews')
      await expect(interviews).toBeVisible({ timeout: 15000 })
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
    } finally {
      await restoreTimezone(request)
    }
  })

  test('cancel_removes_today_interview_action', async ({ page, request }) => {
    await resetAndLogin(request)
    const application = await createApplication(request)

    try {
      const { first } = await createInterviewFixture(request, application.id)

      await page.goto('/today')
      const prepRow = page.locator('tr').filter({ hasText: 'Prepare for Technical interview' })
      await expect(prepRow).toBeVisible({ timeout: 15000 })
      await expect(prepRow).toContainText('Interview preparation')
      await expect(prepRow.getByRole('button', { name: 'Snooze' })).toBeVisible()
      await expect(prepRow.getByRole('button', { name: 'Complete' })).toHaveCount(0)

      await prepRow.getByRole('button', { name: 'Open details' }).click()
      await expect(page).toHaveURL(new RegExp(`/applications\\?track_id=${application.id}$`))

      const interviewRow = page.getByTestId(`application-interview-${first.id}`)
      await expect(interviewRow).toBeVisible({ timeout: 15000 })
      await interviewRow.getByRole('button', { name: 'Cancel interview' }).click()
      await expect(interviewRow).toContainText('cancelled')

      const todayResponse = await request.get(`${API_URL}/crm/today`)
      expect(todayResponse.ok()).toBeTruthy()
      const todayItems = (await todayResponse.json()).items
      expect(todayItems.some((item: { action_key: string }) => item.action_key.startsWith(`interview:${first.id}:`))).toBeFalsy()

      await page.goto('/today')
      await expect(page.locator('tr').filter({ hasText: 'Prepare for Technical interview' })).toHaveCount(0)
    } finally {
      await restoreTimezone(request)
    }
  })
})
