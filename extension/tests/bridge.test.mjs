import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { APP_ORIGIN } from '../config.js'

const source = readFileSync(new URL('../jobgrid-bridge.js', import.meta.url), 'utf8')
const UUID = '1b8cee75-42c0-45b1-8c46-bfcfa1d1ffcc'
const SENDER = { id: 'test-extension', url: 'chrome-extension://test-extension/background.js' }
const request = (kind = 'session', values = {}) => ({
  version: 1, request_id: UUID, kind, payload: {}, ...values,
})
const session = (id = 101) => ({ protocol_version: 1, account_id: id, account_label: 'Pilot A' })
const json = (data, status = 200, headers = {}) =>
  new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json', ...headers } })

function setup({ origin = APP_ORIGIN, answer = () => json(session()) } = {}) {
  const calls = []
  const pageWrites = []
  let listener
  const chrome = {
    runtime: {
      id: 'test-extension',
      onMessage: { addListener: (fn) => { listener = fn } },
    },
  }
  const context = {
    chrome, location: { origin }, URL, TextEncoder, AbortController,
    setTimeout, clearTimeout,
    fetch: async (url, options) => {
      calls.push({ url, options })
      return answer(url, options, calls.length)
    },
    document: {
      write: () => pageWrites.push('write'),
      querySelector: () => pageWrites.push('read'),
    },
  }
  vm.runInNewContext(source, context, { filename: 'jobgrid-bridge.js', timeout: 1000 })
  async function send(message, sender = SENDER) {
    assert.equal(typeof listener, 'function', 'trusted origin should install listener')
    return await new Promise((resolve) => listener(message, sender, resolve))
  }
  return { calls, pageWrites, send, listener: () => listener }
}

// ext_03_case_01
test('session goes to one fixed same-origin path and echoes the request UUID', async () => {
  const bridge = setup()
  const response = await bridge.send(request())
  assert.equal(response.version, 1)
  assert.equal(response.request_id, UUID)
  assert.equal(response.ok, true)
  assert.deepEqual(JSON.parse(JSON.stringify(response.data)), session())
  assert.equal(bridge.calls.length, 1)
  assert.equal(bridge.calls[0].url, `${APP_ORIGIN}/api/crm/browser-memory/session`)
  assert.equal(bridge.calls[0].options.method, 'GET')
  assert.equal(bridge.calls[0].options.credentials, 'same-origin')
  assert.equal(bridge.calls[0].options.redirect, 'error')
  assert.equal(bridge.calls[0].options.body, undefined)
  assert.equal(bridge.pageWrites.length, 0)
})

// ext_03_case_02
test('external sender, version mismatch, extra fields and oversized message do not fetch', async () => {
  const bridge = setup()
  const invalid = [
    [request(), { id: 'attacker-extension' }],
    [request(), { ...SENDER, url: 'https://jobboard.example/' }],
    [request(), { ...SENDER, tab: { id: 13 } }],
    [request('session', { version: 2 }), SENDER],
    [request('session', { destination: 'https://evil.test' }), SENDER],
    [request('session', { payload: { api: '/other' } }), SENDER],
    [request('session', { request_id: 'not-uuid' }), SENDER],
    [request('session', { payload: { url: 'A'.repeat(8300) } }), SENDER],
  ]
  for (const [input, sender] of invalid) {
    const outcome = await bridge.send(input, sender)
    assert.equal(outcome.ok, false)
    assert.equal(outcome.error.code, 'protocol_error')
  }
  assert.equal(bridge.calls.length, 0)
  assert.equal(setup({ origin: 'https://attacker.test' }).listener(), undefined)
})

// ext_03_case_03
test('HTML, 401, rate limit, malformed and mismatched responses fail closed', async () => {
  const html = setup({ answer: () => new Response('<!doctype html><h1>Login</h1>', {
    status: 200, headers: { 'content-type': 'text/html' },
  }) })
  assert.equal((await html.send(request())).error.code, 'unavailable')
  const auth = setup({ answer: () => json({ detail: 'Not authenticated' }, 401) })
  assert.equal((await auth.send(request())).error.code, 'not_authenticated')
  const rate = setup({ answer: () => json({}, 429, { 'Retry-After': '10' }) })
  assert.equal((await rate.send(request())).error.retry_after, 10)
  const malformed = setup({ answer: () => json({ account_id: 101 }) })
  assert.equal((await malformed.send(request())).error.code, 'unavailable')
  const different = setup({ answer: () => json(session(202)) })
  assert.equal((await different.send(request('visit', { account_id: 101, payload: { url: 'https://jobs.lever.co/acme/1' } }))).error.code, 'account_changed')
  assert.equal(different.calls.length, 1, 'wrong account cannot make a write request')
  for (const fixture of [html, auth, rate, malformed, different]) assert.equal(fixture.pageWrites.length, 0)
})

test('fixed check and write paths, expected-account headers and session recheck', async () => {
  const target = 'https://jobs.lever.co/acme/abc'
  const calls = []
  const bridge = setup({ answer: (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/session')) return json(session())
    return json({ protocol_version: 1, account_id: 101, checked_at: '2026-11-04T00:00:00Z' })
  } })
  for (const [kind, payload, suffix, method] of [
    ['check', { url: target }, '/check', 'POST'],
    ['visit', { url: target }, '/visit', 'POST'],
    ['apply', { url: target, company: 'Acme', title: 'Engineer', confirmed: true, idempotency_key: UUID }, '/apply', 'POST'],
    ['forget_visits', {}, '/visits', 'DELETE'],
  ]) {
    const first = calls.length
    const outcome = await bridge.send(request(kind, { account_id: 101, payload }))
    assert.equal(outcome.ok, true, kind)
    assert.equal(calls.length - first, 3, `${kind}: session, operation, session`)
    assert.equal(calls[first + 1].url, `${APP_ORIGIN}/api/crm/browser-memory${suffix}`)
    assert.equal(calls[first + 1].options.method, method)
    assert.equal(calls[first + 1].options.credentials, 'same-origin')
    if (['visit', 'apply', 'forget_visits'].includes(kind)) {
      assert.equal(calls[first + 1].options.headers['X-JobGrid-Browser'], '1')
      assert.equal(calls[first + 1].options.headers['X-JobGrid-Account-ID'], '101')
    } else assert.equal(calls[first + 1].options.headers['X-JobGrid-Account-ID'], undefined)
    if (kind === 'apply') {
      assert.equal(calls[first + 1].options.headers['Idempotency-Key'], UUID)
      assert.equal(JSON.parse(calls[first + 1].options.body).idempotency_key, undefined)
    }
    if (kind === 'forget_visits') assert.equal(calls[first + 1].options.body, undefined)
  }
  assert.equal(bridge.pageWrites.length, 0)
})

test('account switched during the request makes response unavailable to the caller', async () => {
  let sessions = 0
  const bridge = setup({ answer: (url) => {
    if (url.endsWith('/session')) return json(session(++sessions === 1 ? 101 : 202))
    return json({ protocol_version: 1, account_id: 101 })
  } })
  const response = await bridge.send(request('check', { account_id: 101, payload: { url: 'https://jobs.lever.co/acme/abc' } }))
  assert.equal(response.ok, false)
  assert.equal(response.error.code, 'account_changed')
  assert.equal(bridge.calls.length, 3)
})

test('release origin matches config and the public manifest', () => {
  const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))
  assert.ok(source.includes(`const TRUSTED_ORIGIN = '${APP_ORIGIN}'`))
  assert.ok(manifest.optional_host_permissions.includes(`${APP_ORIGIN}/*`))
  assert.doesNotMatch(source, /document\.cookie|window\.postMessage|eval\s*\(|<all_urls>/)
})

test('repeated session-probe injection registers one bridge listener per document', () => {
  const listeners = []
  const context = {
    chrome: { runtime: {
      id: 'test-extension',
      onMessage: { addListener: (fn) => listeners.push(fn) },
    } },
    location: { origin: APP_ORIGIN },
    URL, TextEncoder, AbortController, setTimeout, clearTimeout,
    fetch: async () => json(session()),
  }
  vm.createContext(context)
  vm.runInContext(source, context, { filename: 'jobgrid-bridge.js', timeout: 1000 })
  vm.runInContext(source, context, { filename: 'jobgrid-bridge.js', timeout: 1000 })
  assert.equal(listeners.length, 1, 'same document must not register duplicate message listeners')
})


// EXT-26: worker-only explicit connection and command authority.
const workerSource = readFileSync(new URL('../background.js', import.meta.url), 'utf8')
const POPUP = {
  id: 'test-extension', origin: 'chrome-extension://test-extension',
  url: 'chrome-extension://test-extension/popup.html', frameId: 0,
}
const commandPacket = (type, fields = {}) => ({
  type, version: 1, request_id: UUID, ...fields,
})

function workerSetup({ accountId = 101, granted = true, reply = null, timers = null } = {}) {
  const messages = []
  const injections = []
  const writes = []
  const tabs = new Map([
    [10, { id: 10, url: APP_ORIGIN + '/dashboard', documentId: 'doc-a' }],
    [20, { id: 20, url: APP_ORIGIN + '/jobs', documentId: 'doc-b' }],
  ])
  let receive
  let removed
  let updated
  let activeAccount = accountId
  const chrome = {
    runtime: {
      id: 'test-extension', getURL: path => 'chrome-extension://test-extension/' + path,
      onMessage: { addListener: fn => { receive = fn } },
    },
    permissions: { contains: async () => granted },
    tabs: {
      get: async id => {
        if (!tabs.has(id)) throw new Error('no tab')
        return tabs.get(id)
      },
      query: async () => [...tabs.values()],
      sendMessage: async (tabId, packet) => {
        messages.push({ tabId, packet })
        if (reply) return reply(tabId, packet, activeAccount)
        return {
          version: 1, request_id: packet.request_id, ok: true,
          data: packet.kind === 'session'
            ? session(activeAccount)
            : { protocol_version: 1, account_id: activeAccount,
                checked_at: '2026-11-04T00:00:00Z' },
        }
      },
      onRemoved: { addListener: fn => { removed = fn } },
      onUpdated: { addListener: fn => { updated = fn } },
    },
    scripting: { executeScript: async opts => injections.push(opts) },
    storage: { session: {
      set: async value => writes.push({ set: value }),
      remove: async key => writes.push({ remove: key }),
    } },
  }
  vm.runInNewContext(workerSource, { chrome, URL, TextEncoder, crypto: globalThis.crypto,
    setTimeout: timers?.setTimeout ?? setTimeout,
    clearTimeout: timers?.clearTimeout ?? clearTimeout },
  { filename: 'background.js', timeout: 1000 })
  async function send(packet, sender = POPUP) {
    assert.equal(typeof receive, 'function')
    return await new Promise(resolve => {
      const keep = receive(packet, sender, resolve)
      if (!keep) setImmediate(() => {})
    })
  }
  return {
    send, messages, injections, tabs, writes,
    setAccount: id => { activeAccount = id },
    remove: id => { tabs.delete(id); removed?.(id) },
    update: (id, url) => { const item = tabs.get(id); tabs.set(id, { ...item, url }); updated?.(id, { url }, tabs.get(id)) },
  }
}

// ext_26_case_01
test('worker requires an explicitly chosen exact-origin tab and keeps commands on it', async () => {
  const worker = workerSetup()
  const denied = await worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/role' },
  }))
  assert.equal(denied.ok, false)
  assert.equal(worker.messages.length, 0)
  const connection = await worker.send(commandPacket('ext26:connect', { tab_id: 20 }))
  assert.equal(connection.ok, true)
  assert.equal(connection.data.account_id, 101)
  assert.equal(worker.messages.length, 1)
  assert.equal(worker.messages[0].tabId, 20)
  assert.equal(worker.injections[0].target.allFrames, false)
  assert.deepEqual(Array.from(worker.injections[0].files), ['jobgrid-bridge.js'])

  const result = await worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/role', title: null },
  }))
  assert.equal(result.ok, true)
  assert.equal(worker.messages.length, 3, 'check plus final account recheck')
  assert.equal(worker.messages[1].tabId, 20)
  assert.equal(worker.messages[2].packet.kind, 'session')
  assert.equal(worker.messages[1].packet.kind, 'check')
  assert.equal(worker.messages[1].packet.account_id, 101)
})

// ext_26_case_02
test('worker rejects forged sender, subframe, oversized and arbitrary commands before API call', async () => {
  const worker = workerSetup()
  for (const [packet, sender] of [
    [commandPacket('ext26:connect', { tab_id: 10 }), { ...POPUP, url: 'https://jobs.lever.co/acme/role' }],
    [commandPacket('ext26:connect', { tab_id: 10 }), { ...POPUP, id: 'evil-extension' }],
    [commandPacket('ext26:connect', { tab_id: 10 }), { ...POPUP, frameId: 1 }],
    [commandPacket('ext26:command', { kind: 'visit', payload: { url: 'https://jobs.lever.co/acme/role' } }), POPUP],
    [commandPacket('ext26:command', { kind: 'apply', payload: { url: 'https://jobs.lever.co/acme/role' } }), POPUP],
    [commandPacket('ext26:command', { kind: 'session', payload: {}, route: '/other' }), POPUP],
    [commandPacket('ext26:connect', { tab_id: 10, headers: { Authorization: 'nope' } }), POPUP],
    [commandPacket('ext26:command', { kind: 'check', payload: { url: 'A'.repeat(8300) } }), POPUP],
  ]) {
    const reply = await worker.send(packet, sender)
    assert.equal(reply.ok, false)
  }
  assert.equal(worker.messages.length, 0)
  assert.equal(worker.injections.length, 0)
})

// ext_26_case_03
test('job-page scripts cannot invoke private apply/forget commands or see responses', async () => {
  const worker = workerSetup()
  assert.equal((await worker.send(commandPacket('ext26:connect', { tab_id: 10 }))).ok, true)
  const baseline = worker.messages.length
  for (const kind of ['apply', 'forget_visits']) {
    const result = await worker.send(commandPacket('ext26:command', {
      kind, payload: kind === 'forget_visits' ? { confirmed: true } : {
        url: 'https://jobs.lever.co/acme/role', company: 'Acme', title: 'Engineer',
        confirmed: true, idempotency_key: UUID,
      },
    }), { ...POPUP, tab: { id: 11 }, url: 'https://jobs.lever.co/acme/role' })
    assert.equal(result.ok, false)
  }
  assert.equal(worker.messages.length, baseline)
  const apply = await worker.send(commandPacket('ext26:command', {
    kind: 'apply', payload: { url: 'https://jobs.lever.co/acme/role',
      company: 'Acme', title: 'Engineer', confirmed: true, idempotency_key: UUID },
  }))
  assert.equal(apply.ok, true)
  const forget = await worker.send(commandPacket('ext26:command', {
    kind: 'forget_visits', payload: { confirmed: true },
  }))
  assert.equal(forget.ok, true)
  const forgetPacket = worker.messages.findLast(m => m.packet.kind === 'forget_visits').packet
  assert.deepEqual(Object.keys(forgetPacket.payload), [])
  assert.equal(worker.messages.at(-1).packet.kind, 'session', 'final account recheck must follow forget')
})


// ext_27_case_01
test('late account-A result is discarded after account B becomes active', async () => {
  let release
  const worker = workerSetup({ reply: (_tabId, packet, account) => {
    if (packet.kind === 'check') return new Promise(resolve => {
      release = () => resolve({ version: 1, request_id: packet.request_id, ok: true,
        data: { protocol_version: 1, account_id: 101, matches: [{ track_id: 77 }] } })
    })
    return { version: 1, request_id: packet.request_id, ok: true,
      data: session(account) }
  } })
  assert.equal((await worker.send(commandPacket('ext26:connect', { tab_id: 10 }))).ok, true)
  const pending = worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/one' },
  }))
  for (let n = 0; n < 5 && !release; n++) await new Promise(resolve => setImmediate(resolve))
  assert.equal(typeof release, 'function')
  worker.setAccount(202)
  release()
  const result = await pending
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'account_changed')
  assert.equal(result.data, undefined)
  assert.equal((await worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/two' },
  }))).error.code, 'not_connected')
})

// ext_27_case_02
test('navigation/removal invalidate selected tab and discard pending private results', async () => {
  let release
  const worker = workerSetup({ reply: (_tab, packet, account) => {
    if (packet.kind === 'check') return new Promise(resolve => { release = () => resolve({
      version: 1, request_id: packet.request_id, ok: true,
      data: { protocol_version: 1, account_id: account, matches: [{ track_id: 99 }] },
    }) })
    return { version: 1, request_id: packet.request_id, ok: true, data: session(account) }
  } })
  assert.equal((await worker.send(commandPacket('ext26:connect', { tab_id: 10 }))).ok, true)
  const pending = worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/one' },
  }))
  for (let n = 0; n < 5 && !release; n++) await new Promise(resolve => setImmediate(resolve))
  worker.update(10, APP_ORIGIN + '/different')
  release()
  const result = await pending
  assert.equal(result.ok, false)
  assert.equal(result.data, undefined)
  const reconnected = await worker.send(commandPacket('ext26:connect', { tab_id: 20 }))
  assert.equal(reconnected.ok, true)
  worker.remove(20)
  const gone = await worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/one' },
  }))
  assert.equal(gone.ok, false)
  assert.equal(gone.data, undefined)
})

// ext_27_case_03
test('an unanswered check times out at eight seconds with no retry or write', async () => {
  const timers = {
    setTimeout: (callback, ms) => { assert.equal(ms, 8000); return setImmediate(callback) },
    clearTimeout: handle => clearImmediate(handle),
  }
  const worker = workerSetup({ timers, reply: (_tab, packet, account) => {
    if (packet.kind === 'check') return new Promise(() => {})
    return { version: 1, request_id: packet.request_id, ok: true, data: session(account) }
  } })
  assert.equal((await worker.send(commandPacket('ext26:connect', { tab_id: 10 }))).ok, true)
  const outcome = await worker.send(commandPacket('ext26:command', {
    kind: 'check', payload: { url: 'https://jobs.lever.co/acme/one' },
  }))
  assert.equal(outcome.ok, false)
  assert.equal(outcome.error.code, 'timeout')
  assert.equal(worker.messages.length, 2)
  assert.equal(worker.messages[1].packet.kind, 'check')
  assert.equal(worker.messages.some(m => m.packet.kind === 'visit' || m.packet.kind === 'apply'), false)
})
