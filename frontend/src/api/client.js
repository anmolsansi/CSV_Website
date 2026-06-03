import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

export const api = {
  loginGoogleUrl: () => `${API_URL}/auth/login/google`,
  me: () => client.get('/auth/me').then((r) => r.data),
  logout: () => client.post('/auth/logout'),
  uploadCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/upload', fd).then((r) => r.data)
  },
  getRows: () => client.get('/rows').then((r) => r.data),
  recordClick: (rowId) => client.post(`/rows/${rowId}/click`).then((r) => r.data),
  getPreferences: () => client.get('/preferences').then((r) => r.data),
  setPreferences: (hidden) =>
    client.put('/preferences', { hidden_columns: hidden }).then((r) => r.data),
}

export default client
