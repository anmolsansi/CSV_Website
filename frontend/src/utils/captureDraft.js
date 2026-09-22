const DRAFT_KEY = 'jobgrid:capture-draft:v1'
const DRAFT_TTL_MS = 60 * 60 * 1000
const MAX_FRAGMENT_CHARS = 32 * 1024
const MAX_URL_CHARS = 2048
const MAX_TEXT_CHARS = 300
const MAX_NOTES_CHARS = 20000

function cleanString(value) {
  return typeof value === 'string' ? value : ''
}

export function isSafeCaptureReturnPath(value) {
  return value === '/capture' ? '/capture' : null
}

export function validateCaptureUrl(value, { required = true } = {}) {
  const url = cleanString(value).trim()
  if (!url) return required ? 'Job URL is required.' : null
  if (url.length > MAX_URL_CHARS) return 'Job URL must be 2,048 characters or fewer.'
  if (/\s/.test(url)) return 'Job URL cannot contain whitespace.'
  try {
    const parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol)) return 'Job URL must use HTTP or HTTPS.'
    if (parsed.username || parsed.password) return 'Job URL cannot contain embedded credentials.'
  } catch {
    return 'Enter a valid HTTP or HTTPS job URL.'
  }
  return null
}

export function normalizeCaptureDraft(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const allowed = new Set(['job_url', 'title', 'company', 'source', 'notes'])
  if (Object.keys(value).some((key) => !allowed.has(key))) return null

  const draft = {
    job_url: cleanString(value.job_url),
    title: cleanString(value.title),
    company: cleanString(value.company),
    source: value.source === 'bookmarklet' ? 'bookmarklet' : value.source === 'manual' ? 'manual' : null,
    notes: cleanString(value.notes),
  }
  if (!draft.source) return null
  if (draft.job_url.length > MAX_URL_CHARS) return null
  if (draft.title.length > MAX_TEXT_CHARS || draft.company.length > MAX_TEXT_CHARS) return null
  if (draft.notes.length > MAX_NOTES_CHARS) return null
  if (draft.job_url && validateCaptureUrl(draft.job_url, { required: false })) return null
  return draft
}

export function saveCaptureDraft(draft, storage = window.sessionStorage, now = Date.now()) {
  const normalized = normalizeCaptureDraft(draft)
  if (!normalized) return false
  storage.setItem(DRAFT_KEY, JSON.stringify({ saved_at: now, draft: normalized }))
  return true
}

export function loadCaptureDraft(storage = window.sessionStorage, now = Date.now()) {
  const raw = storage.getItem(DRAFT_KEY)
  if (!raw) return null
  try {
    const envelope = JSON.parse(raw)
    const savedAt = Number(envelope?.saved_at)
    if (!Number.isFinite(savedAt) || savedAt > now || now - savedAt > DRAFT_TTL_MS) {
      storage.removeItem(DRAFT_KEY)
      return null
    }
    const draft = normalizeCaptureDraft(envelope?.draft)
    if (!draft) {
      storage.removeItem(DRAFT_KEY)
      return null
    }
    return draft
  } catch {
    storage.removeItem(DRAFT_KEY)
    return null
  }
}

export function clearCaptureDraft(storage = window.sessionStorage) {
  storage.removeItem(DRAFT_KEY)
}

export function ingestCaptureFragment(win = window, now = Date.now()) {
  const hash = win.location.hash || ''
  if (!hash.startsWith('#payload=')) return { draft: null, error: null, consumed: false }

  const cleanLocation = `${win.location.pathname}${win.location.search}`
  win.history.replaceState(null, '', cleanLocation)

  if (hash.length > MAX_FRAGMENT_CHARS) {
    clearCaptureDraft(win.sessionStorage)
    return { draft: null, error: 'Capture payload was too large and was discarded.', consumed: true }
  }

  try {
    const raw = new URLSearchParams(hash.slice(1)).get('payload')
    if (!raw) throw new Error('missing payload')
    const parsed = JSON.parse(raw)
    const draft = normalizeCaptureDraft(parsed)
    if (!draft) throw new Error('invalid payload')
    saveCaptureDraft(draft, win.sessionStorage, now)
    return { draft, error: null, consumed: true }
  } catch {
    clearCaptureDraft(win.sessionStorage)
    return { draft: null, error: 'Capture payload was malformed and was discarded.', consumed: true }
  }
}

export function createCaptureBookmarklet(appOrigin = window.location.origin) {
  const origin = new URL(appOrigin)
  const base = `${origin.origin}/capture#payload=`
  return `javascript:(()=>{const p={job_url:location.href,title:document.title,company:'',source:'bookmarklet',notes:''};const u=${JSON.stringify(base)}+encodeURIComponent(JSON.stringify(p));const w=window.open(u,'_blank','noopener,noreferrer');if(!w){window.prompt('Popup blocked. Copy this JobGrid capture link:',u)}})()`
}

export const captureDraftConstants = {
  key: DRAFT_KEY,
  ttlMs: DRAFT_TTL_MS,
  maxFragmentChars: MAX_FRAGMENT_CHARS,
}
