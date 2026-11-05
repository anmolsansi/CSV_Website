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


test('EXT-42 foreign account and hostile page cannot reuse selected extension memory or issue writes', async () => {
  test.setTimeout(150_000)
  await withRealExtension(async ({ context, app, popup }) => {
    const a = 'ext42-a-' + crypto.randomUUID() + '@example.test'
    const b = 'ext42-b-' + crypto.randomUUID() + '@example.test'
    const ownerA = await signIn(app, a)
    await connectRealExtension(popup, app, ownerA)
    const url = 'https://jobs.lever.co/acmelabs/' + crypto.randomUUID().replaceAll('-', '')
    const { job, jobTab } = await openObservedJob(context, popup, url)
    const prior = await checkedVisit(app, url)
    expect(prior.account_id).toBe(ownerA)
    expect(prior.visit.visited).toBe(true)
    expect(prior.matches).toEqual([])

    // Page-world and subframe postMessage traffic is not a privileged popup
    // sender. No page DOM, storage or message receiver ever receives matches.
    const pageState = await job.evaluate(async () => {
      const message = {
        type: 'ext39:submit-pending', version: 1, request_id: crypto.randomUUID(),
        tab_id: 1, account_id: 1, payload: { confirmed: true },
      }
      const received: unknown[] = []
      const listener = (event: MessageEvent) => {
        if (event.source === window) received.push(event.data)
      }
      window.addEventListener('message', listener)
      window.postMessage(message, '*')
      const frame = document.createElement('iframe')
      frame.srcdoc = '<script>parent.postMessage({type:"ext26:command",kind:"apply"}, "*")<\/script>'
      document.body.append(frame)
      await new Promise(resolve => setTimeout(resolve, 100))
      window.removeEventListener('message', listener)
      return {
        messages: received,
        body: document.body.innerText,
        localKeys: Object.keys(localStorage),
        sessionKeys: Object.keys(sessionStorage),
        hasExtensionRuntime: typeof (window as any).chrome?.runtime?.sendMessage === 'function',
      }
    })
    expect(pageState.messages.some((value: any) => value?.ok === true ||
      value?.data?.matches)).toBe(false)
    expect(pageState.body).not.toContain('JobGrid account')
    expect(pageState.body).not.toContain('Applied to this company')
    expect(pageState.localKeys.filter((key: string) => /jobgrid/i.test(key))).toEqual([])
    expect(pageState.sessionKeys.filter((key: string) => /jobgrid/i.test(key))).toEqual([])
    expect(pageState.hasExtensionRuntime).toBe(false)

    const draft = await extCommand(popup, 'ext34:stage-apply', {
      tab_id: jobTab, company: 'Acme Labs', title: 'Platform Engineer',
    })
    expect(draft.ok).toBe(true)
    const ownerB = await signIn(app, b)
    expect(ownerB).not.toBe(ownerA)
    await job.bringToFront()
    const rejected = await extCommand(popup, 'ext39:submit-pending', { tab_id: jobTab })
    expect(rejected.ok).toBe(false)
    expect(['account_changed', 'not_connected', 'no_check', 'unavailable']).toContain(rejected.error.code)
    const foreign = await checkedVisit(app, url)
    expect(foreign.account_id).toBe(ownerB)
    expect(foreign.visit).toEqual({ visited: false, first_visited_at: null })
    expect(foreign.matches).toEqual([])
    await signIn(app, a)
    const restoredA = await checkedVisit(app, url)
    expect(restoredA.visit.first_visited_at).toBe(prior.visit.first_visited_at)
    expect(restoredA.matches).toEqual([])
  })
})


test('EXT-43 development popup exposes labels, live feedback and keyboard focus at 200% zoom', async () => {
  test.setTimeout(150_000)
  await withRealExtension(async ({ context, app, popup }) => {
    const owner = await signIn(app, 'ext43-' + crypto.randomUUID() + '@example.test')
    await connectRealExtension(popup, app, owner)
    const url = 'https://jobs.lever.co/acmelabs/' + crypto.randomUUID().replaceAll('-', '')
    const { job } = await openObservedJob(context, popup, url)
    await popup.reload()
    await expect(popup.locator('#check')).toBeEnabled()
    await expect(popup.locator('#connection')).toHaveAttribute('aria-live', 'polite')
    await expect(popup.locator('#feedback')).toHaveAttribute('aria-live', 'polite')
    await expect(popup.locator('#result')).toHaveAttribute('aria-live', 'polite')
    await expect(popup.getByLabel('Employer')).toHaveAttribute('required', '')
    await expect(popup.getByLabel('Job title')).toHaveAttribute('required', '')
    await expect(popup.locator('label[for="forget-phrase"]')).toContainText('FORGET VISITS')
    for (const id of ['connect', 'pause', 'disconnect', 'forget', 'check', 'stage', 'submit-apply']) {
      await expect(popup.locator('#' + id)).toHaveAttribute('type', id === 'stage' ? 'submit' : 'button')
    }
    // A real action-popup does not become a browser tab. For this Playwright
    // harness the extension page is a tab, so dispatch its click while the
    // public job tab remains the active tab for activeTab authorization.
    await job.bringToFront()
    await popup.evaluate(() => (document.getElementById('check') as HTMLButtonElement).click())
    await expect(popup.locator('#apply-section')).toBeVisible({ timeout: 15000 })
    await expect(popup.locator('#feedback')).toContainText('Check complete')
    await expect(popup.locator('#result-detail')).not.toContainText('never applied')
    await popup.getByLabel('Employer').fill('Acme Labs')
    await popup.getByLabel('Job title').fill('Platform Engineer')
    await popup.locator('#apply-company').focus()
    await popup.keyboard.press('Tab')
    await expect(popup.locator('#apply-title')).toBeFocused()
    await job.bringToFront()
    await popup.evaluate(() => (document.getElementById('draft-form') as HTMLFormElement).requestSubmit())
    await expect(popup.locator('#approval')).toBeVisible()
    await expect(popup.locator('#draft-error')).toContainText('Review')
    await expect(popup.locator('#submit-apply')).toBeDisabled()
    await popup.locator('#confirm-apply').check()
    await expect(popup.locator('#submit-apply')).toBeEnabled()
    await popup.locator('#confirm-apply').uncheck()
    await expect(popup.locator('#submit-apply')).toBeDisabled()

    await popup.setViewportSize({ width: 400, height: 700 })
    await popup.evaluate(() => { document.body.style.zoom = '200%' })
    const dimensions = await popup.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }))
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport)
    await expect(popup.locator('#apply-company')).toBeVisible()
    await expect(popup.locator('#submit-apply')).toBeVisible()
    await expect(popup.locator('#result-title')).not.toBeEmpty()
    // All facts and errors are text and live-region content, never badge-only.
    expect(await popup.locator('[role="status"]').count()).toBeGreaterThan(0)
  })
})


test('EXT-44 offline failure, navigation, opt-out and full profile restart fail closed', async () => {
  test.setTimeout(150_000)
  await withRealExtension(async ({ context, app, popup, extensionId, restart }) => {
    const owner = await signIn(app, 'ext44-' + crypto.randomUUID() + '@example.test')
    await connectRealExtension(popup, app, owner)
    const url = 'https://jobs.lever.co/acmelabs/' + crypto.randomUUID().replaceAll('-', '')
    const { job, jobTab } = await openObservedJob(context, popup, url)
    const stored = await checkedVisit(app, url)
    expect(stored.visit.visited).toBe(true)
    await job.bringToFront()
    await context.setOffline(true)
    const offline = await extCommand(popup, 'ext33:current-tab-check')
    expect(offline.ok).toBe(false)
    expect(['unavailable', 'timeout', 'protocol_error', 'not_authenticated',
      'account_changed']).toContain(offline.error.code)
    // An offline failure cannot fabricate "no recorded application" or a
    // successful second visit. Existing server history is checked after recovery.
    await context.setOffline(false)
    const durable = await checkedVisit(app, url)
    expect(durable.visit.first_visited_at).toBe(stored.visit.first_visited_at)

    await job.goto('https://jobs.lever.co/acmelabs')
    const stale = await extCommand(popup, 'ext32:tab-status', { tab_id: jobTab })
    expect(stale.ok).toBe(false)
    expect(['no_check', 'stale_tab', 'not_connected']).toContain(stale.error.code)
    const disabled = await extCommand(popup, 'ext30:site-opt-in',
      { host: 'jobs.lever.co', enabled: false })
    expect(disabled.ok).toBe(true)
    expect(disabled.data.opted_in).toBe(false)
    await job.goto(url)
    await job.waitForTimeout(850)
    const silent = await extCommand(popup, 'ext32:tab-status', { tab_id: jobTab })
    expect(silent.ok).toBe(false)
    const unchanged = await checkedVisit(app, url)
    expect(unchanged.visit.first_visited_at).toBe(stored.visit.first_visited_at)

    // Closing the persistent profile is stronger than a worker wake-up:
    // no private result, active account binding or staged command may be
    // replayed by the newly created extension service worker.
    const fresh = await restart()
    const serviceWorker = fresh.serviceWorkers()[0] ||
      await fresh.waitForEvent('serviceworker', { timeout: 15000 })
    expect(new URL(serviceWorker.url()).hostname).toBe(extensionId)
    const freshPopup = await fresh.newPage()
    await freshPopup.goto('chrome-extension://' + extensionId + '/popup.dev.html')
    const disconnected = await extCommand(freshPopup, 'ext35:status')
    expect(disconnected.ok).toBe(true)
    expect(disconnected.data.connected).toBe(false)
    const storage = await freshPopup.evaluate(async () =>
      (globalThis as any).chrome.storage.session.get(['jobgridTabChecks', 'jobgridConnection']))
    expect(storage.jobgridTabChecks).toBeUndefined()
    expect(storage.jobgridConnection).toBeUndefined()
    const unauthorised = await extCommand(freshPopup, 'ext39:submit-pending', { tab_id: jobTab })
    expect(unauthorised.ok).toBe(false)
    expect(['not_connected', 'no_check']).toContain(unauthorised.error.code)
  })
})
