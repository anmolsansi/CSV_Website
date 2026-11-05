/* JobGrid extension worker: explicit, popup-only account connection (EXT-26). */
'use strict'

const APP_ORIGIN = 'https://csv-website-steel.vercel.app'
const VERSION = 1
const PROBE = 'ext05:session-probe'
const CONNECT = 'ext26:connect'
const COMMAND = 'ext26:command'
const DISCONNECT = 'ext26:disconnect'
const SITE_OPT = 'ext30:site-opt-in'
const SITE_STATUS = 'ext30:site-status'
const TAB_STATUS = 'ext32:tab-status'
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
// Packaged popup.html may be opened as a top-level extension tab in E2E.
// Trust the exact packaged URL and top-frame identity, not sender.tab absence.
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
    'tab_id', 'kind', 'payload', 'host', 'enabled'])) return false
  try {
    if (new TextEncoder().encode(JSON.stringify(message)).length > MAX_BYTES) return false
  } catch { return false }
  if (message.version !== VERSION || !validUUID(message.request_id)) return false
  if (message.type === CONNECT) return keysOnly(message, ['type', 'version',
    'request_id', 'tab_id']) && validId(message.tab_id)
  if (message.type === DISCONNECT) return Object.keys(message).length === 3
  if (message.type === SITE_OPT) return keysOnly(message,
    ['type', 'version', 'request_id', 'host', 'enabled']) &&
    Object.hasOwn(ATS_ORIGINS, message.host) && typeof message.enabled === 'boolean'
  if (message.type === SITE_STATUS) return keysOnly(message,
    ['type', 'version', 'request_id', 'host']) && Object.hasOwn(ATS_ORIGINS, message.host)
  if (message.type === TAB_STATUS) return keysOnly(message,
    ['type', 'version', 'request_id', 'tab_id']) && validId(message.tab_id)
  if (message.type === COMMAND) return keysOnly(message,
    ['type', 'version', 'request_id', 'kind', 'payload']) &&
    validCommand(message)
  return false
}

async function clearConnection() {
  generation++
  connection = null
  clearObservationTimers()
  await warningWrites
  await chrome.storage.session.remove(['jobgridConnection', 'jobgridTabChecks'])
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
  clearObservationTimers()
  await warningWrites
  await chrome.storage.session.remove('jobgridTabChecks')
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
    if (['account_changed', 'protocol_error', 'not_authenticated'].includes(result.error.code)) {
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
  cancelObservation(tabId)
  void flushWarnings().catch(() => {})
  if (connection?.tabId === tabId) void clearConnection()
})
chrome.tabs.onUpdated?.addListener((tabId, changes, tab) => {
  if (connection?.tabId === tabId && (changes.url || changes.status === 'loading')) {
    void clearConnection()
    return
  }
  observeTabUpdate(tabId, changes, tab)
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (![PROBE, CONNECT, COMMAND, DISCONNECT, SITE_OPT, SITE_STATUS, TAB_STATUS].includes(message?.type)) return false
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
    if (message.type === SITE_OPT) return changeSiteOptIn(message.host, message.enabled)
    if (message.type === SITE_STATUS) return readSiteStatus(message.host)
    if (message.type === TAB_STATUS) return readTabStatus(message.tab_id)
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


// EXT-30: explicit, exact-host opt-in. Nothing is registered on installation.
// No host permission request is made except in response to a popup gesture.
const ATS_ORIGINS = Object.freeze({
  'boards.greenhouse.io': 'https://boards.greenhouse.io/*',
  'job-boards.greenhouse.io': 'https://job-boards.greenhouse.io/*',
  'jobs.lever.co': 'https://jobs.lever.co/*',
})
const SITE_STORAGE_KEY = 'jobgridSiteOptIns'
const scriptId = host => 'jobgrid-public-' + host.replaceAll('.', '-')
let siteSyncQueue = Promise.resolve()

async function readOptIns() {
  if (!chrome.storage.local?.get) return {}
  const stored = (await chrome.storage.local.get(SITE_STORAGE_KEY))?.[SITE_STORAGE_KEY]
  if (!plain(stored)) return {}
  const result = {}
  for (const host of Object.keys(ATS_ORIGINS)) {
    if (stored[host] === true) result[host] = true
  }
  return result
}

async function readSiteStatus(host) {
  const optIns = await readOptIns()
  const granted = await chrome.permissions.contains({ origins: [ATS_ORIGINS[host]] })
  return { ok: true, data: { protocol_version: VERSION, host,
    opted_in: optIns[host] === true, permission_granted: granted } }
}

async function syncSiteScriptsNow() {
  if (!chrome.scripting.getRegisteredContentScripts ||
      !chrome.scripting.registerContentScripts ||
      !chrome.scripting.unregisterContentScripts) return
  const optIns = await readOptIns()
  for (const [host, origin] of Object.entries(ATS_ORIGINS)) {
    const id = scriptId(host)
    const current = await chrome.scripting.getRegisteredContentScripts({ ids: [id] })
    const registered = current.some(item => item.id === id)
    const shouldRegister = optIns[host] === true &&
      await chrome.permissions.contains({ origins: [origin] })
    if (!shouldRegister && registered) {
      await chrome.scripting.unregisterContentScripts({ ids: [id] })
    } else if (shouldRegister && !registered) {
      await chrome.scripting.registerContentScripts([{
        id, matches: [origin], js: ['job-candidates.js'],
        runAt: 'document_idle', allFrames: false, persistAcrossSessions: false,
      }])
    }
  }
}

function syncSiteScripts() {
  const task = siteSyncQueue.then(syncSiteScriptsNow)
  siteSyncQueue = task.catch(() => {}) // a failed sync does not poison future grants
  return task
}

async function changeSiteOptIn(host, enabled) {
  if (!chrome.storage.local?.set) return unavailable()
  if (enabled) {
    if (!connection) return error('not_connected', 'Connect a JobGrid tab first')
    // This call must remain the first awaited operation after the popup click,
    // to preserve Chrome's user-gesture permission grant.
    const granted = await chrome.permissions.request({ origins: [ATS_ORIGINS[host]] })
    if (!granted) return error('permission_denied', 'Site access was not granted')
  }
  const optIns = await readOptIns()
  if (enabled) optIns[host] = true
  else delete optIns[host]
  await chrome.storage.local.set({ [SITE_STORAGE_KEY]: optIns })
  await syncSiteScripts()
  return readSiteStatus(host)
}

chrome.permissions.onRemoved?.addListener(removed => {
  const affected = Object.entries(ATS_ORIGINS)
    .filter(([, origin]) => removed?.origins?.includes(origin))
    .map(([host]) => host)
  if (affected.length === 0) return
  void (async () => {
    const optIns = await readOptIns()
    for (const host of affected) delete optIns[host]
    await chrome.storage.local.set({ [SITE_STORAGE_KEY]: optIns })
    for (const [tabId, observedUrl] of observedUrls) {
      if (affected.includes(classifyObservedUrl(observedUrl))) cancelObservation(tabId)
    }
    for (const [tabId, warning] of tabWarnings) {
      if (affected.includes(classifyObservedUrl(warning.url))) cancelObservation(tabId)
    }
    await flushWarnings()
    await syncSiteScripts()
  })().catch(() => {})
})

// After a worker restart, restore registration only for an earlier explicit
// site choice that Chrome still grants. The connection itself remains in memory.
if (chrome.storage.local?.get) void syncSiteScripts().catch(() => {})


// EXT-31: a single read-only check after a supported top-level navigation.
// This is worker-owned; job pages cannot issue API requests or writes.
const OBSERVE_DELAY_MS = 500
const observationTimers = new Map()
const observedUrls = new Map()
const checkedPages = new Map()
const OBSERVE_SECRET_KEYS = new Set(['token', 'access_token', 'auth',
  'authorization', 'code', 'password', 'session', 'session_token'])

function classifyObservedUrl(value) {
  if (typeof value !== 'string' || value.length > 2048 ||
      value !== value.trim() || /[\u0000-\u001f\u007f]/.test(value)) return null
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.port ||
        url.hostname.endsWith('.') || !Object.hasOwn(ATS_ORIGINS, url.hostname) ||
        url.origin !== 'https://' + url.hostname) return null
    const path = url.hostname === 'jobs.lever.co'
      ? /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/[A-Za-z0-9][A-Za-z0-9_-]*$/
      : /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/jobs\/[A-Za-z0-9][A-Za-z0-9_-]*$/
    if (!path.test(url.pathname)) return null
    for (const key of url.searchParams.keys()) {
      if (OBSERVE_SECRET_KEYS.has(key.toLowerCase())) return null
    }
    return url.hostname
  } catch { return null }
}

function cancelObservation(tabId) {
  const timer = observationTimers.get(tabId)
  if (timer) clearTimeout(timer)
  observationTimers.delete(tabId)
  observedUrls.delete(tabId)
  checkedPages.delete(tabId)
  tabWarnings.delete(tabId)
}

function clearObservationTimers() {
  for (const tabId of observationTimers.keys()) cancelObservation(tabId)
  observedUrls.clear()
  checkedPages.clear()
  tabWarnings.clear()
}

async function observationStillAllowed(tabId, url, selected) {
  if (!connection || connection !== selected || !classifyObservedUrl(url)) return false
  try {
    const host = classifyObservedUrl(url)
    const optIns = await readOptIns()
    if (optIns[host] !== true ||
        !await chrome.permissions.contains({ origins: [ATS_ORIGINS[host]] })) return false
    const tab = await chrome.tabs.get(tabId)
    return connection === selected && tab.url === url && tab.status === 'complete'
  } catch { return false }
}

async function readPublicCandidates(tabId, url) {
  const requestId = crypto.randomUUID()
  let timer
  const expired = Symbol('expired')
  let result
  try {
    result = await Promise.race([
      chrome.tabs.sendMessage(tabId, {
        type: 'ext29:extract', version: VERSION, request_id: requestId, url,
      }),
      new Promise(resolve => { timer = setTimeout(() => resolve(expired), TIMEOUT_MS) }),
    ])
  } catch { return null
  } finally { clearTimeout(timer) }
  if (result === expired || !plain(result) || result.ok !== true ||
      result.version !== VERSION || result.request_id !== requestId ||
      result.url !== url ||
      !keysOnly(result, ['version', 'request_id', 'ok', 'url', 'title', 'company']) ||
      (result.company !== null && !validText(result.company, 320)) ||
      (result.title !== null && !validText(result.title, 500))) return null
  return { company: result.company, title: result.title }
}

async function runNavigationCheck(tabId, url, selected) {
  if (!await observationStillAllowed(tabId, url, selected)) return
  const candidates = await readPublicCandidates(tabId, url)
  if (!candidates || !await observationStillAllowed(tabId, url, selected)) return
  const result = await dispatch('check', { url, ...candidates })
  if (!result.ok || !connection || connection !== selected ||
      !await observationStillAllowed(tabId, url, selected) ||
      !validCheckFacts(result.data)) return
  // Keep the response before any future visit write. EXT-32 persists and
  // uses this immutable pre-write warning snapshot.
  const beforeVisit = result.data
  checkedPages.set(tabId, { url, accountId: selected.accountId, beforeVisit })
  // Persist the check evidence before any write. A failed session-storage write
  // aborts the visit, rather than making the warning impossible to recover.
  await recordTabWarning(tabId, url, selected, beforeVisit, 'checked')
  if (!await observationStillAllowed(tabId, url, selected)) return
  if (beforeVisit.visit.visited === true) {
    await recordTabWarning(tabId, url, selected, beforeVisit, 'already_visited')
    return
  }
  const visit = await dispatch('visit', { url })
  // The server uses the selected cookie owner; an unknown response must never
  // appear as a saved visit. Original check matches are never overwritten.
  if (!await observationStillAllowed(tabId, url, selected)) return
  await recordTabWarning(tabId, url, selected, beforeVisit,
    visit.ok ? 'saved' : 'save_unknown')
}

function observeTabUpdate(tabId, changes, tab) {
  if (!validId(tabId)) return
  if (changes?.url || changes?.status === 'loading') {
    const hadWarning = tabWarnings.has(tabId)
    cancelObservation(tabId)
    if (hadWarning) void flushWarnings().catch(() => {})
  }
  if (changes?.status !== 'complete' &&
      !(changes?.url && tab?.status === 'complete')) return
  const url = tab?.url
  const selected = connection
  if (!selected || !classifyObservedUrl(url) || observedUrls.get(tabId) === url) return
  observedUrls.set(tabId, url)
  const timer = setTimeout(() => {
    observationTimers.delete(tabId)
    void runNavigationCheck(tabId, url, selected).catch(() => {})
  }, OBSERVE_DELAY_MS)
  observationTimers.set(tabId, timer)
}


// EXT-32: preserve the pre-visit warning and mark writes as confirmed only
// after the authenticated visit response and final tab/account check.
const tabWarnings = new Map()
let warningWrites = Promise.resolve()
const MAX_TAB_WARNINGS = 40

function validCheckFacts(data) {
  return plain(data) && plain(data.visit) &&
    typeof data.visit.visited === 'boolean' &&
    (data.visit.first_visited_at === null ||
      typeof data.visit.first_visited_at === 'string') &&
    Array.isArray(data.matches) && data.matches.length <= 20 &&
    Number.isSafeInteger(data.company_history_count) &&
    typeof data.company_known === 'boolean' &&
    typeof data.lookup_complete === 'boolean' &&
    typeof data.checked_at === 'string'
}

function flushWarnings() {
  const write = warningWrites.then(async () => {
    await chrome.storage.session.set({
      jobgridTabChecks: Object.fromEntries(tabWarnings),
    })
  })
  warningWrites = write.catch(() => {})
  return write
}

async function recordTabWarning(tabId, url, selected, beforeVisit, saveState) {
  if (!connection || connection !== selected) return
  if (!tabWarnings.has(tabId) && tabWarnings.size >= MAX_TAB_WARNINGS) {
    tabWarnings.delete(tabWarnings.keys().next().value)
  }
  tabWarnings.set(tabId, {
    account_id: selected.accountId, tab_id: tabId, url,
    before_visit: beforeVisit, save_state: saveState,
  })
  await flushWarnings()
}

async function readTabStatus(tabId) {
  if (!connection) return error('not_connected', 'Open JobGrid to connect')
  const state = tabWarnings.get(tabId)
  if (!state || state.account_id !== connection.accountId) {
    return error('no_check', 'No checked job is available for this tab')
  }
  try {
    const tab = await chrome.tabs.get(tabId)
    if (tab.url !== state.url) return error('stale_tab', 'Page changed')
  } catch { return unavailable() }
  return { ok: true, data: {
    protocol_version: VERSION, account_id: state.account_id,
    url: state.url, before_visit: state.before_visit,
    save_state: state.save_state,
  } }
}
