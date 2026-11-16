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
  if (level === 'error') console.error('[JobGrid diagnostic]', data)
  else console.warn('[JobGrid diagnostic]', data)
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
