// A display and manual-retry cooldown, never an automatic request scheduler.
export const RECOVERY_WINDOW_SECONDS = 120

export function secondsUntil(deadline, now) {
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}

export function formatCountdown(seconds) {
  const remaining = Math.max(0, Math.floor(seconds))
  const minutes = String(Math.floor(remaining / 60)).padStart(2, '0')
  const secs = String(remaining % 60).padStart(2, '0')
  return `${minutes}:${secs}`
}

export function recoveryDeadline(startedAt, responseAt = startedAt, retryAfterSeconds = null) {
  const serverDeadline = retryAfterSeconds == null ? 0 : responseAt + retryAfterSeconds * 1000
  return Math.max(startedAt + RECOVERY_WINDOW_SECONDS * 1000, serverDeadline)
}
