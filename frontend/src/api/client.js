import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status } = error.response
      if (status === 401 || status === 403) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

function todayWindowParams() {
  const start = new Date()
  start.setHours(0, 0, 0, 0)

  const end = new Date(start)
  end.setDate(end.getDate() + 1)

  return {
    clicked_today_start: start.toISOString(),
    clicked_today_end: end.toISOString(),
  }
}

export const api = {
  loginUrl: (provider) => `${API_URL}/auth/login/${provider}`,
  devLogin: (email = 'test@jobgrid.dev') =>
    client.post('/auth/dev-login', { email }).then((r) => r.data),
  me: () => client.get('/auth/me').then((r) => r.data),
  logout: () => client.post('/auth/logout'),
  uploadCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/upload', fd).then((r) => r.data)
  },
  getRows: ({ sortBy = 'created_at', sortDir = 'desc', atsGroup = '', locationGroup = '', searchBucket = '', decision = '', sponsorshipStatus = '', q = '', openedOnly = false, unopenedOnly = false, hasError = false, jdMissing = false, page = 1, pageSize = 50 } = {}) =>
    client
      .get('/rows', {
        params: {
          sort_by: sortBy,
          sort_dir: sortDir,
          page,
          page_size: pageSize,
          ...todayWindowParams(),
          ...(atsGroup ? { ats_group: atsGroup } : {}),
          ...(locationGroup ? { location_group: locationGroup } : {}),
          ...(searchBucket ? { search_bucket: searchBucket } : {}),
          ...(decision ? { decision } : {}),
          ...(sponsorshipStatus ? { sponsorship_status: sponsorshipStatus } : {}),
          ...(q ? { q } : {}),
          ...(openedOnly ? { opened_only: true } : {}),
          ...(unopenedOnly ? { unopened_only: true } : {}),
          ...(hasError ? { has_error: true } : {}),
          ...(jdMissing ? { jd_missing: true } : {}),
        },
      })
      .then((r) => r.data),
  recordClick: (rowId) => client.post(`/rows/${rowId}/click`).then((r) => r.data),
  openRow: (rowId) => client.post(`/rows/${rowId}/click`).then((r) => r.data),
  deleteRows: (rowIds, mode = 'delete') =>
    client.delete('/rows', { data: { row_ids: rowIds, mode } }).then((r) => r.data),
  getPreferences: () => client.get('/preferences').then((r) => r.data),
  setPreferences: ({ hiddenColumns, columnOrder }) =>
    client
      .put('/preferences', {
        hidden_columns: hiddenColumns,
        column_order: columnOrder,
      })
      .then((r) => r.data),

  // CRM - Applications
  getApplications: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.sort_by) qs.set('sort_by', params.sort_by)
    if (params.sort_dir) qs.set('sort_dir', params.sort_dir)
    if (params.page) qs.set('page', params.page)
    if (params.page_size) qs.set('page_size', params.page_size)
    if (params.status) qs.set('status', params.status)
    if (params.company) qs.set('company', params.company)
    if (params.ats_group) qs.set('ats_group', params.ats_group)
    if (params.search_bucket) qs.set('search_bucket', params.search_bucket)
    if (params.quick_range) qs.set('quick_range', params.quick_range)
    if (params.date_from) qs.set('date_from', params.date_from)
    if (params.date_to) qs.set('date_to', params.date_to)
    if (params.min_score) qs.set('min_score', params.min_score)
    if (params.max_score) qs.set('max_score', params.max_score)
    if (params.follow_up_due) qs.set('follow_up_due', 'true')
    if (params.follow_up_today) qs.set('follow_up_today', 'true')
    if (params.follow_up_overdue) qs.set('follow_up_overdue', 'true')
    if (params.follow_up_none) qs.set('follow_up_none', 'true')
    if (params.opened_not_applied) qs.set('opened_not_applied', 'true')
    if (params.has_error) qs.set('has_error', 'true')
    if (params.jd_missing) qs.set('jd_missing', 'true')
    if (params.location_group) qs.set('location_group', params.location_group)
    if (params.decision) qs.set('decision', params.decision)
    if (params.sponsorship_status) qs.set('sponsorship_status', params.sponsorship_status)
    if (params.applied_only) qs.set('applied_only', 'true')
    if (params.q) qs.set('q', params.q)
    return client.get(`/crm/applications?${qs.toString()}`).then((r) => r.data)
  },
  updateApplication: (itemId, payload) =>
    client.patch(`/crm/applications/${itemId}`, payload).then((r) => r.data),
  createApplicationFromRow: (rowId) =>
    client.post(`/crm/from-row/${rowId}`).then((r) => r.data),
  bulkUpdateApplications: (ids, patch) =>
    client.patch('/crm/applications/bulk', { ids, patch }).then((r) => r.data),
  bulkCreateApplicationsFromRows: (rowIds) =>
    client.post('/crm/from-rows/bulk', { row_ids: rowIds }).then((r) => r.data),
  getApplicationStats: (params = {}) =>
    client.get('/crm/stats', { params }).then((r) => r.data),

  // CRM - Analytics
  getAnalytics: () => client.get('/crm/analytics').then((r) => r.data),
  getFunnelAnalytics: () => client.get('/crm/analytics/funnel').then((r) => r.data),
  getAtsPerformance: () => client.get('/crm/analytics/ats').then((r) => r.data),
  getBucketPerformance: () => client.get('/crm/analytics/buckets').then((r) => r.data),
  getGoalProgress: () => client.get('/crm/analytics/goals').then((r) => r.data),
  getWeeklyReport: () => client.get('/crm/analytics/weekly').then((r) => r.data),
  getGoals: () => client.get('/crm/goals').then((r) => r.data),
  updateGoals: (goals) => client.put(`/crm/goals?open_per_day=${goals.open_per_day}&apply_per_day=${goals.apply_per_day}&followup_per_day=${goals.followup_per_day}&applypilot_per_day=${goals.applypilot_per_day}`).then((r) => r.data),

  // CRM - Saved Views
  getViews: (viewType) =>
    client.get('/crm/views', { params: viewType ? { view_type: viewType } : {} }).then((r) => r.data),
  getView: (viewId) =>
    client.get(`/crm/views/${viewId}`).then((r) => r.data),
  saveView: (payload) =>
    client.post('/crm/views', payload).then((r) => r.data),
  deleteView: (viewId) =>
    client.delete(`/crm/views/${viewId}`).then((r) => r.data),
  pinView: (viewId) =>
    client.put(`/crm/views/${viewId}/pin`).then((r) => r.data),
  duplicateView: (viewId) =>
    client.post(`/crm/views/duplicate/${viewId}`).then((r) => r.data),
  createDefaultViews: () =>
    client.post('/crm/views/defaults').then((r) => r.data),

  // CRM - Sessions
  getSessions: () => client.get('/crm/sessions').then((r) => r.data),
  getActiveSession: () => client.get('/crm/sessions/active').then((r) => r.data),
  startSession: (payload) => client.post('/crm/sessions', payload).then((r) => r.data),
  updateSession: (sessionId, payload) =>
    client.patch(`/crm/sessions/${sessionId}`, payload).then((r) => r.data),
  deleteSession: (sessionId) =>
    client.delete(`/crm/sessions/${sessionId}`).then((r) => r.data),

  // CRM - Audit
  getAuditEvents: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.event_type) qs.set('event_type', params.event_type)
    if (params.session_id) qs.set('session_id', params.session_id)
    if (params.limit) qs.set('limit', params.limit)
    return client.get(`/crm/audit?${qs.toString()}`).then((r) => r.data)
  },

  // CRM - Export
  exportDashboard: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.format) qs.set('format', params.format)
    if (params.atsGroup) qs.set('ats_group', params.atsGroup)
    if (params.rowIds && params.rowIds.length) qs.set('row_ids', params.rowIds.join(','))
    if (params.columns) qs.set('columns', params.columns)
    return client.get(`/crm/export/dashboard?${qs.toString()}`, { responseType: 'blob' })
  },
  exportApplications: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.format) qs.set('format', params.format)
    if (params.status) qs.set('status', params.status)
    if (params.company) qs.set('company', params.company)
    if (params.atsGroup) qs.set('ats_group', params.atsGroup)
    if (params.searchBucket) qs.set('search_bucket', params.searchBucket)
    if (params.followUpDue) qs.set('follow_up_due', 'true')
    if (params.openedNotApplied) qs.set('opened_not_applied', 'true')
    if (params.q) qs.set('q', params.q)
    if (params.rowIds && params.rowIds.length) qs.set('row_ids', params.rowIds.join(','))
    return client.get(`/crm/export/applications?${qs.toString()}`, { responseType: 'blob' })
  },

  // CRM - Follow-up presets
  setFollowUpPreset: (itemId, preset) =>
    client.post(`/crm/applications/${itemId}/follow-up?preset=${preset}`).then((r) => r.data),
  bulkFollowUpPreset: (ids, preset) =>
    Promise.all(ids.map((id) => client.post(`/crm/applications/${id}/follow-up?preset=${preset}`).then((r) => r.data))),

  // CRM - Duplicate management
  markDuplicate: (itemId, duplicateOfId = null) => {
    const qs = duplicateOfId ? `?duplicate_of_id=${duplicateOfId}` : ''
    return client.post(`/crm/applications/${itemId}/mark-duplicate${qs}`).then((r) => r.data)
  },

  // CRM - ApplyPilot
  createApplyPilotBatch: (rowIds, name) => {
    const qs = new URLSearchParams()
    qs.set('row_ids', rowIds.join(','))
    if (name) qs.set('name', name)
    return client.post(`/crm/applypilot/batches?${qs.toString()}`).then((r) => r.data)
  },
  getApplyPilotBatches: () => client.get('/crm/applypilot/batches').then((r) => r.data),
  getApplyPilotBatch: (batchId) => client.get(`/crm/applypilot/batches/${batchId}`).then((r) => r.data),
  deleteApplyPilotBatch: (batchId) => client.delete(`/crm/applypilot/batches/${batchId}`).then((r) => r.data),
  downloadApplyPilotBatch: (batchId) => client.get(`/crm/applypilot/batches/${batchId}/download`, { responseType: 'blob' }),
  importApplyPilotResults: (results) => client.post('/crm/applypilot/import', results).then((r) => r.data),
  getApplyPilotReadiness: (rowId) => client.get(`/crm/applypilot/readiness/${rowId}`).then((r) => r.data),

  // CRM - Intelligence
  getPriorityScore: (rowId) => client.get(`/crm/intelligence/priority/${rowId}`).then((r) => r.data),
  getJobSummary: (rowId) => client.get(`/crm/intelligence/summary/${rowId}`).then((r) => r.data),
  getResumeChecklist: (rowId) => client.get(`/crm/intelligence/checklist/${rowId}`).then((r) => r.data),
  getBatchIntelligence: (rowIds) => client.get(`/crm/intelligence/batch?row_ids=${rowIds.join(',')}`).then((r) => r.data),

  // CRM - Company history
  getCompanyHistory: (company) => client.get(`/crm/companies/${encodeURIComponent(company)}`).then((r) => r.data),

  // CRM - Duplicates
  getDuplicates: () => client.get('/crm/duplicates').then((r) => r.data),
  resolveDuplicate: (rowId, action) => client.post(`/crm/duplicates/${rowId}/resolve`, { action }).then((r) => r.data),
  mergeDuplicates: (primaryId, duplicateIds) => client.post('/crm/duplicates/merge', null, { params: { primary_id: primaryId, duplicate_ids: duplicateIds } }).then((r) => r.data),

  // CRM - Backup
  exportBackup: () => client.get('/crm/backup/export', { responseType: 'blob' }),
  importBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import', fd).then((r) => r.data)
  },

  // CRM - Import external
  importExternalApplications: (data) => client.post('/crm/import/external', data).then((r) => r.data),
}

export default client
