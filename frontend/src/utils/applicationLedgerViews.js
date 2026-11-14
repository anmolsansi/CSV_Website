// UI-only navigation state for My Applications. Never send tab to the CRM API.
export const APPLICATION_TABS = [
  { id: 'applied', label: 'Ever Applied', description: 'Confirmed submissions in any current stage' },
  { id: 'all', label: 'All Tracked', description: 'Saved, opened and submitted roles' },
  { id: 'followups', label: 'Follow-ups Due', description: 'Records with a follow-up due now' },
]

const VALID_TABS = new Set(APPLICATION_TABS.map((item) => item.id))

export function applicationTabFromUrl(search, filters = {}) {
  const requested = new URLSearchParams(search).get('tab')
  if (VALID_TABS.has(requested)) return requested
  if (filters.appliedOnly) return 'applied'
  if (filters.followUpDue) return 'followups'
  return 'all'
}

export function filtersForApplicationTab(filters, tab) {
  if (!VALID_TABS.has(tab)) return { ...filters }
  return {
    ...filters,
    appliedOnly: tab === 'applied',
    openedNotApplied: false,
    followUpDue: tab === 'followups',
    followUpToday: false,
    followUpOverdue: false,
    followUpNone: false,
  }
}

export function applicationEmptyState(tab, hasAnyFilters) {
  if (hasAnyFilters) return {
    title: 'No matching applications',
    body: 'Try clearing a filter or switching to All Tracked.',
  }
  if (tab === 'applied') return {
    title: 'No confirmed applications yet',
    body: 'Use Mark applied after you submit a job application. Saving or opening a link is not a submission.',
  }
  if (tab === 'followups') return {
    title: 'No follow-ups are due',
    body: 'Set a follow-up date for a tracked job to see it here when due.',
  }
  return {
    title: 'No tracked jobs yet',
    body: 'Send a job to Applications from Job Links to start tracking it.',
  }
}
