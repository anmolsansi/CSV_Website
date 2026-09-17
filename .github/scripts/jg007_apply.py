from pathlib import Path
import re


def read(path):
    return Path(path).read_text()


def write(path, text):
    Path(path).write_text(text)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact match, got {count}")
    return text.replace(old, new, 1)


def sub_once(text, pattern, repl, label):
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, got {count}")
    return updated


# Keep navigation filter state separate from sort/pagination state.
path = "frontend/src/api/queryParams.js"
text = read(path)
text = replace_once(
    text,
    "function toSearchParams(serialized, viewId) {",
    """function extractFilters(values, fields) {
  const excluded = new Set(['sortBy', 'sortDir', 'page', 'pageSize'])
  const filters = {}
  for (const [canonical] of fields) {
    if (excluded.has(canonical)) continue
    if (Object.prototype.hasOwnProperty.call(values, canonical)) filters[canonical] = values[canonical]
  }
  return filters
}

function toSearchParams(serialized, viewId) {""",
    "queryParams extractFilters",
)
text = replace_once(
    text,
    "    filters: values,\n    page: values.page ?? defaults.page ?? 1,",
    "    filters: extractFilters(values, DASHBOARD_FIELDS),\n    page: values.page ?? defaults.page ?? 1,",
    "dashboard nav filters",
)
text = replace_once(
    text,
    "    filters: values,\n    page: values.page ?? defaults.page ?? 1,",
    "    filters: extractFilters(values, APPLICATION_FIELDS),\n    page: values.page ?? defaults.page ?? 1,",
    "application nav filters",
)
write(path, text)


# Route all browse/export calls through the shared serializers.
path = "frontend/src/api/client.js"
text = read(path)
text = replace_once(
    text,
    "import axios from 'axios'\n",
    "import axios from 'axios'\nimport { serializeApplicationQuery, serializeDashboardQuery } from './queryParams'\n",
    "client import",
)
text = sub_once(
    text,
    r"  getRows: \(\{.*?\n      \.then\(\(r\) => r\.data\),\n  recordClick:",
    """  getRows: (params = {}) =>
    client
      .get('/rows', {
        params: {
          ...serializeDashboardQuery(params, { includePagination: true, includeFalse: true }),
          ...todayWindowParams(),
        },
      })
      .then((r) => r.data),
  recordClick:""",
    "client getRows",
)
text = sub_once(
    text,
    r"  getApplications: \(params = \{\}\) => \{.*?\n  \},\n  updateApplication:",
    """  getApplications: (params = {}) =>
    client
      .get('/crm/applications', {
        params: serializeApplicationQuery(params, { includePagination: true, includeFalse: true }),
      })
      .then((r) => r.data),
  updateApplication:""",
    "client getApplications",
)
text = sub_once(
    text,
    r"  exportDashboard: \(params = \{\}\) => \{.*?\n  \},\n  exportApplications: \(params = \{\}\) => \{.*?\n  \},\n\n  // CRM - Follow-up presets",
    """  exportDashboard: (params = {}) => {
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

  // CRM - Follow-up presets""",
    "client exports",
)
write(path, text)


# Saved Views carry the actual query state in the navigation URL.
path = "frontend/src/pages/SavedViews.jsx"
text = read(path)
text = replace_once(
    text,
    "import { api } from '../api/client'\n",
    "import { api } from '../api/client'\nimport { savedViewSearch } from '../api/queryParams'\n",
    "saved views import",
)
text = sub_once(
    text,
    r"  const applyView = \(view\) => \{.*?\n  \}\n\n  const editView",
    """  const applyView = (view) => {
    setError('')
    try {
      const query = savedViewSearch(view.view_type, view.filters || {}, view.id).toString()
      if (view.view_type === 'job_links') {
        navigate(`/?${query}`)
      } else if (view.view_type === 'applications') {
        navigate(`/applications?${query}`)
      } else if (view.view_type === 'pipeline') {
        navigate(`/pipeline?view=${view.id}`)
      }
    } catch (err) {
      setError(`Saved view cannot be applied: ${err.message}`)
    }
  }

  const editView""",
    "saved views apply",
)
write(path, text)


# Dashboard hydrates query state, tracks the settled request, and exports the exact settled query.
path = "frontend/src/pages/Dashboard.jsx"
text = read(path)
text = replace_once(
    text,
    "import { api } from '../api/client'\n",
    "import { api } from '../api/client'\nimport { dashboardNavigationState, dashboardStateQuery, queryValidationMessage, serializeDashboardQuery } from '../api/queryParams'\n",
    "dashboard import",
)
text = replace_once(
    text,
    "export default function Dashboard() {\n",
    """export default function Dashboard() {
  const initialNavigation = useMemo(
    () => dashboardNavigationState(window.location.search, { ...DEFAULT_SORT, ...DEFAULT_FILTERS, page: 1, pageSize: 50 }),
    []
  )
  const initialFilters = { ...DEFAULT_FILTERS, ...initialNavigation.filters }
""",
    "dashboard initial nav",
)
text = replace_once(
    text,
    "  const [sort, setSort] = useState(DEFAULT_SORT)\n  const [filters, setFilters] = useState(DEFAULT_FILTERS)\n",
    "  const [sort, setSort] = useState(initialNavigation.sort)\n  const [filters, setFilters] = useState(initialFilters)\n",
    "dashboard initial state",
)
text = replace_once(
    text,
    "  const [pagination, setPagination] = useState(DEFAULT_PAGINATION)\n",
    "  const [pagination, setPagination] = useState({ ...DEFAULT_PAGINATION, page: initialNavigation.page, pageSize: initialNavigation.pageSize })\n",
    "dashboard pagination",
)
text = replace_once(
    text,
    "  const [openingBatch, setOpeningBatch] = useState(false)\n",
    "  const [openingBatch, setOpeningBatch] = useState(false)\n  const settledQueryRef = useRef(null)\n  const requestSequenceRef = useRef(0)\n  const [queryError, setQueryError] = useState(() => queryValidationMessage(initialNavigation))\n",
    "dashboard query refs",
)
text = sub_once(
    text,
    r"  const loadRows = \(nextSort = sort, nextFilters = filters, nextPage = pagination\.page, nextPageSize = pagination\.pageSize\) => \{.*?\n  \}\n\n  useEffect\(\(\) => \{",
    """  const loadRows = (nextSort = sort, nextFilters = filters, nextPage = pagination.page, nextPageSize = pagination.pageSize) => {
    const requestId = ++requestSequenceRef.current
    const requestQuery = dashboardStateQuery(nextSort, nextFilters, nextPage, nextPageSize)
    setLoading(true)
    return api.getRows(requestQuery).then((d) => {
      if (requestId !== requestSequenceRef.current) return
      setColumns(d.columns)
      setRows(d.rows)
      setStats(normalizeStats(d.stats))
      setFilterOptions(normalizeFilterOptions(d.filter_options))
      setColumnOrder((prev) => mergeColumnOrder(prev, d.columns))
      setSelectedRowIds(new Set())
      setPagination({ page: d.page || nextPage, pageSize: d.page_size || nextPageSize, totalCount: d.total_count || d.rows.length, hasNext: d.has_next || false })
      settledQueryRef.current = requestQuery
    }).catch(() => {
      if (requestId === requestSequenceRef.current) toast('Could not load jobs. Please retry.', 'error')
    }).finally(() => {
      if (requestId === requestSequenceRef.current) setLoading(false)
    })
  }

  useEffect(() => {""",
    "dashboard loadRows",
)
text = replace_once(
    text,
    "      api.getRows({ ...DEFAULT_SORT, ...DEFAULT_FILTERS, page: 1, pageSize: 50 }),\n",
    "      api.getRows(dashboardStateQuery(initialNavigation.sort, initialFilters, initialNavigation.page, initialNavigation.pageSize)),\n",
    "dashboard initial request",
)
text = replace_once(
    text,
    "      setPagination({ page: rowData.page || 1, pageSize: rowData.page_size || 50, totalCount: rowData.total_count || rowData.rows.length, hasNext: rowData.has_next || false })\n    }).finally(() => setLoading(false))\n",
    "      setPagination({ page: rowData.page || initialNavigation.page, pageSize: rowData.page_size || initialNavigation.pageSize, totalCount: rowData.total_count || rowData.rows.length, hasNext: rowData.has_next || false })\n      settledQueryRef.current = dashboardStateQuery(initialNavigation.sort, initialFilters, initialNavigation.page, initialNavigation.pageSize)\n    }).catch(() => toast('Could not load jobs. Please retry.', 'error')).finally(() => setLoading(false))\n",
    "dashboard initial settle",
)
text = sub_once(
    text,
    r"  const handleExport = async \(\) => \{.*?\n  \}\n\n  const handleClick",
    """  const handleExport = async () => {
    if (loading || !settledQueryRef.current) {
      toast('Wait for the current filters to finish loading before exporting.', 'warning')
      return
    }
    const querySnapshot = dashboardStateQuery(sort, filters, pagination.page, pagination.pageSize)
    const currentSignature = JSON.stringify(serializeDashboardQuery(querySnapshot, { includePagination: false, includeFalse: true }))
    const settledSignature = JSON.stringify(serializeDashboardQuery(settledQueryRef.current, { includePagination: false, includeFalse: true }))
    if (currentSignature !== settledSignature) {
      toast('Filters changed before the matching results settled. Retry after loading finishes.', 'warning')
      return
    }
    const params = { ...querySnapshot, format: exportFormat, scope: exportScope }
    if (exportScope === 'selected') {
      if (selectedRowIds.size === 0) { toast('No rows selected', 'warning'); return }
      params.rowIds = [...selectedRowIds]
    }
    const visibleCols = orderedColumns.filter((col) => !hidden.includes(col))
    if (visibleCols.length > 0 && visibleCols.length < orderedColumns.length) params.columns = visibleCols.join(',')
    try {
      const res = await api.exportDashboard(params)
      const ext = exportFormat === 'json' ? 'json' : 'csv'
      const blob = new Blob([res.data], { type: ext === 'json' ? 'application/json' : 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dashboard_export.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      toast('Export downloaded', 'success')
    } catch {
      toast('Export failed. No file was downloaded. Please retry.', 'error')
    }
  }

  const handleClick""",
    "dashboard export",
)
text = replace_once(
    text,
    "  useEffect(() => {\n    window.addEventListener('keydown', handleKeyDown)\n    return () => window.removeEventListener('keydown', handleKeyDown)\n  }, [handleKeyDown])\n\n  return (\n",
    """  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const clearNavigationError = () => {
    window.history.replaceState({}, '', window.location.pathname)
    setQueryError('')
    setSort(DEFAULT_SORT)
    setFilters(DEFAULT_FILTERS)
    setPagination(DEFAULT_PAGINATION)
    loadRows(DEFAULT_SORT, DEFAULT_FILTERS, 1, DEFAULT_PAGINATION.pageSize)
  }

  return (
""",
    "dashboard clear nav",
)
text = replace_once(
    text,
    '    <div className="container">\n        <CsvUpload',
    '    <div className="container">\n        {queryError && <div className="error-msg" role="alert">{queryError} <button className="btn btn-grey btn-sm" onClick={clearNavigationError}>Clear saved-view filters</button></div>}\n        <CsvUpload',
    "dashboard error ui",
)
text = replace_once(
    text,
    '<button className="btn btn-grey" onClick={handleExport}>Download</button>',
    '<button className="btn btn-grey" onClick={handleExport} disabled={loading}>Download</button>',
    "dashboard export disabled",
)
write(path, text)


# Applications use the same canonical query state and settled export guard.
path = "frontend/src/pages/Applications.jsx"
text = read(path)
text = replace_once(
    text,
    "import { useEffect, useState, useCallback } from 'react'",
    "import { useEffect, useMemo, useRef, useState, useCallback } from 'react'",
    "applications react imports",
)
text = replace_once(
    text,
    "import { api } from '../api/client'\n",
    "import { api } from '../api/client'\nimport { applicationNavigationState, applicationStateQuery, queryValidationMessage, serializeApplicationQuery } from '../api/queryParams'\n",
    "applications import",
)
text = sub_once(
    text,
    r"\nfunction buildApiParams\(filters, sort, pagination\) \{.*?\n\}\n\nexport default function Applications\(\) \{",
    "\nexport default function Applications() {",
    "remove local app serializer",
)
text = replace_once(
    text,
    "export default function Applications() {\n",
    """export default function Applications() {
  const initialNavigation = useMemo(
    () => applicationNavigationState(window.location.search, { ...DEFAULT_FILTERS, sortBy: 'opened_at', sortDir: 'desc', page: 1, pageSize: 50 }),
    []
  )
  const initialFilters = { ...DEFAULT_FILTERS, ...initialNavigation.filters }
""",
    "applications initial nav",
)
text = replace_once(text, "  const [filters, setFilters] = useState(DEFAULT_FILTERS)\n", "  const [filters, setFilters] = useState(initialFilters)\n", "applications filters state")
text = replace_once(text, "  const [sort, setSort] = useState({ field: 'opened_at', direction: 'desc' })\n", "  const [sort, setSort] = useState(initialNavigation.sort)\n", "applications sort state")
text = replace_once(
    text,
    "  const [pagination, setPagination] = useState(DEFAULT_PAGINATION)\n  const toast = useToast()\n",
    "  const [pagination, setPagination] = useState({ ...DEFAULT_PAGINATION, page: initialNavigation.page, pageSize: initialNavigation.pageSize })\n  const settledQueryRef = useRef(null)\n  const requestSequenceRef = useRef(0)\n  const [queryError, setQueryError] = useState(() => queryValidationMessage(initialNavigation))\n  const toast = useToast()\n",
    "applications refs",
)
text = sub_once(
    text,
    r"  const refresh = \(nextFilters = filters, nextSort = sort, nextPage = pagination\.page\) => \{.*?\n  \}\n\n  useEffect",
    """  const refresh = (nextFilters = filters, nextSort = sort, nextPage = pagination.page) => {
    const requestId = ++requestSequenceRef.current
    const query = applicationStateQuery(nextSort, nextFilters, nextPage, pagination.pageSize)
    setLoading(true)
    return api.getApplications(query).then((data) => {
      if (requestId !== requestSequenceRef.current) return
      setApplications(data.rows || [])
      setFilterOptions(data.filter_options || { ats_groups: [] })
      setPagination({ page: data.page || nextPage, pageSize: data.page_size || 50, totalCount: data.total_count || (data.rows || []).length, hasNext: data.has_next || false })
      settledQueryRef.current = query
    }).catch(() => {
      if (requestId === requestSequenceRef.current) toast('Could not load applications. Please retry.', 'error')
    }).finally(() => {
      if (requestId === requestSequenceRef.current) setLoading(false)
    })
  }

  useEffect""",
    "applications refresh",
)
text = sub_once(
    text,
    r"  const handleExport = async \(\) => \{.*?\n  \}\n\n  const handleKeyDown",
    """  const handleExport = async () => {
    if (loading || !settledQueryRef.current) {
      toast('Wait for the current filters to finish loading before exporting.', 'warning')
      return
    }
    const querySnapshot = applicationStateQuery(sort, filters, pagination.page, pagination.pageSize)
    const currentSignature = JSON.stringify(serializeApplicationQuery(querySnapshot, { includePagination: false, includeFalse: true }))
    const settledSignature = JSON.stringify(serializeApplicationQuery(settledQueryRef.current, { includePagination: false, includeFalse: true }))
    if (currentSignature !== settledSignature) {
      toast('Filters changed before the matching results settled. Retry after loading finishes.', 'warning')
      return
    }
    const params = { ...querySnapshot, format: exportFormat, scope: exportScope }
    if (exportScope === 'selected') {
      if (selectedIds.size === 0) { toast('No rows selected', 'warning'); return }
      params.rowIds = [...selectedIds]
    } else if (exportScope === 'applied') {
      params.scope = 'filtered'
      Object.assign(params, { ...DEFAULT_FILTERS, status: 'applied' })
    } else if (exportScope === 'followups') {
      params.scope = 'filtered'
      Object.assign(params, { ...DEFAULT_FILTERS, followUpDue: true })
    }
    try {
      const res = await api.exportApplications(params)
      const ext = exportFormat === 'json' ? 'json' : 'csv'
      const blob = new Blob([res.data], { type: ext === 'json' ? 'application/json' : 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `applications_export.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      toast('Export downloaded', 'success')
    } catch {
      toast('Export failed. No file was downloaded. Please retry.', 'error')
    }
  }

  const handleKeyDown""",
    "applications export",
)
text = replace_once(
    text,
    "  useEffect(() => {\n    window.addEventListener('keydown', handleKeyDown)\n    return () => window.removeEventListener('keydown', handleKeyDown)\n  }, [handleKeyDown])\n\n  const columns = [",
    """  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const clearNavigationError = () => {
    window.history.replaceState({}, '', window.location.pathname)
    setQueryError('')
    setSort({ field: 'opened_at', direction: 'desc' })
    setFilters(DEFAULT_FILTERS)
    setPagination(DEFAULT_PAGINATION)
    refresh(DEFAULT_FILTERS, { field: 'opened_at', direction: 'desc' }, 1)
  }

  const columns = [""",
    "applications clear nav",
)
text = replace_once(
    text,
    '    <div className="container">\n      <div className="page-header-row">',
    '    <div className="container">\n      {queryError && <div className="error-msg" role="alert">{queryError} <button className="btn btn-grey btn-sm" onClick={clearNavigationError}>Clear saved-view filters</button></div>}\n      <div className="page-header-row">',
    "applications error ui",
)
text = replace_once(
    text,
    '<button className="btn btn-grey" onClick={handleExport}>Download</button>',
    '<button className="btn btn-grey" onClick={handleExport} disabled={loading}>Download</button>',
    "applications export disabled",
)
write(path, text)


# Build guide records implemented current behavior only.
docs = Path("docs/JOBGRID_BUILD_GUIDE.md")
text = docs.read_text()
heading = "## JG-007 shared browser and saved-view query serialization"
if heading not in text:
    text += """

## JG-007 shared browser and saved-view query serialization

`frontend/src/api/queryParams.js` is the frontend source of truth for Dashboard and Applications query serialization. It accepts the documented camelCase UI names and snake_case wire aliases, normalizes booleans and numbers explicitly, and emits the backend's snake_case query contract.

The same serializer is used for list loads, Dashboard top-five retrieval, filtered exports, and Saved View navigation. Export requests always send an explicit `scope` and sort, never copy `page`/`page_size`, and selected scope sends only selected IDs for the backend ownership check.

Saved Views serialize filter state into the destination URL. Dashboard and Applications hydrate their initial filter and sort state from that URL after reload. Unknown keys or invalid booleans/numbers render a recoverable error with a clear action instead of being ignored silently.

Dashboard and Applications record the last settled browse query. Export is disabled while a browse request is loading, snapshots the current query at click time, and refuses to export if that snapshot does not match the settled result. HTTP export failures show an error and never report a successful download.

Focused verification:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/filter-export-parity.spec.ts --project=chromium
```

JG-007 changes no database schema and does not change the JG-005/JG-006 backend filtering or ownership contracts.
"""
    docs.write_text(text)
