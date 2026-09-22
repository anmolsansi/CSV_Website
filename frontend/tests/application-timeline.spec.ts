import { randomUUID } from 'node:crypto'
import { test, expect, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://localhost:8000'

async function resetAndLogin(request: APIRequestContext) {
  await request.post(`${API_URL}/test/reset`)
  await request.post(`${API_URL}/test/seed`)
  const login = await request.post(`${API_URL}/auth/dev-login`, {
    data: { email: 'test@jobgrid.dev' },
  })
  expect(login.ok()).toBeTruthy()
}

async function createAppliedTrack(request: APIRequestContext) {
  const rowsResponse = await request.get(`${API_URL}/rows`, {
    params: { page: 1, page_size: 1, sort_by: 'created_at', sort_dir: 'asc' },
  })
  expect(rowsResponse.ok()).toBeTruthy()
  const row = (await rowsResponse.json()).rows[0]
  expect(row).toBeTruthy()

  const created = await request.post(`${API_URL}/crm/from-row/${row.id}`)
  expect(created.ok()).toBeTruthy()
  const track = await created.json()

  const applied = await request.patch(`${API_URL}/crm/applications/${track.id}`, {
    data: { mark_applied: true },
  })
  expect(applied.ok()).toBeTruthy()
  return await applied.json()
}

async function addEvidence(request: APIRequestContext, trackId: number, body: string, occurredAt?: string) {
  const response = await request.post(`${API_URL}/crm/tracks/${trackId}/evidence`, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: {
      kind: 'confirmation_text',
      body,
      ...(occurredAt ? { occurred_at: occurredAt } : {}),
    },
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
}

test.describe('JG-035 application timeline', () => {
  test('apply_evidence_correct_reload', async ({ page, request }) => {
    await resetAndLogin(request)
    const track = await createAppliedTrack(request)

    await page.goto(`/applications?track_id=${track.id}`)
    const timeline = page.getByTestId('application-timeline')
    await expect(timeline).toBeVisible({ timeout: 15000 })

    await timeline.getByLabel('Evidence', { exact: true }).fill('Synthetic confirmation received')
    await timeline.getByRole('button', { name: 'Add evidence', exact: true }).click()
    await expect(timeline.getByText('Synthetic confirmation received', { exact: true })).toBeVisible()

    const corrected = new Date(new Date(track.applied_at).getTime() - 24 * 60 * 60 * 1000)
    await timeline.getByLabel('Corrected applied date').fill(corrected.toISOString().slice(0, 16))
    await timeline.getByLabel('Reason', { exact: true }).first().fill('Recorded the wrong day during testing')
    await expect(timeline.getByTestId('applied-date-preview')).toContainText('Daily application metrics will move')
    await timeline.getByRole('button', { name: 'Correct applied date', exact: true }).click()
    await expect(timeline.getByText(/Applied date corrected/)).toBeVisible({ timeout: 10000 })

    await page.reload()
    await expect(page.getByTestId('application-timeline')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Synthetic confirmation received', { exact: true })).toBeVisible()
    await expect(page.getByText(/Applied date corrected/)).toBeVisible()
  })

  test('unknown_import_date_label and script_like_text_rendered_literally', async ({ page, request }) => {
    await resetAndLogin(request)
    const track = await createAppliedTrack(request)
    const literal = '<script>window.__jg035_injected = true</script>'
    const evidence = await addEvidence(request, track.id, literal)

    await page.goto(`/applications?track_id=${track.id}`)
    const item = page.getByTestId(`timeline-item-evidence-${evidence.id}`)
    await expect(item).toBeVisible({ timeout: 15000 })
    await expect(item.getByTestId('timeline-event-date')).toHaveText('Unknown')
    await expect(item.getByTestId('timeline-body')).toHaveText(literal)
    await expect(page.locator('script').filter({ hasText: '__jg035_injected' })).toHaveCount(0)
    expect(await page.evaluate(() => (window as any).__jg035_injected || false)).toBe(false)
  })

  test('stale_edit_draft_preserved', async ({ page, request }) => {
    await resetAndLogin(request)
    const track = await createAppliedTrack(request)
    const evidence = await addEvidence(request, track.id, 'Original evidence')

    await page.goto(`/applications?track_id=${track.id}`)
    const item = page.getByTestId(`timeline-item-evidence-${evidence.id}`)
    await expect(item).toBeVisible({ timeout: 15000 })
    await item.getByRole('button', { name: 'Edit evidence' }).click()
    const editor = item.getByLabel('Edit evidence')
    await editor.fill('My unsaved local draft')

    const concurrent = await request.patch(`${API_URL}/crm/tracks/${track.id}/evidence/${evidence.id}`, {
      headers: { 'X-Operation-ID': randomUUID() },
      data: { version: evidence.version, body: 'Concurrent server edit' },
    })
    expect(concurrent.ok()).toBeTruthy()

    await item.getByRole('button', { name: 'Save edit' }).click()
    await expect(page.getByTestId('timeline-conflict')).toContainText('draft is preserved')
    await expect(editor).toHaveValue('My unsaved local draft')
  })
})
