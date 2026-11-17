import { test, expect } from '@playwright/test'

const cors = {
  'access-control-allow-origin': 'http://localhost:5173',
  'access-control-allow-credentials': 'true',
  'access-control-expose-headers': 'Retry-After',
}

test('health request starts before auth and holds session loading until 200', async ({ page }) => {
  let releaseHealth: (() => void) | null = null
  let healthCount = 0
  let authCount = 0
  const backendRequests: string[] = []

  await page.route('http://localhost:8000/health', async (route) => {
    backendRequests.push('health')
    healthCount += 1
    await new Promise<void>((resolve) => { releaseHealth = resolve })
    await route.fulfill({
      status: 200,
      headers: cors,
      contentType: 'application/json',
      body: '{"status":"ok"}',
    })
  })
  await page.route('**/auth/me', async (route) => {
    backendRequests.push('me')
    authCount += 1
    await route.fulfill({
      status: 401,
      headers: cors,
      contentType: 'application/json',
      body: '{"detail":"Not authenticated"}',
    })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Starting JobGrid' })).toBeVisible()
  expect(healthCount).toBe(1)
  expect(authCount).toBe(0)
  releaseHealth?.()

  await expect(page.getByRole('heading', { name: 'Log in or sign up' })).toBeVisible()
  expect(backendRequests[0]).toBe('health')
  expect(healthCount).toBe(1) // StrictMode must not initiate a second health GET
  expect(authCount).toBeGreaterThanOrEqual(1)
})

test('health 429 prevents session calls and requires a manual retry', async ({ page }) => {
  let healthCount = 0
  let authCount = 0
  let allowRecovery = false

  await page.route('http://localhost:8000/health', async (route) => {
    healthCount += 1
    if (!allowRecovery) {
      await route.fulfill({
        status: 429,
        headers: { ...cors, 'retry-after': '2' },
        contentType: 'text/plain',
        body: 'Too Many Requests',
      })
      return
    }
    await route.fulfill({
      status: 200,
      headers: cors,
      contentType: 'application/json',
      body: '{"status":"ok"}',
    })
  })
  await page.route('**/auth/me', async (route) => {
    authCount += 1
    await route.fulfill({ status: 401, headers: cors, body: '{"detail":"Not authenticated"}', contentType: 'application/json' })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'JobGrid backend not ready' })).toBeVisible()
  await expect(page.getByText('Health response: HTTP 429.')).toBeVisible()
  const retry = page.getByRole('button', { name: 'Retry backend connection' })
  await expect(retry).toBeDisabled()
  await page.waitForTimeout(450)
  expect(healthCount).toBe(1)
  expect(authCount).toBe(0)
  await expect(retry).toBeEnabled({ timeout: 10_000 })
  expect(healthCount).toBe(1) // No automatic retry or keepalive
  allowRecovery = true
  await retry.click()
  await expect(page.getByRole('heading', { name: 'Log in or sign up' })).toBeVisible()
  expect(healthCount).toBe(2)
  expect(authCount).toBeGreaterThanOrEqual(1)
})

test('unverifiable cross-origin health response does not trigger auth or a retry storm', async ({ page }) => {
  let healthCount = 0
  let authCount = 0
  await page.route('http://localhost:8000/health', async (route) => {
    healthCount += 1
    await route.abort('failed')
  })
  await page.route('**/auth/me', async (route) => {
    authCount += 1
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'JobGrid backend not ready' })).toBeVisible()
  await expect(page.getByText(/could not confirm the backend is healthy/i)).toBeVisible()
  await page.waitForTimeout(600)
  expect(healthCount).toBe(1)
  expect(authCount).toBe(0)
})
