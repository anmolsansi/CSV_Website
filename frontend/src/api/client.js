import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

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
  me: () => client.get('/auth/me').then((r) => r.data),
  logout: () => client.post('/auth/logout'),
  uploadCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/upload', fd).then((r) => r.data)
  },
  getRows: ({ sortBy = 'created_at', sortDir = 'desc', atsGroup = '', locationGroup = '', searchBucket = '', decision = '', sponsorshipStatus = '', q = '', openedOnly = false, unopenedOnly = false, hasError = false, jdMissing = false } = {}) =>
    client
      .get('/rows', {
        params: {
          sort_by: sortBy,
          sort_dir: sortDir,
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
  getApplications: (params = {}) =>
    client.get('/crm/applications', { params }).then((r) => r.data),
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

  // CRM - Saved Views
  getViews: (viewType) =>
    client.get('/crm/views', { params: viewType ? { view_type: viewType } : {} }).then((r) => r.data),
  saveView: (payload) =>
    client.post('/crm/views', payload).then((r) => r.data),
  deleteView: (viewId) =>
    client.delete(`/crm/views/${viewId}`).then((r) => r.data),

  // CRM - Sessions
  getSessions: () => client.get('/crm/sessions').then((r) => r.data),
  startSession: (payload) => client.post('/crm/sessions', payload).then((r) => r.data),
  updateSession: (sessionId, payload) =>
    client.patch(`/crm/sessions/${sessionId}`, payload).then((r) => r.data),
  deleteSession: (sessionId) =>
    client.delete(`/crm/sessions/${sessionId}`).then((r) => r.data),

  // CRM - Export
  exportDashboard: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.format) qs.set('format', params.format)
    if (params.atsGroup) qs.set('ats_group', params.atsGroup)
    if (params.rowIds && params.rowIds.length) qs.set('row_ids', params.rowIds.join(','))
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

  // CRM - Duplicate management
  markDuplicate: (itemId, duplicateOfId = null) => {
    const qs = duplicateOfId ? `?duplicate_of_id=${duplicateOfId}` : ''
    return client.post(`/crm/applications/${itemId}/mark-duplicate${qs}`).then((r) => r.data)
  },
}

export default client
