import axios from 'axios'
import { serializeApplicationQuery, serializeDashboardQuery } from './queryParams'

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
      const skipAuthRedirect = error.config?.skipAuthRedirect
      const alreadyOnLogin = window.location.pathname === '/login'
      if ((status === 401 || status === 403) && !skipAuthRedirect && !alreadyOnLogin) {
        const returnTo = window.location.pathname === '/capture' ? '?return_to=%2Fcapture' : ''
        window.location.href = `/login${returnTo}`
      }
    }
    return Promise.reject(error)
  }
)

export function formatApiError(error, fallback = 'Request failed. Please retry.') {
  const detail = error?.response?.data?.detail
  const status = error?.response?.status
  const code = typeof detail?.code === 'string'
    ? detail.code
    : status
      ? 'request_failed'
      : 'network_error'

  let fields = []
  if (Array.isArray(detail?.fields)) {
    fields = detail.fields
      .filter((item) => item && typeof item.message === 'string')
      .map((item) => ({
        field: typeof item.field === 'string' && item.field ? item.field : 'non_field',
        message: item.message,
      }))
  } else if (typeof detail === 'string' && detail) {
    fields = [{ field: 'non_field', message: detail }]
  } else if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    fields = Object.entries(detail)
      .filter(([key, value]) => key !== 'code' && typeof value === 'string' && value)
      .map(([field, message]) => ({ field, message }))
  }

  if (fields.length === 0) {
    fields = [{
      field: 'non_field',
      message: status ? fallback : 'Network error. Please retry.',
    }]
  }

  return {
    code,
    fields,
    message: fields[0].message,
  }
}

export function apiFieldErrors(error, fallback) {
  return formatApiError(error, fallback).fields.reduce((acc, item) => {
    if (!acc[item.field]) acc[item.field] = item.message
    return acc
  }, {})
}

function createOperationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16)
    const nibble = char === 'x' ? value : (value & 0x3) | 0x8
    return nibble.toString(16)
  })
}

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
  loginUrl: (provider, returnTo = null) => {
    const safeReturn = returnTo === '/capture' ? '?return_to=%2Fcapture' : ''
    return `${API_URL}/auth/login/${provider}${safeReturn}`
  },
  devLogin: (email = 'test@jobgrid.dev') =>
    client.post('/auth/dev-login', { email }).then((r) => r.data),
  me: () => client.get('/auth/me', { skipAuthRedirect: true }).then((r) => r.data),
  logout: () => client.post('/auth/logout'),
  uploadCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/upload', fd).then((r) => r.data)
  },
  getRows: (params = {}) =>
    client
      .get('/rows', {
        params: {
          ...serializeDashboardQuery(params, { includePagination: true, includeFalse: true }),
          ...todayWindowParams(),
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
  getApplications: (params = {}) =>
    client
      .get('/crm/applications', {
        params: serializeApplicationQuery(params, { includePagination: true, includeFalse: true }),
      })
      .then((r) => r.data),
  updateApplication: (itemId, payload) =>
    client.patch(`/crm/applications/${itemId}`, payload).then((r) => r.data),
  createApplicationFromRow: (rowId) =>
    client.post(`/crm/from-row/${rowId}`).then((r) => r.data),
  bulkUpdateApplications: (ids, patch) =>
    client.patch('/crm/applications/bulk', { ids, patch }).then((r) => r.data),
  bulkCreateApplicationsFromRows: (rowIds, status) =>
    client.post('/crm/from-rows/bulk', { row_ids: rowIds, ...(status ? { status } : {}) }).then((r) => r.data),
  getApplicationStats: (params = {}) =>
    client.get('/crm/stats', { params }).then((r) => r.data),
  getApplicationMatches: (rowId) =>
    client.get('/crm/application-matches', { params: { row_id: rowId } }).then((r) => r.data),
  findApplicationMatches: (payload) =>
    client.post('/crm/application-matches', payload).then((r) => r.data),
  captureJob: (payload, idempotencyKey = createOperationId()) =>
    client.post('/crm/jobs/capture', payload, {
      headers: { 'Idempotency-Key': idempotencyKey },
    }).then((r) => r.data),
  markRowApplied: (rowId) =>
    client.post('/crm/from-rows/bulk', { row_ids: [rowId], status: 'applied' }).then((r) => r.data),

  // CRM - Job freshness and deadlines
  getJobAvailability: (rowId) =>
    client.get(`/crm/jobs/${rowId}/availability`).then((r) => r.data),
  updateJobAvailability: (rowId, payload) =>
    client.patch(`/crm/jobs/${rowId}/availability`, payload).then((r) => r.data),
  checkJobAvailability: (rowId) =>
    client.post(`/crm/jobs/${rowId}/availability/check`).then((r) => r.data),
  getTrackAvailability: (trackId) =>
    client.get(`/crm/tracks/${trackId}/availability`).then((r) => r.data),
  updateTrackAvailability: (trackId, payload) =>
    client.patch(`/crm/tracks/${trackId}/availability`, payload).then((r) => r.data),
  checkTrackAvailability: (trackId) =>
    client.post(`/crm/tracks/${trackId}/availability/check`).then((r) => r.data),

  // CRM - Private document versions
  getDocuments: () => client.get('/crm/documents').then((r) => r.data),
  uploadDocument: (file, { kind, label, documentFamilyId, signal, onProgress, idempotencyKey } = {}) => {
    const fd = new FormData()
    fd.append('kind', kind)
    fd.append('label', label)
    if (documentFamilyId) fd.append('document_family_id', documentFamilyId)
    fd.append('file', file)
    return client.post('/crm/documents', fd, {
      signal,
      headers: { 'Idempotency-Key': idempotencyKey || createOperationId() },
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      },
    }).then((r) => r.data)
  },
  downloadDocument: (documentId) =>
    client.get(`/crm/documents/${documentId}/download`, { responseType: 'blob' }),
  deleteDocument: (documentId) =>
    client.delete(`/crm/documents/${documentId}`),
  getDocumentApplications: (documentId, params = {}) =>
    client.get(`/crm/documents/${documentId}/applications`, { params }).then((r) => r.data),
  getTrackDocuments: (trackId) =>
    client.get(`/crm/tracks/${trackId}/documents`).then((r) => r.data),
  attachTrackDocument: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/documents`, payload).then((r) => r.data),
  detachTrackDocument: (trackId, documentId) =>
    client.delete(`/crm/tracks/${trackId}/documents/${documentId}`),

  // CRM - Application evidence and timeline
  getApplicationTimeline: (trackId, params = {}) =>
    client.get(`/crm/tracks/${trackId}/timeline`, { params }).then((r) => r.data),
  createApplicationEvidence: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/evidence`, payload, {
      headers: { 'Idempotency-Key': createOperationId() },
    }).then((r) => r.data),
  updateApplicationEvidence: (trackId, evidenceId, payload) =>
    client.patch(`/crm/tracks/${trackId}/evidence/${evidenceId}`, payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  deleteApplicationEvidence: (trackId, evidenceId) =>
    client.delete(`/crm/tracks/${trackId}/evidence/${evidenceId}`, {
      headers: { 'X-Operation-ID': createOperationId() },
    }),
  correctApplicationAppliedDate: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/applied-date-corrections`, payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  correctApplicationStatus: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/status-corrections`, payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),

  // CRM - Analytics
  getAnalytics: () => client.get('/crm/analytics').then((r) => r.data),
  getFunnelAnalytics: () => client.get('/crm/analytics/funnel').then((r) => r.data),
  getAtsPerformance: () => client.get('/crm/analytics/ats').then((r) => r.data),
  getBucketPerformance: () => client.get('/crm/analytics/buckets').then((r) => r.data),
  getGoalProgress: () => client.get('/crm/analytics/goals').then((r) => r.data),
  getWeeklyReport: () => client.get('/crm/analytics/weekly').then((r) => r.data),
  getProfileTimezone: () => client.get('/crm/profile/timezone').then((r) => r.data),
  updateProfileTimezone: (timezone) =>
    client.patch('/crm/profile/timezone', { timezone }).then((r) => r.data),
  getProfileRetention: () => client.get('/crm/profile/retention').then((r) => r.data),
  updateProfileRetention: (archiveAfterDays) =>
    client.patch('/crm/profile/retention', { archive_after_days: archiveAfterDays }).then((r) => r.data),
  getGoals: () => client.get('/crm/goals').then((r) => r.data),
  updateGoals: (goals) => client.put(`/crm/goals?open_per_day=${goals.open_per_day}&apply_per_day=${goals.apply_per_day}&followup_per_day=${goals.followup_per_day}&applypilot_per_day=${goals.applypilot_per_day}`).then((r) => r.data),


  // CRM - Today
  getToday: (params = {}) =>
    client.get('/crm/today', { params }).then((r) => r.data),
  createWorkItem: (payload) =>
    client.post('/crm/work-items', payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  updateWorkItem: (itemId, payload) =>
    client.patch(`/crm/work-items/${itemId}`, payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  snoozeTodayAction: (payload) =>
    client.post('/crm/today/snooze', payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  resolveTodayFollowUp: (payload) =>
    client.post('/crm/today/follow-up', payload, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  addViewToToday: (viewId, limit = 20) =>
    client.post('/crm/today/from-view', {
      view_id: viewId,
      limit,
      request_id: createOperationId(),
    }).then((r) => r.data),

  // CRM - Reminders
  getReminderPreferences: () =>
    client.get('/crm/reminders/preferences').then((r) => r.data),
  updateReminderPreferences: (payload) =>
    client.patch('/crm/reminders/preferences', payload).then((r) => r.data),
  getReminders: (params = {}) =>
    client.get('/crm/reminders', { params }).then((r) => r.data),
  retryReminder: (deliveryId, version) =>
    client.post(`/crm/reminders/${deliveryId}/retry`, {
      version,
      confirm_possible_duplicate: true,
    }, {
      headers: { 'X-Operation-ID': createOperationId() },
    }).then((r) => r.data),
  markReminderRead: (deliveryId, version) =>
    client.post(`/crm/reminders/${deliveryId}/read`, { version }).then((r) => r.data),

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
    const { format = 'csv', scope = 'all', rowIds = [], columns, ...query } = params
    const qs = new URLSearchParams()
    qs.set('format', format)
    qs.set('scope', scope)
    Object.entries(serializeDashboardQuery(query, { includePagination: false, includeFalse: true }))
      .forEach(([key, value]) => qs.set(key, String(value)))
    if (rowIds.length) qs.set('row_ids', rowIds.join(','))
    if (columns) qs.set('columns', columns)
    return client.get(`/crm/export/dashboard?${qs.toString()}`, { responseType: 'blob' })
  },
  exportApplications: (params = {}) => {
    const { format = 'csv', scope = 'all', rowIds = [], ...query } = params
    const qs = new URLSearchParams()
    qs.set('format', format)
    qs.set('scope', scope)
    Object.entries(serializeApplicationQuery(query, { includePagination: false, includeFalse: true }))
      .forEach(([key, value]) => qs.set(key, String(value)))
    if (rowIds.length) qs.set('row_ids', rowIds.join(','))
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
  getCompanies: (params = {}) => client.get('/crm/companies', { params }).then((r) => r.data),
  getCompanyHistory: (company) => client.get(`/crm/companies/${encodeURIComponent(company)}`).then((r) => r.data),
  getCompanyAliases: (company) =>
    client.get('/crm/company-aliases', { params: { company } }).then((r) => r.data),
  createCompanyAlias: (company, alias) =>
    client.post('/crm/company-aliases', { company, alias }).then((r) => r.data),
  deleteCompanyAlias: (aliasId) =>
    client.delete(`/crm/company-aliases/${aliasId}`).then((r) => r.data),

  // CRM - Duplicates
  getDuplicates: () => client.get('/crm/duplicates').then((r) => r.data),
  resolveDuplicate: (rowId, action) => client.post(`/crm/duplicates/${rowId}/resolve`, { action }).then((r) => r.data),
  mergeDuplicates: (primaryId, duplicateIds) => client.post('/crm/duplicates/merge', null, { params: { primary_id: primaryId, duplicate_ids: duplicateIds } }).then((r) => r.data),

  // CRM - Backup
  exportBackup: () => client.get('/crm/backup/export', { responseType: 'blob' }),
  exportBackupV2: () => client.get('/crm/backup/export', { params: { version: '2' }, responseType: 'blob' }),
  previewBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import?mode=verify_only', fd).then((r) => r.data)
  },
  restoreBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import?mode=merge_missing', fd).then((r) => r.data)
  },
  importBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/crm/backup/import', fd).then((r) => r.data)
  },

  // CRM - Import external
  importExternalApplications: (data) => client.post('/crm/import/external', data).then((r) => r.data),
}

export default client
