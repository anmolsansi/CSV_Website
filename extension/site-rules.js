/** EXT-28: conservative, offline-only ATS detail classifier. No page reads or network. */
const ATS_PATHS = Object.freeze({
  'boards.greenhouse.io': { site: 'greenhouse', path: /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/jobs\/([A-Za-z0-9][A-Za-z0-9_-]*)$/ },
  'job-boards.greenhouse.io': { site: 'greenhouse', path: /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/jobs\/([A-Za-z0-9][A-Za-z0-9_-]*)$/ },
  'jobs.lever.co': { site: 'lever', path: /^\/[A-Za-z0-9][A-Za-z0-9_-]*\/([A-Za-z0-9][A-Za-z0-9_-]*)$/ },
})
const SECRET_KEYS = new Set([
  'token', 'access_token', 'auth', 'authorization', 'code', 'password',
  'session', 'session_token',
])

const MANUAL = Object.freeze({
  supported: false, eligibility: 'manual', site: null, detail_id: null, url: null,
})

/**
 * Return only the ATS provider and detail ID, never infer the employer from
 * the path slug. The original URL is supplied only for an accepted detail.
 * All unsupported/unsafe URLs require a separate, manual user gesture.
 */
export function classifyJobDetailUrl(input) {
  if (typeof input !== 'string' || input.length > 2048 || !input ||
      input !== input.trim() || /[\u0000-\u001f\u007f]/.test(input)) return MANUAL
  let parsed
  try {
    parsed = new URL(input)
  } catch {
    return MANUAL
  }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password ||
      parsed.port || !Object.hasOwn(ATS_PATHS, parsed.hostname) ||
      parsed.hostname.endsWith('.') || parsed.origin !== `https://${parsed.hostname}`) {
    return MANUAL
  }
  for (const key of parsed.searchParams.keys()) {
    if (SECRET_KEYS.has(key.toLowerCase())) return MANUAL
  }
  const spec = ATS_PATHS[parsed.hostname]
  const match = spec.path.exec(parsed.pathname)
  if (!match) return MANUAL
  return {
    supported: true, eligibility: 'automatic', site: spec.site,
    detail_id: match[1], url: input,
  }
}
