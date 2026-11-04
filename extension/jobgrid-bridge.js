/* Isolated JobGrid-tab bridge. Inject only after selecting an authorized tab (EXT-26). */
;(() => {
  'use strict'

  // Must match config.js APP_ORIGIN and the manifest's exact optional host.
  const TRUSTED_ORIGIN = 'https://csv-website-steel.vercel.app'
  const VERSION = 1
  const MAX_BYTES = 8192
  const TIMEOUT_MS = 8000
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  const API_ROOT = '/api/crm/browser-memory'
  const ROUTES = Object.freeze({
    session: Object.freeze({ method: 'GET', path: '/session' }),
    check: Object.freeze({ method: 'POST', path: '/check' }),
    visit: Object.freeze({ method: 'POST', path: '/visit' }),
    apply: Object.freeze({ method: 'POST', path: '/apply' }),
    forget_visits: Object.freeze({ method: 'DELETE', path: '/visits' }),
  })

  if (typeof chrome === 'undefined' || !chrome.runtime?.id ||
      !chrome.runtime.onMessage?.addListener || location.origin !== TRUSTED_ORIGIN) return

  // This script is injected on demand by the read-only worker. A repeated
  // session probe must not accumulate message listeners in the same document.
  // An isolated-world global resets naturally when the tab navigates.
  const BRIDGE_MARKER = '__jobgridBridgeVersion1Installed'
  if (globalThis[BRIDGE_MARKER] === true) return
  Object.defineProperty(globalThis, BRIDGE_MARKER, { value: true })

  const isObject = (value) => value !== null && typeof value === 'object' &&
    !Array.isArray(value) && Object.prototype.toString.call(value) === '[object Object]'
  const hasOnly = (value, keys) => Object.keys(value).every((key) => keys.includes(key))
  const isAccount = (value) => Number.isSafeInteger(value) && value > 0
  const isUUID = (value) => typeof value === 'string' && UUID.test(value)
  const isText = (value, max, required = false) =>
    typeof value === 'string' && value.length <= max && (!required || value.trim().length > 0)

  function isSafeUrl(value) {
    if (!isText(value, 2048, true)) return false
    try {
      const parsed = new URL(value)
      return ['http:', 'https:'].includes(parsed.protocol) && !!parsed.hostname &&
        !parsed.username && !parsed.password
    } catch {
      return false
    }
  }

  function isValid(message) {
    if (!isObject(message) || !hasOnly(message,
      ['version', 'request_id', 'kind', 'account_id', 'payload'])) return false
    try {
      if (new TextEncoder().encode(JSON.stringify(message)).length > MAX_BYTES) return false
    } catch {
      return false
    }
    if (message.version !== VERSION || !isUUID(message.request_id) ||
        !Object.hasOwn(ROUTES, message.kind) || !isObject(message.payload)) return false
    if (message.kind === 'session') {
      return !Object.hasOwn(message, 'account_id') && Object.keys(message.payload).length === 0
    }
    if (!isAccount(message.account_id)) return false
    const body = message.payload
    if (message.kind === 'forget_visits') return Object.keys(body).length === 0
    if (!isSafeUrl(body.url)) return false
    if (message.kind === 'visit') return hasOnly(body, ['url'])
    if (message.kind === 'check') return hasOnly(body, ['url', 'company', 'title']) &&
      (body.company == null || isText(body.company, 320)) &&
      (body.title == null || isText(body.title, 500))
    return hasOnly(body, ['url', 'company', 'title', 'confirmed', 'idempotency_key']) &&
      isText(body.company, 320, true) && isText(body.title, 500, true) &&
      body.confirmed === true && isUUID(body.idempotency_key)
  }

  const error = (code, message, retry_after) => ({
    code, message, ...(retry_after === undefined ? {} : { retry_after }),
  })
  const fail = (code, message, retry_after) => ({ ok: false, error: error(code, message, retry_after) })
  const unavailable = () => fail('unavailable', 'Couldn’t check · Retry')

  function trustedSender(sender) {
    if (!sender || sender.id !== chrome.runtime.id || sender.tab) return false
    const root = `chrome-extension://${chrome.runtime.id}/`
    return (!sender.url || sender.url.startsWith(root)) &&
      (!sender.origin || sender.origin === `chrome-extension://${chrome.runtime.id}`)
  }

  async function call(kind, message, signal) {
    const route = ROUTES[kind]
    const headers = { Accept: 'application/json' }
    const options = {
      method: route.method,
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      signal,
      headers,
    }
    if (route.method === 'POST') {
      headers['Content-Type'] = 'application/json'
      const { idempotency_key: ignored, ...payload } = message.payload
      options.body = JSON.stringify(payload)
    }
    if (kind === 'visit' || kind === 'apply' || kind === 'forget_visits') {
      headers['X-JobGrid-Browser'] = '1'
      headers['X-JobGrid-Account-ID'] = String(message.account_id)
      if (kind === 'apply') headers['Idempotency-Key'] = message.payload.idempotency_key
    }
    let response
    try {
      response = await fetch(`${TRUSTED_ORIGIN}${API_ROOT}${route.path}`, options)
      if (response.redirected) return unavailable()
    } catch {
      return signal.aborted ? fail('timeout', 'Couldn’t check · Retry') : unavailable()
    }
    if (response.status === 401) return fail('not_authenticated', 'Sign in to JobGrid')
    if (response.status === 429) {
      const value = Number(response.headers.get('Retry-After'))
      const retryAfter = Number.isSafeInteger(value) && value >= 0 && value <= 3600 ? value : undefined
      return fail('rate_limited', 'Too many requests · Retry later', retryAfter)
    }
    if (!response.ok || !response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
      return unavailable()
    }
    let data
    try {
      const text = await response.text()
      if (new TextEncoder().encode(text).length > MAX_BYTES) return unavailable()
      data = JSON.parse(text)
    } catch {
      return unavailable()
    }
    if (!isObject(data) || data.protocol_version !== VERSION || !isAccount(data.account_id)) {
      return unavailable()
    }
    if (kind === 'session' && !isText(data.account_label, 320, true)) return unavailable()
    return { ok: true, data }
  }

  async function handle(message) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
    try {
      const session = await call('session', { payload: {} }, controller.signal)
      if (!session.ok || message.kind === 'session') return session
      if (session.data.account_id !== message.account_id) {
        return fail('account_changed', 'Reconnect your JobGrid account')
      }
      const result = await call(message.kind, message, controller.signal)
      if (!result.ok) return result
      if (result.data.account_id !== message.account_id) {
        return fail('account_changed', 'Reconnect your JobGrid account')
      }
      // Do not show a response if the cookie switched during the request.
      const after = await call('session', { payload: {} }, controller.signal)
      if (!after.ok || after.data.account_id !== message.account_id) {
        return fail('account_changed', 'Reconnect your JobGrid account')
      }
      return result
    } finally {
      clearTimeout(timer)
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const requestId = typeof message?.request_id === 'string' && isUUID(message.request_id)
      ? message.request_id : null
    const reply = (outcome) => sendResponse({ version: VERSION, request_id: requestId, ...outcome })
    if (!trustedSender(sender) || !isValid(message)) {
      reply(fail('protocol_error', 'Unsupported request'))
      return false
    }
    handle(message).then(reply, () => reply(unavailable()))
    return true
  })
})()
