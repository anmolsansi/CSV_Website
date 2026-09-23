import { useEffect, useMemo, useState } from 'react'
import client, { api } from '../api/client'

const STORAGE_KEY = 'jobgrid:last-bulk-action'

function readStoredAction() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function storeAction(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Session storage is an enhancement. The live panel still works without it.
  }
}

function operationKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16)
    const nibble = char === 'x' ? value : (value & 0x3) | 0x8
    return nibble.toString(16)
  })
}

function serverDeadlineLabel(value) {
  if (!value) return 'No immediate Undo deadline returned.'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

export default function BulkActionStatus() {
  const [action, setAction] = useState(readStoredAction)
  const [pending, setPending] = useState(false)
  const [conflict, setConflict] = useState(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const requestInterceptor = client.interceptors.request.use((config) => {
      if (
        config?.method?.toLowerCase() === 'delete'
        && config?.url === '/rows'
        && config?.data?.mode === 'archive'
        && !config.data.request_key
      ) {
        return {
          ...config,
          data: { ...config.data, request_key: operationKey() },
        }
      }
      return config
    })
    const responseInterceptor = client.interceptors.response.use((response) => {
      const data = response?.data
      if (data?.operation_id && data?.undo_expires_at) {
        const next = {
          operationId: data.operation_id,
          undoExpiresAt: data.undo_expires_at,
          archived: data.archived ?? data.effect_count ?? 0,
          status: data.undo_status || 'completed',
        }
        storeAction(next)
        setAction(next)
        setConflict(null)
        setMessage('')
      }
      return response
    })
    return () => {
      client.interceptors.request.eject(requestInterceptor)
      client.interceptors.response.eject(responseInterceptor)
    }
  }, [])

  const deadline = useMemo(
    () => serverDeadlineLabel(action?.undoExpiresAt),
    [action?.undoExpiresAt]
  )

  if (!action) return null

  const runUndo = async (mode = 'all_or_nothing') => {
    if (pending) return
    setPending(true)
    setMessage('')
    try {
      const result = await api.undoBulkAction(action.operationId, mode)
      setConflict(null)
      setMessage(
        result.status === 'undone'
          ? `Undo restored ${result.restored} record${result.restored === 1 ? '' : 's'}.`
          : `Recovered ${result.restored} record${result.restored === 1 ? '' : 's'}; ${result.conflicts} changed and ${result.missing} missing.`
      )
      const next = { ...action, status: result.status, undoResult: result }
      storeAction(next)
      setAction(next)
      window.dispatchEvent(new CustomEvent('jobgrid:bulk-changed', { detail: result }))
      if (window.location.pathname !== '/archive') {
        window.location.reload()
      }
    } catch (error) {
      const status = error?.response?.status
      const detail = error?.response?.data?.detail || {}
      if (status === 409) {
        setConflict({
          conflicts: Number(detail.conflicts || 0),
          missing: Number(detail.missing || 0),
        })
        setMessage('Nothing was overwritten. Some records changed after the bulk action.')
      } else if (status === 410) {
        setConflict(null)
        setMessage('Immediate Undo expired. The archived rows are still recoverable from Archive.')
      } else {
        setMessage(detail?.fields?.[0]?.message || 'Undo could not be completed. Retry after refreshing.')
      }
    } finally {
      setPending(false)
    }
  }

  const dismiss = () => {
    storeAction(null)
    setAction(null)
    setConflict(null)
    setMessage('')
  }

  return (
    <section className="card" aria-live="polite" aria-label="Last bulk action" style={{ margin: '12px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <strong>Bulk action</strong>
          <div>{action.archived ? `${action.archived} archived. ` : ''}Immediate Undo deadline: {deadline}</div>
          <small>Operation {action.operationId}</small>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {!['undone', 'expired'].includes(action.status) && (
            <button className="btn btn-primary btn-sm" type="button" disabled={pending} onClick={() => runUndo('all_or_nothing')}>
              {pending ? 'Undoing…' : 'Undo'}
            </button>
          )}
          {conflict && (
            <button className="btn btn-grey btn-sm" type="button" disabled={pending} onClick={() => runUndo('restore_unchanged')}>
              Restore unchanged records
            </button>
          )}
          <button className="btn btn-grey btn-sm" type="button" onClick={dismiss}>Dismiss</button>
        </div>
      </div>
      {conflict && (
        <p role="status" style={{ marginBottom: 0 }}>
          Changed: {conflict.conflicts}. Missing: {conflict.missing}. Default Undo restored 0 records.
        </p>
      )}
      {message && <p role="status" style={{ marginBottom: 0 }}>{message}</p>}
    </section>
  )
}