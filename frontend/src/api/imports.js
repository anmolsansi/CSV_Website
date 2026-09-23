import client, { formatApiError } from './client'

export const MAX_IMPORT_UPLOAD_BYTES = 10 * 1024 * 1024

export const IMPORT_TARGET_FIELDS = [
  'ats_group', 'location_group', 'search_bucket', 'title',
  'title_match_status', 'title_reject_reason', 'url', 'display_domain',
  'company_guess', 'job_id_guess', 'canonical_company_job_key',
  'application_url', 'application_dedupe_key', 'page_number', 'decision',
  'rejection_reasons', 'posted_status', 'posted_value', 'posted_source',
  'posted_age_days', 'location_status', 'location_evidence', 'is_usa_role',
  'location_country', 'location_city', 'location_state',
  'location_raw_extracted', 'location_confidence', 'location_source',
  'sponsorship_status', 'positive_sponsorship_matches',
  'negative_sponsorship_matches', 'sponsorship_evidence_snippet',
  'positive_sponsorship_evidence_snippet', 'clearance_matches',
  'clearance_evidence_snippet', 'jd_quality_status', 'jd_quality_reasons',
  'jd_text_length', 'jd_text', 'extraction_method', 'retry_attempted',
  'error', 'source_file', 'work_model_extracted', 'salary_min_extracted',
  'salary_max_extracted', 'salary_currency_extracted',
  'posted_status_extracted', 'posted_value_extracted',
  'posted_source_extracted', 'posted_age_days_extracted',
  'sponsorship_status_extracted', 'positive_sponsorship_matches_extracted',
  'negative_sponsorship_matches_extracted',
  'positive_sponsorship_evidence_extracted',
  'negative_sponsorship_evidence_extracted',
  'clearance_or_citizenship_extracted',
  'clearance_or_citizenship_evidence_extracted',
  'education_requirement_extracted', 'employment_type_extracted',
  'resume_match_score', 'resume_score', 'fit_category', 'score_confidence',
  'role_family', 'seniority_level', 'required_years_min',
  'core_languages_extracted', 'core_frameworks_extracted',
  'core_cloud_devops_extracted', 'database_requirements_extracted',
  'ai_ml_requirements_extracted', 'matched_resume_skills',
  'missing_or_weaker_skills', 'score_reason', 'closed_or_unusable_jd',
  'closed_or_unusable_reason',
]

function createUuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16)
    const nibble = char === 'x' ? value : (value & 0x3) | 0x8
    return nibble.toString(16)
  })
}

export function createImportCommitKey() {
  return createUuid()
}

function firstCsvRecord(text) {
  let quoted = false
  let record = ''
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        record += '""'
        index += 1
        continue
      }
      quoted = !quoted
      record += char
      continue
    }
    if (!quoted && (char === '\n' || char === '\r')) break
    record += char
  }
  return record
}

function delimiterCounts(record) {
  const counts = { ',': 0, '\t': 0, ';': 0 }
  let quoted = false
  for (let index = 0; index < record.length; index += 1) {
    const char = record[index]
    if (char === '"') {
      if (quoted && record[index + 1] === '"') {
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (!quoted && Object.prototype.hasOwnProperty.call(counts, char)) counts[char] += 1
  }
  return counts
}

function parseCsvHeader(text) {
  const record = firstCsvRecord(text.replace(/^\uFEFF/, ''))
  if (!record) throw new Error('CSV import must contain a header row.')
  const counts = delimiterCounts(record)
  const delimiter = Object.entries(counts).sort((left, right) => right[1] - left[1])[0][0]
  const fields = []
  let value = ''
  let quoted = false
  for (let index = 0; index < record.length; index += 1) {
    const char = record[index]
    if (char === '"') {
      if (quoted && record[index + 1] === '"') {
        value += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (!quoted && char === delimiter) {
      fields.push(value)
      value = ''
      continue
    }
    value += char
  }
  fields.push(value)
  if (!fields.some((field) => field !== '')) {
    throw new Error('CSV import must contain at least one named column.')
  }
  return fields
}

function parseJsonHeaders(text) {
  let payload
  try {
    payload = JSON.parse(text.replace(/^\uFEFF/, ''))
  } catch {
    throw new Error('JSON import must be valid JSON before it can be mapped.')
  }
  if (!Array.isArray(payload) || payload.length === 0) {
    throw new Error('JSON import must be a non-empty array of objects.')
  }
  const headers = []
  const seen = new Set()
  payload.forEach((item) => {
    if (!item || Array.isArray(item) || typeof item !== 'object') {
      throw new Error('Every JSON import record must be an object.')
    }
    Object.keys(item).forEach((key) => {
      if (!seen.has(key)) {
        seen.add(key)
        headers.push(key)
      }
    })
  })
  if (headers.length === 0) throw new Error('JSON import must contain at least one named column.')
  return headers
}

export async function readImportHeaders(file) {
  if (!file) throw new Error('Choose a CSV or JSON file.')
  if (file.size > MAX_IMPORT_UPLOAD_BYTES) {
    throw new Error('Import upload exceeds the 10 MiB limit.')
  }
  const lowerName = file.name.toLowerCase()
  if (!lowerName.endsWith('.csv') && !lowerName.endsWith('.json')) {
    throw new Error('Import files must be CSV or JSON.')
  }
  const text = await file.text()
  return lowerName.endsWith('.json') ? parseJsonHeaders(text) : parseCsvHeader(text)
}

export function defaultImportMapping(headers) {
  const used = new Set()
  const mapping = {}
  headers.forEach((label, index) => {
    if (IMPORT_TARGET_FIELDS.includes(label) && !used.has(label)) {
      mapping[String(index)] = label
      used.add(label)
    }
  })
  return mapping
}

export async function createImportPreview(file, mapping) {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  form.append('options', '{}')
  return client.post('/crm/imports/preview', form).then((response) => response.data)
}

export async function getImportPreview(previewId) {
  return client.get(`/crm/imports/${previewId}`).then((response) => response.data)
}

export async function commitImportPreview(previewId, payload) {
  return client.post(`/crm/imports/${previewId}/commit`, payload).then((response) => response.data)
}

export async function downloadRejectedImportRows(previewId) {
  return client.get(`/crm/imports/${previewId}/rejected.csv`, { responseType: 'blob' })
}

export function importError(error, fallback = 'Import could not be completed.') {
  return formatApiError(error, fallback)
}
