import { test, expect } from '@playwright/test'

const API_URL = 'http://localhost:8000'

test.describe('Job freshness', () => {
  test('manual_deadline_close_reopen', async ({ page, request }) => {
    await request.post(`${API_URL}/test/reset`)
    await request.post(`${API_URL}/test/seed`)
    const login = await request.post(`${API_URL}/auth/dev-login`, {
      data: { email: 'test@jobgrid.dev' },
    })
    expect(login.ok()).toBeTruthy()

    const rowsResponse = await request.get(`${API_URL}/rows`, {
      params: { sort_by: 'created_at', sort_dir: 'desc', page: 1, page_size: 1 },
    })
    expect(rowsResponse.ok()).toBeTruthy()
    const rows = (await rowsResponse.json()).rows || []
    expect(rows.length).toBeGreaterThan(0)

    const createApplication = await request.post(`${API_URL}/crm/from-rows/bulk`, {
      data: { row_ids: [rows[0].id] },
    })
    expect(createApplication.ok()).toBeTruthy()

    await page.goto('/applications')
    await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible()
    const firstApplicationRow = page.locator('tbody tr').first()
    await firstApplicationRow
      .getByRole('button', { name: 'History, evidence & documents' })
      .click({ force: true })

    const availability = page.getByTestId('job-availability')
    await expect(availability).toBeVisible()
    await expect(availability.getByTestId('manual-freshness-fallback')).toContainText(
      'Automatic link checks are off',
    )
    await expect(availability.getByTestId('deadline-timezone-note')).toContainText('UTC')
    await expect(availability.getByTestId('availability-label')).toHaveText('Status unknown')
    await expect(availability.getByRole('button', { name: 'Check link' })).toHaveCount(0)

    const todayDate = new Date().toISOString().slice(0, 10)
    await availability.locator('input[type="date"]').fill(todayDate)
    await availability.getByRole('button', { name: 'Save deadline' }).click()
    await expect(availability.getByRole('status')).toContainText('Deadline saved')

    await page.goto('/today')
    await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible()
    const deadlineRow = page.getByRole('row', { name: /Review application deadline/ })
    await expect(deadlineRow).toBeVisible()
    await expect(deadlineRow).toContainText('Status unknown')
    await expect(deadlineRow.getByRole('button', { name: 'Complete' })).toHaveCount(0)

    await deadlineRow.getByRole('button', { name: 'Snooze' }).click()
    const snoozeDialog = page.getByRole('dialog', { name: 'Snooze action' })
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
    const pad = (value: number) => String(value).padStart(2, '0')
    const localTomorrow = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T${pad(tomorrow.getHours())}:${pad(tomorrow.getMinutes())}`
    await snoozeDialog.locator('input[type="datetime-local"]').fill(localTomorrow)
    await snoozeDialog.getByRole('button', { name: 'Save' }).click()
    await expect(deadlineRow).toHaveCount(0)

    await page.goto('/applications')
    await page.locator('tbody tr').first()
      .getByRole('button', { name: 'History, evidence & documents' })
      .click({ force: true })
    const reopenedAvailability = page.getByTestId('job-availability')
    await expect(reopenedAvailability.getByTestId('availability-label')).toHaveText('Status unknown')

    page.once('dialog', (dialog) => dialog.accept())
    await reopenedAvailability.getByRole('button', { name: 'Mark closed' }).click()
    await expect(reopenedAvailability.getByTestId('availability-label')).toHaveText('Closed by you')
    await expect(reopenedAvailability.getByRole('status')).toContainText('Marked closed by you')

    page.once('dialog', (dialog) => dialog.accept())
    await reopenedAvailability.getByRole('button', { name: 'Reopen' }).click()
    await expect(reopenedAvailability.getByTestId('availability-label')).toHaveText('Status unknown')
    await expect(reopenedAvailability.getByRole('status')).toContainText('Reopened as status unknown')

    const finalState = await request.get(
      `${API_URL}/crm/jobs/${rows[0].id}/availability`,
    )
    expect(finalState.ok()).toBeTruthy()
    const finalData = await finalState.json()
    expect(finalData.state).toBe('unknown')
    expect(finalData.confirmed_closed_at).toBeNull()
    expect(finalData.deadline_local_date).toBe(todayDate)
  })


  test('timezone_label_visible', async ({ page, request }) => {
    await request.post(`${API_URL}/test/reset`)
    await request.post(`${API_URL}/test/seed`)

    await page.goto('/')
    const firstRow = page.locator('tbody tr').first()
    await expect(firstRow).toBeVisible()
    await firstRow.click({ force: true })

    const availability = page.getByTestId('job-availability')
    await expect(availability).toBeVisible()
    await expect(availability.getByTestId('deadline-timezone-note')).toContainText(
      'UTC',
    )
    await expect(availability.locator('input[type="date"]')).toBeVisible()
  })
})
