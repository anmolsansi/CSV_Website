import { test, expect } from '@playwright/test'

const cors = {
  'access-control-allow-origin': 'http://localhost:5173',
  'access-control-allow-credentials': 'true',
  'access-control-expose-headers': 'Retry-After, X-Render-Routing',
}

test('Render 429 on Archive shows an app-wide warning without retrying requests', async ({ page }) => {
  await page.clock.install()
  let requests = 0
  const consoleWarnings: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'warning' && message.text().includes('[JobGrid diagnostic]')) {
      consoleWarnings.push(message.text())
    }
  })
  await page.route(/\/rows(?:\?|$)/, async (route) => {
    requests += 1
    await route.fulfill({
      status: 429,
      headers: { ...cors, 'x-render-routing': 'hibernate-rate-limited', 'retry-after': '4' },
      contentType: 'text/plain',
      body: 'Too Many Requests',
    })
  })

  await page.goto('/archive')
  const banner = page.getByTestId('global-service-warning')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('hosting service is temporarily limiting requests')
  await expect(banner.getByRole('button', { name: 'Reload page' })).toBeDisabled()
  await expect(banner.getByTestId('retry-countdown')).toContainText('02:00')
  const initialRequests = requests
  expect(initialRequests).toBeGreaterThanOrEqual(1)
  await page.clock.fastForward(120_000)
  await expect(banner.getByTestId('retry-countdown')).toContainText('00:00')
  await expect(banner.getByRole('button', { name: 'Reload page' })).toBeEnabled()
  expect(requests).toBe(initialRequests) // No implicit GET retries
  expect(consoleWarnings.length).toBeGreaterThanOrEqual(1)
  await banner.getByRole('button', { name: 'Dismiss warning' }).click()
  await expect(banner).toHaveCount(0)
})

test('server 503 on Analytics renders a meaningful unavailable warning', async ({ page }) => {
  await page.clock.install()
  await page.route(/\/crm\/analytics(?:\?|$)/, (route) => route.fulfill({
    status: 503,
    headers: cors,
    contentType: 'text/plain',
    body: 'Service Unavailable',
  }))
  await page.goto('/analytics')
  const banner = page.getByTestId('global-service-warning')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('temporarily unavailable')
  await expect(banner.getByTestId('retry-countdown')).toContainText('02:00')
  await expect(banner.getByRole('button', { name: 'Reload page' })).toBeDisabled()
})
