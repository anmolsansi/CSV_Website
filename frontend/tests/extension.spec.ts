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


// EXT-41–44: only disposable Chromium profiles and a local authenticated API.
// These tests deliberately pregrant optional hosts in the *copied* manifest,
// never the shipped development or release manifests.
async function withRealExtension(
  callback: (env: { context: Awaited<ReturnType<typeof chromium.launchPersistentContext>>,
    app: Page, popup: Page, extensionId: string,
    restart: () => Promise<Awaited<ReturnType<typeof chromium.launchPersistentContext>>> }) => Promise<void>,
) {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'jobgrid-ext-acceptance-'))
  const extensionPath = path.join(workspace, 'extension')
  const profile = path.join(workspace, 'profile')
  let context: Awaited<ReturnType<typeof chromium.launchPersistentContext>> | undefined
  const launch = () => chromium.launchPersistentContext(profile, {
    headless: true, channel: 'chromium',
    args: ['--disable-extensions-except=' + extensionPath, '--load-extension=' + extensionPath],
  })
  try {
    await fs.cp(SOURCE, extensionPath, { recursive: true })
    const manifest = JSON.parse(await fs.readFile(path.join(extensionPath, 'manifest.dev.json'), 'utf8'))
    const hosts = ['http://localhost:5173/*', 'https://jobs.lever.co/*']
    for (const host of hosts) expect(manifest.optional_host_permissions).toContain(host)
    manifest.host_permissions = hosts
    manifest.optional_host_permissions = manifest.optional_host_permissions
      .filter((host: string) => !hosts.includes(host))
    await fs.writeFile(path.join(extensionPath, 'manifest.json'), JSON.stringify(manifest))
    await overlayOrigin(path.join(extensionPath, 'config.js'),
      "parseTrustedOrigin('" + RELEASE_ORIGIN + "')",
      "parseTrustedOrigin('" + ORIGIN + "', { allowLocal: true })")
    await overlayOrigin(path.join(extensionPath, 'jobgrid-bridge.js'),
      "const TRUSTED_ORIGIN = '" + RELEASE_ORIGIN + "'",
      "const TRUSTED_ORIGIN = '" + ORIGIN + "'")
    await overlayOrigin(path.join(extensionPath, 'background.js'),
      "const APP_ORIGIN = '" + RELEASE_ORIGIN + "'",
      "const APP_ORIGIN = '" + ORIGIN + "'")
    context = await launch()
    const worker = context.serviceWorkers()[0] ||
      await context.waitForEvent('serviceworker', { timeout: 15000 })
    const extensionId = new URL(worker.url()).hostname
    const app = await context.newPage()
    await app.goto(ORIGIN)
    const popup = await context.newPage()
    await popup.goto('chrome-extension://' + extensionId + '/popup.dev.html')
    await callback({ context, app, popup, extensionId, restart: async () => {
      await context?.close()
      context = await launch()
      return context
    } })
  } finally {
    await context?.close()
    await fs.rm(workspace, { recursive: true, force: true })
  }
}

async function extCommand(popup: Page, type: string, extra: Record<string, unknown> = {}) {
  return popup.evaluate(async ({ type, extra }) => {
    const request_id = crypto.randomUUID()
    const response = await (globalThis as any).chrome.runtime.sendMessage({
      type, version: 1, request_id, ...extra,
    })
    if (response?.request_id !== request_id || response?.version !== 1)
      throw Error('Extension command response envelope mismatch')
    return response
  }, { type, extra })
}

async function tabIdFor(popup: Page, url: string): Promise<number> {
  return popup.evaluate(async value => {
    const tabs = await (globalThis as any).chrome.tabs.query({})
    const matches = tabs.filter((t: any) => t.url === value)
    if (matches.length !== 1) throw Error('Expected exactly one matching tab')
    return matches[0].id as number
  }, url)
}

async function connectRealExtension(popup: Page, app: Page, owner: number) {
  const tab_id = await tabIdFor(popup, app.url())
  const result = await extCommand(popup, 'ext26:connect', { tab_id })
  expect(result.ok, JSON.stringify(result.error)).toBe(true)
  expect(result.data.account_id).toBe(owner)
}

async function checkedVisit(app: Page, url: string) {
  const response = await app.evaluate(async value => {
    const res = await fetch('/api/crm/browser-memory/check', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: value, company: 'Acme Labs', title: 'Platform Engineer' }),
    })
    return { status: res.status, data: await res.json() }
  }, url)
  expect(response.status).toBe(200)
  return response.data
}

async function openObservedJob(
  context: Awaited<ReturnType<typeof chromium.launchPersistentContext>>,
  popup: Page, url: string,
) {
  await context.route('https://jobs.lever.co/**', route => route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><html><body><div class="posting-headline">' +
      '<h2>Platform Engineer</h2><span class="company">Acme Labs</span></div>' +
      '<form><input name="secret" value="private-form-value"></form></body></html>',
  }))
  const permission = await extCommand(popup, 'ext30:site-opt-in',
    { host: 'jobs.lever.co', enabled: true })
  expect(permission.ok, JSON.stringify(permission.error)).toBe(true)
  const job = await context.newPage()
  await job.goto(url)
  const jobTab = await tabIdFor(popup, url)
  await expect.poll(async () => {
    const state = await extCommand(popup, 'ext32:tab-status', { tab_id: jobTab })
    return state.ok ? state.data.save_state : null
  }, { timeout: 20000 }).toBe('saved')
  return { job, jobTab }
}

test('EXT-41 local API: first visit is not previous; explicit apply is durable and canonical revisit preserves timestamps', async () => {
  test.setTimeout(150_000)
  await withRealExtension(async ({ context, app, popup }) => {
    const owner = await signIn(app, 'ext41-' + crypto.randomUUID() + '@example.test')
    await connectRealExtension(popup, app, owner)
    const url = 'https://jobs.lever.co/acmelabs/' + crypto.randomUUID().replaceAll('-', '')
    const { job, jobTab } = await openObservedJob(context, popup, url)
    const first = await extCommand(popup, 'ext32:tab-status', { tab_id: jobTab })
    expect(first.ok).toBe(true)
    expect(first.data.account_id).toBe(owner)
    expect(first.data.before_visit.visit).toEqual({ visited: false, first_visited_at: null })
    expect(first.data.save_state).toBe('saved')
    const visited = await checkedVisit(app, url)
    expect(visited.visit.visited).toBe(true)
    expect(visited.visit.first_visited_at).toMatch(/Z$/)
    expect(visited.matches).toEqual([])
    const staged = await extCommand(popup, 'ext34:stage-apply', {
      tab_id: jobTab, company: 'Acme Labs', title: 'Platform Engineer',
    })
    expect(staged.ok, JSON.stringify(staged.error)).toBe(true)
    await job.bringToFront()
    const saved = await extCommand(popup, 'ext39:submit-pending', { tab_id: jobTab })
    expect(saved.ok, JSON.stringify(saved.error)).toBe(true)
    expect(saved.data).toMatchObject({ saved: true, account_id: owner, url })
    const applied = await checkedVisit(app, url)
    expect(applied.matches).toHaveLength(1)
    expect(applied.matches[0].confidence).toBe('exact')
    await job.reload()
    await expect.poll(async () => {
      const state = await extCommand(popup, 'ext32:tab-status', { tab_id: jobTab })
      return state.ok && state.data.before_visit.visit.visited === true &&
        state.data.before_visit.matches[0]?.confidence === 'exact'
    }, { timeout: 20000 }).toBe(true)
    const canonical = await checkedVisit(app, url + '?utm_source=synthetic')
    expect(canonical.visit.first_visited_at).toBe(visited.visit.first_visited_at)
    expect(canonical.matches[0].track_id).toBe(applied.matches[0].track_id)
    expect(canonical.matches[0].applied_at).toBe(applied.matches[0].applied_at)
  })
})
