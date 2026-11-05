import { APP_ORIGIN } from './config.js'
import { safeMatchText, summarizeWarning, summarizeFailure } from './popup-state.js'
import { normalizeApplicationFields, checkedJobForAccount, sameStagedIntent } from './popup-apply.js'

const byId = id => document.getElementById(id)
const el = {
  connect: byId('connect'), pause: byId('pause'), disconnect: byId('disconnect'),
  check: byId('check'), connection: byId('connection'), feedback: byId('feedback'),
  title: byId('result-title'), detail: byId('result-detail'),
  save: byId('result-save'), lookup: byId('result-lookup'), matches: byId('matches'),
  applySection: byId('apply-section'), applyAccount: byId('apply-account'),
  applyUrl: byId('apply-url'), draftForm: byId('draft-form'),
  company: byId('apply-company'), jobTitle: byId('apply-title'),
  draftError: byId('draft-error'), stage: byId('stage'),
  approval: byId('approval'), confirmApply: byId('confirm-apply'),
  submitApply: byId('submit-apply'),
  forget: byId('forget'), forgetConfirmation: byId('forget-confirmation'),
  forgetAccount: byId('forget-account'), forgetPhrase: byId('forget-phrase'),
  forgetFinal: byId('forget-final'), forgetCancel: byId('forget-cancel'),
  jobgridLink: byId('open-jobgrid'),
}
let state = { connected: false, paused: false }
let busy = false
let retryUntil = 0
let retryTimer = null
let checkNeedsRetry = false
let checkedJob = null
let checkedTabId = null
let stagedIntent = null
let forgetAccountId = null

function hideForgetConfirmation() {
  forgetAccountId = null
  el.forgetConfirmation.hidden = true
  el.forgetPhrase.value = ''
}


function resetStage() {
  stagedIntent = null
  el.approval.hidden = true
  el.confirmApply.checked = false
}
function hideApplication() {
  resetStage()
  checkedJob = null
  checkedTabId = null
  el.applySection.hidden = true
  el.company.value = ''
  el.jobTitle.value = ''
  el.draftError.textContent = ''
}
function showApplication(record, tabId) {
  if (!checkedJobForAccount(record, state) || !Number.isSafeInteger(tabId) ||
      record.apply_status === 'saved') {
    hideApplication()
    return
  }
  const switched = !checkedJob || checkedJob.url !== record.url ||
    checkedJob.account_id !== record.account_id || checkedTabId !== tabId
  if (switched) {
    resetStage()
    el.company.value = ''
    el.jobTitle.value = ''
    el.draftError.textContent = ''
  }
  checkedJob = record
  checkedTabId = tabId
  el.applySection.hidden = false
  el.applyAccount.textContent = 'Selected JobGrid account: ' +
    (state.account_label || 'Account') + ' (ID ' + state.account_id + ')'
  el.applyUrl.textContent = 'Checked job URL: ' + record.url
  controls()
}

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
  el.check.disabled = busy || !state.connected || state.paused || Date.now() < retryUntil
  el.check.textContent = checkNeedsRetry ? 'Retry check' : 'Check current tab'
  el.pause.textContent = state.paused ? 'Resume checks' : 'Pause checks'
  el.stage.disabled = busy || !checkedJob || !state.connected || state.paused
  el.submitApply.disabled = busy || !stagedIntent || !el.confirmApply.checked ||
    !checkedJobForAccount(checkedJob, state)
  el.forget.disabled = busy || !state.connected || state.paused
  el.forgetFinal.disabled = busy || !state.connected || state.paused ||
    forgetAccountId !== state.account_id ||
    el.forgetPhrase.value !== 'FORGET VISITS'
}
function feedback(message) { el.feedback.textContent = message }
function render(record) {
  if (!record?.before_visit) hideApplication()
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
  if (action === 'check') {
    checkNeedsRetry = true
    if (problem?.code === 'rate_limited') {
      const seconds = Number.isSafeInteger(problem.retry_after) &&
        problem.retry_after >= 0 && problem.retry_after <= 3600
        ? problem.retry_after : 60
      retryUntil = Math.max(retryUntil, Date.now() + seconds * 1000)
      if (retryTimer !== null) clearTimeout(retryTimer)
      retryTimer = setTimeout(() => { retryTimer = null; controls() },
        Math.max(0, retryUntil - Date.now()) + 10)
    }
    controls()
  }
  if (action !== 'apply') hideApplication()
  const view = summarizeFailure(problem, action)
  el.title.textContent = view.title
  el.detail.textContent = view.detail
  el.save.textContent = ''
  if (el.lookup) el.lookup.textContent = ''
  el.matches.replaceChildren()
  feedback(view.title + '. ' + view.detail)
}
function showConnection() {
  if (!state.connected || state.paused || forgetAccountId !== state.account_id)
    hideForgetConfirmation()
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
    hideApplication()
    showConnection()
    showFailure(connection.error, 'connect')
    return
  }
  state = connection.data
  showConnection()
  if (!state.connected || state.paused) {
    hideApplication()
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
      showApplication(checked.data, active[0].id)
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
  if (!state.paused && !window.confirm('Pause automatic JobGrid checks? You can resume later.')) return
  hideForgetConfirmation()
  feedback(state.paused ? 'Resuming checks…' : 'Pausing checks…')
  const result = await send('ext35:set-paused', { paused: !state.paused })
  if (!result.ok) { showFailure(result.error); return }
  feedback(result.data.paused ? 'Automatic checks are paused.' : 'Checks resumed.')
  await refresh()
}))

el.disconnect.addEventListener('click', () => run(async () => {
  if (!window.confirm('Disconnect this JobGrid account? Saved visits and applications will remain.')) return
  hideForgetConfirmation()
  const result = await send('ext26:disconnect')
  if (!result.ok) { showFailure(result.error); return }
  feedback('Disconnected. Saved JobGrid visits were not deleted.')
  await refresh()
}))

el.check.addEventListener('click', () => run(async () => {
  if (Date.now() < retryUntil) return
  feedback('Checking current tab…')
  render(null)
  const result = await send('ext33:current-tab-check')
  if (!result.ok) {
    showFailure(result.error)
    return
  }
  checkNeedsRetry = false
  retryUntil = 0
  render(result.data)
  try {
    const active = await chrome.tabs.query({ active: true, currentWindow: true })
    if (active.length === 1 && active[0].url === result.data.url)
      showApplication(result.data, active[0].id)
  } catch { hideApplication() }
  feedback('Check complete. Manual checks do not save a visit.')
}))

controls()
void refresh()

for (const input of [el.company, el.jobTitle]) {
  input.addEventListener('input', () => {
    resetStage()
    el.draftError.textContent = 'Review again after changing the details.'
    controls()
  })
}

el.confirmApply.addEventListener('change', controls)

el.draftForm.addEventListener('submit', event => {
  event.preventDefault()
  void run(async () => {
    if (!checkedJobForAccount(checkedJob, state) || !Number.isSafeInteger(checkedTabId)) {
      showFailure({ code: 'account_changed' })
      return
    }
    const values = normalizeApplicationFields(el.company.value, el.jobTitle.value)
    if (!values.ok) {
      el.draftError.textContent = values.message
      return
    }
    resetStage()
    el.draftError.textContent = 'Reviewing the selected account and checked URL…'
    const prepared = await send('ext34:stage-apply', {
      tab_id: checkedTabId, company: values.company, title: values.title,
    })
    if (!prepared.ok) {
      showFailure(prepared.error, 'apply')
      return
    }
    if (!sameStagedIntent(checkedJob, state, prepared.data, values)) {
      showFailure({ code: 'account_changed' })
      return
    }
    stagedIntent = prepared.data
    el.draftError.textContent = 'Review the employer, role, account and URL before saving.'
    el.approval.hidden = false
    el.confirmApply.checked = false
    controls()
  })
})

el.submitApply.addEventListener('click', () => {
  void run(async () => {
    const values = normalizeApplicationFields(el.company.value, el.jobTitle.value)
    if (!el.confirmApply.checked || !values.ok ||
        !sameStagedIntent(checkedJob, state, stagedIntent, values) ||
        !Number.isSafeInteger(checkedTabId)) {
      resetStage()
      el.draftError.textContent = 'Review the exact account, URL and details again.'
      return
    }
    feedback('Saving to the selected JobGrid account…')
    const result = await send('ext39:submit-pending', { tab_id: checkedTabId })
    if (!result.ok) {
      showFailure(result.error, 'apply')
      if (['stale_tab', 'no_check', 'account_changed', 'not_authenticated'].includes(result.error?.code))
        hideApplication()
      return
    }
    if (result.data?.saved !== true || result.data.account_id !== state.account_id ||
        result.data.url !== checkedJob.url) {
      showFailure({ code: 'save_unknown' }, 'apply')
      return
    }
    render({ ...checkedJob, apply_status: 'saved' })
    hideApplication()
    feedback('JobGrid confirmed this application was recorded. No job-site form was submitted.')
  })
})

el.jobgridLink.href = APP_ORIGIN + '/applications'

el.forget.addEventListener('click', () => {
  if (!state.connected || state.paused) return
  forgetAccountId = state.account_id
  el.forgetAccount.textContent = 'Selected account: ' +
    (state.account_label || 'Account') + ' (ID ' + state.account_id + ')'
  el.forgetPhrase.value = ''
  el.forgetConfirmation.hidden = false
  controls()
})

el.forgetPhrase.addEventListener('input', controls)
el.forgetCancel.addEventListener('click', () => {
  hideForgetConfirmation()
  controls()
})

el.forgetFinal.addEventListener('click', () => {
  void run(async () => {
    if (!state.connected || state.paused || forgetAccountId !== state.account_id ||
        el.forgetPhrase.value !== 'FORGET VISITS') return
    const originalAccount = forgetAccountId
    feedback('Deleting external visit memory for this account…')
    const result = await send('ext26:command', {
      kind: 'forget_visits', payload: { confirmed: true },
    })
    if (!result.ok) {
      showFailure(result.error, 'forget')
      return
    }
    if (result.data?.account_id !== originalAccount ||
        !Number.isSafeInteger(result.data?.deleted) || result.data.deleted < 0) {
      showFailure({ code: 'unavailable' }, 'forget')
      return
    }
    hideForgetConfirmation()
    hideApplication()
    render(null)
    await refresh()
    feedback(result.data.deleted + ' external visit record(s) deleted from JobGrid. Applications and CSV history remain.')
  })
})
