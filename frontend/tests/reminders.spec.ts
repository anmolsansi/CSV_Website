import { test, expect, type Page, type Route } from '@playwright/test'

const EMPTY_TODAY = {
  items: [],
  next_cursor: null,
  as_of: '2026-09-22T14:00:00Z',
  timezone: 'America/New_York',
  counts: { total: 0, overdue: 0, due_today: 0, undated: 0 },
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function routeEmptyToday(page: Page) {
  await page.route('**/crm/today**', async (route) => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'GET' && url.pathname === '/crm/today') {
      await json(route, EMPTY_TODAY)
      return
    }
    await route.fallback()
  })
}

test.describe('JG-039/JG-040 reminders', () => {
  test('ui_does_not_label_queued_as_sent', async ({ page }) => {
    await routeEmptyToday(page)

    await page.route('**/crm/reminders**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/crm/reminders/preferences') {
        await json(route, {
          enabled: true,
          channel: 'in_app',
          local_time: '09:00',
          quiet_start: '21:00',
          quiet_end: '08:00',
          timezone: 'America/New_York',
          version: 'abc123abc123abc123abc123abc123ab',
          email_available: false,
          email_unavailable_reason: 'email_delivery_disabled',
        })
        return
      }
      if (url.pathname === '/crm/reminders') {
        await json(route, {
          items: [{
            id: 41,
            track_id: 73,
            company: 'Acme',
            role: 'Backend Engineer',
            channel: 'in_app',
            status: 'pending',
            scheduled_at: '2026-09-22T15:00:00Z',
            sent_at: null,
            read_at: null,
            unread: false,
            attempt_count: 0,
            last_error_code: null,
            version: 1,
            possible_duplicate: false,
          }],
          next_cursor: null,
        })
        return
      }
      await route.fallback()
    })

    await page.goto('/today')
    const reminders = page.getByRole('region', { name: 'Reminders' })
    await expect(reminders).toContainText('Pending')
    await expect(reminders).not.toContainText('Sent')
    await expect(reminders).not.toContainText('Delivered, unread')
  })

  test('opt_in_due_opt_out', async ({ page }) => {
    await routeEmptyToday(page)

    let preference = {
      enabled: false,
      channel: 'in_app',
      local_time: '09:00',
      quiet_start: '21:00',
      quiet_end: '08:00',
      timezone: 'America/New_York',
      version: 'v000000000000000000000000000001',
      email_available: false,
      email_unavailable_reason: 'email_delivery_disabled',
    }
    let history: Record<string, unknown>[] = []

    await page.route('**/crm/reminders**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())

      if (url.pathname === '/crm/reminders/preferences' && request.method() === 'GET') {
        await json(route, preference)
        return
      }
      if (url.pathname === '/crm/reminders/preferences' && request.method() === 'PATCH') {
        const payload = request.postDataJSON()
        expect(payload.version).toBe(preference.version)
        preference = {
          ...preference,
          enabled: payload.enabled,
          channel: payload.channel,
          local_time: payload.local_time,
          quiet_start: payload.quiet_start,
          quiet_end: payload.quiet_end,
          version: preference.enabled
            ? 'v000000000000000000000000000003'
            : 'v000000000000000000000000000002',
        }
        history = preference.enabled
          ? [{
              id: 51,
              track_id: 73,
              company: 'Beta',
              role: 'Platform Engineer',
              channel: 'in_app',
              status: 'sent',
              scheduled_at: '2026-09-22T13:00:00Z',
              sent_at: '2026-09-22T13:00:05Z',
              read_at: null,
              unread: true,
              attempt_count: 1,
              last_error_code: null,
              version: 2,
              possible_duplicate: false,
            }]
          : [{
              id: 51,
              track_id: 73,
              company: 'Beta',
              role: 'Platform Engineer',
              channel: 'in_app',
              status: 'sent',
              scheduled_at: '2026-09-22T13:00:00Z',
              sent_at: '2026-09-22T13:00:05Z',
              read_at: null,
              unread: true,
              attempt_count: 1,
              last_error_code: null,
              version: 2,
              possible_duplicate: false,
            }]
        await json(route, preference)
        return
      }
      if (url.pathname === '/crm/reminders' && request.method() === 'GET') {
        await json(route, { items: history, next_cursor: null })
        return
      }
      await route.fallback()
    })

    await page.goto('/today')
    const reminders = page.getByRole('region', { name: 'Reminders' })
    const enabled = reminders.getByRole('checkbox', { name: 'Enable reminders' })

    await expect(enabled).not.toBeChecked()
    await enabled.check()
    await reminders.getByRole('button', { name: 'Save reminders' }).click()
    await expect(reminders).toContainText('Delivered, unread')

    await page.reload()
    await expect(page.getByRole('region', { name: 'Reminders' })
      .getByRole('checkbox', { name: 'Enable reminders' })).toBeChecked()
    await expect(page.getByRole('region', { name: 'Reminders' }))
      .toContainText('Delivered, unread')

    await page.getByRole('region', { name: 'Reminders' })
      .getByRole('checkbox', { name: 'Enable reminders' }).uncheck()
    await page.getByRole('region', { name: 'Reminders' })
      .getByRole('button', { name: 'Save reminders' }).click()

    await page.reload()
    await expect(page.getByRole('region', { name: 'Reminders' })
      .getByRole('checkbox', { name: 'Enable reminders' })).not.toBeChecked()
    // Opt-out cancels only unsent occurrences. Accepted history remains visible.
    await expect(page.getByRole('region', { name: 'Reminders' }))
      .toContainText('Delivered, unread')
  })
})
