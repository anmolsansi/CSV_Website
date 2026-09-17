const BOOL_TRUE = new Set(['true', '1'])
const BOOL_FALSE = new Set(['false', '0'])

const DASHBOARD_FIELDS = [
  ['sortBy', 'sort_by', 'string'],
  ['sortDir', 'sort_dir', 'string'],
  ['atsGroup', 'ats_group', 'string'],
  ['locationGroup', 'location_group', 'string'],
  ['searchBucket', 'search_bucket', 'string'],
  ['decision', 'decision', 'string'],
  ['sponsorshipStatus', 'sponsorship_status', 'string'],
  ['fitCategory', 'fit_category', 'string'],
  ['seniorityLevel', 'seniority_level', 'string'],
  ['workModel', 'work_model', 'string'],
  ['roleFamily', 'role_family', 'string'],
  ['salaryMin', 'salary_min', 'number'],
  ['salaryMax', 'salary_max', 'number'],
  ['q', 'q', 'string'],
  ['openedOnly', 'opened_only', 'boolean'],
  ['unopenedOnly', 'unopened_only', 'boolean'],
  ['openableOnly', 'openable_only', 'boolean'],
  ['hasError', 'has_error', 'boolean'],
  ['jdMissing', 'jd_missing', 'boolean'],
  ['page', 'page', 'number'],
  ['pageSize', 'page_size', 'number'],
]

const APPLICATION_FIELDS = [
  ['sortBy', 'sort_by', 'string'],
  ['sortDir', 'sort_dir', 'string'],
  ['status', 'status', 'string'],
  ['company', 'company', 'string'],
  ['atsGroup', 'ats_group', 'string'],
  ['searchBucket', 'search_bucket', 'string'],
  ['quickRange', 'quick_range', 'string'],
  ['dateFrom', 'date_from', 'string'],
  ['dateTo', 'date_to', 'string'],
  ['minScore', 'min_score', 'number'],
  ['maxScore', 'max_score', 'number'],
  ['followUpDue', 'follow_up_due', 'boolean'],
  ['followUpToday', 'follow_up_today', 'boolean'],
  ['followUpOverdue', 'follow_up_overdue', 'boolean'],
  ['followUpNone', 'follow_up_none', 'boolean'],
  ['openedNotApplied', 'opened_not_applied', 'boolean'],
  ['hasError', 'has_error', 'boolean'],
  ['jdMissing', 'jd_missing', 'boolean'],
  ['locationGroup', 'location_group', 'string'],
  ['decision', 'decision', 'string'],
  ['sponsorshipStatus', 'sponsorship_status', 'string'],
  ['postedAgeMin', 'posted_age_min', 'number'],
  ['postedAgeMax', 'posted_age_max', 'number'],
  ['dateAppliedFrom', 'date_applied_from', 'string'],
  ['dateAppliedTo', 'date_applied_to', 'string'],
  ['appliedOnly', 'applied_only', 'boolean'],
  ['q', 'q', 'string'],
  ['page', 'page', 'number'],
  ['pageSize', 'page_size', 'number'],
]

function toRecord(input) {
  if (input instanceof URLSearchParams) {
    return Object.fromEntries(input.entries())
  }
  if (typeof input === 'string') {
    return Object.fromEntries(new URLSearchParams(input.startsWith('?') ? input.slice(1) : input).entries())
  }
  return input && typeof input === 'object' ? input : {}
}

function parseBoolean(value, key) {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  const normalized = String(value).trim().toLowerCase()
  if (BOOL_TRUE.has(normalized)) return true
  if (BOOL_FALSE.has(normalized)) return false
  throw new Error(`Invalid boolean for ${key}`)
}

function parseNumber(value, key) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (value === '' || value === null || value === undefined) return null
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(`Invalid number for ${key}`)
  return parsed
}

function normalizeValue(value, type, key) {
  if (value === undefined || value === null) return null
  if (type === 'boolean') return parseBoolean(value, key)
  if (type === 'number') return parseNumber(value, key)
  return String(value)
}

function normalizeQuery(input, fields, { allowMeta = true } = {}) {
  const record = toRecord(input)
  const allowed = new Set(allowMeta ? ['view'] : [])
  const descriptors = new Map()
  for (const [canonical, wire, type] of fields) {
    descriptors.set(canonical, [canonical, wire, type])
    descriptors.set(wire, [canonical, wire, type])
    allowed.add(canonical)
    allowed.add(wire)
  }

  const unsupportedKeys = Object.keys(record).filter((key) => !allowed.has(key))
  const values = {}
  const errors = []

  for (const [canonical, wire, type] of fields) {
    let raw
    if (Object.prototype.hasOwnProperty.call(record, canonical)) raw = record[canonical]
    else if (Object.prototype.hasOwnProperty.call(record, wire)) raw = record[wire]
    else continue

    try {
      const normalized = normalizeValue(raw, type, canonical)
      if (normalized !== null) values[canonical] = normalized
    } catch (error) {
      errors.push(error.message)
    }
  }

  return { values, unsupportedKeys, errors }
}

function serializeQuery(input, fields, { includePagination = true, includeFalse = true } = {}) {
  const { values, unsupportedKeys, errors } = normalizeQuery(input, fields, { allowMeta: true })
  if (unsupportedKeys.length) throw new Error(`Unsupported query keys: ${unsupportedKeys.join(', ')}`)
  if (errors.length) throw new Error(errors.join('; '))

  const params = {}
  for (const [canonical, wire, type] of fields) {
    if (!includePagination && (canonical === 'page' || canonical === 'pageSize')) continue
    if (!Object.prototype.hasOwnProperty.call(values, canonical)) continue
    const value = values[canonical]
    if (type === 'string' && value === '') continue
    if (type === 'boolean' && value === false && !includeFalse) continue
    params[wire] = value
  }
  return params
}

function toSearchParams(serialized, viewId) {
  const params = new URLSearchParams()
  if (viewId !== undefined && viewId !== null && viewId !== '') params.set('view', String(viewId))
  Object.entries(serialized).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    params.set(key, typeof value === 'boolean' ? String(value) : String(value))
  })
  return params
}

export function normalizeDashboardQuery(input, options) {
  return normalizeQuery(input, DASHBOARD_FIELDS, options)
}

export function normalizeApplicationQuery(input, options) {
  return normalizeQuery(input, APPLICATION_FIELDS, options)
}

export function serializeDashboardQuery(input, options) {
  return serializeQuery(input, DASHBOARD_FIELDS, options)
}

export function serializeApplicationQuery(input, options) {
  return serializeQuery(input, APPLICATION_FIELDS, options)
}

export function dashboardStateQuery(sort, filters, page = 1, pageSize = 50) {
  return { ...sort, ...filters, page, pageSize }
}

export function applicationStateQuery(sort, filters, page = 1, pageSize = 50) {
  return {
    ...filters,
    sortBy: sort.field === 'clickedAt' ? 'opened_at' : sort.field,
    sortDir: sort.direction,
    page,
    pageSize,
  }
}

export function dashboardNavigationState(search, defaults = {}) {
  const result = normalizeDashboardQuery(search, { allowMeta: true })
  const values = { ...defaults, ...result.values }
  return {
    sort: {
      sortBy: values.sortBy ?? defaults.sortBy,
      sortDir: values.sortDir ?? defaults.sortDir,
    },
    filters: values,
    page: values.page ?? defaults.page ?? 1,
    pageSize: values.pageSize ?? defaults.pageSize ?? 50,
    unsupportedKeys: result.unsupportedKeys,
    errors: result.errors,
  }
}

export function applicationNavigationState(search, defaults = {}) {
  const result = normalizeApplicationQuery(search, { allowMeta: true })
  const values = { ...defaults, ...result.values }
  return {
    sort: {
      field: values.sortBy ?? defaults.sortBy ?? 'opened_at',
      direction: values.sortDir ?? defaults.sortDir ?? 'desc',
    },
    filters: values,
    page: values.page ?? defaults.page ?? 1,
    pageSize: values.pageSize ?? defaults.pageSize ?? 50,
    unsupportedKeys: result.unsupportedKeys,
    errors: result.errors,
  }
}

export function savedViewSearch(viewType, filters = {}, viewId) {
  if (viewType === 'job_links') {
    return toSearchParams(serializeDashboardQuery(filters, { includePagination: false, includeFalse: true }), viewId)
  }
  if (viewType === 'applications') {
    return toSearchParams(serializeApplicationQuery(filters, { includePagination: false, includeFalse: true }), viewId)
  }
  const params = new URLSearchParams()
  if (viewId !== undefined && viewId !== null) params.set('view', String(viewId))
  return params
}

export function queryValidationMessage({ unsupportedKeys = [], errors = [] }) {
  const parts = []
  if (unsupportedKeys.length) parts.push(`Unsupported saved-view keys: ${unsupportedKeys.join(', ')}`)
  if (errors.length) parts.push(errors.join('; '))
  return parts.join('. ')
}
