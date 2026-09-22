import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatApiError } from '../api/client'
import { useToast } from '../App'

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

function versionLabel(document) {
  return `${document.label} · v${document.version_number} · ${document.kind === 'cover_letter' ? 'Cover letter' : 'Resume'}`
}

async function downloadDocument(document) {
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

export default function ApplicationDocuments({ application }) {
  const toast = useToast()
  const [links, setLinks] = useState([])
  const [library, setLibrary] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [usage, setUsage] = useState('used')
  const [confirmCorrection, setConfirmCorrection] = useState(false)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [trackDocuments, documents] = await Promise.all([
        api.getTrackDocuments(application.id),
        api.getDocuments(),
      ])
      setLinks(trackDocuments.items || [])
      setLibrary((documents.items || []).filter(
        (item) => item.state === 'ready' && item.availability === 'ready'
      ))
    } catch (requestError) {
      setError(formatApiError(
        requestError,
        'Could not load application documents. Please retry.'
      ).message)
    } finally {
      setLoading(false)
    }
  }, [application.id])

  useEffect(() => {
    refresh()
  }, [refresh])

  const selected = useMemo(
    () => library.find((item) => item.id === selectedId) || null,
    [library, selectedId]
  )
  const currentUsed = useMemo(() => {
    if (!selected) return null
    return links.find(
      (item) => item.usage === 'used' && item.kind === selected.kind
    ) || null
  }, [links, selected])
  const selectedLink = useMemo(
    () => links.find((item) => item.document.id === selectedId) || null,
    [links, selectedId]
  )
  const needsCorrection = Boolean(
    usage === 'used'
    && currentUsed
    && currentUsed.document.id !== selectedId
  )

  useEffect(() => {
    setConfirmCorrection(false)
  }, [selectedId, usage])

  const attach = async (event) => {
    event.preventDefault()
    if (!selected || pending || selectedLink) return
    if (needsCorrection && !confirmCorrection) return
    setPending(true)
    setError('')
    try {
      await api.attachTrackDocument(application.id, {
        document_version_id: selected.id,
        usage,
        ...(needsCorrection
          ? { replace_document_version_id: currentUsed.document.id }
          : {}),
      })
      toast(
        needsCorrection
          ? 'Recorded the corrected Used document version.'
          : 'Document attached to application.',
        'success'
      )
      setSelectedId('')
      setConfirmCorrection(false)
      await refresh()
    } catch (requestError) {
      const formatted = formatApiError(
        requestError,
        'Could not attach this document. Please retry.'
      )
      setError(formatted.message)
      toast(formatted.message, 'error')
    } finally {
      setPending(false)
    }
  }

  const detach = async (link) => {
    if (pending) return
    setPending(true)
    setError('')
    try {
      await api.detachTrackDocument(application.id, link.document.id)
      toast('Document detached. The immutable library version was not deleted.', 'success')
      await refresh()
    } catch (requestError) {
      const formatted = formatApiError(
        requestError,
        'Could not detach this document. Please retry.'
      )
      setError(formatted.message)
      toast(formatted.message, 'error')
    } finally {
      setPending(false)
    }
  }

  return (
    <section
      className="document-panel"
      aria-label="Application documents"
      data-testid="application-documents"
    >
      <div className="document-panel-header">
        <div>
          <h3>Application documents</h3>
          <p className="muted-text">
            Record the exact immutable resume or cover letter used for this application.
          </p>
        </div>
        <Link
          className="btn btn-grey btn-sm"
          to={`/documents?track_id=${application.id}`}
        >
          Open document library
        </Link>
      </div>

      {loading ? (
        <p role="status">Loading documents…</p>
      ) : (
        <>
          <div className="document-link-list">
            {links.length === 0 ? (
              <p className="muted-text">No documents are attached to this application yet.</p>
            ) : links.map((link) => (
              <div
                className="document-link-row"
                key={link.id}
                data-testid={`application-document-${link.document.id}`}
              >
                <div>
                  <strong>{versionLabel(link.document)}</strong>
                  <div className="document-meta">
                    <span className={`document-usage document-usage-${link.usage}`}>
                      {link.usage === 'used' ? 'Used' : 'Reference'}
                    </span>
                    <span>{formatBytes(link.document.size_bytes)}</span>
                    {link.document.availability === 'missing' && (
                      <span className="error-msg">Private file bytes require recovery.</span>
                    )}
                  </div>
                </div>
                <div className="document-actions">
                  <button
                    type="button"
                    className="btn btn-grey btn-sm"
                    disabled={pending || link.document.availability !== 'ready'}
                    onClick={() => downloadDocument(link.document).catch((requestError) => {
                      const message = formatApiError(
                        requestError,
                        'Could not download this document.'
                      ).message
                      setError(message)
                      toast(message, 'error')
                    })}
                  >
                    Download
                  </button>
                  <button
                    type="button"
                    className="btn btn-grey btn-sm"
                    disabled={pending}
                    onClick={() => detach(link)}
                  >
                    Detach
                  </button>
                </div>
              </div>
            ))}
          </div>

          <form className="document-attach-form" onSubmit={attach}>
            <label>
              Document version
              <select
                aria-label="Document version"
                value={selectedId}
                onChange={(event) => setSelectedId(event.target.value)}
                disabled={pending}
              >
                <option value="">Choose a ready version</option>
                {library.map((document) => (
                  <option key={document.id} value={document.id}>
                    {versionLabel(document)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Usage
              <select
                aria-label="Document usage"
                value={usage}
                onChange={(event) => setUsage(event.target.value)}
                disabled={pending}
              >
                <option value="used">Used</option>
                <option value="reference">Reference</option>
              </select>
            </label>

            {selectedLink && (
              <p className="muted-text" role="status">
                This exact version is already attached as {selectedLink.usage === 'used' ? 'Used' : 'Reference'}.
              </p>
            )}

            {needsCorrection && (
              <div className="document-correction-warning" role="alert">
                <p>
                  <strong>A different {selected.kind === 'resume' ? 'resume' : 'cover letter'} is already recorded as Used.</strong>{' '}
                  Replacing it is a correction to application history. The earlier immutable version stays in the library.
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={confirmCorrection}
                    onChange={(event) => setConfirmCorrection(event.target.checked)}
                  />
                  I confirm this corrects the recorded Used version.
                </label>
              </div>
            )}

            <button
              className="btn btn-blue"
              type="submit"
              disabled={
                pending
                || !selected
                || Boolean(selectedLink)
                || (needsCorrection && !confirmCorrection)
              }
            >
              {pending ? 'Saving…' : needsCorrection ? 'Correct Used version' : 'Attach document'}
            </button>
          </form>
        </>
      )}

      {error && <p className="error-msg" role="alert">{error}</p>}
    </section>
  )
}
