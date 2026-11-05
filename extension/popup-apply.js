/** Popup-only client validation. The worker and backend remain authoritative. */
export function normalizeApplicationFields(company, title) {
  if (typeof company !== 'string' || typeof title !== 'string') {
    return { ok: false, message: 'Employer and job title are required.' }
  }
  const employer = company.trim()
  const role = title.trim()
  if (!employer || !role) {
    return { ok: false, message: 'Enter both the employer and job title.' }
  }
  if (employer.length > 320 || role.length > 500) {
    return { ok: false, message: 'Employer or title exceeds the allowed length.' }
  }
  return { ok: true, company: employer, title: role }
}

export function checkedJobForAccount(record, state) {
  if (!state?.connected || state.paused ||
      !Number.isSafeInteger(state.account_id) ||
      !Number.isSafeInteger(record?.account_id) ||
      record.account_id !== state.account_id ||
      typeof record.url !== 'string' || !record.url ||
      !record.before_visit?.visit ||
      !Array.isArray(record.before_visit.matches) ||
      record.apply_status === 'saved' ||
      record.before_visit.matches.some(match =>
        match?.confidence === 'exact' || match?.confidence === 'canonical')) return false
  return true
}

export function sameStagedIntent(record, state, pending, values) {
  return checkedJobForAccount(record, state) &&
    pending?.pending === true &&
    pending.account_id === state.account_id &&
    pending.url === record.url &&
    pending.company === values.company &&
    pending.title === values.title &&
    typeof pending.idempotency_key === 'string'
}
