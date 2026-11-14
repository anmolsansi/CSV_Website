import { test, expect, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function makeTrack(request: APIRequestContext, rowId: number, state: 'interview' | 'offer' | 'opened') {
  const created = await request.post(`${API_URL}/crm/from-row/${rowId}`)
  expect(created.ok()).toBeTruthy()
  const track = await created.json()
  if (state !== 'opened') {
    const applied = await request.patch(`${API_URL}/crm/applications/${track.id}`, {
      data: { mark_applied: true },
    })
    expect(applied.ok()).toBeTruthy()
    const staged = await request.patch(`${API_URL}/crm/applications/${track.id}`, {
      data: { status: state },
    })
    expect(staged.ok()).toBeTruthy()
  } else {
    const due = await request.patch(`${API_URL}/crm/applications/${track.id}`, {
      data: { follow_up_at: new Date(Date.now() - 24 * 3600000).toISOString() },
    })
    expect(due.ok()).toBeTruthy()
  }
  return track
}

test.describe('AL-07 to AL-12: My Applications', () => {
  test.beforeAll(async ({ request }) => {
    expect((await request.post(`${API_URL}/test/reset`)).ok()).toBeTruthy()
    expect((await request.post(`${API_URL}/test/seed`)).ok()).toBeTruthy()
    expect((await request.post(`${API_URL}/auth/dev-login`, { data: { email: 'test@jobgrid.dev' } })).ok()).toBeTruthy()
    const rows = await request.get(`${API_URL}/rows`, { params: { page_size: 5 } })
    expect(rows.ok()).toBeTruthy()
    const jobs = (await rows.json()).rows
    expect(jobs.length).toBeGreaterThanOrEqual(3)
    await makeTrack(request, jobs[0].id, 'interview')
    await makeTrack(request, jobs[1].id, 'offer')
    await makeTrack(request, jobs[2].id, 'opened')
  })

  test('AL-07: tabs use lifetime truth rather than current stage', async ({ page }) => {
    await page.goto('/applications?tab=applied')
    await expect(page.getByRole('tab', { name: 'Ever Applied' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tabpanel')).toBeVisible()
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(2)
    await expect(page.getByRole('tab', { name: 'All Tracked' })).toBeVisible()
    await page.getByRole('tab', { name: 'All Tracked' }).click()
    await expect(page).toHaveURL(/tab=all/)
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(3)
    await page.getByRole('tab', { name: 'Follow-ups Due' }).click()
    await expect(page).toHaveURL(/tab=followups/)
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(1)
    await page.reload()
    await expect(page.getByRole('tab', { name: 'Follow-ups Due' })).toHaveAttribute('aria-selected', 'true')
  })

  test('AL-08: account metrics are not page-only counts', async ({ page, request }) => {
    const response = await request.get(`${API_URL}/crm/analytics`)
    expect(response.ok()).toBeTruthy()
    const summary = await response.json()
    await page.goto('/applications?tab=applied&status=interview')
    const labels = [
      ['Lifetime applied', 'total_applied'],
      ['Current interviews', 'interviews'],
      ['Current offers', 'offers'],
      ['Follow-ups due', 'follow_ups_due'],
    ] as const
    for (const [label, key] of labels) {
      const card = page.locator('.stat-card').filter({ has: page.getByText(label, { exact: true }) })
      await expect(card.locator('strong')).toHaveText(String(summary[key]))
    }
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(1)
  })

  test('AL-09/10: sortable stage, date, updated time and reusable detail survive reload', async ({ page }) => {
    await page.goto('/applications?tab=applied')
    await expect(page.locator('.applications-table th')).toContainText(['', 'Company', 'Title', 'Status', 'Last updated', 'ATS', 'Bucket', 'Score', 'Opened At', 'Applied At', 'Follow-up', 'Notes', 'URL', 'Actions'])
    const first = page.locator('.applications-table tbody tr').first()
    await first.getByRole('button', { name: 'History, evidence & documents' }).click()
    await expect(page).toHaveURL(/track_id=\d+/)
    await expect(page.getByTestId('application-timeline')).toBeVisible()
    await page.reload()
    await expect(page.getByTestId('application-timeline')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Correct with reason' }).first()).toBeVisible()
  })

  test('AL-11: saved query, filters and export use matching scope', async ({ page }) => {
    await page.goto('/applications?tab=applied&view=42&status=interview&sort_by=applied_at&sort_dir=desc')
    await expect(page.getByRole('tab', { name: 'Ever Applied' })).toHaveAttribute('aria-selected', 'true')
    const exportBar = page.locator('.export-bar')
    await exportBar.locator('select').nth(1).selectOption('filtered')
    const out = page.waitForRequest((request) => request.url().includes('/crm/export/applications?'))
    await exportBar.getByRole('button', { name: 'Download' }).click()
    const query = new URL((await out).url()).searchParams
    expect(query.get('scope')).toBe('filtered')
    expect(query.get('applied_only')).toBe('true')
    expect(query.get('status')).toBe('interview')
    expect(query.get('sort_by')).toBe('applied_at')
    expect(query.has('page')).toBe(false)
    expect(query.has('tab')).toBe(false)
    await page.reload()
    await expect(page).toHaveURL(/view=42/)
    await expect(page.getByRole('tab', { name: 'Ever Applied' })).toHaveAttribute('aria-selected', 'true')
  })

  test('AL-12: application read failure offers retry, separate from account summary', async ({ page }) => {
    let fail = true
    await page.route('**/crm/applications?**', (route) => fail
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Temporary failure"}' })
      : route.continue())
    await page.goto('/applications?tab=all')
    await expect(page.getByRole('alert')).toContainText('Could not load applications')
    fail = false
    await page.getByRole('button', { name: 'Retry applications' }).click()
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(3)
  })

  test('AL-12: metrics failure is independently recoverable', async ({ page }) => {
    let fail = true
    await page.route('**/crm/analytics', (route) => fail
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Temporary failure"}' })
      : route.continue())
    await page.goto('/applications?tab=all')
    await expect(page.getByRole('alert')).toContainText('Could not load the account overview')
    await expect(page.locator('.applications-table tbody tr')).toHaveCount(3)
    fail = false
    await page.getByRole('button', { name: 'Retry overview' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.locator('.stat-card').filter({ hasText: 'Lifetime applied' }).locator('strong')).toHaveText('2')
  })

  test('AL-12: arrow navigation and mobile horizontal table keep controls accessible', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 })
    await page.goto('/applications?tab=applied')
    const applied = page.getByRole('tab', { name: 'Ever Applied' })
    await applied.focus()
    await applied.press('ArrowRight')
    await expect(page.getByRole('tab', { name: 'All Tracked' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('.applications-table')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Last updated' })).toBeVisible()
  })
})
