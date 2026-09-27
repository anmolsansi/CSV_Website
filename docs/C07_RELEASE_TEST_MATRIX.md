# C-07 Corrected Release Test Matrix — Completion Evidence

Date: 2026-09-27

Tracking issue: #168  
Implementation PR: #169  
Baseline: `6a9210ccf9aecb6e5398f437297f0b9af1524084`

## Scope

C-07 converts the repaired recovery, pagination, timestamp, and browser-time contracts from C-01 through C-06 into repository release gates. It changes CI/test policy only. It does not change a product route, API contract, database schema, migration, or user-facing workflow.

The release candidate is accepted only when every required GitHub status check is green on the exact source SHA and `main` is protected so those checks cannot be bypassed by an ordinary merge.

This file is the repository-level C-07 release-matrix record. `docs/RELEASE_ACCEPTANCE.md` remains the JG-024 staging/external-provider runbook. A green C-07 matrix is a prerequisite for those later staging gates; it does not turn blocked OAuth, SMTP, restore, deployment, or rollback gates into PASS.

## Required status checks

The intended protected-branch checks are the actual hosted job names:

- `Frontend Build`
- `E2E Tests (Playwright)`
- `Backend Compile Check`
- `Backend Tests (pytest)`
- `Backend Tests (SQLite)`
- `C-06 Browser Timezones`

Do not substitute a workflow-file review for branch protection. Repository protection must be verified from GitHub after the final checks exist.

## Runtime matrix

| Gate | Runtime | Required behavior |
| --- | --- | --- |
| Frontend build | Node 20 / Vite | Production build uses `VITE_API_URL=/api` and dev login disabled. |
| PostgreSQL backend | Python 3.12 / PostgreSQL 16 | Full pytest suite plus focused recovery/backup/Today regressions. Regular runtime DB and migration/schema DB are distinct disposable databases. |
| SQLite backend | Python 3.12 / SQLite | Full supported SQLite suite. PostgreSQL-only behavior is excluded explicitly; the executed suite permits zero runtime skips. |
| Main browser | Chromium / UTC | Full browser suite, helper safety tests, focused real-backend release workflow, migrated PostgreSQL API. |
| Browser-time contract | Chromium / UTC, Asia/Kolkata, America/New_York | C-06 fixed-clock wall-time/instant contracts plus real API snooze/reschedule persistence. |

## Environment isolation

Hosted test services set the local frontend/API contract explicitly instead of inheriting production `.env` values:

- `FRONTEND_URL=http://localhost:5173`
- `CORS_ORIGINS=http://localhost:5173`
- `TEST_AUTH=true`
- `ENVIRONMENT=test`
- `RUN_MAINTENANCE_JOBS=false`
- `RUN_REMINDER_WORKER=false`
- `REMINDER_EMAIL_DELIVERY_ENABLED=false`
- `JOB_URL_CHECKS_ENABLED=false`
- empty SMTP host
- per-job `/tmp/...` private document storage
- browser jobs use `VITE_API_URL=http://localhost:8000` and dev login enabled only for the controlled test flow

This prevents CI from sending email, starting destructive/external workers, checking arbitrary job URLs, or writing documents into the repository/public tree.

## Failure policy

`scripts/verify_junit.py` rejects:

- missing/invalid JUnit evidence
- an empty test report
- any test failure
- any test error
- skips beyond the job's declared allowance

The PostgreSQL and SQLite executed release suites allow zero skips. SQLite PostgreSQL-only behavior is removed from that execution deliberately through the existing `postgresql` marker plus a small recorded explicit deselection list for dialect/primary-runtime assertions that are PostgreSQL-specific but historically unmarked. The workflow separately collects the marked PostgreSQL-only population so a disappearing exclusion set is visible.

The recorded unmarked PostgreSQL-only assertions are:

- `test_both_dialect_api_responses_are_200`
- `test_postgresql_advisory_lock_contention_is_skipped_and_recoverable`
- `test_primary_runtime_numeric_sort_is_numeric_not_lexical`
- `test_today_postgres_query_plans_use_owner_due_indexes`

The first hosted SQLite execution proved the distinction matters: 604 supported tests passed and the only failure was `test_primary_runtime_numeric_sort_is_numeric_not_lexical`, whose contract explicitly asserts that the primary runtime dialect is PostgreSQL. C-07 therefore records/deselects that assertion rather than changing runtime product code or weakening SQLite behavior.

Browser and backend collections are listed before execution and must contain tests. Migration/readiness failures exit nonzero. Failure artifacts preserve Playwright traces/results and sanitized backend logs.

## C-07 checkpoint mapping

| Checkpoint | Evidence |
| --- | --- |
| C-07.01 | `.github/workflows/ci.yml` keeps PostgreSQL 16 and distinct `jobgrid_test` / `jobgrid_schema_test` targets. Alembic reaches head before browser execution; schema acceptance uses the isolated test database. |
| C-07.02 | `.github/workflows/c07-sqlite.yml` runs the supported SQLite suite, records explicit PostgreSQL-only exclusions, and rejects any runtime skip in the executed SQLite population. |
| C-07.03 | PostgreSQL CI collects/runs focused complete-backup, backup-contract, document-backup, mixed Today/interview, Today queue, and timestamp regressions. The C-06 workflow collects all three browser timezone projects before execution. |
| C-07.04 | CI pins frontend/API/CORS settings, disables external workers and email delivery, and isolates document storage. |
| C-07.05 | Frontend production build, tab-helper tests, complete UTC Chromium, focused JG-023 real-backend browser workflow, backend routes through migrated FastAPI, and the targeted real-API timezone workflow remain required. |
| C-07.06 | Nonempty collection guards, JUnit verifier, migration/readiness checks, and artifact `if-no-files-found` policy reject missing evidence or unexpected outcomes. |
| C-07.07 | Hosted jobs record source/workflow SHA, migration revision where applicable, runtime/dependency versions, JUnit/collection outputs, browser reports/results, and sanitized failure logs. |
| C-07.08 | **Pending final repository-setting verification.** `main` must require the actual check names listed above. |
| C-07.09 | **Pending final hosted validation.** Record the exact final PR head SHA and green workflow run IDs in issue #168 / PR #169 after the last repository change. |

## Branch-protection procedure

GitHub repository administrators must protect `main` and require the six actual status-check names listed above. The connected repository automation used for C-07 exposes protection reads but not protection writes, so this setting must be applied through an authorized GitHub repository-settings surface if it is not already present.

After changing the setting, verify the GitHub branch response reports `protected: true` and that the protection/ruleset requires the intended C-07 job names. Do not merge by bypassing a red or missing release check.

## Hosted validation

Final source SHA: **record in issue #168 / PR #169 after final run**  
Standard CI run: **record after final run**  
SQLite release run: **record after final run**  
C-06 browser-time run: **record after final run**  
Branch protection: **PENDING repository setting**

Keeping exact run IDs in the GitHub tracking record avoids a documentation-only commit invalidating the exact-SHA evidence after the final matrix completes.

## Rollback

C-07 changes repository test/release policy only. Rollback is reverting the workflow/test-documentation commits. There is no database migration or persisted product-data conversion. Do not weaken branch protection merely to make a failing candidate mergeable. Preserve the first failing artifacts, correct the cause, and rerun the affected matrix on the new source SHA.
