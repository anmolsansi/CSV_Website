# JobGrid Phase 3: Manual Application Recording

This is the current implementation guide for AL-13–AL-17 on the Phase 3 branch. It complements [the JobGrid build guide](JOBGRID_BUILD_GUIDE.md) and [the contract/ADR](AL_PHASE3_MANUAL_APPLICATION_CONTRACT.md).

## What and why

**Add application** records a real external job application without a CSV row. It is distinct from **Capture job**, which saves a link without applying, and from browser extension confirmation. Existing status changes and historical Ever Applied exports continue using `JobTrack.applied_at` and the `first_applied` lifecycle record. No URL is opened or submitted by JobGrid.

## User flow

1. Visit **Applications > Add application**. Use your actual job URL, company, title, and the date/time you submitted. Optional notes and follow-up are supported.
2. The page checks owner-scoped prior submissions. An exact or canonical match sends you to existing history. A company/title-only match requires checking a separate-submission acknowledgement.
3. Click **Review application details** and verify the frozen URL, employer, role, and submission time. Click **Confirm I applied and save** only after actually submitting externally.
4. The server returns a persisted application ID. The success link opens that application in **Ever Applied**, including its timeline. Saved/opened jobs do not become applied unless explicitly confirmed.
5. When a network failure or HTTP 5xx produces an unknown outcome, do **not** assume failure or success. Check **My Applications** and only then click **Retry same save**. That retry sends the same UUID and payload. Changing any field starts a new intent.

## API

`POST /crm/applications` uses the existing authenticated cookie, a canonical UUID `Idempotency-Key`, and strict JSON:

```json
{
  "url": "https://jobs.example.com/roles/123",
  "company": "Example Company",
  "title": "Software Engineer",
  "applied_at": "2026-11-12T20:30:00+05:30",
  "confirmed": true,
  "notes": "Applied through the company site",
  "follow_up_at": "2026-11-19T20:30:00+05:30"
}
```

Optional additional boolean `acknowledge_possible_match: true` is required only when a similar previously applied company+title is identified. Required fields are exact, and unexpected fields are rejected. Job URLs must be public HTTP(S) links without embedded credentials or credential-like query keys. Date/time values require an explicit offset or Z, and cannot be date-only. `applied_at` must not be in the future. Company/title are at most 300 chars, notes 20,000, URL 2,048. Missing key is 400, validation errors 422, and duplicates/conflicting retries 409. Duplicate conflicts contain only owner-scoped summaries.

201 means a new `JobTrack`. 200 means a previous exact-URL tracked-but-unapplied record was explicitly confirmed, or an identical receipt was replayed. The body supplies `application_id`, `created`, `replayed`, `applied_at`, and `status`. A replay after later interview status changes returns the frozen original receipt response and does not reset the stage.

## Data and transaction behavior

- `backend/app/services/manual_applications.py` owns strict validation, exact/canonical lookups, possible matches, first-date lifecycle mutation, notes/follow-up preservation, owner row lock, and idempotency.
- `backend/app/routers/manual_applications.py` uses the standard session cookie authentication and commits the application, lifecycle facts, and receipt as a single transaction. It never takes a client-selected account ID.
- `backend/app/models.py` adds `ManualApplicationReceipt`. Its `user_id + request_key` is unique and its payload digest protects against changed retries. Only bounded operational receipts are retained for 30 days. Receipt responses exclude raw URLs/notes.
- `backend/alembic/versions/022_manual_application_receipts.py` is additive after revision 021. On PostgreSQL, it denies anonymous/authenticated Data API access. Operational receipts are not exported as portable user data. The application and lifecycle records remain in the existing backup/restore graph.
- Exact already-applied submissions and canonical URL variants are blocked with no changes. Exact URLs that are tracked but not applied can be reused without overwriting existing company/title/notes/opening evidence. Only explicit dated application evidence is created.
- `frontend/src/pages/AddApplication.jsx` and `frontend/src/api/client.js` own the form and HTTP request. `frontend/src/pages/Applications.jsx` links the workflow, and `frontend/src/App.jsx` registers `/applications/new`.

## Testing and local validation

Use only disposable development/test databases:

```bash
cd backend
pytest -q tests/test_manual_applications.py tests/test_schema_parity.py
python -m compileall -q app
cd ../frontend
npm ci
npm run build
npx playwright test tests/manual-applications.spec.ts --project=chromium
```

Run the full required PostgreSQL/SQLite backend and browser CI matrix before merge. Inspect `backend/tests/test_manual_applications.py` for owner isolation, no CSV/visit side effects, date conversion, staged-status preservation, exact/canonical/possible match conflicts, replay, changed payload, invalid dates and injection/unsafe URLs, and injected rollback. `frontend/tests/manual-applications.spec.ts` covers the explicit review, lifetime-save link, existing-match warning, invalid date, and stable retry UUID.

## Operating, recovery and rollback

The endpoint emits minimal outcome, replay and duration logs without raw job URLs, notes or credentials. Monitor 409 conflicts and failed writes after release. A failed DB commit leaves no saved receipt or application. If the response is lost, users must check history before retrying. A previous receipt may expire after 30 days, but the durable application remains and duplicate checks prevent a new first-applied event.

Rollback the route and UI if errors occur, leaving the additive table and all application data in place. **Never run a destructive downgrade on live databases** and never purge the `first_applied` lifecycle ledger to correct metrics. This branch has not been staged, deployed or smoke-tested against a real account. Those steps require separate authorization.
