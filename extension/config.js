/** Public, build-time JobGrid frontend configuration. No API host, cookies or tokens. */
export const PROTOCOL_VERSION = 1

/**
 * Accept only an exact URL origin, never an origin with a path, userinfo, query,
 * fragment, wildcard, or non-HTTPS scheme. Local HTTP is an explicit fixture-only
 * opt-in for a disposable loopback frontend, not a release configuration.
 */
export function parseTrustedOrigin(value, { allowLocal = false } = {}) {
  if (typeof value !== 'string' || !value || value.trim() !== value || value.includes('*')) {
    throw new TypeError('Expected an exact frontend origin')
  }
  let url
  try {
    url = new URL(value)
  } catch {
    throw new TypeError('Invalid frontend origin')
  }
  const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1'
  if ((url.protocol !== 'https:' && !(allowLocal && local && url.protocol === 'http:')) ||
      url.username || url.password || url.origin !== value ||
      url.pathname !== '/' || url.search || url.hash || !url.hostname ||
      url.hostname.endsWith('.')) {
    throw new TypeError('Frontend must be an exact trusted HTTPS origin')
  }
  return url.origin
}

// Origin identified in docs/C09_STAGING_OPERATIONS.md; live extension auth is unverified.
// The release operator must revalidate this deployment before pilot distribution.
export const APP_ORIGIN = parseTrustedOrigin('https://csv-website-steel.vercel.app')

export const ATS_HOSTS = Object.freeze([
  'boards.greenhouse.io',
  'job-boards.greenhouse.io',
  'jobs.lever.co',
])

export function isAllowedAppOrigin(candidate, allowed = APP_ORIGIN, options = {}) {
  try {
    return parseTrustedOrigin(candidate, options) === parseTrustedOrigin(allowed, options)
  } catch {
    return false
  }
}
