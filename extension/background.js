/* JobGrid extension worker: explicit, popup-only account connection (EXT-26). */
'use strict'

const APP_ORIGIN = 'https://csv-website-steel.vercel.app'
const VERSION = 1
const PROBE = 'ext05:session-probe'
const CONNECT = 'ext26:connect'
const COMMAND = 'ext26:command'
const DISCONNECT = 'ext26:disconnect'
const MAX_BYTES = 8192
const TIMEOUT_MS = 8000
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

let connection = null
let generation = 0
const SESSION_DEBOUNCE_MS = 5000

const plain = value => value !== null && typeof value === 'object' &&
  !Array.isArray(value) && Object.prototype.toString.call(value) === '[object Object]'
const keysOnly = (obj, keys) => Object.keys(obj).every(k => keys.includes(k))
const validId = value => Number.isSafeInteger(value) && value > 0
const validUUID = value => typeof value === 'string' && UUID.test(value)
const error = (code, message = 'JobGrid account unavailable') => ({
  version: VERSION, ok: false, error: { code, message },
})
const answer = (requestId, result) => ({ version: VERSION, request_id: requestId, ...result })
const unavailable = () => error('unavailable')
const popupSender = sender => sender?.id === chrome.runtime.id &&
  sender.url === chrome.runtime.getURL('popup.html') &&
  (!sender.origin || sender.origin === 'chrome-extension://' + chrome.runtime.id) &&
  (sender.frameId === undefined || sender.frameId === 0)
const exactAppTab = tab => {
  if (!validId(tab?.id) || typeof tab.url !== 'string') return false
  try {
    const url = new URL(tab.url)
    return url.origin === APP_ORIGIN && !url.username && !url.password
  } catch { return false }
}
const validUrl = value => typeof value === 'string' && value.length <= 2048 &&
  value.trim() === value && /^https?:\/\//.test(value)
const validText = (value, limit, required = false) => typeof value === 'string' &&
  value.length <= limit && (!required || !!value.trim())

function validCommand(message) {
  if (!plain(message.payload)) return false
  const body = message.payload
  if (message.kind === 'session') return Object.keys(body).length === 0
  if (message.kind === 'check') return keysOnly(body, ['url', 'company', 'title']) &&
    validUrl(body.url) && (body.company == null || validText(body.company, 320)) &&
    (body.title == null || validText(body.title, 500))
  if (message.kind === 'apply') return keysOnly(body,
    ['url', 'company', 'title', 'confirmed', 'idempotency_key']) &&
    validUrl(body.url) && validText(body.company, 320, true) &&
    validText(body.title, 500, true) && body.confirmed === true &&
    validUUID(body.idempotency_key)
  if (message.kind === 'forget_visits') return keysOnly(body, ['confirmed']) &&
    body.confirmed === true
  return false // Visit is strictly worker-derived in the later EXT-32 flow.
}

function validMessage(message) {
  if (!plain(message) || !keysOnly(message, ['type', 'version', 'request_id',
    'tab_id', 'kind', 'payload'])) return false
  try {
    if (new TextEncoder().encode(JSON.stringify(message)).length > MAX_BYTES) return false
  } catch { return false }
  if (message.version !== VERSION || !validUUID(message.request_id)) return false
  if (message.type === CONNECT) return keysOnly(message, ['type', 'version',
    'request_id', 'tab_id']) && validId(message.tab_id)
  if (message.type === DISCONNECT) return Object.keys(message).length === 3
  if (message.type === COMMAND) return keysOnly(message,
    ['type', 'version', 'request_id', 'kind', 'payload']) &&
    validCommand(message)
  return false
}

async function clearConnection() {
  generation++
  connection = null
  await chrome.storage.session.remove('jobgridConnection')
}

async function bridge(tabId, kind, payload = {}, accountId, documentId = null) {
  const requestId = crypto.randomUUID()
  const packet = { version: VERSION, request_id: requestId, kind, payload }
  if (accountId !== undefined) packet.account_id = accountId
  const expired = Symbol('request-expired')
  let timer
  let result
  try {
    const sent = documentId
      ? chrome.tabs.sendMessage(tabId, packet, { documentId })
      : chrome.tabs.sendMessage(tabId, packet)
    result = await Promise.race([
      sent,
      new Promise(resolve => { timer = setTimeout(() => resolve(expired), TIMEOUT_MS) }),
    ])
  } catch {
    return unavailable()
  } finally {
    clearTimeout(timer)
  }
  if (result === expired) {
    return error('timeout', kind === 'apply'
      ? 'Save status unknown · Retry' : 'Couldn’t check · Retry')
  }
  if (!plain(result) || result.version !== VERSION ||
      result.request_id !== requestId || typeof result.ok !== 'boolean') {
    return error('protocol_error', 'Unsupported response')
  }
  if (result.ok && (!plain(result.data) || !validId(result.data.account_id) ||
      result.data.protocol_version !== VERSION)) {
    return error('protocol_error', 'Unsupported response')
  }
  if (!result.ok && (!plain(result.error) || typeof result.error.code !== 'string')) {
    return error('protocol_error', 'Unsupported response')
  }
  return result
}

async function checkedTab(tabId) {
  const granted = await chrome.permissions.contains({ origins: [APP_ORIGIN + '/*'] })
  if (!granted) return null
  const tab = await chrome.tabs.get(tabId)
  return exactAppTab(tab) ? tab : null
}

async function injectBridge(tabId) {
  return chrome.scripting.executeScript({
    target: { tabId, allFrames: false }, files: ['jobgrid-bridge.js'], world: 'ISOLATED',
  })
}

async function connect(tabId) {
  const epoch = ++generation
  connection = null
  const tab = await checkedTab(tabId)
  if (!tab) return unavailable()
  const injected = await injectBridge(tabId)
  const documentId = typeof injected?.[0]?.documentId === 'string' ? injected[0].documentId : null
  const result = await bridge(tabId, 'session')
  if (!result.ok) return result
  const current = await checkedTab(tabId)
  if (epoch !== generation || !current || current.url !== tab.url) return unavailable()
  connection = { tabId, accountId: result.data.account_id, generation: epoch,
    tabUrl: tab.url, documentId, lastSessionCheckAt: Date.now() }
  await chrome.storage.session.set({
    jobgridConnection: { tabId, accountId: result.data.account_id },
  })
  return { ok: true, data: {
    protocol_version: VERSION, account_id: result.data.account_id,
    account_label: result.data.account_label,
  } }
}

async function dispatch(kind, payload) {
  const selected = connection
  if (!selected) return error('not_connected', 'Open JobGrid to connect')
  const firstTab = await checkedTab(selected.tabId)
  if (!firstTab || firstTab.url !== selected.tabUrl) {
    await clearConnection()
    return unavailable()
  }
  if (kind === 'session') {
    const now = Date.now()
    if (now - selected.lastSessionCheckAt < SESSION_DEBOUNCE_MS) {
      return error('session_debounced', 'Retry account check shortly')
    }
    selected.lastSessionCheckAt = now
  }
  const body = kind === 'forget_visits' ? {} : payload
  const result = await bridge(selected.tabId, kind, body,
    kind === 'session' ? undefined : selected.accountId, selected.documentId)
  if (!connection || connection !== selected) return unavailable()
  if (!result.ok) {
    if (['account_changed', 'protocol_error'].includes(result.error.code)) {
      await clearConnection()
    }
    return result
  }
  if (result.data.account_id !== selected.accountId) {
    await clearConnection()
    return error('account_changed', 'Reconnect your JobGrid account')
  }
  // The bridge also rechecks on each write. This final worker check prevents
  // private results reaching the popup after an account switch or tab reload.
  if (kind !== 'session') {
    const fresh = await bridge(selected.tabId, 'session', {}, undefined, selected.documentId)
    if (!fresh.ok || fresh.data.account_id !== selected.accountId) {
      await clearConnection()
      return error('account_changed', 'Reconnect your JobGrid account')
    }
  }
  const finalTab = await checkedTab(selected.tabId)
  if (!connection || connection !== selected || !finalTab ||
      finalTab.url !== selected.tabUrl) {
    await clearConnection()
    return unavailable()
  }
  return result
}

chrome.tabs.onRemoved?.addListener(tabId => {
  if (connection?.tabId === tabId) void clearConnection()
})
chrome.tabs.onUpdated?.addListener((tabId, changes) => {
  if (connection?.tabId === tabId && (changes.url || changes.status === 'loading')) {
    void clearConnection()
  }
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (![PROBE, CONNECT, COMMAND, DISCONNECT].includes(message?.type)) return false
  const requestId = validUUID(message?.request_id) ? message.request_id : null
  if (!popupSender(sender) || !validMessage(message) && message.type !== PROBE) {
    sendResponse(answer(requestId, error('forbidden_sender', 'Unsupported request')))
    return false
  }

  const run = async () => {
    if (message.type === PROBE) {
      // Backwards-compatible EXT-05 read-only probe, never picks a tab if ambiguous.
      const granted = await chrome.permissions.contains({ origins: [APP_ORIGIN + '/*'] })
      if (!granted) return error('not_connected')
      const tabs = await chrome.tabs.query({ url: [APP_ORIGIN + '/*'] })
      if (tabs.length !== 1 || !exactAppTab(tabs[0])) return unavailable()
      await injectBridge(tabs[0].id)
      return bridge(tabs[0].id, 'session')
    }
    if (message.type === CONNECT) return connect(message.tab_id)
    if (message.type === DISCONNECT) {
      await clearConnection()
      return { ok: true, data: { protocol_version: VERSION, disconnected: true } }
    }
    return dispatch(message.kind, message.payload)
  }

  run().then(result => sendResponse(answer(requestId, result)),
    () => sendResponse(answer(requestId, unavailable())))
  return true
})
