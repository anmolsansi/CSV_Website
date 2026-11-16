/** Pure HTTP failure classification shared by every frontend feature. */
const MAX_RETRY_AFTER_SECONDS = 3600

function headerValue(headers, name) {
  return headers?.[name] ?? headers?.get?.(name) ?? null
}

export function readRetryAfter(headers) {
  const raw = headerValue(headers, 'retry-after')
  if (typeof raw !== 'string' && typeof raw !== 'number') return null
  const value = String(raw).trim()
  if (!value) return null
  let seconds
  if (/^\d+$/.test(value)) {
    seconds = Number(value)
  } else {
    const date = Date.parse(value)
    if (!Number.isFinite(date)) return null
    seconds = Math.ceil((date - Date.now()) / 1000)
  }
  return Number.isSafeInteger(seconds) && seconds > 0 && seconds <= MAX_RETRY_AFTER_SECONDS
    ? seconds
    : null
}

export function isRenderHibernationThrottle(error) {
  const header = headerValue(error?.response?.headers, 'x-render-routing')
  return error?.response?.status === 429
    && typeof header === 'string'
    && header.toLowerCase() === 'hibernate-rate-limited'
}

export function isApplicationAuthThrottle(error) {
  return error?.response?.status === 429
    && error?.response?.data?.detail === 'Too many attempts. Try again later.'
}

/** Only safe, generic messages are returned; never expose server error bodies. */
export function classifyRequestFailure(error) {
  if (error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') return null
  const status = error?.response?.status
  const retryAfter = readRetryAfter(error?.response?.headers)
  if (status === 429) {
    if (isRenderHibernationThrottle(error)) {
      return {
        kind: 'hosting_throttle', retryAfter, globalNotice: true, level: 'warn',
        message: 'The hosting service is temporarily limiting requests. Your action may not have reached JobGrid. Please wait before trying again.',
      }
    }
    if (isApplicationAuthThrottle(error)) {
      return {
        kind: 'auth_attempt_limit', retryAfter, globalNotice: false, level: 'warn',
        message: 'Too many sign-in attempts for this account or connection. Please wait before trying again.',
      }
    }
    return {
      kind: 'unknown_throttle', retryAfter, globalNotice: true, level: 'warn',
      message: 'The server is temporarily limiting requests. Please wait before trying again. Your action may not have completed.',
    }
  }
  if (status === 408 || status === 502 || status === 503 || status === 504) {
    return {
      kind: 'service_unavailable', retryAfter, globalNotice: true, level: 'warn',
      message: 'JobGrid is temporarily unavailable. Your action may not have completed. Please check before trying again.',
    }
  }
  if (status >= 500) {
    return {
      kind: 'server_failure', retryAfter, globalNotice: true, level: 'error',
      message: 'JobGrid encountered a server error. Your action may not have completed. Please check before trying again.',
    }
  }
  if (!status) {
    return {
      kind: 'network_failure', retryAfter: null, globalNotice: true, level: 'warn',
      message: 'JobGrid could not reach the server. Check your connection before trying again.',
    }
  }
  return null
}

export function sessionCheckProblem(error) {
  const status = error?.response?.status
  if (status === 401 || status === 403) return null
  const problem = classifyRequestFailure(error)
  if (status === 429) {
    return {
      kind: 'rate_limited',
      retryAfter: problem?.retryAfter ?? null,
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
  if (isApplicationAuthThrottle(error)) {
    return 'Too many sign-in attempts for this account or connection. Please wait before trying again.'
  }
  return 'The login service is temporarily limiting requests. Your password might not have been checked. Please wait and try again.'
}
