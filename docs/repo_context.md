# Repo Context — JobGrid — 2026-09-25

Baseline: `7684cbc0f8d3a4e131bd986d21a05d15ccea8e63` on `main` after PR #159 merged JG-001–JG-010 recovery and acceptance work.

This file is the compact repository context for implementation agents. It describes the current codebase, contracts, active risks, and completion state. Read `development.md` for the full completion plan and ticket-level closeout instructions. Historical planning files may contain stale proposed names or completion labels, so current code plus `development.md` take precedence.

## Stack and runtime

- Frontend: React 18, Vite 5, React Router 7, Axios, TanStack Table, Playwright.
- Backend: Python 3.12, FastAPI 0.111, SQLAlchemy 2.0, Alembic, APScheduler.
- Database: PostgreSQL is the deployment target. SQLite is also an explicitly supported/tested runtime path and has connection-level foreign-key and numeric-sort adapters in `backend/app/database.py`.
- Auth: server-side session cookies. Google, Microsoft, and Apple OAuth configuration lives in `backend/app/config.py`. `TEST_AUTH` exists only for test/dev flows and must be false in production.
- Observability: FastAPI metrics middleware plus optional Sentry.
- Main migration head: `018_bulk_undo_foundation.py`. Migrations 001–018 cover the initial schema, backup identity, lifecycle events, user timezone, archive/maintenance state, Today, identity, evidence, reminders, documents, capture, availability, contacts/interviews, import previews, and undo foundation.

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

Important service modules live in `backend/app/services/`. Do not move business logic back into route handlers when an owning service already exists. Major service boundaries include `row_queries.py`, `validation.py`, `lifecycle.py`, `today.py`, `today_f8.py`, `reminders.py`, `retention.py`, `job_identity.py`, `evidence.py`, `documents.py`, `capture.py`, `availability.py`, `contacts.py`, `imports.py`, `bulk_actions.py`, `undo_foundation.py`, and the backup services.

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

Application detail functionality is composed from focused components including `ApplicationTimeline`, `ApplicationDocuments`, `ApplicationPeople`, `ApplicationInterviews`, and `JobAvailability`. Backup/restore, reminders, retention settings, import preview, archive/undo status, navigation, command palette, and accessibility helpers also have dedicated components.

## Data and ownership contracts

These are hard invariants for future work:

1. `CsvRow` and `JobTrack` are different identities. A CSV row represents imported discovery data. A JobTrack is the durable application/job memory. Never substitute one ID for the other.
2. Visit state is not application state. Opening a URL or setting row click state must not imply that the user applied.
3. Deleting or archiving source CSV data must not erase durable application history. JobTrack retains its own company/title/URL snapshot and may outlive its source row.
4. Private reads and writes are account-scoped. Never accept a user ID from the client as authority. Resolve ownership from the authenticated user and verify related IDs belong to that same account.
5. Lifecycle/evidence/history writes are durable product data. Preserve idempotency, ordering, and transaction boundaries when adding new writers.
6. Optimistic versions and undo journals protect concurrent writes. A stale undo or stale mutation must conflict instead of silently overwriting newer state.
7. Timestamps represent different concepts. UTC instants, account-local day boundaries, date-only deadlines, and local scheduled wall times must not be treated as interchangeable.

## Filtering and top-five opening

`backend/app/services/row_queries.py` is the shared account-scoped filtering/query boundary used to keep list/export behavior aligned. Frontend query serialization is centralized under `frontend/src/api/queryParams.js`.

The top-five workflow operates on the complete active filtered/sorted server result, not only the visible page. `frontend/src/api/openJobs.js` contains the browser-side tab helper. Opening a job marks only a successful navigation/visit, not an application.

Do not reintroduce page-local top-five selection, unsafe protocols, `window.opener` access, or filter serialization drift.

## Today, reminders, and time

Today is implemented across `backend/app/services/today.py`, `today_f8.py`, the Today router/schema, and `frontend/src/pages/Today.jsx`. The F8 extension adds interview preparation into the established Today contract through composition in `backend/app/main.py`.

Known completion risk: mixed-source Today pagination still needs the C-04 repair described in `development.md`. The current audit found that interviews can be merged after the base queue has already been paginated, which can make later items unreachable or produce an incorrect cursor. Do not treat existing Today implementation as final acceptance until C-04 closes.

Reminder scheduling and delivery are separate activation gates. `RUN_REMINDER_WORKER` and `REMINDER_EMAIL_DELIVERY_ENABLED` default off. Maintenance jobs also default off. Tests and local work must not accidentally send real email or run destructive background work.

Browser time testing is not fully release-hardened yet. `frontend/playwright.config.ts` currently defines setup plus one Chromium project. C-06/C-07 in `development.md` require explicit multi-timezone browser coverage instead of relying on the host timezone.

## Documents and private storage

Documents are private immutable versions stored outside the database. Database rows own metadata, selections, checksums, and lifecycle state. Bytes live under `DOCUMENT_STORAGE_DIR`.

Production configuration rejects repository/public/temp storage paths. If `DOCUMENT_STORAGE_DIR` is absent, document upload/download functionality is unavailable while the rest of JobGrid can remain healthy. A production deployment must provide durable private storage and prove survival across restart/redeploy before release acceptance.

Do not put uploaded files under `frontend/public`, the repository tree, or a production temp directory. Do not expose storage paths or object names as authorization tokens.

## Backup and recovery

Portable recovery is versioned and must preserve account ownership, local references, replay identity, and transactional failure behavior.

Current behavior after PR #159:

- JSON v2 is records-only and explicitly excludes document bytes.
- ZIP is the complete user-facing backup path and contains the composed v2 metadata graph plus verified immutable document bytes.
- Base backup records, contact/interview/link extensions, import mappings, supported undo/audit metadata, and document metadata are composed through the current backup services.
- `backend/app/services/backup_sessions.py` owns shared restore transaction and export snapshot helpers.
- Restore validation happens before writes. Supported child restore layers join the same owned transaction rather than committing independently.
- Failed bundle restore removes files published by that failed attempt where possible. Filesystem and database state are still not one ACID transaction, so crash reconciliation remains an operational concern.

Do not bypass the composed export/restore path by calling an older base exporter directly. Do not use source database integer IDs as portable cross-section references.

## Imports, contacts, and undo/archive

External imports use a preview -> deliberate commit flow with private previews, reusable mappings, row/byte limits, reconciliation decisions, and replay/concurrency protections. Keep preview parsing separate from final writes.

Contacts and interviews are account-owned and may be linked to applications. Calendar output must preserve stable identifiers, escaping, timezone meaning, cancellations/reschedules, and ownership boundaries.

Archive/undo uses `BulkAction` / `BulkActionEffect` plus optimistic version checks. Restored undo history is evidence only and must not become executable destructive state. Automatic purge is not an assumed product behavior and remains disabled unless explicitly approved.

## Production safety and configuration

`backend/app/config.py` fails fast in production when critical configuration is unsafe. Production requires:

- `TEST_AUTH=false`
- a non-placeholder signing secret of sufficient length
- public HTTPS `FRONTEND_URL` and `OAUTH_REDIRECT_BASE`
- explicitly configured public HTTPS CORS origins

Retention, reminder email delivery, maintenance work, and external job URL checks are intentionally disabled by default and require explicit operator activation.

Never commit database URLs, OAuth secrets, SMTP credentials, session cookies, private keys, user backups, or inbox contents.

## Testing and CI

Backend tests are under `backend/tests` and use pytest. Frontend browser tests are under `frontend/tests` and use Playwright. `frontend/unit/open-jobs.test.mjs` covers the tab-opening helper. The frontend production check is `npm run build`.

`.github/workflows/ci.yml` currently runs:

- Frontend Build
- E2E Tests (Playwright) against a migrated PostgreSQL-backed local API
- Backend Compile Check
- Backend Tests (pytest) with PostgreSQL 16

PR #159's head passed hosted CI after the JG-001–JG-010 recovery changes. The implementation evidence records 598 PostgreSQL tests passing, a scoped SQLite suite of 110 passed with one PostgreSQL-only skip, 13 focused Chromium checks, 8 tab-helper checks, and a successful frontend production build. Those results verify the first ten tickets locally/through that PR, not the whole remaining roadmap.

Critical test safety: `backend/tests/conftest.py` can recreate/drop PostgreSQL tables. `DATABASE_URL` and `TEST_DATABASE_URL` used by tests must always point to disposable test databases. Never point pytest or browser fixtures at production or the only copy of staging data.

Current release gaps: CI does not yet enforce the complete C-07 matrix, including the supported SQLite path and explicit multi-zone browser projects. The `main` branch is currently unprotected and has no required status-check enforcement, so branch protection remains part of C-07 rather than an assumed repository guarantee.

## Deployment topology

The checked-in cloud runbook currently targets:

- Vercel for the React/Vite frontend
- Render for the FastAPI backend
- Supabase as managed PostgreSQL only

`render.yaml`, `frontend/vercel.json`, `backend/.python-version`, and `docs/CLOUD_DEPLOYMENT_VERCEL_RENDER_SUPABASE.md` are the primary deployment assets/runbook. Alembic remains the only schema migration system. Do not introduce Supabase Auth, Realtime, or a second migration path merely because Supabase hosts PostgreSQL.

This topology is deployment preparation, not proof of production readiness. Real OAuth, SMTP receipt, durable document storage, staging restore, restart/durability, old-code rollback, and production smoke/observation remain external acceptance gates under C-09 through C-12.

## Current completion state

`development.md` is the primary completion guide.

- JG-001–JG-010 are verified complete at the current local/PR acceptance level after PR #159.
- The guide currently classifies the remaining original tickets as 42 implemented with requirement-level verification pending, 10 needing repair, and 2 externally blocked.
- The immediate engineering sequence is C-04 mixed-source Today pagination, C-05 SQLite timestamp contracts, C-06 deterministic browser-time tests, and C-07 corrected release CI.
- C-08 is broad product acceptance across the existing implementation. Do not rebuild features that already satisfy their contracts.
- C-09/C-10 are real staging and external-provider gates.
- C-11 reconciles ticket/documentation evidence only after acceptance.
- C-12 is the actual production release, observation, rollback-readiness, and closure gate.

A historical `COMPLETED` label in a roadmap file is not enough to claim release completion. Use current code, concrete tests/evidence, `development.md`, and the release acceptance runbook.

## High-risk landmines for builders

- Do not confuse CsvRow IDs with JobTrack IDs.
- Do not make click/open mean applied.
- Do not cascade source-row deletion into application history.
- Do not weaken authenticated account scoping when joining contacts, documents, imports, backups, evidence, Today, or undo records.
- Do not add independent commits inside composed backup restore layers.
- Do not change backup wire formats, cursor formats, timestamp semantics, or public API contracts silently.
- Do not reactivate automatic purge, reminder email, URL checking, or maintenance jobs by default.
- Do not store private documents in the repository, a served directory, or ephemeral production temp storage.
- Do not treat mocked browser tests, dev login, queued SMTP, or a green local suite as staging/production evidence.
- Do not add new frameworks, queues, databases, storage providers, or auth systems unless the owning requirement proves the existing architecture cannot satisfy it.

## Where to start for future work

1. Read this file for repository boundaries and current landmines.
2. Read the relevant C package and JG closeout section in `development.md`.
3. Inspect the actual owning router, service, model/schema, frontend API/page/component, tests, migration history, and recent relevant commits before editing.
4. Reuse existing implementation and conventions. Capture a failing reproduction before repairing a confirmed defect.
5. Make the smallest coherent change, run the narrowest relevant validation, then broader affected checks.
6. Update documentation when behavior or operating contracts change.
7. Do not mark work complete without concrete evidence at the exact SHA being claimed.
