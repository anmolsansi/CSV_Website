import { useCallback, useEffect, useMemo, useState } from 'react'
import { formatApiError } from '../api/client'
import { contactApi } from '../api/contacts'
import { useToast } from '../App'

const ROLES = ['recruiter', 'referrer', 'interviewer', 'other']

const EMPTY_CONTACT = {
  name: '',
  email: '',
  profile_url: '',
  company_display: '',
  notes: '',
}

function compactPayload(values) {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value === '' ? null : value]))
}

function normalize(value) {
  return String(value || '').trim().toLowerCase()
}

function findReusableContact(contacts, draft) {
  const email = normalize(draft.email)
  if (email) {
    const emailMatch = contacts.find((contact) => normalize(contact.email) === email)
    if (emailMatch) return emailMatch
  }
  const name = normalize(draft.name)
  const company = normalize(draft.company_display)
  if (!name) return null
  return contacts.find((contact) => (
    normalize(contact.name) === name
    && normalize(contact.company_display) === company
  )) || null
}

export default function ApplicationPeople({ application }) {
  const toast = useToast()
  const [linked, setLinked] = useState([])
  const [contacts, setContacts] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [role, setRole] = useState('recruiter')
  const [referralSource, setReferralSource] = useState('')
  const [draft, setDraft] = useState(EMPTY_CONTACT)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [applicationContacts, availableContacts] = await Promise.all([
        contactApi.getApplicationContacts(application.id),
        contactApi.listContacts(),
      ])
      setLinked(applicationContacts.contacts || [])
      setContacts(availableContacts.contacts || [])
    } catch (requestError) {
      setError(formatApiError(requestError, 'Could not load people for this application.').message)
    } finally {
      setLoading(false)
    }
  }, [application.id])

  useEffect(() => { refresh() }, [refresh])

  const selected = useMemo(
    () => contacts.find((contact) => String(contact.id) === String(selectedId)) || null,
    [contacts, selectedId]
  )

  const linkContact = async (contactId, { reused = false } = {}) => {
    await contactApi.linkApplicationContact(application.id, {
      contact_id: contactId,
      role,
      referral_source: referralSource || null,
    })
    setSelectedId('')
    setReferralSource('')
    toast(reused ? 'Existing person reused and linked.' : 'Person linked to application.', 'success')
    await refresh()
  }

  const linkExisting = async (event) => {
    event.preventDefault()
    if (!selected || pending) return
    setPending(true)
    setError('')
    try {
      await linkContact(selected.id)
    } catch (requestError) {
      const message = formatApiError(requestError, 'Could not link this person.').message
      setError(message)
      toast(message, 'error')
    } finally {
      setPending(false)
    }
  }

  const createAndLink = async (event) => {
    event.preventDefault()
    if (!draft.name.trim() || pending) return
    setPending(true)
    setError('')
    try {
      const reusable = findReusableContact(contacts, draft)
      if (reusable) {
        await linkContact(reusable.id, { reused: true })
        setDraft(EMPTY_CONTACT)
        return
      }

      const contact = await contactApi.createContact(compactPayload({ ...draft, name: draft.name.trim() }))
      await linkContact(contact.id)
      setDraft(EMPTY_CONTACT)
      toast('Person created and linked.', 'success')
    } catch (requestError) {
      // Keep the draft intact so a network or validation error never destroys private notes.
      const message = formatApiError(requestError, 'Could not create and link this person. Your draft was kept.').message
      setError(message)
      toast(message, 'error')
    } finally {
      setPending(false)
    }
  }

  const unlink = async (associationId) => {
    if (pending) return
    setPending(true)
    setError('')
    try {
      await contactApi.unlinkApplicationContact(application.id, associationId)
      toast('Person unlinked from this application. The contact remains in your private address book.', 'success')
      await refresh()
    } catch (requestError) {
      const message = formatApiError(requestError, 'Could not unlink this person.').message
      setError(message)
      toast(message, 'error')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="document-panel" aria-label="Application people" data-testid="application-people">
      <div className="document-panel-header">
        <div>
          <h3>People</h3>
          <p className="muted-text">Private recruiter, referrer, and interviewer context. Saving an email does not send anything.</p>
        </div>
        <button type="button" className="btn btn-grey btn-sm" onClick={refresh} disabled={pending}>Refresh</button>
      </div>

      {loading ? <p role="status">Loading people…</p> : (
        <>
          {linked.length === 0 ? (
            <p className="muted-text">No people are linked to this application yet.</p>
          ) : (
            <div className="document-link-list">
              {linked.map((item) => (
                <div className="document-link-row" key={item.id} data-testid={`application-person-${item.id}`}>
                  <div>
                    <strong>{item.contact?.name || 'Deleted contact'}</strong>
                    <div className="document-meta">
                      <span>{item.role}</span>
                      {item.contact?.company_display && <span>{item.contact.company_display}</span>}
                      {item.contact?.email && <span>{item.contact.email}</span>}
                      {item.referral_source && <span>Source: {item.referral_source}</span>}
                    </div>
                    {item.contact?.notes && <p className="muted-text">{item.contact.notes}</p>}
                    {item.contact?.profile_url && (
                      <a href={item.contact.profile_url} target="_blank" rel="noreferrer">Open profile</a>
                    )}
                  </div>
                  <button type="button" className="btn btn-grey btn-sm" disabled={pending} onClick={() => unlink(item.id)}>Unlink</button>
                </div>
              ))}
            </div>
          )}

          <form className="document-attach-form" onSubmit={linkExisting}>
            <label>
              Reuse saved person
              <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={pending}>
                <option value="">Choose a contact</option>
                {contacts.map((contact) => (
                  <option key={contact.id} value={contact.id}>{contact.name}{contact.company_display ? ` · ${contact.company_display}` : ''}</option>
                ))}
              </select>
            </label>
            <label>
              Role
              <select value={role} onChange={(event) => setRole(event.target.value)} disabled={pending}>
                {ROLES.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label>
              Referral source
              <input value={referralSource} maxLength={300} onChange={(event) => setReferralSource(event.target.value)} placeholder="Optional source" disabled={pending} />
            </label>
            <button className="btn btn-blue" type="submit" disabled={!selected || pending}>{pending ? 'Saving…' : 'Link saved person'}</button>
          </form>

          <details>
            <summary>Create a new person</summary>
            <p className="muted-text">If the email, or the same name and company, already exists, JobGrid reuses that contact instead of creating a duplicate.</p>
            <form className="document-attach-form" onSubmit={createAndLink}>
              <label>Name<input required maxLength={200} value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label>Email<input type="email" maxLength={320} value={draft.email} onChange={(event) => setDraft((current) => ({ ...current, email: event.target.value }))} placeholder="Optional" /></label>
              <label>Company<input maxLength={300} value={draft.company_display} onChange={(event) => setDraft((current) => ({ ...current, company_display: event.target.value }))} placeholder="Optional" /></label>
              <label>Profile URL<input type="url" maxLength={2048} value={draft.profile_url} onChange={(event) => setDraft((current) => ({ ...current, profile_url: event.target.value }))} placeholder="https://…" /></label>
              <label>Private notes<textarea maxLength={20000} value={draft.notes} onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))} /></label>
              <button className="btn btn-blue" type="submit" disabled={!draft.name.trim() || pending}>{pending ? 'Saving…' : 'Create and link'}</button>
            </form>
          </details>
        </>
      )}

      {error && <p className="error-msg" role="alert">{error}</p>}
    </section>
  )
}