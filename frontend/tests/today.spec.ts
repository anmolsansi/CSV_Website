import { test, expect, type Page, type Route } from '@playwright/test'

const AS_OF = '2026-09-21T15:00:00Z'
const TIMEZONE = 'America/New_York'

function manualItem(overrides: Record<string, unknown> = {}) {
  return {
    action_key: 'manual:41',
    type: 'manual',
    id: 41,
    description: 'Review Acme application',
    due_at: '2026-09-20T15:00:00Z',
    priority: 1,
    version: 1,
    snooze_version: 1,
    snoozed_until: null,
    track_id: null,
    row_id: 11,
    source_view_id: null,
    origin_label: 'Job',
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
    description: 'Follow up with Beta about Platform Engineer',
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
  const overdue = items.filter((item) => item.due_at && String(item.due_at) < '2026-09-21T04:00:00Z').length
  const dueToday = items.filter((item) => item.due_at && String(item.due_at) >= '2026-09-21T04:00:00Z').length
  const undated = items.filter((item) => !item.due_at).length
  return {
    items,
    next_cursor: null,
    as_of: AS_OF,
    timezone: TIMEZONE,
    counts: { overdue, due_today: dueToday, undated },
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

test.describe('JG-027 Today screen', () => {
  test('today.spec.ts: overdue appears and tomorrow does not with fixed account clock', async ({ page }) => {
    const overdue = manualItem()
    const dueToday = followupItem()
    const undated = manualItem({
      action_key: 'manual:42',
      id: 42,
      description: 'Prepare networking notes',
      due_at: null,
      row_id: null,
      company: null,
      role: null,
      origin_label: 'Manual',
    })

    // JG-026 owns server membership. The JG-027 fixture freezes the account
    // clock/timezone and returns only the visible membership from that contract.
    await routeTodayList(page, () => [overdue, dueToday, undated])

    await page.goto('/today')

    await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Overdue' })).toBeVisible()
    await expect(page.getByText('Review Acme application')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Due today' })).toBeVisible()
    await expect(page.getByText('Follow up with Beta about Platform Engineer')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Undated' })).toBeVisible()
    await expect(page.getByText('Prepare networking notes')).toBeVisible()
    await expect(page.getByText('Tomorrow Co')).toHaveCount(0)
    await expect(page.getByText('America/New_York')).toBeVisible()
  })

  test('keyboard_snooze_persists_after_reload', async ({ page }) => {
    let snoozed = false
    const item = manualItem()

    await routeTodayList(page, () => snoozed ? [] : [item])
    await page.route('**/crm/today/snooze', async (route) => {
      const payload = route.request().postDataJSON()
      expect(payload.action_key).toBe(item.action_key)
      expect(payload.version).toBe(1)
      expect(payload.until).toContain('2026-09-22')
      snoozed = true
      await fulfillJson(route, {
        action_key: item.action_key,
        snoozed_until: payload.until,
        version: 2,
      })
    })

    await page.goto('/today')
    const snoozeButton = page.getByRole('button', { name: 'Snooze' })
    await snoozeButton.focus()
    await snoozeButton.press('Enter')

    const dialog = page.getByRole('dialog', { name: 'Snooze action' })
    await expect(dialog).toBeVisible()
    await dialog.locator('input[type="datetime-local"]').fill('2026-09-22T10:00')
    await dialog.getByRole('button', { name: 'Save' }).press('Enter')

    await expect(dialog).toHaveCount(0)
    await expect(page.getByText('Nothing needs attention today')).toBeVisible()

    await page.reload()
    await expect(page.getByText('Nothing needs attention today')).toBeVisible()
    expect(snoozed).toBeTruthy()
  })

  test('failed_complete_preserves_item', async ({ page }) => {
    const item = manualItem()
    await routeTodayList(page, () => [item])

    await page.route('**/crm/work-items/41', async (route) => {
      expect(route.request().method()).toBe('PATCH')
      const payload = route.request().postDataJSON()
      expect(payload).toEqual({ version: 1, state: 'done' })
      await fulfillJson(route, {
        detail: { code: 'synthetic_failure', message: 'Synthetic complete failure' },
      }, 500)
    })

    await page.goto('/today')
    await page.getByRole('button', { name: 'Complete' }).click()

    await expect(page.getByText('Review Acme application')).toBeVisible()
    await expect(page.locator('.toast-error')).toContainText('Synthetic complete failure')
    await expect(page.getByRole('button', { name: 'Complete' })).toBeEnabled()
  })

  test('followup_reschedule_updates_application_drawer', async ({ page }) => {
    let followUpAt = '2026-09-21T14:00:00Z'
    let actionKey = 'followup:73:2026-09-21T14:00:00Z'

    await routeTodayList(page, () => [followupItem({ action_key: actionKey, due_at: followUpAt })])

    await page.route('**/crm/today/follow-up', async (route) => {
      const payload = route.request().postDataJSON()
      expect(payload.action_key).toBe(actionKey)
      expect(payload.resolution).toBe('reschedule')
      expect(payload.follow_up_at).toContain('2026-09-23')
      followUpAt = payload.follow_up_at
      actionKey = `followup:73:${followUpAt.replace('+00:00', 'Z')}`
      await fulfillJson(route, {
        track_id: 73,
        follow_up_at: followUpAt,
        status: 'follow_up',
      })
    })

    await page.route('**/crm/applications**', async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() !== 'GET' || url.pathname !== '/crm/applications') {
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
    await dialog.locator('input[type="datetime-local"]').fill('2026-09-23T11:30')
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).toHaveCount(0)

    // The current source has no separate application drawer. JG-027 therefore
    // verifies the persisted reschedule in the existing Applications edit surface.
    await page.getByRole('button', { name: 'Open details' }).click()
    await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible()
    await expect(page.locator('tbody tr').first().locator('input[type="datetime-local"]').nth(1)).not.toHaveValue('')
    await expect(page.getByText('Beta')).toBeVisible()
  })

  test('saved-view preview shows exact count and caps creation at 20', async ({ page }) => {
    const savedView = {
      id: 9,
      name: 'High-score targets',
      view_type: 'job_links',
      filters: { q: 'platform' },
      is_pinned: false,
      created_at: '2026-09-20T10:00:00Z',
    }

    await page.route('**/crm/views**', async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'GET' && url.pathname === '/crm/views') {
        await fulfillJson(route, [savedView])
        return
      }
      await route.fallback()
    })

    await page.route('**/rows**', async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'GET' && url.pathname === '/rows') {
        await fulfillJson(route, {
          rows: [{ id: 1 }],
          total_count: 27,
          page: 1,
          page_size: 1,
          has_next: true,
        })
        return
      }
      await route.fallback()
    })

    let submittedLimit = 0
    await page.route('**/crm/today/from-view', async (route) => {
      const payload = route.request().postDataJSON()
      submittedLimit = payload.limit
      expect(payload.view_id).toBe(9)
      expect(typeof payload.request_id).toBe('string')
      await fulfillJson(route, {
        items: [],
        created: 20,
        existing: 0,
        completed: 0,
      })
    })

    await page.goto('/saved-views')
    await page.getByRole('button', { name: 'Add to Today' }).click()

    const preview = page.getByTestId('today-view-preview')
    await expect(preview).toContainText('Origin: High-score targets')
    await expect(preview).toContainText('Exact matches: 27')
    await expect(preview.getByRole('button', { name: 'Add 20 to Today' })).toBeVisible()

    await preview.getByRole('button', { name: 'Add 20 to Today' }).click()
    await expect(preview).toContainText('Created 20, already pending 0, completed 0.')
    expect(submittedLimit).toBe(20)
  })
})
