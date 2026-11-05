import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../background.js', import.meta.url), 'utf8')
const UUID = '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc'
const APP = 'https://csv-website-steel.vercel.app'
const JOB = 'https://jobs.lever.co/acme/role-123'
const POPUP = { id: 'ext-test', url: 'chrome-extension://ext-test/popup.html',
  origin: 'chrome-extension://ext-test', frameId: 0 }
const packet = (type, extra = {}) => ({ type, version: 1, request_id: UUID, ...extra })
const res = (id, extras = {}) => ({ version: 1, request_id: UUID, ok: true,
  data: { protocol_version: 1, account_id: id, ...extras } })

export function createWorker() {
  const permissions = new Set([APP + '/*'])
  const scripts = new Map()
  const requested = []
  const storageLocal = {}
  const storageSession = {}
  const badges = new Map()
  const tabs = new Map([
    [1, { id: 1, url: APP + '/dashboard', status: 'complete' }],
    [2, { id: 2, url: JOB, status: 'complete' }],
  ])
  let listener, updated, removed, permissionRemoved
  let activeAccount = 101
  const behavior = { checkFailure: false, visitFailure: false, applyFailureOnce: false, alreadyVisited: false, candidateFailure: false }
  const calls = []
  const scriptOperations = []
  const chrome = {
    action: { setBadgeText: async ({ tabId, text }) => { badges.set(tabId, text) } },
    runtime: {
      id: 'ext-test', getURL: path => 'chrome-extension://ext-test/' + path,
      onMessage: { addListener: fn => { listener = fn } },
    },
    permissions: {
      contains: async ({ origins }) => origins.every(origin => permissions.has(origin)),
      request: async ({ origins }) => {
        requested.push(...origins)
        for (const origin of origins) permissions.add(origin)
        return true
      },
      onRemoved: { addListener: fn => { permissionRemoved = fn } },
    },
    scripting: {
      executeScript: async () => [{ documentId: 'doc-app' }],
      getRegisteredContentScripts: async ({ ids }) => ids.filter(id => scripts.has(id))
        .map(id => scripts.get(id)),
      registerContentScripts: async items => {
        for (const item of items) {
          scripts.set(item.id, item)
          scriptOperations.push(['register', item])
        }
      },
      unregisterContentScripts: async ({ ids }) => {
        for (const id of ids) {
          scripts.delete(id)
          scriptOperations.push(['unregister', id])
        }
      },
    },
    tabs: {
      get: async id => {
        if (!tabs.has(id)) throw Error('missing tab')
        return tabs.get(id)
      },
      query: async (filter = {}) => filter.active ? [tabs.get(2)] : [tabs.get(1)],
      sendMessage: async (tabId, message) => {
        calls.push([tabId, message])
        if (message.type === 'ext29:extract') {
          if (behavior.candidateFailure) return { version: 1, request_id: message.request_id, ok: false }
          return { version: 1, request_id: message.request_id, ok: true, url: JOB,
            company: 'Acme', title: 'Engineer' }
        }
        if (message.kind === 'apply' && behavior.applyFailureOnce) {
          behavior.applyFailureOnce = false
          return { version: 1, request_id: message.request_id, ok: false,
            error: { code: 'timeout', message: 'Save status unknown' } }
        }
        if ((message.kind === 'check' && behavior.checkFailure) ||
            (message.kind === 'visit' && behavior.visitFailure)) {
          return { version: 1, request_id: message.request_id, ok: false,
            error: { code: 'unavailable', message: 'Retry' } }
        }
        return { version: 1, request_id: message.request_id, ok: true,
          data: message.kind === 'session'
            ? { protocol_version: 1, account_id: activeAccount, account_label: 'Test account' }
            : message.kind === 'check'
              ? { protocol_version: 1, account_id: activeAccount, checked_at: '2026-11-04T00:00:00Z',
                visit: { visited: behavior.alreadyVisited, first_visited_at: behavior.alreadyVisited ? '2026-11-03T00:00:00Z' : null }, matches: [],
                company_history_count: 0, company_known: false, lookup_complete: true }
              : message.kind === 'forget_visits'
                ? { protocol_version: 1, account_id: activeAccount, deleted: 3 }
                : { protocol_version: 1, account_id: activeAccount, created: true,
                first_visited_at: '2026-11-04T00:00:01Z' },
        }
      },
      onUpdated: { addListener: fn => { updated = fn } },
      onRemoved: { addListener: fn => { removed = fn } },
    },
    storage: {
      local: {
        get: async key => ({ [key]: storageLocal[key] }),
        set: async obj => Object.assign(storageLocal, obj),
      },
      session: {
        get: async key => ({ [key]: storageSession[key] }),
        set: async obj => Object.assign(storageSession, obj),
        remove: async key => { for (const k of Array.isArray(key) ? key : [key]) delete storageSession[k] },
      },
    },
  }
  vm.runInNewContext(source, {
    chrome, URL, TextEncoder, crypto: globalThis.crypto,
    setTimeout, clearTimeout,
  }, { filename: 'background.js', timeout: 1000 })
  async function send(message, sender = POPUP) {
    return await new Promise(resolve => {
      const accepted = listener(message, sender, resolve)
      assert.equal(accepted, true)
    })
  }
  return {
    send, calls, scripts, requested, scriptOperations, storageSession, storageLocal, badges,
    permissions, tabs, packet, behavior, setAccount: id => { activeAccount = id },
    connect: () => send(packet('ext26:connect', { tab_id: 1 })),
    emitUpdated: (id, change) => { const tab = tabs.get(id); Object.assign(tab, change);
      updated?.(id, change, tab) },
    revoke: origin => { permissions.delete(origin); permissionRemoved?.({ origins: [origin] }) },
    remove: id => { tabs.delete(id); removed?.(id) },
  }
}

test('EXT-30 never asks for access or registers a content script on startup', async () => {
  const worker = createWorker()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(worker.requested, [])
  assert.equal(worker.scripts.size, 0)
  const status = await worker.send(packet('ext30:site-status', { host: 'jobs.lever.co' }))
  assert.equal(status.data.opted_in, false)
  assert.equal(status.data.permission_granted, false)
})

test('EXT-30 requires a selected account and popup gesture, then registers one exact host', async () => {
  const w = createWorker()
  const request = packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: true })
  assert.equal((await w.send(request)).error.code, 'not_connected')
  assert.equal(w.requested.length, 0)
  assert.equal((await w.connect()).ok, true)
  const enabled = await w.send(request)
  assert.equal(enabled.ok, true)
  assert.equal(enabled.data.opted_in, true)
  assert.deepEqual(w.requested, ['https://jobs.lever.co/*'])
  const entries = [...w.scripts.values()]
  assert.equal(entries.length, 1)
  assert.equal(entries[0].id, 'jobgrid-public-jobs-lever-co')
  assert.deepEqual(Array.from(entries[0].matches), ['https://jobs.lever.co/*'])
  assert.deepEqual(Array.from(entries[0].js), ['job-candidates.js'])
  assert.equal(entries[0].allFrames, false)
  assert.equal(entries[0].persistAcrossSessions, false)
  await w.send(request)
  assert.equal(w.scripts.size, 1, 'registering twice is idempotent')
  const disabled = await w.send(packet('ext30:site-opt-in', {
    host: 'jobs.lever.co', enabled: false,
  }))
  assert.equal(disabled.ok, true)
  assert.equal(w.scripts.size, 0)
  assert.equal(w.storageLocal.jobgridSiteOptIns['jobs.lever.co'], undefined)
})

test('EXT-30 denies forged senders, unknown hosts and revocation cannot remain opted in', async () => {
  const w = createWorker()
  await w.connect()
  for (const message of [
    packet('ext30:site-opt-in', { host: 'jobs.lever.co.evil.test', enabled: true }),
    packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: 'true' }),
    packet('ext30:site-status', { host: 'boards.greenhouse.io', extra: 'spoof' }),
  ]) assert.equal((await w.send(message)).ok, false)
  assert.equal((await w.send(packet('ext30:site-opt-in', {
    host: 'jobs.lever.co', enabled: true,
  }), { ...POPUP, url: 'https://jobs.lever.co/acme/role' })).ok, false)
  await w.send(packet('ext30:site-opt-in', { host: 'jobs.lever.co', enabled: true }))
  w.revoke('https://jobs.lever.co/*')
  await new Promise(resolve => setImmediate(resolve))
  const status = await w.send(packet('ext30:site-status', { host: 'jobs.lever.co' }))
  assert.equal(status.data.opted_in, false)
  assert.equal(w.scripts.size, 0)
})


const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const optIntoLever = async w => {
  assert.equal((await w.connect()).ok, true)
  assert.equal((await w.send(packet('ext30:site-opt-in', {
    host: 'jobs.lever.co', enabled: true,
  }))).ok, true)
}

test('EXT-31 triggers exactly one check per qualifying top-level navigation', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(w.calls.filter(([, message]) => message.kind === 'check').length, 1)
  assert.equal(w.calls.filter(([, message]) => message.type === 'ext29:extract').length, 1)
  assert.equal(w.calls.filter(([, message]) => message.kind === 'visit').length, 1)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(550)
  assert.equal(w.calls.filter(([, message]) => message.kind === 'check').length, 1)
})

test('EXT-31 cancels a pending check on navigation and rejects unsupported URLs', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  w.emitUpdated(2, { url: 'https://jobs.lever.co/acme', status: 'loading' })
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(w.calls.filter(([, message]) => message.kind === 'check').length, 0)
  assert.equal(w.calls.filter(([, message]) => message.kind === 'visit').length, 0)
})

test('EXT-31 does not check when candidate extraction fails or permission is revoked', async () => {
  const a = createWorker()
  await optIntoLever(a)
  a.behavior.candidateFailure = true
  a.emitUpdated(2, { status: 'complete' })
  await sleep(630)
  assert.equal(a.calls.filter(([, message]) => message.kind === 'check').length, 0)
  const b = createWorker()
  await optIntoLever(b)
  b.revoke('https://jobs.lever.co/*')
  b.emitUpdated(2, { status: 'complete' })
  await sleep(630)
  assert.equal(b.calls.filter(([, message]) => message.kind === 'check').length, 0)
})


test('EXT-32 stores the original warning before the visit and preserves it after success', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const status = await w.send(packet('ext32:tab-status', { tab_id: 2 }))
  assert.equal(status.ok, true)
  assert.equal(status.data.account_id, 101)
  assert.equal(status.data.save_state, 'saved')
  assert.equal(status.data.before_visit.visit.visited, false,
    'visit response must not rewrite pre-write warning')
  assert.deepEqual(JSON.parse(JSON.stringify(status.data.before_visit.matches)), [])
  assert.equal(w.storageSession.jobgridTabChecks['2'].before_visit.visit.visited, false)
  const kinds = w.calls.map(([, msg]) => msg.kind).filter(Boolean)
  assert.ok(kinds.indexOf('check') >= 0 && kinds.indexOf('visit') > kinds.indexOf('check'))
})

test('EXT-32 never writes when check fails, and marks failed writes unknown', async () => {
  const a = createWorker()
  await optIntoLever(a)
  a.behavior.checkFailure = true
  a.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(a.calls.filter(([, msg]) => msg.kind === 'visit').length, 0)
  assert.equal((await a.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, false)

  const b = createWorker()
  await optIntoLever(b)
  b.behavior.visitFailure = true
  b.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const unknown = await b.send(packet('ext32:tab-status', { tab_id: 2 }))
  assert.equal(unknown.ok, true)
  assert.equal(unknown.data.save_state, 'save_unknown')
  assert.equal(unknown.data.before_visit.visit.visited, false)
})

test('EXT-32 pre-existing clicked/opened evidence still receives an idempotent visit write; stale account cannot write', async () => {
  const a = createWorker()
  await optIntoLever(a)
  a.behavior.alreadyVisited = true
  a.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(a.calls.filter(([, msg]) => msg.kind === 'visit').length, 1,
    'a prior CSV click may exist without a durable browser visit')
  const previously = await a.send(packet('ext32:tab-status', { tab_id: 2 }))
  assert.equal(previously.data.save_state, 'saved')
  assert.equal(previously.data.before_visit.visit.visited, true,
    'the warning remains exactly as it was before the idempotent write')

  const b = createWorker()
  await optIntoLever(b)
  b.setAccount(202)
  b.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(b.calls.filter(([, msg]) => msg.kind === 'visit').length, 0)
  assert.equal((await b.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, false)
})

test('EXT-32 disconnect erases private warning state and blocks tab-status sender spoofing', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const forged = await w.send(packet('ext32:tab-status', { tab_id: 2 }), {
    ...POPUP, url: JOB,
  })
  assert.equal(forged.ok, false)
  assert.equal((await w.send(packet('ext26:disconnect'))).ok, true)
  assert.equal(w.storageSession.jobgridTabChecks, undefined)
  assert.equal((await w.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, false)
})


test('EXT-32 removes cached warnings on permission revocation and tab navigation', async () => {
  const revoked = createWorker()
  await optIntoLever(revoked)
  revoked.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal((await revoked.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, true)
  revoked.revoke('https://jobs.lever.co/*')
  await sleep(30)
  assert.equal((await revoked.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, false)
  assert.equal(revoked.storageSession.jobgridTabChecks['2'], undefined)

  const changed = createWorker()
  await optIntoLever(changed)
  changed.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  changed.emitUpdated(2, { url: 'https://jobs.lever.co/acme', status: 'loading' })
  await sleep(30)
  assert.equal((await changed.send(packet('ext32:tab-status', { tab_id: 2 }))).ok, false)
  assert.equal(changed.storageSession.jobgridTabChecks['2'], undefined)
})


test('EXT-33 manually checks an unsupported public tab but never writes a visit', async () => {
  const w = createWorker()
  assert.equal((await w.connect()).ok, true)
  w.tabs.set(2, { id: 2, url: 'https://careers.example.org/roles/engineer', status: 'complete' })
  const result = await w.send(packet('ext33:current-tab-check'))
  assert.equal(result.ok, true)
  assert.equal(result.data.save_state, 'manual_only')
  assert.equal(result.data.before_visit.visit.visited, false)
  const stored = await w.send(packet('ext32:tab-status', { tab_id: 2 }))
  assert.equal(stored.ok, true)
  assert.equal(stored.data.save_state, 'manual_only')
  assert.equal(w.calls.filter(([, m]) => m.kind === 'check').length, 1)
  assert.equal(w.calls.filter(([, m]) => m.kind === 'visit').length, 0)
  assert.equal(w.calls.filter(([, m]) => m.type === 'ext29:extract').length, 0)
  assert.equal(w.requested.length, 0, 'activeTab fallback never asks for host access')
})


test('EXT-33 rejects local, credential-bearing and non-HTTPS manual URLs', async () => {
  const w = createWorker()
  await w.connect()
  for (const url of [
    'http://careers.example.org/jobs/1',
    'https://localhost/jobs/1',
    'https://127.0.0.1/jobs/1',
    'https://user:pass@careers.example.org/jobs/1',
    'https://careers.example.org/jobs/1?token=secret',
    'https://careers.example.org/jobs/1#secret',
    'https://csv-website-steel.vercel.app/dashboard',
  ]) {
    w.tabs.set(2, { id: 2, url, status: 'complete' })
    const result = await w.send(packet('ext33:current-tab-check'))
    assert.equal(result.ok, false, url)
    assert.equal(result.error.code, 'unsupported')
  }
  assert.equal(w.calls.filter(([, m]) => m.kind === 'check').length, 0)
  assert.equal(w.calls.filter(([, m]) => m.kind === 'visit').length, 0)
})


test('EXT-34 keeps stable pending UUID for identical drafts, clears changed and switched accounts', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const draft = packet('ext34:stage-apply', {
    tab_id: 2, company: 'Acme', title: 'Engineer',
  })
  const first = await w.send(draft)
  assert.equal(first.ok, true)
  assert.equal(first.data.pending, true)
  assert.ok(first.data.idempotency_key)
  const same = await w.send(draft)
  assert.equal(same.data.idempotency_key, first.data.idempotency_key)
  assert.equal(w.storageSession.jobgridPendingApply['2'].company, 'Acme')
  const changed = await w.send({ ...draft, title: 'Senior Engineer' })
  assert.notEqual(changed.data.idempotency_key, first.data.idempotency_key)
  assert.equal(w.calls.filter(([, m]) => m.kind === 'apply').length, 0)
  w.setAccount(202)
  const invalid = await w.send(packet('ext34:pending-apply', { tab_id: 2 }))
  assert.equal(invalid.ok, false)
  assert.equal(invalid.error.code, 'account_changed')
  assert.equal(w.storageSession.jobgridPendingApply, undefined)
})


test('EXT-35 pause blocks observations, clears warnings/badges and resume rechecks account', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.behavior.alreadyVisited = true
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  assert.equal(w.badges.get(2), 'V')
  const count = w.calls.filter(([, m]) => m.kind === 'check').length
  const paused = await w.send(packet('ext35:set-paused', { paused: true }))
  assert.equal(paused.ok, true)
  assert.equal(paused.data.paused, true)
  assert.equal(w.badges.get(2), '')
  assert.equal(w.storageSession.jobgridTabChecks, undefined)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(600)
  assert.equal(w.calls.filter(([, m]) => m.kind === 'check').length, count)
  assert.equal((await w.send(packet('ext33:current-tab-check'))).error.code, 'paused')
  const resumed = await w.send(packet('ext35:set-paused', { paused: false }))
  assert.equal(resumed.ok, true)
  assert.equal(resumed.data.paused, false)
  await w.send(packet('ext26:disconnect'))
  assert.equal((await w.send(packet('ext35:status'))).data.connected, false)
  assert.equal(w.storageSession.jobgridPaused, undefined)
})


test('EXT-34 never accepts a job-page sender or reuses a draft after navigation', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const stage = packet('ext34:stage-apply', { tab_id: 2, company: 'Acme', title: 'Engineer' })
  const forged = await w.send(stage, { ...POPUP, url: JOB })
  assert.equal(forged.ok, false)
  assert.equal(w.storageSession.jobgridPendingApply, undefined)
  const good = await w.send(stage)
  assert.equal(good.ok, true)
  w.emitUpdated(2, { url: 'https://jobs.lever.co/acme/different', status: 'loading' })
  await sleep(30)
  assert.equal(w.storageSession.jobgridPendingApply?.['2'], undefined)
  const noCheck = await w.send(stage)
  assert.equal(noCheck.error.code, 'no_check')
  assert.equal(w.calls.filter(([, m]) => m.kind === 'apply').length, 0)
})

test('EXT-39 only explicit staged confirmation submits and concurrent clicks share one backend write', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const pending = await w.send(packet('ext34:stage-apply', {
    tab_id: 2, company: '  Acme  ', title: ' Engineer ',
  }))
  assert.equal(pending.ok, true)
  assert.equal(w.calls.filter(([, m]) => m.kind === 'apply').length, 0)
  const [one, two] = await Promise.all([
    w.send(packet('ext39:submit-pending', { tab_id: 2 })),
    w.send(packet('ext39:submit-pending', { tab_id: 2 })),
  ])
  assert.equal(one.ok, true)
  assert.equal(two.ok, true)
  assert.equal(one.data.saved, true)
  const writes = w.calls.filter(([, m]) => m.kind === 'apply')
  assert.equal(writes.length, 1)
  assert.equal(writes[0][1].payload.idempotency_key, pending.data.idempotency_key)
  assert.equal(writes[0][1].payload.company, 'Acme')
  assert.equal(writes[0][1].payload.title, 'Engineer')
  assert.equal(writes[0][1].payload.url, JOB)
  assert.equal(writes[0][1].payload.confirmed, true)
  const status = await w.send(packet('ext32:tab-status', { tab_id: 2 }))
  assert.equal(status.data.apply_status, 'saved')
  assert.equal(status.data.before_visit.visit.visited, false)
  assert.equal(w.badges.get(2), 'A')
  assert.equal(w.storageSession.jobgridPendingApply?.['2'], undefined)
  assert.equal((await w.send(packet('ext39:submit-pending', { tab_id: 2 }))).error.code, 'no_check')
})

test('EXT-39 ambiguous timeout is not success and explicit retry preserves the original UUID and payload', async () => {
  const w = createWorker()
  await optIntoLever(w)
  w.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  const draft = await w.send(packet('ext34:stage-apply', {
    tab_id: 2, company: 'Acme', title: 'Engineer',
  }))
  w.behavior.applyFailureOnce = true
  const first = await w.send(packet('ext39:submit-pending', { tab_id: 2 }))
  assert.equal(first.ok, false)
  assert.equal(first.error.code, 'save_unknown')
  assert.equal(w.storageSession.jobgridPendingApply['2'].idempotency_key, draft.data.idempotency_key)
  const retry = await w.send(packet('ext39:submit-pending', { tab_id: 2 }))
  assert.equal(retry.ok, true)
  const writes = w.calls.filter(([, m]) => m.kind === 'apply').map(([, m]) => m.payload)
  assert.equal(writes.length, 2)
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0])), JSON.parse(JSON.stringify(writes[1])))
})

test('EXT-39 fails closed for forged sender, stale tab, switched account and expired draft', async () => {
  const a = createWorker()
  await optIntoLever(a)
  a.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  await a.send(packet('ext34:stage-apply', { tab_id: 2, company: 'Acme', title: 'Engineer' }))
  assert.equal((await a.send(packet('ext39:submit-pending', { tab_id: 2 }),
    { ...POPUP, url: JOB })).ok, false)
  assert.equal(a.calls.filter(([, m]) => m.kind === 'apply').length, 0)
  a.emitUpdated(2, { url: 'https://jobs.lever.co/acme/other', status: 'loading' })
  await sleep(25)
  assert.equal((await a.send(packet('ext39:submit-pending', { tab_id: 2 }))).error.code, 'no_check')

  const b = createWorker()
  await optIntoLever(b)
  b.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  await b.send(packet('ext34:stage-apply', { tab_id: 2, company: 'Acme', title: 'Engineer' }))
  b.setAccount(202)
  assert.equal((await b.send(packet('ext39:submit-pending', { tab_id: 2 }))).ok, false)
  assert.equal(b.calls.filter(([, m]) => m.kind === 'apply').length, 0)

  const c = createWorker()
  await optIntoLever(c)
  c.emitUpdated(2, { status: 'complete' })
  await sleep(650)
  await c.send(packet('ext34:stage-apply', { tab_id: 2, company: 'Acme', title: 'Engineer' }))
  c.storageSession.jobgridPendingApply['2'].created_at = Date.now() - 16 * 60 * 1000
  assert.equal((await c.send(packet('ext39:submit-pending', { tab_id: 2 }))).error.code, 'no_check')
  assert.equal(c.calls.filter(([, m]) => m.kind === 'apply').length, 0)
})
