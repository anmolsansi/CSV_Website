/* EXT-05 read-only integration spike. Real tab selection/tracking belongs to EXT-26+. */
'use strict'

const APP_ORIGIN = 'https://csv-website-steel.vercel.app'
const PROBE = 'ext05:session-probe'
const VERSION = 1

function failure(code) {
  return { version: VERSION, ok: false, error: { code, message: 'JobGrid account unavailable' } }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only our own packaged popup can request this read-only probe.
  if (message?.type !== PROBE || sender?.id !== chrome.runtime.id ||
      sender?.url !== chrome.runtime.getURL('popup.html') || sender?.tab) {
    return false
  }

  ;(async () => {
    const permitted = await chrome.permissions.contains({ origins: [APP_ORIGIN + '/*'] })
    if (!permitted) return failure('not_connected')
    const tabs = await chrome.tabs.query({ url: [APP_ORIGIN + '/*'] })
    // This spike deliberately refuses ambiguous tabs. EXT-26 owns tab selection.
    if (tabs.length !== 1 || !Number.isInteger(tabs[0].id)) {
      return failure('unavailable')
    }
    const tabId = tabs[0].id
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      files: ['jobgrid-bridge.js'],
      world: 'ISOLATED',
    })
    const requestId = crypto.randomUUID()
    const reply = await chrome.tabs.sendMessage(tabId, {
      version: VERSION,
      request_id: requestId,
      kind: 'session',
      payload: {},
    })
    if (reply?.version !== VERSION || reply?.request_id !== requestId ||
        typeof reply.ok !== 'boolean') return failure('unavailable')
    if (reply.ok && (!Number.isSafeInteger(reply.data?.account_id) ||
        reply.data.account_id <= 0 || reply.data.protocol_version !== VERSION)) {
      return failure('unavailable')
    }
    return reply
  })().then(sendResponse, () => sendResponse(failure('unavailable')))
  return true
})
