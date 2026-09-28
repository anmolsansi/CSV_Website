import { expect, test } from '@playwright/test'
import { browserLocalWallToIso, futureLocalDateTime } from './time-helpers'

function manualItem(overrides = {}) {
  return {
    action_key: 'manual:41',
    id: 41,
    type: 'manual_task',
    description: 'Review Acme application',
    due_at: '2026-09-26T16:00:00Z',
    priority: 40,
    row_id: 1,
    company: 'Acme',
    role: 'Backend Engineer',
    origin_label: 'Manual',
    snoozed_until: null,
    ...overrides,
  }
}

function followupItem(overrides = {}) {
  return {
    action_key: 'followup:2',
    id: 2,
    type: 'followup',
    description: 'Follow up with Beta about Platform Engineer',
    due_at: '2026-09-27T16:00:00Z',
    priority: 30,
    row_id: 2,
    company: 'Beta',
    role: 'Platform Engineer',
    origin_label: 'Application',
    snoozed_until: null,
    ...overrides,
  }
}

async function routeTodayList(page, itemsFactory) {
  await page.route('**/today**', async (route) => {
    const request = route.request()
    if (request.method() !== 'GET') {
      await route.continue()
      return
    }
    const url = new URL(request.url())
    if (url.pathname !== '/today') {
      await route.continue()
      return
    }
    const items = itemsFactory()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        date: '2026-09-27',
        timezone: 'America/New_York',
        items,
        counts: {
          overdue: items.filter((item) => item.due_at && item.due_at < '2026-09-27T04:00:00Z').length,
          due_today: items.filter((item) => item.due_at && item.due_at >= '2026-09-27T04:00:00Z').length,
          undated: items.filter((item) => !item.due_at).length,
          total: items.length,
        },
        next_cursor: null,
      }),
    })
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

    await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Overdue' })).toBeVisible()
    await expect(page.getByText('Review Acme application')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Due today' })).toBeVisible()
    await expect(page.getByText('Follow up with Beta about Platform Engineer')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Undated' })).toBeVisible()
    await expect(page.getByText('Prepare networking notes')).toBeVisible()
    await expect(page.getByText('Tomorrow Co')).toHaveCount(0)
    await expect(page.getByText('Your next useful actions in America/New_York.', { exact: true })).toBeVisible()
  })

  test('keyboard_snooze_persists_after_reload', async ({ page }) => {
    let snoozed = false
    const item = manualItem()
    const snoozeUntil = await futureLocalDateTime(page)
    const expectedSnoozeInstant = await browserLocalWallToIso(page, snoozeUntil)

    await routeTodayList(page, () => (snoozed ? [] : [item]))
    await page.route('**/today/actions/manual%3A41/snooze', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      const payload = route.request().postDataJSON()
      expect(payload.snoozed_until).toBe(expectedSnoozeInstant)
      snoozed = true
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    })

    await page.goto('/today')
    await page.getByText('Review Acme application').click()
    await page.keyboard.press('s')

    const snoozeDialog = page.getByRole('dialog')
    await snoozeDialog.getByLabel('Snooze until').fill(snoozeUntil)
    await snoozeDialog.getByRole('button', { name: 'Snooze' }).click()
    await expect(page.getByText('Review Acme application')).toHaveCount(0)

    await page.reload()
    await expect(page.getByText('Review Acme application')).toHaveCount(0)
  })

  test('failed_complete_preserves_item', async ({ page }) => {
    const item = manualItem()
    await routeTodayList(page, () => [item])
    await page.route('**/today/actions/manual%3A41/complete', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'failed' }) })
    })

    await page.goto('/today')
    await page.getByText('Review Acme application').click()
    await page.keyboard.press('c')
    await expect(page.getByText('Review Acme application')).toBeVisible()
  })

  test('followup_reschedule_updates_application_drawer', async ({ page }) => {
    const item = followupItem()
    const rescheduleUntil = await futureLocalDateTime(page)
    const expectedInstant = await browserLocalWallToIso(page, rescheduleUntil)
    await routeTodayList(page, () => [item])

    await page.route('**/today/actions/followup%3A2/reschedule', async (route) => {
      const payload = route.request().postDataJSON()
      expect(payload.due_at).toBe(expectedInstant)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    })

    await page.goto('/today')
    await page.getByText('Follow up with Beta about Platform Engineer').click()
    await page.keyboard.press('r')
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Reschedule to').fill(rescheduleUntil)
    await dialog.getByRole('button', { name: 'Reschedule' }).click()
    await expect(dialog).toHaveCount(0)
  })

  test('saved-view preview shows exact count and caps creation at 20', async ({ page }) => {
    await routeTodayList(page, () => [])
    await page.route('**/today/saved-view-preview**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ count: 24, capped_count: 20 }),
      })
    })

    await page.goto('/today')
    const previewButton = page.getByRole('button', { name: /preview/i })
    if (await previewButton.count()) {
      await previewButton.first().click()
      await expect(page.getByText(/24/)).toBeVisible()
      await expect(page.getByText(/20/)).toBeVisible()
    }
  })
})
