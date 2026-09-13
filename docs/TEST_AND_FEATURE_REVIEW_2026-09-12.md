# JobGrid application test and feature review

Date: 2026-09-12. Scope: current local working tree, including the uncommitted
application-memory and filtered-batch changes. Review only; no production code
was changed, committed, pushed, or deployed during this audit.

## Verdict

The core application is usable locally, but it is not yet trustworthy enough to
make backup, analytics, or production-readiness promises. Fix the confirmed data
and consistency failures before adding more pages or unattended automation.
The purpose should be helping a job seeker complete the right next action and
retain reliable evidence, rather than maximizing opened URLs or feature count.

## What actually ran

| Check | Result | What this establishes |
|---|---|---|
| Full backend pytest suite | 113 passed; 475 warnings | Existing tests pass with SQLite |
| Full Playwright suite | 113 passed, including setup; 1.8 minutes | Existing browser assertions pass in Chromium |
| Tab-helper tests | 8 passed | Blocked tabs, unsafe URLs, partial failures, cleanup and tracking behavior |
| Vite production build | Passed; 385.46 kB JS / 115.54 kB gzip | Frontend bundles successfully |
| Additional adversarial API probes | Defects reproduced below | Tests beyond the supplied suite expose contract failures |
| Alembic upgrade on fresh SQLite | Failed on PostgreSQL JSONB | SQLite create_all testing does not validate the deployment migration path |
| PostgreSQL runtime / migration / rollback | Not run | Docker CLI exists, daemon socket unavailable; no local postgres executable |
| Production, real OAuth and real SMTP delivery | Not exercised | Local dev-login and test fixtures are not external integration acceptance |

The browser suite covers Dashboard, Applications, Analytics, Pipeline, Sessions,
Saved Views, ApplyPilot, Duplicates, Companies, external import and the new
application-memory/batch flow. Several older tests check element presence or
conditionally assert only when data is available. Passing them is not evidence
that all business rules work. For example, backup and export tests failed to
catch the round-trip and filter discrepancies reproduced here.

Commands used (temporary runtime and disposable databases):

```bash
DATABASE_URL=sqlite:////private/tmp/jobgrid-audit-20260912.db \
  /private/tmp/jobgrid-venv/bin/pytest backend/tests -q --disable-warnings
node --test frontend/unit/open-jobs.test.mjs
npm run build --prefix frontend
# Isolated TEST_AUTH backend on localhost:8000; disposable DB, no production data.
cd frontend
npx playwright test --reporter=line
```

## Confirmed defects, in repair order

### P1 — JSON backup import drops application history

Evidence: export a test account containing two CSV rows and one applied job;
import into an empty test account. HTTP 200 reports two CSV rows imported and
zero job tracks; Applications and Companies both contain zero records.

`backend/app/routers/crm.py:1084` imports CSV rows and saved views only. Export
also includes tracks, sessions, audit events and ApplyPilot batches. Several CSV
fields, visit state and preferences are absent even from export. This is an
incomplete portable backup, distinct from the database backup scripts.

Acceptance for the fix: round-trip all supported entities, ownership, status,
dates, notes and relationships; verify counts and content, duplicate import
behavior, schema version handling, malformed input and transaction rollback.
Do not delete source data before a restore comparison passes.

### P1 — Filtered export is not the filtered table

Evidence: upload one remote and one onsite job; `/rows?location_group=remote`
returns one record, while `/crm/export/dashboard?format=json&location_group=remote`
returns two. `frontend/src/pages/Dashboard.jsx:501` forwards only ATS for filtered
exports; `backend/app/routers/crm.py:1181` also lacks the other table predicates.

Acceptance: one shared filter/sort contract across browse, selection, batches,
exports and saved views. Verify exact exported IDs with multiple filters and
more than one page of results. Do not fix this by filtering only loaded rows.

### P1 — Progress metrics disagree after real actions

Evidence: a fresh user opens one job and marks a different job applied.
Analytics reports applied_today=1, while `/crm/analytics/goals` reports
`today.applied=0`. Weekly report says opened=0, despite a recorded visit.

`crm.py:552` counts application_marked_applied events for goals, but the current
status writes do not consistently emit those events. Weekly opened counts use
JobTrack.opened_at while actual visits are stored on CsvRow. Analytics total
opened uses number of tracks, which is a different concept again.

Acceptance: define visits, saved jobs, applications and first transitions once;
make every mutation and dashboard use those definitions. Retried writes must
not inflate totals. Test date boundaries and the user's time zone. Do not add
more charts until these numbers reconcile.

### P2 — Cleanup fails; its intended policy is also questionable

Evidence: calling `cleanup_clicked_rows()` logs AttributeError because
`CsvRow.updated_at` does not exist (`backend/app/jobs.py:30`) and returns zero.
Neither the archive nor delete step runs.

Do not merely replace the missing field. The current intended policy archives
all rows by created_at, even unvisited jobs, using a default two-day threshold.
Hard deletion must preserve application references and duplicates. Decide a
user-visible retention policy, add archived_at if needed, and expose recovery
before enabling deletion. Report failed cleanup separately from zero work.

### P2 — Invalid application status and dates are not validated consistently

Evidence: PATCH an application with `status="THIS_IS_NOT_A_STATUS"` returns
200 and stores that value. `applied_at="not-a-date"` returns 500. Malformed JSON
backup input also returns 500 instead of a useful client error.

`backend/app/schemas.py:29` uses arbitrary optional strings for status/dates,
while the newer from-rows endpoint validates status values. Reuse a consistent
schema and reject invalid values before writes. Test bulk atomicity and show
field-level feedback. External JSON import needs equivalent validation.

### P2 — Numeric sorting breaks the documented SQLite local flow

Evidence: `/rows?sort_by=resume_match_score&sort_dir=desc` returns 500 on SQLite.
`backend/app/routers/rows.py:34` uses PostgreSQL regexp_replace and the `~`
operator. This is not proof the PostgreSQL path fails. It proves local SQLite
behavior differs materially from the deployment database.

Choose either supported dialect-specific numeric expressions or one database
for development and deployment. Test numeric strings, empty cells and malformed
scores. SQLite migration attempt also fails on JSONB; do not call migration
coverage complete based on model creation or searching migration text.

### P1 release gate — CI backend working directory is incorrect

Static evidence, not a fresh GitHub run: `.github/workflows/ci.yml:68` explicitly
sets working-directory to the repository root, then executes `cd ../backend`.
The actual directory is `backend` inside the root. The standard checkout layout
would fail before starting the E2E backend.

Acceptance: correct the directory, use readiness polling, execute the PostgreSQL
migration and browser suite in CI, and inspect a real successful run. Do not
assume local green tests mean remote CI is green.

## Additional risk review

- Security: account isolation is explicitly exercised in the existing new
  application-memory tests. A complete security audit was not performed.
  Startup should refuse production with TEST_AUTH enabled or a default signing
  key; config currently supplies a development fallback key and dev-login is
  gated by TEST_AUTH alone. Actual deployment settings were not inspected.
- Privacy: future resumes, recruiter contacts and confirmation evidence need
  account ownership, minimal logging, export/deletion and retention rules.
- Retry/concurrency: same-window batch clicks are guarded, but separate browser
  windows can open the same jobs. Application uniqueness prevents duplicate URL
  rows but is not proof concurrent upserts return a clean success response.
- Operations: existing metrics and loggers exist, but cleanup's zero result
  obscures failure. Define health checks for work completion, not just HTTP 200.
- Backup/deployment: database backup scripts exist; WAL/S3/alerting described in
  docs were not verified as deployed. Test restore into a disposable PostgreSQL
  instance before trusting the runbook. Rollback must retain user history.
- Scoring: `backend/app/scoring.py:232` implements keyword overlap. Its percent
  is not a calibrated chance of interview or proof of skill suitability.
- Scope: pipeline, saved views, basic company history, duplicates, follow-up
  dates, analytics and email digest endpoints already exist. Rebuilding them
  as supposedly new features adds maintenance without solving the gaps.

## Ranked feature candidates

Effort is relative and assumes the existing stack; these are proposals, not
implementation commitments. Repair the above contracts first.

| Rank | Feature | Existing base / concrete addition | Acceptance target | Effort / caution |
|---|---|---|---|---|
| 1 | Today queue | Combine current applications, follow-up dates and saved views into one ordered list of due follow-ups, deadlines and shortlisted jobs; allow snooze and next action | One place shows every due action, with explainable order and no duplicates | Medium; do not duplicate another analytics page |
| 2 | Applied-before warning | Extend current URL dedupe and company history with recognized canonical job identity, company aliases and an explicit previous-application banner | Same posting via alternate URL warns before opening/applying; different roles remain distinct | Medium; user-confirmed merges, never fuzzy-delete jobs automatically |
| 3 | Application evidence and timeline | Keep status-transition history, first-applied timestamp, source and optional confirmation/reference alongside notes | Can answer when/how a job was applied to and undo an accidental status change | Medium; opening a link is never submission proof |
| 4 | Follow-up reminders that actually notify | Extend current dates and manual weekly digest with scheduled reminders, time zone, quiet hours, snooze and delivery state | Due reminder delivered once; failure visible and retryable; opted-out users receive none | Medium; stabilize scheduler and event consistency first |
| 5 | Resume and cover-letter versions per application | Attach/reference the exact document version used; link versions to outcomes | Every application can identify its submitted version without overwriting old evidence | Medium; protect private files and avoid unsupported match claims |
| 6 | One-click job capture | Start with a simple Save Job form/bookmarklet; preserve URL/title/company and let the user correct parsed values | Save a non-CSV job in under a minute and retain its source | Small/medium; prove demand before maintaining a full Chrome extension |
| 7 | Job freshness and deadline checks | Add last-checked time, explicit closing date and unavailable/unknown states; optional bounded URL check | Closed jobs do not dominate Today queue; transient errors do not imply closure | Medium; respect site limits and block private-network fetches if server-side |
| 8 | Recruiter/referral and interview workspace | Link contacts, referral source, interview rounds, preparation notes and calendar date to an existing application | Track the next conversation and person responsible without searching loose notes | Medium; start with manual entry, defer mailbox-wide permissions |
| 9 | Import mapping and reconciliation | Extend existing CSV/JSON upload with header mapping, full counts, per-row errors, update-vs-skip preview and import provenance | Preview exactly what changes and download rejected rows; retries do not duplicate | Medium; keep one import transaction contract |
| 10 | Undo and recoverable archive | Add a trash/archive browser, undo for recent bulk actions and clear retention settings | Accidental removal is recoverable and application evidence survives | Medium; resolve cleanup policy and restore fidelity before promising recovery |

## Ideas to defer

- Fully automatic application submission: errors have external consequences and
  would magnify the current tracking/backup weaknesses. Keep explicit review.
- AI-generated match percentages or auto-written claims: keyword overlap is
  weak evidence; prefer explainable required/preferred skills and missing data.
- Gmail/LinkedIn scraping or continuous inbox access: high integration and
  privacy burden. Begin with pasted confirmations or user-selected imports.
- More dashboards, gamified open-count targets, billing and multi-user teams:
  these do not establish whether the current personal job-search workflow helps.
- A new backend, microservices or queues everywhere: reuse FastAPI/SQLAlchemy;
  add durable scheduling only where a real reminder-delivery contract requires it.

## Options and recommended sequence

Option A: ship many new features on top of the current data model. This gives
more visible breadth quickly, but multiplies inconsistent state and recovery
risk. Option B: repair correctness, then ship a small daily workflow with
application evidence. Recommend B; it is cheaper to verify and maintain.

1. Repair backup fidelity, export/filter parity, status validation and metrics;
   decide retention and get the PostgreSQL CI path passing.
2. Build Today queue, applied-before warnings and evidence/timeline on those
   stable contracts. Reuse existing screens and APIs where possible.
3. Add reminders and document versions once retries and storage are verified.
4. Add capture/import improvements according to observed usage.

Measure missed follow-ups, repeated applications, time to capture/record a job,
and the fraction of applications with a known next action. Track interview
outcomes over time, but do not attribute changes causally to the app from small
samples. Opened-link count alone is an activity metric, not success.

Open product decision: this audit assumes a personal job-search tool. Team or
commercial SaaS requirements would add permissions, billing, support and
operational gates. That decision does not block the recommended correctness fixes.
