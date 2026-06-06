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
  getRows: ({ sortBy = 'created_at', sortDir = 'desc', atsGroup = '' } = {}) =>
    client
      .get('/rows', {
        params: {
          sort_by: sortBy,
          sort_dir: sortDir,
          ...todayWindowParams(),
          ...(atsGroup ? { ats_group: atsGroup } : {}),
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
}

export default client
