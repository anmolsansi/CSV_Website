

## F8 recruiter and interview workspace, JG-053 through JG-055

JG-053 through JG-055 add a private, owner-scoped people and interview workspace to durable application memory. The feature is additive. Existing application, Today, reminder, document, evidence, and availability behavior remains authoritative for its existing source types. JG-056 remains the separate full F8 privacy, scheduling, recovery, and mixed-source acceptance ticket.

### Persistence and migration

Alembic revision `016_contacts_interviews` follows revision `015` and creates four owner-scoped stores:

- `contacts` stores the private person record, optional email, profile URL, company display label, notes, optimistic `version`, timestamps, and a soft-delete marker.
- `application_contacts` links one owned contact to one owned application with `recruiter`, `referrer`, `interviewer`, or `other` role plus optional referral source. The owner/application/contact/role tuple is unique.
- `interviews` stores the application, optional contact, UTC start/end instants, IANA display timezone, kind, location or meeting URL, status, round label, private notes, private preparation notes, timestamps, and optimistic `version`.
- `mutation_receipts` stores bounded owner-scoped UUID replay identity and payload hashes for idempotent F8 creates. Receipts are operational replay state and are pruned after 30 days.

Database foreign keys and service queries both enforce ownership. Cross-account contact/application/interview references return the same not-found shape as missing data. Contact deletion keeps a redacted historical marker so an interview does not silently lose the fact that a person was associated with it.

### Contacts and interviews API

The authenticated API surface is:

```text
GET    /crm/contacts
POST   /crm/contacts
PATCH  /crm/contacts/{contact_id}
DELETE /crm/contacts/{contact_id}
GET    /crm/tracks/{track_id}/contacts
POST   /crm/tracks/{track_id}/contacts
DELETE /crm/tracks/{track_id}/contacts/{association_id}
GET    /crm/tracks/{track_id}/interviews
POST   /crm/tracks/{track_id}/interviews
PATCH  /crm/interviews/{interview_id}
GET    /crm/interviews/{interview_id}/calendar.ics
```

Contact and interview creates use `Idempotency-Key: <UUID>`. An exact replay returns the original result. Reusing a key with different input returns HTTP 409. Edits use the current positive entity version. Stale edits return HTTP 409 without overwriting the stored record. Interview end must be after start and duration cannot exceed 24 hours. Stored timestamps are UTC while the validated IANA timezone remains available for display.

Overlap detection is advisory. Saving a scheduled interview returns IDs of other scheduled interviews whose time windows overlap, but does not reject the save.

Changing or cancelling an interview reconciles unsent reminder state tied to that application without rewriting sent history. Cancelling an interview also removes its derived Today preparation action.

### Calendar export privacy

`GET /crm/interviews/{interview_id}/calendar.ics` requires the authenticated owner. Foreign and missing IDs both return 404.

The generated file contains one RFC5545 `VEVENT` with a stable JobGrid UID, UTC start/end, optimistic-version-derived `SEQUENCE`, status, scheduling fields, and escaped/folded text. CR/LF input is escaped before output so user-controlled text cannot inject a second event or property. Private interview notes, preparation notes, contact email, and referral notes are never written to the calendar file.

The UI labels the action **Download calendar event** and confirms **No invitation was sent**. JobGrid does not claim to send mail or create an event in an external calendar provider.

### Portable backup and recovery

Portable v2 export keeps the exact frozen v2 envelope for accounts with no F8 records. When F8 private data exists, export adds a checksummed `f8_private` extension. Contacts receive backup-local references. Application-contact links and interviews reference backup-local contact and application identities rather than database IDs. Restore resolves those references into the destination account and records replay identity so repeated restore does not duplicate private records. Verify-only mode validates the F8 reference graph without mutating it.

Conflicting or unresolved F8 references fail closed. Operational mutation receipts are not exported as ordinary user content.

### Application, company, and Today UI

`ApplicationPeople`, `ApplicationInterviews`, and `ApplicationWorkspace` provide reusable loading, empty, success, pending, error, conflict, and draft-preservation states. All workspace calls use the shared authenticated frontend API client.

People can be reused from the private address book or created and linked from an application. The same workspace appears in expanded Applications details and Company History role details, so Company History does not create a second contact/interview state model.

Interview scheduling shows the selected interview timezone and the account timezone preview. Existing interviews show overlap warnings, associated people, preparation notes, and explicit cancellation. Calendar download is an authenticated blob download.

`GET /crm/today` derives same-day future scheduled interview preparation actions with stable identity:

```text
interview:{interview_id}:{starts_at_utc}
```

The action reuses `WorkItemOverride` snooze state, provides Snooze and exact application navigation, and deliberately does not expose a generic Complete button because completing preparation must not mutate interview status. Cancelling or rescheduling the source interview invalidates the old derived identity.

### Verification

Focused backend checks:

```sh
cd backend
python -m pytest tests/test_contact_backup_contract.py tests/test_contacts_interviews.py tests/test_contacts_api.py tests/test_calendar_export.py tests/test_interview_today.py -q
python -m compileall app
python -m alembic upgrade head
```

Focused frontend checks:

```sh
cd frontend
npm ci
npm run build
npx playwright test tests/contacts-interviews.spec.ts --project=chromium
```

`frontend/tests/contacts-interviews.spec.ts` exercises the real browser/backend flow for linked people, private contact display, overlap warnings, timezone display, authenticated calendar download wording, Company History reuse, Today interview preparation, and exact application navigation. It restores the account timezone after the test so existing timezone-dependent acceptance tests remain isolated.

The repository GitHub Actions workflow is the completion gate. It applies PostgreSQL migrations, runs the full backend suite and compile checks, builds the production frontend, and runs the complete Chromium collection. JG-053, JG-054, and JG-055 must not be marked complete until that workflow is green for the final implementation head.

### Rollback

Prefer code rollback while leaving additive revision 016 and private F8 rows in place. Older application code can ignore the new tables while preserving user data for a later forward deploy.

If F8 must be disabled operationally, hide the contacts/interviews entry points first. Do not delete contact, interview, backup, sent reminder, or historical application data as part of a routine rollback. Downgrade revision 016 only after F8 traffic has stopped and private records that must be retained have been preserved. A rollback must never move private notes into logs, calendar output, public URLs, or another less-protected storage path.
