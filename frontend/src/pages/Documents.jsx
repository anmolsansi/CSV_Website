import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatApiError } from '../api/client'
import { useToast } from '../App'

const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

function formatDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
}

function kindLabel(kind) {
  return kind === 'cover_letter' ? 'Cover letter' : 'Resume'
}

async function saveDownload(document) {
  const response = await api.downloadDocument(document.id)
  const url = URL.createObjectURL(response.data)
  try {
    const link = window.document.createElement('a')
    link.href = url
    link.download = document.original_filename || 'document'
    window.document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export default function Documents() {
  const toast = useToast()
  const trackId = useMemo(() => {
    const raw = new URLSearchParams(window.location.search).get('track_id')
    const parsed = raw ? Number(raw) : null
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null
  }, [])

  const [documents, setDocuments] = useState([])
  const [quota, setQuota] = useState({ used_bytes: 0, limit_bytes: 100 * 1024 * 1024 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState('resume')
  const [file, setFile] = useState(null)
  const [familyId, setFamilyId] = useState('')
  const [familySourceLabel, setFamilySourceLabel] = useState('')
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [deletePendingId, setDeletePendingId] = useState(null)
  const [downloadPendingId, setDownloadPendingId] = useState(null)
  const [applicationDetails, setApplicationDetails] = useState({})
  const [referenceConflict, setReferenceConflict] = useState(null)
  const abortRef = useRef(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.getDocuments()
      setDocuments(data.items || [])
      setQuota(data.quota || { used_bytes: 0, limit_bytes: 100 * 1024 * 1024 })
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not load the document library. Please retry.'
      ).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const readyFamilies = useMemo(() => {
    const latest = new Map()
    for (const document of documents) {
      if (document.state === 'deleted') continue
      const current = latest.get(document.document_family_id)
      if (!current || document.version_number > current.version_number) {
        latest.set(document.document_family_id, document)
      }
    }
    return [...latest.values()]
  }, [documents])

  const startNewVersion = (document) => {
    setFamilyId(document.document_family_id)
    setFamilySourceLabel(`${document.label} · v${document.version_number}`)
    setKind(document.kind)
    setLabel(document.label)
    setFile(null)
    setProgress(0)
    setError('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const clearVersionMode = () => {
    setFamilyId('')
    setFamilySourceLabel('')
    setLabel('')
    setFile(null)
    setProgress(0)
  }

  const submitUpload = async (event) => {
    event.preventDefault()
    if (uploading) return

    const trimmedLabel = label.trim()
    if (!trimmedLabel) {
      setError('Enter a document label.')
      return
    }
    if (!file) {
      setError('Choose a PDF or UTF-8 text file.')
      return
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      setError('This file is larger than the 10 MiB document limit.')
      return
    }
    const lowerName = file.name.toLowerCase()
    if (!lowerName.endsWith('.pdf') && !lowerName.endsWith('.txt')) {
      setError('Choose a .pdf or .txt file. The server also verifies the actual bytes.')
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    setUploading(true)
    setProgress(0)
    setError('')
    try {
      const created = await api.uploadDocument(file, {
        kind,
        label: trimmedLabel,
        documentFamilyId: familyId || undefined,
        signal: controller.signal,
        onProgress: setProgress,
      })
      toast(
        `${kindLabel(created.kind)} ${created.label} v${created.version_number} uploaded.`,
        'success'
      )
      setLabel('')
      setFile(null)
      setFamilyId('')
      setFamilySourceLabel('')
      setProgress(100)
      await refresh()
    } catch (requestError) {
      if (requestError?.code === 'ERR_CANCELED') {
        setError('Upload canceled. No ready document version was created by this request.')
      } else {
        const formatted = formatApiError(
          requestError,
          'Could not upload this document. Please retry.'
        )
        setError(formatted.message)
        toast(formatted.message, 'error')
      }
    } finally {
      abortRef.current = null
      setUploading(false)
    }
  }

  const download = async (document) => {
    if (downloadPendingId) return
    setDownloadPendingId(document.id)
    setError('')
    try {
      await saveDownload(document)
    } catch (requestError) {
      const formatted = formatApiError(
        requestError,
        'Could not download this private document.'
      )
      setError(formatted.message)
      toast(formatted.message, 'error')
    } finally {
      setDownloadPendingId(null)
    }
  }

  const showApplications = async (document) => {
    setError('')
    try {
      const data = await api.getDocumentApplications(document.id, { page: 1, limit: 50 })
      setApplicationDetails((current) => ({ ...current, [document.id]: data }))
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not load linked applications.'
      ).message)
    }
  }

  const remove = async (document) => {
    if (deletePendingId) return
    if (!window.confirm(
      `Delete ${document.label} v${document.version_number}? This is allowed only when no application references it.`
    )) return

    setDeletePendingId(document.id)
    setReferenceConflict(null)
    setError('')
    try {
      await api.deleteDocument(document.id)
      toast('Document removed from the active library. Its private bytes entered retention cleanup.', 'success')
      await refresh()
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail
      if (requestError?.response?.status === 409 && detail?.code === 'document_is_referenced') {
        setReferenceConflict({
          document,
          applications: detail.applications || [],
        })
      } else {
        const formatted = formatApiError(
          requestError,
          'Could not delete this document.'
        )
        setError(formatted.message)
        toast(formatted.message, 'error')
      }
    } finally {
      setDeletePendingId(null)
    }
  }

  const quotaPercent = quota.limit_bytes
    ? Math.min(100, Math.round((quota.used_bytes / quota.limit_bytes) * 100))
    : 0

  return (
    <div className="page-container documents-page">
      <div className="page-header-row">
        <div>
          <h2>Documents</h2>
          <p>Private, immutable resume and cover-letter versions linked to exact applications.</p>
        </div>
        {trackId && (
          <Link className="btn btn-grey" to={`/applications?track_id=${trackId}`}>
            Back to application
          </Link>
        )}
      </div>

      <section className="document-upload-card" aria-labelledby="document-upload-heading">
        <div className="document-panel-header">
          <div>
            <h3 id="document-upload-heading">
              {familyId ? 'Upload a new immutable version' : 'Upload document'}
            </h3>
            <p className="muted-text">
              PDF or UTF-8 text, up to 10 MiB. File bytes stay in private authenticated storage.
            </p>
          </div>
          {familyId && (
            <button className="btn btn-grey btn-sm" type="button" onClick={clearVersionMode}>
              Cancel new-version mode
            </button>
          )}
        </div>

        {familyId && (
          <p className="document-version-mode" role="status">
            New version of <strong>{familySourceLabel}</strong>. Existing versions will not be overwritten.
          </p>
        )}

        <form className="document-upload-form" onSubmit={submitUpload}>
          <label>
            Kind
            <select
              aria-label="Document kind"
              value={kind}
              disabled={uploading || Boolean(familyId)}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="resume">Resume</option>
              <option value="cover_letter">Cover letter</option>
            </select>
          </label>
          <label>
            Label
            <input
              aria-label="Document label"
              maxLength={150}
              value={label}
              disabled={uploading}
              placeholder={kind === 'resume' ? 'Backend resume' : 'General cover letter'}
              onChange={(event) => setLabel(event.target.value)}
            />
          </label>
          <label className="document-file-field">
            File
            <input
              aria-label="Document file"
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              disabled={uploading}
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <div className="document-actions">
            <button className="btn btn-blue" type="submit" disabled={uploading}>
              {uploading ? 'Uploading…' : familyId ? 'Upload new version' : 'Upload document'}
            </button>
            {uploading && (
              <button
                className="btn btn-grey"
                type="button"
                onClick={() => abortRef.current?.abort()}
              >
                Cancel upload
              </button>
            )}
          </div>
          {uploading && (
            <div className="document-progress" role="status" aria-live="polite">
              <progress value={progress} max="100" aria-label="Upload progress" />
              <span>{progress}%</span>
            </div>
          )}
        </form>
      </section>

      <section className="document-quota-card" aria-label="Document storage quota">
        <div>
          <strong>Storage</strong>
          <span>{formatBytes(quota.used_bytes)} of {formatBytes(quota.limit_bytes)}</span>
        </div>
        <progress value={quotaPercent} max="100" aria-label="Storage quota used" />
        <span>{quotaPercent}% used</span>
      </section>

      {error && <p className="error-msg" role="alert">{error}</p>}

      {referenceConflict && (
        <section className="document-conflict-card" role="alert" data-testid="document-delete-conflict">
          <h3>Detach before deleting</h3>
          <p>
            <strong>{referenceConflict.document.label} v{referenceConflict.document.version_number}</strong>{' '}
            is still part of application history. Deleting it now would break that record.
          </p>
          {referenceConflict.applications.length > 0 && (
            <ul>
              {referenceConflict.applications.map((application) => (
                <li key={`${application.track_id}-${application.usage}`}>
                  <Link to={`/applications?track_id=${application.track_id}`}>
                    {application.company || 'Unknown company'} · {application.title || 'Unknown role'}
                  </Link>{' '}
                  <span className={`document-usage document-usage-${application.usage}`}>
                    {application.usage === 'used' ? 'Used' : 'Reference'}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <button className="btn btn-grey btn-sm" type="button" onClick={() => setReferenceConflict(null)}>
            Dismiss
          </button>
        </section>
      )}

      <section aria-labelledby="document-library-heading">
        <div className="document-panel-header">
          <div>
            <h3 id="document-library-heading">Library</h3>
            <p className="muted-text">
              Versions are immutable. “New version” creates another version in the same family.
            </p>
          </div>
          <button className="btn btn-grey btn-sm" type="button" disabled={loading} onClick={refresh}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        {loading ? (
          <p role="status">Loading document library…</p>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <p>No documents yet.</p>
            <p>Upload a resume or cover letter to start an immutable version history.</p>
          </div>
        ) : (
          <div className="document-library-list" data-testid="document-library">
            {documents.map((document) => {
              const details = applicationDetails[document.id]
              const latest = readyFamilies.find(
                (item) => item.document_family_id === document.document_family_id
              )
              const isLatest = latest?.id === document.id
              return (
                <article className="document-card" key={document.id} data-testid={`document-${document.id}`}>
                  <div className="document-card-main">
                    <div>
                      <div className="document-title-line">
                        <strong>{document.label}</strong>
                        <span className="document-version-badge">v{document.version_number}</span>
                        <span>{kindLabel(document.kind)}</span>
                        {isLatest && <span className="document-latest-badge">Latest</span>}
                      </div>
                      <div className="document-meta">
                        <span>{document.original_filename}</span>
                        <span>{formatBytes(document.size_bytes)}</span>
                        <span>{formatDate(document.created_at)}</span>
                        <span>SHA-256 {document.sha256.slice(0, 12)}…</span>
                      </div>
                      {document.availability === 'missing' && (
                        <p className="error-msg" role="status">
                          Metadata is intact, but private file bytes are missing and require recovery. No other version will be substituted.
                        </p>
                      )}
                      {document.state !== 'ready' && (
                        <p className="muted-text">State: {document.state}. This version cannot be attached.</p>
                      )}
                    </div>
                    <div className="document-actions">
                      <button
                        className="btn btn-grey btn-sm"
                        type="button"
                        disabled={downloadPendingId === document.id || document.availability !== 'ready'}
                        onClick={() => download(document)}
                      >
                        {downloadPendingId === document.id ? 'Downloading…' : 'Download'}
                      </button>
                      <button
                        className="btn btn-grey btn-sm"
                        type="button"
                        disabled={uploading}
                        onClick={() => startNewVersion(document)}
                      >
                        New version
                      </button>
                      <button
                        className="btn btn-grey btn-sm"
                        type="button"
                        onClick={() => showApplications(document)}
                      >
                        Linked applications
                      </button>
                      <button
                        className="btn btn-red btn-sm"
                        type="button"
                        disabled={deletePendingId === document.id}
                        onClick={() => remove(document)}
                      >
                        {deletePendingId === document.id ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>

                  {details && (
                    <div className="document-applications" data-testid={`document-applications-${document.id}`}>
                      <strong>Linked applications</strong>
                      {details.items?.length ? (
                        <ul>
                          {details.items.map((application) => (
                            <li key={`${application.track_id}-${application.usage}`}>
                              <Link to={`/applications?track_id=${application.track_id}`}>
                                {application.company || 'Unknown company'} · {application.title || 'Unknown role'}
                              </Link>{' '}
                              <span className={`document-usage document-usage-${application.usage}`}>
                                {application.usage === 'used' ? 'Used' : 'Reference'}
                              </span>{' '}
                              <span>{application.status}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted-text">Not linked to any application.</p>
                      )}
                      {details.has_next && (
                        <p className="muted-text">
                          More than 50 links exist. This view intentionally shows a bounded first page.
                        </p>
                      )}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
