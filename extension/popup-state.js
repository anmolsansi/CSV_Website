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
  return { kind, title, detail, save }
}

export function safeMatchText(match) {
  const company = typeof match?.company === 'string' ? match.company.slice(0, 320) : 'Unknown employer'
  const title = typeof match?.title === 'string' ? match.title.slice(0, 500) : 'Unknown role'
  const confidence = ['exact', 'canonical', 'possible'].includes(match?.confidence)
    ? match.confidence : 'unverified'
  return company + ' · ' + title + ' (' + confidence + ')'
}
