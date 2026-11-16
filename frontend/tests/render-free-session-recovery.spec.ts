import { test, expect } from '@playwright/test'

test('Render 429 on session check does not impersonate a logout or flood the API', async ({ page }) => {
  let checks = 0
  let allowRecovery = false
  await page.route('**/auth/me', async (route) => {
    checks += 1
    // Vite development builds mount effects twice under React.StrictMode.
    // Keep every initial session check throttled until the user explicitly retries.
    if (!allowRecovery) {
      await route.fulfill({
        status: 429,
        headers: {
          'x-render-routing': 'hibernate-rate-limited',
          'retry-after': '2',
          // CI calls localhost:8000 from localhost:5173: expose these non-safelisted headers.
          'access-control-allow-origin': 'http://localhost:5173',
          'access-control-allow-credentials': 'true',
          'access-control-expose-headers': 'Retry-After, X-Render-Routing',
        },
        contentType: 'text/plain',
        body: 'Too Many Requests',
      })
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'test@jobgrid.dev' }),
      })
    }
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'JobGrid connection unavailable' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Log in or sign up' })).toHaveCount(0)
  const retry = page.getByRole('button', { name: 'Retry connection' })
  await expect(retry).toBeDisabled()
  await page.waitForTimeout(500)
  const initialChecks = checks
  expect(initialChecks).toBeGreaterThanOrEqual(1)
  await expect(retry).toBeEnabled({ timeout: 10_000 })
  expect(checks).toBe(initialChecks) // No automatic retry
  allowRecovery = true
  await retry.click()
  await expect(page.getByText('test@jobgrid.dev', { exact: true })).toBeVisible()
  expect(checks).toBe(initialChecks + 1) // Exactly one user-directed retry
})

test('real unauthenticated session still renders the normal login flow', async ({ page }) => {
  await page.route('**/auth/me', async (route) => {
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}' })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Log in or sign up' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'JobGrid connection unavailable' })).toHaveCount(0)
})
