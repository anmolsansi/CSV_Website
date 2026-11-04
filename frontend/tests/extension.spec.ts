/**
 * EXT-05: disposable, real Chromium extension → Vite proxy → FastAPI session spike.
 *
 * Requires TEST_AUTH on a disposable backend at localhost:8000. No mocked fetch,
 * production accounts, installed release extensions, or recorded private history.
 */
import { chromium, expect, test, type Page } from '@playwright/test'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ORIGIN = 'http://localhost:5173'
const RELEASE_ORIGIN = 'https://csv-website-steel.vercel.app'
const SOURCE = fileURLToPath(new URL('../../extension/', import.meta.url))

async function overlayOrigin(file: string, before: string, after: string) {
  const source = await fs.readFile(file, 'utf8')
  if (!source.includes(before)) throw new Error(`Missing origin fixture anchor in ${path.basename(file)}`)
  await fs.writeFile(file, source.replace(before, after))
}

async function signIn(page: Page, email: string): Promise<number> {
  const response = await page.evaluate(async (value) => {
    const result = await fetch('/api/auth/dev-login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: value }),
    })
    return { status: result.status, body: await result.json() }
  }, email)
  expect(response.status).toBe(200)
  expect(response.body.id).toBeGreaterThan(0)
  return response.body.id
}

test('EXT-05 real tab bridge follows account switch and fails closed on logout/tab close', async () => {
  test.setTimeout(90_000)
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'jobgrid-ext05-'))
  const extensionPath = path.join(workspace, 'extension')
  const userDataDir = path.join(workspace, 'profile')
  let context: Awaited<ReturnType<typeof chromium.launchPersistentContext>> | undefined
  try {
    await fs.cp(SOURCE, extensionPath, { recursive: true })
    // Headless CI cannot approve Chrome's browser-owned permission bubble.
    // Pregrant only disposable localhost in the *temporary fixture* manifest.
    // The checked-in dev/release manifests retain their optional-only grants.
    const fixtureManifest = JSON.parse(
      await fs.readFile(path.join(extensionPath, 'manifest.dev.json'), 'utf8'),
    )
    const localhostHost = 'http://localhost:5173/*'
    expect(fixtureManifest.optional_host_permissions).toContain(localhostHost)
    fixtureManifest.optional_host_permissions =
      fixtureManifest.optional_host_permissions.filter((host: string) => host !== localhostHost)
    fixtureManifest.host_permissions = [localhostHost]
    await fs.writeFile(
      path.join(extensionPath, 'manifest.json'),
      JSON.stringify(fixtureManifest, null, 2),
    )
    await overlayOrigin(
      path.join(extensionPath, 'config.js'),
      `parseTrustedOrigin('${RELEASE_ORIGIN}')`,
      `parseTrustedOrigin('${ORIGIN}', { allowLocal: true })`,
    )
    await overlayOrigin(
      path.join(extensionPath, 'jobgrid-bridge.js'),
      `const TRUSTED_ORIGIN = '${RELEASE_ORIGIN}'`,
      `const TRUSTED_ORIGIN = '${ORIGIN}'`,
    )
    await overlayOrigin(
      path.join(extensionPath, 'background.js'),
      `const APP_ORIGIN = '${RELEASE_ORIGIN}'`,
      `const APP_ORIGIN = '${ORIGIN}'`,
    )

    context = await chromium.launchPersistentContext(userDataDir, {
      headless: true,
      channel: 'chromium', // modern headless Chromium supports MV3 extension workers
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    })
    const worker = context.serviceWorkers()[0] ||
      await context.waitForEvent('serviceworker', { timeout: 15000 })
    const extensionId = new URL(worker.url()).hostname

    const appPage = await context.newPage()
    await appPage.goto(ORIGIN)
    const popup = await context.newPage()
    await popup.goto(`chrome-extension://${extensionId}/popup.html`)

    // The worker still checks actual granted host rights in Chromium. The
    // runtime grant UX requires a separate unrestricted manual Chrome check.
    await expect.poll(
      () => popup.evaluate(() => (globalThis as any).chrome.permissions.contains({
        origins: ['http://localhost:5173/*'],
      })),
      { timeout: 10000 },
    ).toBe(true)

    async function probe(): Promise<any> {
      return popup.evaluate(() => (globalThis as any).chrome.runtime.sendMessage({
        type: 'ext05:session-probe',
      }))
    }

    const emailA = `ext05-a-${crypto.randomUUID()}@example.test`
    const emailB = `ext05-b-${crypto.randomUUID()}@example.test`
    const idA = await signIn(appPage, emailA)
    const first = await probe()
    expect(first.ok).toBe(true)
    expect(first.data).toEqual({
      protocol_version: 1,
      account_id: idA,
      account_label: `JobGrid account ${idA}`,
    })

    const idB = await signIn(appPage, emailB)
    expect(idB).not.toBe(idA)
    const second = await probe()
    expect(second.ok).toBe(true)
    expect(second.data.account_id).toBe(idB)
    expect(second.data.account_label).toBe(`JobGrid account ${idB}`)

    const logout = await appPage.evaluate(async () =>
      (await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
      })).status)
    expect(logout).toBe(200)
    const signedOut = await probe()
    expect(signedOut.ok).toBe(false)
    expect(signedOut.error.code).toBe('not_authenticated')
    expect(signedOut.data).toBeUndefined()

    await appPage.close()
    const missingTab = await probe()
    expect(missingTab.ok).toBe(false)
    expect(missingTab.error.code).toBe('unavailable')
    expect(missingTab.data).toBeUndefined()
  } finally {
    if (context) await context.close()
    await fs.rm(workspace, { recursive: true, force: true })
  }
})
