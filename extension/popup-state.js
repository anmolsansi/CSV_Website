/** Presentation-only, untrusted check facts. Never derive "applied" from a visit. */
export function summarizeWarning(record) {
  const facts = record?.before_visit
  if (!facts || typeof facts !== 'object' || !facts.visit ||
      !Array.isArray(facts.matches)) {
    return { kind: 'empty', title: 'No job checked yet',
      detail: 'Use Check current tab to look up a public job page.', save: '' }
  }
  const definite = facts.matches.some(match =>
    match?.confidence === 'exact' || match?.confidence === 'canonical')
  const possible = facts.matches.some(match => match?.confidence === 'possible')
  let kind, title, detail
  if (definite) {
    kind = 'applied'
    title = 'Application found'
    detail = 'An application matches this job URL.'
  } else if (possible) {
    kind = 'possible'
    title = 'Possible application match'
    detail = 'An employer and role may match. Verify before applying.'
  } else if (facts.visit.visited === true) {
    kind = 'visited'
    title = 'Previously visited'
    detail = 'This job was visited before this check.'
  } else if (facts.company_known || facts.company_history_count > 0) {
    kind = 'company'
    title = 'Employer in your history'
    detail = 'You have prior history with this employer, not necessarily this job.'
  } else if (facts.lookup_complete === false) {
    kind = 'partial'
    title = 'Search is incomplete'
    detail = 'No definite match was found, but possible matches may be missing.'
  } else {
    kind = 'clear'
    title = 'No matching history found'
    detail = 'This is not a guarantee you have never applied elsewhere.'
  }
  const save = record.save_state === 'saved'
    ? 'This page was saved as a visit.'
    : record.save_state === 'save_unknown'
      ? 'Visit save status is unknown. Check JobGrid before retrying.'
      : record.save_state === 'checked'
        ? 'Visit save is pending.'
        : record.save_state === 'manual_only'
          ? 'Manual check only. This page was not saved as a visit.'
          : 'Visit save status is not available.'
  const lookup = facts.lookup_complete === false
    ? 'Search incomplete: other possible matches may be missing.'
    : ''
  return { kind, title, detail, save, lookup }
}

/** Safe, explicit UI messages. Never treat a failed check as no history. */
export function summarizeFailure(failure, action = 'check') {
  const code = typeof failure?.code === 'string' ? failure.code : 'unavailable'
  const saving = action === 'apply'
  const operation = saving ? 'save the application' : action === 'forget'
    ? 'forget visits' : action === 'connect'
      ? 'connect to JobGrid' : 'check this page'
  const prefix = 'Could not ' + operation + '. '
  const rate = Number.isSafeInteger(failure?.retry_after) &&
    failure.retry_after >= 0 && failure.retry_after <= 3600
    ? ' Try again in ' + failure.retry_after + ' seconds.' : ' Try again later.'
  if (code === 'offline') return { kind: 'offline', title: 'Offline',
    detail: 'Connect to the internet, then try again. No history was checked.' }
  if (code === 'not_authenticated' || code === 'account_changed')
    return { kind: 'auth', title: 'JobGrid sign-in needed',
      detail: 'Sign in to the selected JobGrid tab, then reconnect. No current history is verified.' }
  if (code === 'forbidden' || code === 'permission_denied' || code === 'forbidden_sender')
    return { kind: 'forbidden', title: 'Access denied',
      detail: 'This request was not authorized. Review account and site permissions.' }
  if (code === 'rate_limited') return { kind: 'rate_limited', title: 'Rate limited',
    detail: 'JobGrid is limiting requests.' + rate }
  if (code === 'unsupported' || code === 'protocol_error')
    return { kind: 'unsupported', title: 'Unsupported request or page',
      detail: 'This page or response cannot be verified safely in this extension.' }
  if (code === 'timeout' || code === 'save_unknown')
    return { kind: 'timeout', title: saving ? 'Save result unknown' : 'Request timed out',
      detail: saving
        ? 'The application may have been saved. Check JobGrid before retrying. A retry uses the same request ID while this session is active.'
        : prefix + 'Check your connection and retry.' }
  if (saving && (code === 'unavailable' || code === 'not_connected'))
    return { kind: 'unknown', title: 'Save result unverified',
      detail: 'The application may have been saved. Check JobGrid before retrying.' }
  return { kind: 'unavailable', title: 'JobGrid unavailable',
    detail: prefix + 'No result was verified. Retry when the service is available.' }
}

export function safeMatchText(match) {
  const company = typeof match?.company === 'string' ? match.company.slice(0, 320) : 'Unknown employer'
  const title = typeof match?.title === 'string' ? match.title.slice(0, 500) : 'Unknown role'
  const confidence = ['exact', 'canonical', 'possible'].includes(match?.confidence)
    ? match.confidence : 'unverified'
  return company + ' · ' + title + ' (' + confidence + ')'
}
