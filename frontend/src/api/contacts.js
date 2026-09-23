const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function operationId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16)
    const nibble = char === 'x' ? value : (value & 0x3) | 0x8
    return nibble.toString(16)
  })
}

async function request(path, { method = 'GET', body, headers = {}, responseType = 'json' } = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    credentials: 'include',
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  if (!response.ok) {
    let data = null
    try { data = await response.json() } catch { data = { detail: 'Request failed.' } }
    const error = new Error('Request failed')
    error.response = { status: response.status, data }
    throw error
  }
  if (response.status === 204) return null
  if (responseType === 'blob') return response.blob()
  return response.json()
}

export const contactApi = {
  listContacts: (q = '') => request(`/crm/contacts?q=${encodeURIComponent(q)}&limit=100`),
  createContact: (payload) => request('/crm/contacts', {
    method: 'POST', body: payload, headers: { 'Idempotency-Key': operationId() },
  }),
  updateContact: (contactId, payload) => request(`/crm/contacts/${contactId}`, { method: 'PATCH', body: payload }),
  deleteContact: (contactId, version) => request(`/crm/contacts/${contactId}?version=${version}`, { method: 'DELETE' }),
  getApplicationContacts: (trackId) => request(`/crm/tracks/${trackId}/contacts`),
  linkApplicationContact: (trackId, payload) => request(`/crm/tracks/${trackId}/contacts`, {
    method: 'POST', body: payload, headers: { 'Idempotency-Key': operationId() },
  }),
  unlinkApplicationContact: (trackId, associationId) => request(`/crm/tracks/${trackId}/contacts/${associationId}`, { method: 'DELETE' }),
  getInterviews: (trackId) => request(`/crm/tracks/${trackId}/interviews`),
  createInterview: (trackId, payload) => request(`/crm/tracks/${trackId}/interviews`, {
    method: 'POST', body: payload, headers: { 'Idempotency-Key': operationId() },
  }),
  updateInterview: (interviewId, payload) => request(`/crm/interviews/${interviewId}`, { method: 'PATCH', body: payload }),
  downloadInterviewCalendar: (interviewId) => request(`/crm/interviews/${interviewId}/calendar.ics`, { responseType: 'blob' }),
}
