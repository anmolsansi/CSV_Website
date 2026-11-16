/**
 * Frontend-wide diagnostics, intentionally local and redacted.
 *
 * Do not include Axios Error objects, response bodies, request URLs, headers,
 * exception messages/stacks or user-visible toast text in console output.
 */
export const API_AVAILABILITY_EVENT = 'jobgrid:api-availability'

const SAFE_RESOURCES = new Set([
  'auth', 'crm', 'rows', 'upload', 'preferences', 'health', 'ready',
])
// Only fixed, known app routes. Dynamic paths and query values are never logged.
const SAFE_ROUTES = new Set([
  '/', '/login', '/archive', '/today', '/applications', '/applications/new',
  '/documents', '/analytics', '/pipeline', '/sessions', '/saved-views',
  '/applypilot', '/duplicates', '/companies', '/capture', '/import',
])
function safePage() {
  const path = typeof window !== 'undefined' ? window.location?.pathname : null
  return SAFE_ROUTES.has(path) ? path : 'other'
}

function safeResource(url) {
  if (typeof url !== 'string') return 'other'
  const first = url.split(/[?#]/, 1)[0].split('/').filter(Boolean)[0]
  return SAFE_RESOURCES.has(first) ? first : 'other'
}

function safeMethod(method) {
  const value = typeof method === 'string' ? method.toUpperCase() : ''
  return ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(value) ? value : 'OTHER'
}

function emit(level, data) {
  const record = { ...data, page: safePage() }
  if (level === 'error') console.error('[JobGrid diagnostic]', record)
  else console.warn('[JobGrid diagnostic]', record)
}

export function logApiFailure(error, problem) {
  const status = error?.response?.status
  // Expected unauthenticated sessions are not an operational warning.
  if (status === 401 || status === 403 || error?.code === 'ERR_CANCELED') return
  if (typeof status === 'number' && status < 400) return
  const kind = problem?.kind ?? 'request_rejected'
  emit(problem?.level === 'error' || status >= 500 ? 'error' : 'warn', {
    event: 'api_failure',
    kind,
    status: Number.isInteger(status) ? status : null,
    method: safeMethod(error?.config?.method),
    resource: safeResource(error?.config?.url),
    retryAfterSeconds: problem?.retryAfter ?? null,
  })
}

export function logUiFeedback(type) {
  if (!['error', 'warning', 'warn'].includes(type)) return
  emit(type === 'error' ? 'error' : 'warn', {
    event: 'ui_feedback',
    kind: type === 'error' ? 'error' : 'warning',
  })
}

export function logReactFailure() {
  emit('error', { event: 'react_render_failure' })
}

let globalDiagnosticsInstalled = false

export function installBrowserDiagnostics() {
  if (globalDiagnosticsInstalled || typeof window === 'undefined') return
  globalDiagnosticsInstalled = true
  window.addEventListener('error', () => {
    emit('error', { event: 'uncaught_browser_error' })
  })
  window.addEventListener('unhandledrejection', () => {
    emit('error', { event: 'unhandled_promise_rejection' })
  })
}
