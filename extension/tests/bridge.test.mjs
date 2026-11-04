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
