import client from './client'

function operationId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16)
    const nibble = char === 'x' ? value : (value & 0x3) | 0x8
    return nibble.toString(16)
  })
}

export const contactApi = {
  listContacts: (q = '') =>
    client.get('/crm/contacts', { params: { q, limit: 100 } }).then((response) => response.data),
  createContact: (payload) =>
    client.post('/crm/contacts', payload, {
      headers: { 'Idempotency-Key': operationId() },
    }).then((response) => response.data),
  updateContact: (contactId, payload) =>
    client.patch(`/crm/contacts/${contactId}`, payload).then((response) => response.data),
  deleteContact: (contactId, version) =>
    client.delete(`/crm/contacts/${contactId}`, { params: { version } }).then((response) => response.data),
  getApplicationContacts: (trackId) =>
    client.get(`/crm/tracks/${trackId}/contacts`).then((response) => response.data),
  linkApplicationContact: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/contacts`, payload, {
      headers: { 'Idempotency-Key': operationId() },
    }).then((response) => response.data),
  unlinkApplicationContact: (trackId, associationId) =>
    client.delete(`/crm/tracks/${trackId}/contacts/${associationId}`).then((response) => response.data),
  getInterviews: (trackId) =>
    client.get(`/crm/tracks/${trackId}/interviews`).then((response) => response.data),
  createInterview: (trackId, payload) =>
    client.post(`/crm/tracks/${trackId}/interviews`, payload, {
      headers: { 'Idempotency-Key': operationId() },
    }).then((response) => response.data),
  updateInterview: (interviewId, payload) =>
    client.patch(`/crm/interviews/${interviewId}`, payload).then((response) => response.data),
  downloadInterviewCalendar: (interviewId) =>
    client.get(`/crm/interviews/${interviewId}/calendar.ics`, { responseType: 'blob' }).then((response) => response.data),
}
