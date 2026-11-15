# AL Phase 3, Manual Application Recording Contract

Status: **Approved implementation design for AL-13–AL-17**. Drafted November 15, 2026. This documents *implementation intent*, not deployment evidence.

## Product boundary

A signed-in user confirms that they actually submitted an external job application. JobGrid records the fact and timestamp. It never opens the URL, captures a visit, submits to an ATS, or creates a CSV row. Manual capture remains a different feature.

## Architecture decision (AL-13)

**A, chosen:** a separate `POST /crm/applications` route delegating to a domain service, a new owner-scoped `manual_application_receipts` table, and existing `JobTrack`, canonical identity and lifecycle writer. Receipt data is operational and not a second application source of truth. It is pruned after 30 days; durable application history, events and backups remain unchanged. This requires one *additive* Alembic migration. A deleted track invalidates its replay receipt rather than recreating it.

**B, rejected:** treating `BrowserApplyReceipt` or `CaptureRequest` as generic idempotency storage. They have distinct domain and backup contracts. Also rejected: relying only on `first_applied` event ID for idempotency, because it cannot safely distinguish conflicting payload retries or preserve an identical response after a later status change.

## API contract

`POST /crm/applications` requires authenticated session, `Idempotency-Key: <canonical UUID>` and JSON with exactly `url`, `company`, `title`, `applied_at`, `confirmed: true`, optional `notes`, `follow_up_at`, `acknowledge_possible_match: true`. Field limits: URL 2048, company/title 300, notes 20,000. Timestamp fields must have an explicit timezone offset or Z; date-only input is deliberately rejected by this endpoint to avoid silently changing an intended day. `applied_at` must not be in the future. `follow_up_at` may be absent. The route never accepts user IDs. All fields are strict, and unknown properties are rejected.

201 response for a new track, 200 for an existing *same exact URL*, previously unsubmitted track. The response contains `application_id`, `created`, `replayed`, `applied_at`, and `status`; success is emitted only after commit. Replay of identical key+payload returns the original persisted response, with `replayed: true`, even if stage later changes. Changed payload with the same key returns 409. Receipt race and unique-key conflicts return 409 with retry guidance, not false success.

Duplicate policy: An exact already-applied record, or any canonical-equivalent *different* URL record, returns 409 with safe owner-local candidate summary; the user must review the existing application instead of silently creating or overwriting one. Same-company/title-only previous applications are weaker `possible` matches. They require an explicit `acknowledge_possible_match` flag or produce 409; when acknowledged, an independent URL may be recorded. The preflight `POST /crm/application-matches` is advisory, and the server rechecks immediately before commit. Never infer applications from CSV, captures or visits.

Any existing exact-URL, unapplied track retains current stage unless it is `opened`; it retains prior non-empty company/title/notes and follow-up fields. New application has `opened_at = NULL`, `open_count = 0`, `csv_row_id = NULL`. The original applied date is the caller's explicitly confirmed instant. Lifecycle first-applied evidence and track changes commit once. Nothing is silently backdated or rewritten. Importing unknown-date history or repeated submissions is AL-19+.

## Errors, security and observability

400 for missing/malformed idempotency key, 422 for missing or unsafe validation fields, 409 for duplicate, ambiguous match, or changed payload, and 500 for unexpected DB errors. Use structured `detail: {code,fields:[{field,message}]}` plus safe `matches` where appropriate; never echo credentials, private URL details or notes in logs. Session owner is locked before checking receipts and identity. SQLite requests acquire a writer reservation before the check; PostgreSQL uses row locks plus unique constraints. Receipt and application writes share one transaction. No new provider or job worker.

The browser UI keeps one UUID per unchanged draft and shows a review step, match context, and a distinct unknown-result state for a network/server ambiguity. A deliberate retry preserves the same UUID/payload. Editing a draft generates a fresh UUID. Confirmed success navigates to the saved application. A 409 never silently merges. Release requires focused backend tests, browser regression, migration parity, all applicable CI, and separate staging approval.

## Files and rollback

Model/migration: `backend/app/models.py`, `backend/alembic/versions/022_manual_application_receipts.py`. Service: `backend/app/services/manual_applications.py`. Router: `backend/app/routers/manual_applications.py`, registered in `backend/app/main.py`. UI/client: `frontend/src/pages/AddApplication.jsx`, `frontend/src/pages/Applications.jsx`, `frontend/src/App.jsx`, `frontend/src/api/client.js`. Tests: `backend/tests/test_manual_applications.py`, `frontend/tests/manual-applications.spec.ts`, schema parity tests. Docs: `docs/JOBGRID_BUILD_GUIDE.md`, `development.md`.

Rollback: disable/rollback route and UI code while **retaining** the additive receipt table and durable application history. Do not downgrade the database or delete first-applied facts as normal rollback. Monitor 4xx conflicts, 5xx, receipt replay, and duplicate failures without recording sensitive payloads.
