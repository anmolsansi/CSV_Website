/* EXT-29: read public ATS headings only, on a worker request after site opt-in. */
;(() => {
  'use strict'
  if (typeof chrome === 'undefined' || !chrome.runtime?.id ||
      !chrome.runtime.onMessage?.addListener || window.top !== window) return

  const PATHS = {
    'boards.greenhouse.io': /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/jobs\/[A-Za-z0-9][A-Za-z0-9_-]*$/,
    'job-boards.greenhouse.io': /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/jobs\/[A-Za-z0-9][A-Za-z0-9_-]*$/,
    'jobs.lever.co': /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/[A-Za-z0-9][A-Za-z0-9_-]*$/,
  }
  const SECRET_KEYS = new Set(['token', 'access_token', 'auth', 'authorization',
    'code', 'password', 'session', 'session_token'])
  const SELECTORS = {
    greenhouse: {
      title: ['[data-testid="job-title"]', '.app-title', 'h1'],
      company: ['[data-testid="company-name"]', '.company-name', '.company-header h2'],
    },
    lever: {
      title: ['.posting-headline h2', '.posting-headline h1', 'h1'],
      company: ['.posting-headline .company', '.posting-company', '.main-header .company-name'],
    },
  }
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  const blockedAncestor = 'form, input, textarea, select, [contenteditable], [hidden], [aria-hidden="true"]'

  function eligible(href) {
    if (typeof href !== 'string' || href.length > 2048) return null
    try {
      const url = new URL(href)
      if (url.protocol !== 'https:' || url.username || url.password || url.port ||
          !Object.hasOwn(PATHS, url.hostname) || url.hostname.endsWith('.') ||
          !PATHS[url.hostname].test(url.pathname)) return null
      for (const key of url.searchParams.keys()) {
        if (SECRET_KEYS.has(key.toLowerCase())) return null
      }
      return url.hostname === 'jobs.lever.co' ? 'lever' : 'greenhouse'
    } catch { return null }
  }

  function heading(selectors, max) {
    for (const selector of selectors) {
      const node = document.querySelector(selector)
      if (!node || typeof node.closest !== 'function' ||
          node.closest(blockedAncestor)) continue
      // Never read form values, body text, input fields, hidden metadata or scripts.
      const raw = typeof node.innerText === 'string' ? node.innerText : node.textContent
      if (typeof raw !== 'string') continue
      const value = raw.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim()
      if (value && value.length <= max) return value
    }
    return null
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== 'ext29:extract') return false
    if (message.version !== 1 || !UUID.test(message.request_id) ||
        message.url !== location.href || Object.keys(message).length !== 4) {
      sendResponse({ version: 1, request_id: message?.request_id, ok: false })
      return false
    }
    const site = eligible(location.href)
    if (!site) {
      sendResponse({ version: 1, request_id: message.request_id, ok: false })
      return false
    }
    const selectors = SELECTORS[site]
    sendResponse({
      version: 1, request_id: message.request_id, ok: true, url: location.href,
      title: heading(selectors.title, 500), company: heading(selectors.company, 320),
    })
    return false
  })
})()
