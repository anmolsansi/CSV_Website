# Repo Context — JobGrid — 2026-09-28

Baseline lineage: `2c485a2ba70edaa419ccea5cbf6f69ad7174b179` on `main` after PR #161, extended by C-04 in PR #162, C-05 in PR #163, C-06 in PR #167, C-07 in PR #169, and C-08 in PR #171.

This file is the compact repository context for implementation agents. Read `development.md` for the full completion plan, while honoring newer accepted architecture decisions recorded in focused C-package evidence. Historical planning text can describe an earlier infrastructure choice; the user-selected C-09 zero-dollar constraint is recorded in `docs/C09_STAGING_OPERATIONS.md` and PR #173 and supersedes the earlier paid Render-disk assumption for C-09 implementation.

## Stack and runtime

- Frontend: React 18, Vite 5, React Router 7, Axios, TanStack Table, Playwright.
- Backend: Python 3.12, FastAPI 0.111, SQLAlchemy 2.0, Alembic, APScheduler.
- Database: PostgreSQL is the deployment target. SQLite is also an explicitly supported/tested runtime path.
- Auth: server-side session cookies. Google, Microsoft, and Apple OAuth configuration lives in `backend/app/config.py`. `TEST_AUTH` exists only for test/dev flows and must be false in production.
- Observability: FastAPI metrics middleware plus optional Sentry.
- Main migration head: `018_bulk_undo_foundation.py`.
- Production document bytes: private S3-compatible object storage through `backend/app/services/document_storage.py`; current C-09 target is Supabase Storage Free. Local/dev tests may still use the filesystem adapter.

Pinned dependencies live in `backend/requirements.txt` and `frontend/package-lock.json`.

## Application boundaries

`backend/app/main.py` is the composition root. It validates production configuration before startup, applies Alembic migrations automatically for non-SQLite databases, registers routers, wires the later Today and backup extensions, and starts maintenance/reminder schedulers only when their feature flags are enabled.

Backend routes are split across `backend/app/routers/`:

- `rows.py` and `upload.py`: CSV ingestion, browsing, visit state, filtering, row-level operations.
- `crm.py`: durable application tracking, companies, analytics, saved views, pipeline, user goals/preferences, and related CRM behavior.
- `today.py`: Today queue API and work-item mutations.
- `reminders.py`: reminder preferences, delivery history, planning and user-facing controls.
- `documents.py`: private immutable document versions and application selections.
- `evidence.py`: application evidence and merged timeline behavior.
- `capture.py`: manual/quick job capture with replay identity and duplicate context.
- `availability.py`: deadlines, manual freshness, and guarded availability checks.
- `company_aliases.py`: conservative job/company identity and aliases.
- `contacts.py`: contacts, application-contact links, interviews, and calendar export support.
- `imports.py`: external import preview, reusable mappings, reconciliation, and commit.
- `bulk_actions.py`: transactional bulk mutation, archive, undo status, and conflict handling.
- `backup.py`: portable backup export, preview, restore, JSON/ZIP handling.
- `auth_router.py` and `email.py`: authentication and supported email flows.

Important service modules live in `backend/app/services/`. Do not move business logic back into route handlers when an owning service already exists. Major service boundaries include `row_queries.py`, `validation.py`, `lifecycle.py`, `today.py`, `today_f8.py`, `reminders.py`, `retention.py`, `job_identity.py`, `evidence.py`, `documents.py`, `document_storage.py`, `capture.py`, `availability.py`, `contacts.py`, `imports.py`, `bulk_actions.py`, `undo_foundation.py`, and the backup services.

## Frontend structure

`frontend/src/App.jsx` owns authentication state and the authenticated route shell. Current authenticated routes are:

- `/` dashboard
- `/archive`
- `/today`
- `/applications`
- `/documents`
- `/analytics`
- `/pipeline`
- `/sessions`
- `/saved-views`
- `/applypilot`
- `/duplicates`
- `/companies`
- `/capture`
- `/import`

`frontend/src/api/client.js` is the primary Axios client. Contacts and import flows also have focused API modules under `frontend/src/api/`. Shared query serialization lives in `queryParams.js`, and top-five opening behavior is isolated in `openJobs.js`.

## Data and ownership contracts

Hard invariants:

1. `CsvRow` and `JobTrack` are different identities.
2. Visit state is not application state.
3. Deleting or archiving source CSV data must not erase durable application history.
4. Private reads and writes are account-scoped. Never accept a user ID from the client as authority.
5. Lifecycle/evidence/history writes are durable product data. Preserve idempotency, ordering, and transaction boundaries.
6. Optimistic versions and undo journals protect concurrent writes.
7. UTC instants, account-local day boundaries, date-only deadlines, and local scheduled wall times are different concepts.

## Filtering and top-five opening

`backend/app/services/row_queries.py` is the shared account-scoped filtering/query boundary. Frontend query serialization is centralized under `frontend/src/api/queryParams.js`.

The top-five workflow operates on the complete active filtered/sorted server result, not only the visible page. Opening a job marks only a successful navigation/visit, not an application.

## Today, reminders, and time

C-04 provides one mixed-source continuation contract across manual actions, follow-ups, deadlines, and interview preparation. C-05 defines SQLite/PostgreSQL timestamp behavior. C-06 makes browser-time acceptance deterministic across UTC, Asia/Kolkata, and America/New_York.

Reminder scheduling and delivery are separate activation gates. `RUN_REMINDER_WORKER` and `REMINDER_EMAIL_DELIVERY_ENABLED` default off. Maintenance jobs and job URL checks also default off.

## Documents and private storage

Documents are private immutable versions stored outside the application database. Database rows own metadata, selections, checksums, state, and opaque `storage_key` values.

`backend/app/services/document_storage.py` owns the storage-adapter boundary:

- filesystem backend for local development/tests;
- S3-compatible backend for production C-09;
- transient local cache/staging for S3 objects;
- safe key validation, private object publish/download/delete/move/list operations;
- storage readiness without exposing provider credentials.

The user-selected C-09 requirement is **zero-dollar infrastructure**. Production therefore stays on Render Free and uses the existing Supabase Free project for a private `jobgrid-documents` Storage bucket through Supabase's S3-compatible endpoint. Render local files are disposable and must never be treated as durable document state.

JobGrid retains the existing 100 MiB per-account document quota. The C-09 storage audit reports aggregate object usage and a 900 MB warning threshold beneath the current 1 GB Supabase Free Storage allowance.

Never put uploaded files in the repository, `frontend/public`, a public bucket, or a browser-readable secret. S3 access keys are server-only high-privilege credentials.

## Backup and recovery

Portable recovery is versioned and must preserve account ownership, local references, replay identity, and transactional failure behavior.

Current behavior after PR #159:

- JSON v2 is records-only and explicitly excludes document bytes.
- ZIP is the complete user-facing backup path and contains the composed v2 metadata graph plus verified immutable document bytes.
- Restore validation happens before writes.
- Supported restore layers join one caller-owned transaction.
- Failed bundle restore removes files/objects published by that failed attempt where possible.
- PostgreSQL and private object storage are still not one ACID transaction, so crash reconciliation remains an operational concern.

The storage adapter preserves this portable contract regardless of whether the active backend is filesystem or S3-compatible object storage.

Do not bypass the composed export/restore path by calling an older base exporter directly. Do not use source database integer IDs as portable cross-section references.

## Imports, contacts, and undo/archive

External imports use a preview → deliberate commit flow with private previews, reusable mappings, row/byte limits, reconciliation decisions, and replay/concurrency protections.

Contacts and interviews are account-owned and may be linked to applications. Calendar output must preserve stable identifiers, escaping, timezone meaning, cancellations/reschedules, and ownership boundaries.

Archive/undo uses `BulkAction` / `BulkActionEffect` plus optimistic version checks. Restored undo history is evidence only and must not become executable destructive state.

## Production safety and configuration

`backend/app/config.py` fails fast in production when critical configuration is unsafe. Production requires:

- `TEST_AUTH=false`
- a non-placeholder signing secret of sufficient length
- public HTTPS `FRONTEND_URL` and `OAUTH_REDIRECT_BASE`
- explicitly configured public HTTPS CORS origins

C-09 deployment readiness additionally requires database connectivity and the configured private object-store bucket through `/ready`.

Never commit database URLs, OAuth secrets, email credentials, S3 credentials, session cookies, private keys, user backups, or private document contents.

## Testing and CI

Backend tests are under `backend/tests`, browser tests under `frontend/tests`, and the frontend production check is `npm run build`.

The release matrix includes PostgreSQL-backed backend/E2E coverage, SQLite coverage, explicit browser timezone coverage, migration evidence, frontend build, and focused release workflow checks.

C-09 adds:

- zero-dollar Render Blueprint assertions;
- storage-adapter readiness tests;
- S3 publish/cache-loss/move/delete/key-safety tests;
- backend-neutral storage-audit tests;
- continued existing document/backup recovery regressions through the same public contracts.

Critical test safety: disposable test databases only. Never point pytest or browser fixtures at production or the only copy of staging data.

## Deployment topology

Current C-09 target:

- Vercel Free for React/Vite frontend
- Render Free for FastAPI backend
- Supabase Free PostgreSQL
- Supabase Free private Storage for document bytes

`render.yaml`, `frontend/vercel.json`, `backend/.python-version`, `backend/app/services/document_storage.py`, and `docs/CLOUD_DEPLOYMENT_VERCEL_RENDER_SUPABASE.md` are the primary deployment assets/runbook.

This topology is deployment preparation, not proof of production readiness. Real OAuth, controlled email receipt, real storage credential/bucket verification, staging recovery, restart/durability, rollback, and production smoke/observation remain external acceptance gates under C-09 through C-12.

## Current completion state

- JG-001–JG-010 are verified complete after PR #159.
- C-01 through C-03 were closed through PR #161.
- C-04 mixed-source Today pagination is closed.
- C-05 SQLite timestamp contracts are closed.
- C-06 deterministic browser-time tests are closed.
- C-07 corrected release CI is closed.
- C-08 local product acceptance is closed by PR #171.
- C-09 repository work is in PR #173. The architecture is now zero-dollar and the private Supabase bucket has been created, but S3 server credentials and live restart/redeploy/recovery evidence remain external steps.
- C-10 is real-provider/deployed acceptance.
- C-11 reconciles ticket/documentation evidence after acceptance.
- C-12 is production release, observation, rollback-readiness, and closure.

A historical `COMPLETED` label is not enough to claim release completion. Use current code, concrete tests/evidence, focused C-package evidence, and release acceptance.

## High-risk landmines

- Do not confuse CsvRow IDs with JobTrack IDs.
- Do not make click/open mean applied.
- Do not cascade source-row deletion into application history.
- Do not weaken account scoping.
- Do not add independent commits inside composed backup restore layers.
- Do not change backup, cursor, timestamp, or public API contracts silently.
- Do not reactivate automatic purge, reminder email, URL checking, or maintenance jobs by default.
- Do not depend on Render Free local files for durable documents.
- Do not make the Supabase bucket public.
- Do not expose S3 credentials to the browser.
- Do not treat mocked tests, dev login, queued email, or green local CI as live staging/production evidence.
- Do not silently upgrade a provider to a paid plan to solve a free-tier limitation.

## Where to start for future work

1. Read this file for current boundaries.
2. Read the relevant C package plus `docs/C09_STAGING_OPERATIONS.md` for the zero-dollar infrastructure decision.
3. Inspect the actual router/service/model/schema/frontend/tests/provider evidence before editing.
4. Reuse existing implementation and conventions.
5. Make the smallest coherent change and run the complete affected release gates.
