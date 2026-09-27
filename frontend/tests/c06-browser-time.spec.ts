import { test, expect, type Page, type Route } from '@playwright/test'

const API_URL = 'http://localhost:8000'
const ACCOUNT_TIMEZONE = 'America/New_York'
const FIXED_BROWSER_NOW = '2026-09-21T15:00:00.000Z'
const FUTURE_SNOOZE_WALL = '2027-03-15T12:30'
const FUTURE_RESCHEDULE_WALL = '2027-03-16T09:45'
const PAST_WALL = '2020-01-01T09:00'

function manualItem(overrides: Record<string, unknown> = {}) {
  return {
    action_key: 'manual:41',
    type: 'manual',
    id: 41,
    description: 'C06 deterministic snooze',
    due_at: '2026-09-21T14:00:00Z',
    priority: 1,
    version: 1,
    snooze_version: 1,
    snoozed_until: null,
    track_id: null,
    row_id: 11,
    source_view_id: null,
    origin_label: 'Manual',
    company: 'Acme',
    role: 'Backend Engineer',
    ...overrides,
  }
}

function followupItem(overrides: Record<string, unknown> = {}) {
  return {
    action_key: 'followup:73:2026-09-21T14:00:00Z',
    type: 'followup',
    id: 73,
    description: 'C06 deterministic reschedule',
    due_at: '2026-09-21T14:00:00Z',
    priority: 1,
    version: 1,
    snooze_version: 1,
    snoozed_until: null,
    track_id: 73,
    row_id: 12,
    source_view_id: null,
    origin_label: 'Follow-up',
    company: 'Beta',
    role: 'Platform Engineer',
    ...overrides,
  }
}

function queue(items: Record<string, unknown>[]) {
  return {
    items,
    next_cursor: null,
    as_of: FIXED_BROWSER_NOW,
    timezone: ACCOUNT_TIMEZONE,
    counts: {
      overdue: 0,
      due_today: items.filter((item) => item.due_at).length,
      undated: items.filter((item) => !item.due_at).length,
    },
  }
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function routeTodayList(page: Page, getItems: () => Record<string, unknown>[]) {
  await page.route('**/crm/today**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname === '/crm/today') {
      await fulfillJson(route, queue(getItems()))
      return
    }
    await route.fallback()
  })
}

async function browserLocalWallToIso(page: Page, wallTime: string) {
  return page.evaluate((value) => new Date(value).toISOString(), wallTime)
}

async function accountDisplay(page: Page, instant: string) {
  return page.evaluate(({ value, timeZone }) => new Intl.DateTimeFormat(undefined, {
    timeZone,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value)), { value: instant, timeZone: ACCOUNT_TIMEZONE })
}

async function browserDateKey(page: Page, instant: string, timeZone?: string) {
  return page.evaluate(({ value, zone }) => {
    const parts = new Intl.DateTimeFormat('en-US', {
      ...(zone ? { timeZone: zone } : {}),
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date(value))
    const get = (type: string) => parts.find((part) => part.type === type)?.value || ''
    return `${get('year')}-${get('month')}-${get('day')}`
  }, { value: instant, zone: timeZone })
}

async function resetAndSeed(page: Page) {
  const reset = await page.request.post(`${API_URL}/test/reset`)
  expect(reset.ok()).toBeTruthy()
  const seed = await page.request.post(`${API_URL}/test/seed`)
  expect(seed.ok()).toBeTruthy()
}

test.describe('C-06 deterministic browser time contracts', () => {
  test.beforeEach(async ({ page }) => {
    await page.clock.install({ time: new Date(FIXED_BROWSER_NOW) })
  })

  test.afterEach(async ({ page }) => {
    // Keep the shared E2E account predictable for tests that run after this file.
    await page.request.post(`${API_URL}/test/reset`)
    await page.request.post(`${API_URL}/test/seed`)
  })

  test('keyboard_snooze_persists_after_reload uses browser-local wall time and UTC payload @time-zone', async ({ page }) => {
    const item = manualItem()
    let persistedSnooze: string | null = null
    let capturedPayload: Record<string, unknown> | null = null
    const expectedInstant = await browserLocalWallToIso(page, FUTURE_SNOOZE_WALL)

    await routeTodayList(page, () => persistedSnooze ? [] : [item])
    await page.route('**/crm/today/snooze', async (route) => {
      capturedPayload = route.request().postDataJSON()
      expect(capturedPayload?.action_key).toBe(item.action_key)
      expect(capturedPayload?.version).toBe(1)
      expect(capturedPayload?.until).toBe(expectedInstant)
      persistedSnooze = String(capturedPayload?.until)
      await fulfillJson(route, {
        action_key: item.action_key,
        snoozed_until: persistedSnooze,
        version: 2,
      })
    })

    await page.goto('/today')
    const snoozeButton = page.getByRole('button', { name: 'Snooze' })
    await snoozeButton.focus()
    await snoozeButton.press('Enter')

    const dialog = page.getByRole('dialog', { name: 'Snooze action' })
    const input = dialog.locator('input[type="datetime-local"]')
    await input.fill(FUTURE_SNOOZE_WALL)
    await expect(input).toHaveValue(FUTURE_SNOOZE_WALL)
    await dialog.getByRole('button', { name: 'Save' }).press('Enter')

    await expect(dialog).toHaveCount(0)
    await expect(page.getByText('Nothing needs attention today')).toBeVisible()
    expect(capturedPayload?.until).toBe(expectedInstant)
    expect(persistedSnooze).toBe(expectedInstant)

    await page.reload()
    await expect(page.getByText('Nothing needs attention today')).toBeVisible()
  })

  test('followup_reschedule_updates_application_drawer round-trips the same instant @time-zone', async ({ page }) => {
    let followUpAt = '2026-09-21T14:00:00Z'
    let actionKey = 'followup:73:2026-09-21T14:00:00Z'
    const expectedInstant = await browserLocalWallToIso(page, FUTURE_RESCHEDULE_WALL)

    await routeTodayList(page, () => [followupItem({ action_key: actionKey, due_at: followUpAt })])
    await page.route('**/crm/today/follow-up', async (route) => {
      const payload = route.request().postDataJSON()
      expect(payload.action_key).toBe(actionKey)
      expect(payload.resolution).toBe('reschedule')
      expect(payload.follow_up_at).toBe(expectedInstant)
      followUpAt = payload.follow_up_at
      actionKey = `followup:73:${followUpAt.replace('+00:00', 'Z')}`
      await fulfillJson(route, {
        track_id: 73,
        follow_up_at: followUpAt,
        status: 'follow_up',
      })
    })

    await page.route('**/crm/applications**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (request.method() !== 'GET' || url.pathname !== '/crm/applications') {
        await route.fallback()
        return
      }
      await fulfillJson(route, {
        rows: [{
          id: 73,
          csv_row_id: 12,
          company: 'Beta',
          title: 'Platform Engineer',
          status: 'follow_up',
          ats_group: 'greenhouse',
          search_bucket: 'target',
          resume_match_score: 91,
          opened_at: '2026-09-19T12:00:00Z',
          applied_at: null,
          follow_up_at: followUpAt,
          notes: '',
          url: 'https://example.test/beta',
        }],
        filter_options: {
          ats_groups: ['greenhouse'],
          location_groups: [],
          decisions: [],
          sponsorship_statuses: [],
        },
        page: 1,
        page_size: 50,
        total_count: 1,
        has_next: false,
      })
    })

    await page.goto('/today')
    await page.getByRole('button', { name: 'Reschedule' }).click()
    const dialog = page.getByRole('dialog', { name: 'Reschedule follow-up' })
    const input = dialog.locator('input[type="datetime-local"]')
    await input.fill(FUTURE_RESCHEDULE_WALL)
    await expect(input).toHaveValue(FUTURE_RESCHEDULE_WALL)
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).toHaveCount(0)

    await page.getByRole('button', { name: 'Open details' }).click()
    await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible()
    await expect(page.locator('tbody tr').first().locator('input[type="datetime-local"]').nth(1))
      .toHaveValue(FUTURE_RESCHEDULE_WALL)
    expect(new Date(followUpAt).toISOString()).toBe(expectedInstant)
  })

  test('account timezone controls day boundary even when browser timezone differs @time-zone', async ({ page }) => {
    const boundaryInstant = '2026-09-22T02:30:00Z'
    const item = manualItem({
      action_key: 'manual:boundary',
      id: 99,
      description: 'Account boundary item',
      due_at: boundaryInstant,
    })
    await routeTodayList(page, () => [item])

    const accountKey = await browserDateKey(page, boundaryInstant, ACCOUNT_TIMEZONE)
    const deviceKey = await browserDateKey(page, boundaryInstant)
    expect(accountKey).toBe('2026-09-21')

    await page.goto('/today')
    const row = page.getByRole('row', { name: /Account boundary item/ })
    await expect(row).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Due today' })).toBeVisible()
    await expect(row).toContainText(await accountDisplay(page, boundaryInstant))
    await expect(page.getByText(ACCOUNT_TIMEZONE)).toBeVisible()

    const configuredBrowserZone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)
    if (configuredBrowserZone !== ACCOUNT_TIMEZONE) {
      expect(deviceKey).not.toBe(accountKey)
    } else {
      expect(deviceKey).toBe(accountKey)
    }
  })

  test('invalid past cancel failed draft and keyboard focus behavior stay deterministic @time-zone', async ({ page }) => {
    const item = manualItem()
    let writes = 0
    await routeTodayList(page, () => [item])
    await page.route('**/crm/today/snooze', async (route) => {
      writes += 1
      await fulfillJson(route, {
        detail: { code: 'synthetic_failure', message: 'Synthetic snooze failure' },
      }, 500)
    })

    await page.goto('/today')
    const snoozeButton = page.getByRole('button', { name: 'Snooze' })
    await snoozeButton.focus()
    await snoozeButton.press('Enter')
    let dialog = page.getByRole('dialog', { name: 'Snooze action' })
    await expect(dialog).toBeVisible()

    await dialog.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(snoozeButton).toBeFocused()

    await snoozeButton.press('Enter')
    dialog = page.getByRole('dialog', { name: 'Snooze action' })
    const input = dialog.locator('input[type="datetime-local"]')

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog.getByRole('alert')).toContainText('Choose a valid future date and time.')
    expect(writes).toBe(0)

    await input.fill(PAST_WALL)
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog.getByRole('alert')).toContainText('Choose a future date and time.')
    expect(writes).toBe(0)

    await input.fill(FUTURE_SNOOZE_WALL)
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog.getByRole('alert')).toContainText('Synthetic snooze failure')
    await expect(input).toHaveValue(FUTURE_SNOOZE_WALL)
    expect(writes).toBe(1)

    await dialog.getByRole('button', { name: 'Close dialog' }).click()
    await expect(dialog).toHaveCount(0)
    await expect(snoozeButton).toBeFocused()
  })

  test('real API snooze and reschedule persist the browser-derived instants @time-zone', async ({ page }) => {
    await resetAndSeed(page)

    const timezoneResponse = await page.request.patch(`${API_URL}/crm/profile/timezone`, {
      data: { timezone: ACCOUNT_TIMEZONE },
    })
    expect(timezoneResponse.ok()).toBeTruthy()

    const workResponse = await page.request.post(`${API_URL}/crm/work-items`, {
      data: {
        description: 'C06 real API snooze',
        due_at: null,
        priority: 1,
      },
    })
    expect(workResponse.ok()).toBeTruthy()
    const workItem = await workResponse.json()

    const rowsResponse = await page.request.get(`${API_URL}/rows`, {
      params: { page: 1, page_size: 5 },
    })
    expect(rowsResponse.ok()).toBeTruthy()
    const rowsBody = await rowsResponse.json()
    const sourceRow = rowsBody.rows[0]
    expect(sourceRow).toBeTruthy()

    const applicationResponse = await page.request.post(`${API_URL}/crm/from-row/${sourceRow.id}`)
    expect(applicationResponse.ok()).toBeTruthy()
    const application = await applicationResponse.json()

    const appliedResponse = await page.request.patch(`${API_URL}/crm/applications/${application.id}`, {
      data: { status: 'applied' },
    })
    expect(appliedResponse.ok()).toBeTruthy()

    const dueFollowUp = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    const followupResponse = await page.request.patch(`${API_URL}/crm/applications/${application.id}`, {
      data: { status: 'follow_up', follow_up_at: dueFollowUp },
    })
    expect(followupResponse.ok()).toBeTruthy()

    const expectedSnoozeInstant = await browserLocalWallToIso(page, FUTURE_SNOOZE_WALL)
    const expectedRescheduleInstant = await browserLocalWallToIso(page, FUTURE_RESCHEDULE_WALL)

    await page.goto('/today')

    const manualRow = page.getByRole('row', { name: /C06 real API snooze/ })
    await expect(manualRow).toBeVisible()
    await manualRow.getByRole('button', { name: 'Snooze' }).click()
    let dialog = page.getByRole('dialog', { name: 'Snooze action' })
    await dialog.locator('input[type="datetime-local"]').fill(FUTURE_SNOOZE_WALL)
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page.getByText('C06 real API snooze')).toHaveCount(0)

    const snoozedQueueResponse = await page.request.get(`${API_URL}/crm/today`, {
      params: { include_snoozed: true, limit: 100 },
    })
    expect(snoozedQueueResponse.ok()).toBeTruthy()
    const snoozedQueue = await snoozedQueueResponse.json()
    const persistedWork = snoozedQueue.items.find((candidate: any) => candidate.action_key === workItem.action_key)
    expect(persistedWork).toBeTruthy()
    expect(new Date(persistedWork.snoozed_until).toISOString()).toBe(expectedSnoozeInstant)

    const followupRow = page.getByRole('row', { name: new RegExp(`${sourceRow.data.company_guess}.*${sourceRow.data.title}`) })
    await expect(followupRow).toBeVisible()
    await followupRow.getByRole('button', { name: 'Reschedule' }).click()
    dialog = page.getByRole('dialog', { name: 'Reschedule follow-up' })
    await dialog.locator('input[type="datetime-local"]').fill(FUTURE_RESCHEDULE_WALL)
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).toHaveCount(0)

    const applicationsResponse = await page.request.get(`${API_URL}/crm/applications`, {
      params: { page: 1, page_size: 50 },
    })
    expect(applicationsResponse.ok()).toBeTruthy()
    const applications = await applicationsResponse.json()
    const persistedApplication = applications.rows.find((candidate: any) => candidate.id === application.id)
    expect(persistedApplication).toBeTruthy()
    expect(new Date(persistedApplication.follow_up_at).toISOString()).toBe(expectedRescheduleInstant)
  })
})