import { APP_ORIGIN } from './config.js'
import { safeMatchText, summarizeWarning, summarizeFailure } from './popup-state.js'

const byId = id => document.getElementById(id)
const el = {
  connect: byId('connect'), pause: byId('pause'), disconnect: byId('disconnect'),
  check: byId('check'), connection: byId('connection'), feedback: byId('feedback'),
  title: byId('result-title'), detail: byId('result-detail'),
  save: byId('result-save'), lookup: byId('result-lookup'), matches: byId('matches'),
}
let state = { connected: false, paused: false }
let busy = false

async function send(type, extra = {}) {
  const id = crypto.randomUUID()
  try {
    const response = await chrome.runtime.sendMessage({
      type, version: 1, request_id: id, ...extra,
    })
    if (!response || response.request_id !== id ||
        response.version !== 1 || typeof response.ok !== 'boolean') {
      return { ok: false, error: { code: 'unavailable', message: 'JobGrid is unavailable' } }
    }
    return response
  } catch {
    return { ok: false, error: { code: 'unavailable', message: 'JobGrid is unavailable' } }
  }
}

function controls() {
  el.connect.disabled = busy
  el.pause.disabled = busy || !state.connected
  el.disconnect.disabled = busy || !state.connected
  el.check.disabled = busy || !state.connected || state.paused
  el.pause.textContent = state.paused ? 'Resume checks' : 'Pause checks'
}
function feedback(message) { el.feedback.textContent = message }
function render(record) {
  const view = summarizeWarning(record)
  el.title.textContent = view.title
  el.detail.textContent = view.detail
  el.save.textContent = view.save
  if (el.lookup) el.lookup.textContent = view.lookup || ''
  el.matches.replaceChildren()
  for (const match of (record?.before_visit?.matches || []).slice(0, 5)) {
    const li = document.createElement('li')
    li.textContent = safeMatchText(match)
    el.matches.append(li)
  }
  if (record?.before_visit?.matches?.length > 5) {
    const more = document.createElement('li')
    more.textContent = 'Additional matches are available in JobGrid.'
    el.matches.append(more)
  }
}
function showFailure(problem, action = 'check') {
  const view = summarizeFailure(problem, action)
  el.title.textContent = view.title
  el.detail.textContent = view.detail
  el.save.textContent = ''
  if (el.lookup) el.lookup.textContent = ''
  el.matches.replaceChildren()
  feedback(view.title + '. ' + view.detail)
}
function showConnection() {
  el.connection.textContent = !state.connected
    ? 'Not connected. Keep a signed-in JobGrid tab open.'
    : state.paused
      ? 'Checks paused for ' + (state.account_label || 'selected account')
      : 'Connected to ' + (state.account_label || 'selected account')
  controls()
}
async function run(action) {
  if (busy) return
  busy = true
  controls()
  try { await action() } catch { showFailure({ code: 'unavailable' }) } finally { busy = false; controls() }
}
async function refresh() {
  const connection = await send('ext35:status')
  if (!connection.ok) {
    state = { connected: false, paused: false }
    showConnection()
    showFailure(connection.error, 'connect')
    return
  }
  state = connection.data
  showConnection()
  if (!state.connected || state.paused) {
    render(null)
    return
  }
  try {
    const active = await chrome.tabs.query({ active: true, currentWindow: true })
    if (active.length !== 1 || !Number.isSafeInteger(active[0].id)) {
      render(null)
      return
    }
    const checked = await send('ext32:tab-status', { tab_id: active[0].id })
    if (checked.ok) {
      render(checked.data)
      feedback('Showing the latest check for this tab.')
    } else if (checked.error?.code === 'no_check') {
      render(null)
    } else {
      showFailure(checked.error)
    }
  } catch {
    render(null)
    showFailure({ code: 'unsupported' })
  }
}

el.connect.addEventListener('click', () => run(async () => {
  feedback('Connecting to JobGrid…')
  // Chrome must see a direct user gesture for its optional host prompt.
  let granted
  try { granted = await chrome.permissions.request({ origins: [APP_ORIGIN + '/*'] }) } catch { granted = false }
  if (!granted) { showFailure({ code: 'permission_denied' }, 'connect'); return }
  let tabs
  try { tabs = await chrome.tabs.query({ url: [APP_ORIGIN + '/*'] }) } catch { tabs = [] }
  const eligible = tabs.filter(tab => {
    try { return new URL(tab.url).origin === APP_ORIGIN } catch { return false }
  })
  if (eligible.length !== 1) {
    feedback('Keep exactly one signed-in JobGrid tab open before connecting.')
    return
  }
  const result = await send('ext26:connect', { tab_id: eligible[0].id })
  if (!result.ok) { showFailure(result.error, 'connect'); return }
  feedback('Connected. Check a public job page to view history.')
  await refresh()
}))

el.pause.addEventListener('click', () => run(async () => {
  feedback(state.paused ? 'Resuming checks…' : 'Pausing checks…')
  const result = await send('ext35:set-paused', { paused: !state.paused })
  if (!result.ok) { showFailure(result.error); return }
  feedback(result.data.paused ? 'Automatic checks are paused.' : 'Checks resumed.')
  await refresh()
}))

el.disconnect.addEventListener('click', () => run(async () => {
  const result = await send('ext26:disconnect')
  if (!result.ok) { showFailure(result.error); return }
  feedback('Disconnected. Saved JobGrid visits were not deleted.')
  await refresh()
}))

el.check.addEventListener('click', () => run(async () => {
  feedback('Checking current tab…')
  render(null)
  const result = await send('ext33:current-tab-check')
  if (!result.ok) {
    showFailure(result.error)
    return
  }
  render(result.data)
  feedback('Check complete. Manual checks do not save a visit.')
}))

controls()
void refresh()
