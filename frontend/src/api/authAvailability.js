/** Understand hosting failures without treating a failed session check as logout.
 * No automatic authentication POST retries, no user data or response body logging.
 */
const MAX_RETRY_AFTER_SECONDS = 3600

export function readRetryAfter(headers) {
  const value = headers?.['retry-after'] ?? headers?.get?.('retry-after')
  if (value == null || value === '') return null
  const seconds = Number(value)
  return Number.isSafeInteger(seconds) && seconds > 0 && seconds <= MAX_RETRY_AFTER_SECONDS
    ? seconds
    : null
}

export function isRenderHibernationThrottle(error) {
  const header = error?.response?.headers?.['x-render-routing']
    ?? error?.response?.headers?.get?.('x-render-routing')
  return error?.response?.status === 429
    && typeof header === 'string'
    && header.toLowerCase() === 'hibernate-rate-limited'
}

export function sessionCheckProblem(error) {
  const status = error?.response?.status
  if (status === 401 || status === 403) return null
  if (status === 429) {
    return {
      kind: 'rate_limited',
      retryAfter: readRetryAfter(error?.response?.headers),
      message: 'The server is temporarily limiting requests. JobGrid could not check your existing session. This does not mean your login failed.',
    }
  }
  return {
    kind: 'unavailable',
    retryAfter: null,
    message: 'JobGrid could not contact the server to check your session. Your login status is still unknown.',
  }
}

export function emailAuth429Message(error) {
  if (isRenderHibernationThrottle(error)) {
    return 'The hosting service is temporarily limiting requests. Your password was not checked. Please try again after the server recovers.'
  }
  if (error?.response?.data?.detail === 'Too many attempts. Try again later.') {
    return 'Too many sign-in attempts for this account or connection. Please wait before trying again.'
  }
  return 'The login service is temporarily limiting requests. Your password might not have been checked. Please wait and try again.'
}
