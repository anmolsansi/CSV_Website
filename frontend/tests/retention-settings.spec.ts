import { test, expect } from '@playwright/test'

const API_URL = 'http://localhost:8000'

test.describe('JG-014 retention settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(`${API_URL}/test/reset`)
    await page.request.post(`${API_URL}/test/seed`)
  })

  test('retention settings defaults off and values validated', async ({ page }) => {
    let patchCount = 0
    page.on('request', (request) => {
      if (request.method() === 'PATCH' && request.url().endsWith('/crm/profile/retention')) {
        patchCount += 1
      }
    })

    await page.goto('/')
    const settings = page.getByRole('region', { name: 'Retention and maintenance' })
    await expect(settings).toBeVisible({ timeout: 15000 })

    const input = page.getByLabel('Archive visited jobs after (days)')
    const save = settings.getByRole('button', { name: 'Save' })
    await expect(input).toHaveValue('0')
    await expect(save).toBeDisabled()
    await expect(settings).toContainText('Maintenance:')
    await expect(settings).toContainText('Disabled')
    await expect(settings).toContainText('Permanent purge:')
    await expect(settings).toContainText('Unavailable')

    await input.fill('6')
    await expect(settings.getByRole('alert')).toContainText(
      'Enter 0 to keep automatic archive off, or a whole number from 7 to 3650.'
    )
    await expect(save).toBeDisabled()
    expect(patchCount).toBe(0)

    await input.fill('30')
    await expect(save).toBeEnabled()
    await page.waitForTimeout(200)
    expect(patchCount).toBe(0)

    await save.click()
    await expect(settings.getByRole('status')).toContainText('Retention policy saved.')
    expect(patchCount).toBe(1)

    await page.reload()
    await expect(page.getByLabel('Archive visited jobs after (days)')).toHaveValue('30')
  })

  test('opening retention settings only previews and does not run cleanup', async ({ page }) => {
    const maintenanceRequests: string[] = []
    page.on('request', (request) => {
      if (/cleanup|maintenance\/run|retention\/run/i.test(request.url())) {
        maintenanceRequests.push(`${request.method()} ${request.url()}`)
      }
    })

    await page.goto('/')
    const settings = page.getByRole('region', { name: 'Retention and maintenance' })
    await expect(settings).toBeVisible({ timeout: 15000 })
    await expect(settings).toContainText('Eligible now:')
    expect(maintenanceRequests).toEqual([])
  })

  test('failed health does not look healthy', async ({ page }) => {
    await page.route('**/crm/profile/retention', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          archive_after_days: 30,
          eligible_row_count: 4,
          maintenance: {
            status: 'unavailable',
            last_successful_cleanup_at: '2026-09-20T07:00:00',
            last_attempted_cleanup_at: '2026-09-20T08:00:00',
            last_outcome: 'failed',
          },
          purge_available: false,
          archived_rows_ui_available: false,
          recovery_message: 'Archived rows are preserved. Recovery requires the existing API/operator workflow.',
        }),
      })
    })

    await page.goto('/')
    const settings = page.getByRole('region', { name: 'Retention and maintenance' })
    await expect(settings).toContainText('Maintenance:')
    await expect(settings).toContainText('Unavailable')
    await expect(settings).toContainText('This does not mean there are zero eligible jobs.')
    await expect(settings).not.toContainText('Maintenance: Healthy')
    await expect(settings).toContainText('Eligible now: 4 visited jobs')
  })

  test('load failure offers retry instead of a blank settings panel', async ({ page }) => {
    let attempts = 0
    await page.route('**/crm/profile/retention', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      attempts += 1
      if (attempts === 1) {
        await route.fulfill({ status: 503, body: 'unavailable' })
        return
      }
      await route.continue()
    })

    await page.goto('/')
    const settings = page.getByRole('region', { name: 'Retention and maintenance' })
    await expect(settings.getByRole('alert')).toContainText('Retention settings are unavailable.')
    await settings.getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByLabel('Archive visited jobs after (days)')).toBeVisible()
  })
})
