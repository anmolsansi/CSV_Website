# C-08 Product Acceptance — Completion Evidence

Date: 2026-09-27

Tracking issue: #170  
Working branch: `c08-product-acceptance`  
Baseline: `52afdb78bca16870dcd1c228da3df7b495cc12c4` (`main` after C-07)

## Scope and closeout rule

C-08 is the repository/local product-acceptance gate defined by `development.md`. It does not claim that external providers or deployed infrastructure have passed staging. C-09/C-10 still own real OAuth, controlled SMTP receipt, durable deployed document storage, deploy/restart behavior, staging backup/restore, rollback, and deployed browser/provider checks.

The C-08 acceptance rule is:

1. reuse the implemented product instead of rebuilding historical tickets;
2. map each local requirement to a concrete automated assertion or reviewed local evidence;
3. verify account isolation and failure/retry behavior where state changes;
4. repair demonstrated local P1/P2 gaps;
5. keep external-only evidence explicitly mapped to C-09/C-10.

The audit found one missing named cross-feature regression: a Today snooze and a reminder for the same follow-up were tested separately, but no assertion proved that snoozing the Today presentation state does not mutate reminder-delivery state. `backend/tests/test_c08_cross_feature_acceptance.py` closes that gap.

## Original journey A — durable applications and company history

Status: **PASS locally**

Concrete evidence:

- `backend/tests/test_application_memory.py::test_mark_applied_is_atomic_and_idempotent` proves a CSV row can create one durable JobTrack without turning a visit into an application and that retries do not duplicate the application.
- `test_deleting_csv_retains_job_and_company` proves deleting the discovery row leaves the durable application/company history intact and detaches `csv_row_id` safely.
- `test_company_directory_normalization_pagination_and_isolation` proves normalized company history plus second-account isolation.
- `test_bulk_foreign_rows_rejected_without_partial_writes` proves a mixed owned/foreign bulk request is rejected atomically.
- `frontend/tests/application-memory.spec.ts`, `company-history.spec.ts`, `applied-before.spec.ts`, `applications.spec.ts`, `pipeline.spec.ts`, and `analytics.spec.ts` exercise the browser surfaces that consume the durable record.
- Identity regressions in `backend/tests/test_job_identity.py` preserve requisition-bearing URLs, remove only explicit tracking parameters, and keep company/title-only similarity at `possible` rather than silently merging jobs.

C-09/C-10 boundary: production/deployed-session persistence remains staging evidence, not C-08 local evidence.

## Original journey B — top five unopened filtered jobs

Status: **PASS locally**

Concrete evidence:

- `backend/tests/test_application_memory.py::test_global_filtered_top_five_and_next_batch` proves selection comes from the complete server result, excludes already-opened, nonmatching, and unsafe rows, and advances to the next five after visit writes.
- `backend/tests/test_query_contracts.py::test_each_filter_and_pair`, `test_null_and_empty_columns_keep_documented_semantics`, and `test_page_boundaries_and_ties_are_deterministic` prove combined filters, null semantics, deterministic tie ordering, and page boundaries.
- `frontend/tests/release-workflows.spec.ts::top5_complete_filters_sort_safe_url_popup_blocking_and_click_recording` compares the browser batch with the server's exact filtered/sorted first five, verifies five successful popup navigations, confirms `window.opener === null`, proves successful visit persistence, and proves blocked popups create no click writes.
- `frontend/unit/open-jobs.test.mjs` covers zero/fewer candidates, unused-tab cleanup, blocked windows, unsafe/malformed URL rejection, tracking failure behavior, partial reservation cleanup, and continuing after a reserved tab is closed.

C-09/C-10 boundary: an actual deployed Chrome popup-policy run remains staging evidence.

## Acceptance pack matrix

| Pack | JG tickets | Local result | Concrete repository evidence | External remainder |
| --- | --- | --- | --- | --- |
| A01 Recovery | JG-001–004 | PASS | `test_backup_contract.py`, `test_backup_export.py`, `test_backup_restore.py`, `test_complete_backup.py`, `test_document_backup.py`, `docs/JG001_010_EXECUTION.md`. Invalid/late failure, replay/conflict, owner isolation, complete graph, byte recovery, and final-commit rollback are asserted. | staging round trip/redeploy under C-09/C-10 |
| A02 Shared filtering | JG-005–007 | PASS | `test_query_contracts.py`, `test_filtered_exports.py`, `filter-export-parity.spec.ts`, `saved-views.spec.ts`, `release-workflows.spec.ts`. Membership/order parity, ties, nulls, malformed selections, ownership, CSV/JSON, saved views, and top-five consumption use the shared query contract. | none beyond deployed smoke |
| A03 Lifecycle metrics | JG-008–011 | PASS | `test_lifecycle_events.py`, `test_lifecycle_mutations.py`, `test_metric_consistency.py`, `test_metric_timezones.py`, `metric-consistency.spec.ts`. First-fact idempotency, legacy/unknown handling, account-local day boundaries, source deletion, and analytics/goals/report agreement are asserted. | none beyond deployed smoke |
| A04 Retention | JG-012–014 | PASS | `test_retention_profile.py`, `test_cleanup_job.py`, `retention-settings.spec.ts`. Disabled default, opt-in validation, preview/no side effects, 500-row bound/resume, concurrent worker exclusion, failure health, and source-history preservation are covered. | operator activation/observation under staging |
| A05 Validation | JG-015–017 | PASS | `test_mutation_validation.py`, `test_all_application_writers.py`, `test_application_validation.spec.ts`, import preview/commit tests. Status/date/URL/text/bulk contracts reject invalid input, foreign IDs reject atomically, and error formatting avoids echoing arbitrary payload data. | none beyond deployed smoke |
| A06 Numeric/database | JG-018–020 | PASS | `test_numeric_sort.py`, `test_database_dialects.py`, `test_schema_parity.py`, `test_timestamp_contracts.py`, `numeric-sort.spec.ts`. Numeric-not-lexical ordering, negatives/blanks/invalids, null-last ordering, tie stability, dialect-specific expressions, schema parity, and UTC-instant persistence are covered. | none beyond release matrix |
| A07 Release foundation | JG-021–024 | PASS for local scope | `test_ci_release_matrix.py`, `test_production_config.py`, `test_release_contracts.py`, `docs/C07_RELEASE_TEST_MATRIX.md`, CI workflows. Production fail-fast, migrated DB checks, supported PostgreSQL/SQLite/browser matrix, and explicit external-gate separation are documented/tested. | real OAuth, SMTP, deploy, restore, rollback in C-09/C-10 |
| A08 Today | JG-025–028 | PASS | `test_today_api.py`, `test_today_models.py`, `test_today_mixed_pagination.py`, `test_today_mixed_cursor_contract.py`, `test_today_mixed_boundedness.py`, `test_interview_today.py`, `today.spec.ts`, `today-mixed-pagination.spec.ts`, C-06 browser-time suite. All sources share one order/cursor; snooze/reschedule/stale versions/timezones and bounded source reads are covered. | deployed browser smoke |
| A09 Identity | JG-029–032 | PASS | `test_job_identity.py`, `test_identity_backfill.py`, `test_application_matches.py`, `applied-before.spec.ts`, `duplicates.spec.ts`. Tracking-key policy is explicit, requisition identity remains distinct, company/title similarity is conservative, and positive/negative duplicate cases are covered. | none beyond deployed smoke |
| A10 Evidence history | JG-033–036 | PASS | `test_evidence_models.py`, `test_evidence_api.py`, `application-timeline.spec.ts`. Create replay produces one evidence/event, ordering is stable, soft deletion hides normal-read body, foreign timeline is 404, corrections append rather than mutate history, stale corrections conflict, and source-row deletion retains evidence. | none beyond deployed smoke |
| A11 Reminders | JG-037–040 | PASS for local scope | `test_reminder_models.py`, `test_reminder_api.py`, `test_reminder_worker.py`, `reminders.spec.ts`, `test_c08_cross_feature_acceptance.py`. Opt-in planning, DST gap/overlap, quiet hours, reschedule cancellation, bounded retry, expired lease recovery, restart dedupe, timezone replan, one PostgreSQL claim, and Today-snooze independence are asserted. | authorized controlled SMTP receipt in C-09/C-10 |
| A12 Documents | JG-041–044 | PASS | `test_document_models.py`, `test_document_api.py`, `test_document_storage.py`, `test_document_backup.py`, `document-versions.spec.ts`. Private immutable versions, limits/type validation, owner-only download, selections, checksums, interrupted/failed restore cleanup, complete byte recovery, and transaction rollback are covered. | durable deployed storage/redeploy proof in C-09/C-10 |
| A13 Capture | JG-045–048 | PASS | `test_capture_models.py`, `test_capture_api.py`, `capture.spec.ts`, shared identity tests. Manual/quick capture, idempotency/replay, malformed input, duplicate context, and the no-implicit-visit/application contract are covered. | deployed bookmarklet/popup behavior in C-10 |
| A14 Availability | JG-049–052 | PASS | `test_availability_models.py`, `test_availability_api.py`, `test_safe_job_fetch.py`, `job-freshness.spec.ts`. Manual dates, stale/unknown states, conservative auto checks, source-change effects, redirect/private-network resistance, reminder cancellation where source state closes, and restore are covered. | external live-site checks remain opt-in/staging |
| A15 People/interviews | JG-053–056 | PASS | `test_contacts_api.py`, `test_contacts_interviews.py`, `test_calendar_export.py`, `test_interview_today.py`, `test_jg056_acceptance.py`, `contacts-interviews.spec.ts`. Account-owned contacts/links, interview cancellation/reschedule, Today integration, calendar stability/escaping/timezones, prep, recovery, and second-account boundaries are covered. | calendar-client/deployed smoke if required by C-10 |
| A16 Imports | JG-057–060 | PASS | `test_import_preview.py`, `test_import_preview_models.py`, `test_import_commit.py`, `test_import_lock.py`, `test_jg060_import_acceptance.py`, `import-external.spec.ts`, `import-mapping.spec.ts`. Reusable mapping, private/expiring preview, duplicate decisions, atomic commit, concurrent destination protection, replay, malformed input, 10 MiB/2,000-row bounds, formula-safe rejects, and maximum-fixture measurements are covered. | none beyond deployed smoke |
| A17 Undo/archive | JG-061–064 | PASS | `test_jg061_undo_foundation.py`, `test_jg061_backup_versions.py`, `test_bulk_undo.py`, `archive-undo.spec.ts`. Optimistic versions, rollback with journal failure, all-or-nothing and partial conflict behavior, retry idempotency, expiry/foreign 404, archive restoration, durable application state, no automatic purge, and newer-edit protection are covered. | none beyond deployed smoke |

## Cross-feature integration contracts

| Contract | Result | Evidence |
| --- | --- | --- |
| apply → follow-up → Today → reminder → archive | PASS locally | lifecycle/application writers + Today + reminder + archive suites share the same owned `JobTrack`; reminder source-change and archive/history regressions preserve durable state. |
| interview reschedule → Today → calendar | PASS locally | `test_contacts_interviews.py`, `test_interview_today.py`, `test_calendar_export.py`, `contacts-interviews.spec.ts`. |
| import → duplicate warning → company history → backup | PASS locally | import commit/acceptance tests, identity/application-match tests, company-history/application-memory tests, and complete-backup graph tests. |
| document selection → application history → restore | PASS locally | document API/storage/version tests plus `test_document_backup.py::test_bundle_restores_bytes_and_links`. |
| bulk archive → later edit → undo conflict | PASS locally | `test_bulk_undo.py::test_one_conflict_default_zero_restore`, `test_partial_mode_restores_only_unchanged`, and `test_undo_cannot_overwrite_newer_import`. |
| Today snooze vs reminder delivery | PASS after C-08 regression | `test_c08_cross_feature_acceptance.py::test_today_snooze_hides_action_without_rescheduling_reminder` proves snooze visibility state does not mutate follow-up or reminder occurrence/schedule/status/version. |

## Accessibility and UI acceptance

The browser suite exercises authenticated navigation and the core workflows for Dashboard, Today, Applications, documents, capture, imports, reminders, contacts/interviews, archive/undo, duplicates, saved views, pipeline, and analytics. C-06 explicitly covers failure/cancel/focus paths and timezone-sensitive `datetime-local` behavior.

C-08 classifies the existing generic React bookmarklet warning and build-size warning as non-blocking only when they do not produce a product-console exception or failed build. C-08 does not authorize silencing warnings by rewriting working architecture. The hosted production build and browser jobs remain the release signal.

Responsive acceptance is bounded to core workflow usability at narrow mobile viewport (390 px class) and normal desktop. The browser suite is the automated product check; staging C-10 remains the final deployed visual/browser check.

## Performance and boundedness

C-08 does not invent a production latency SLA from a shared CI runner. It accepts deterministic product bounds and records measurements instead:

- import hard limits: 10 MiB and 2,000 records; over-limit requests produce zero destination writes;
- import maximum fixture: 2,000 records is parsed/committed while recording query count and elapsed time in `test_jg060_import_acceptance.py::test_maximum_fixture_records_actual_counts_queries_and_runtime`;
- retention cleanup: at most 500 eligible rows per batch, with deterministic resume;
- Today: each source performs bounded candidate reads and the C-04 large fixture verifies mixed pagination/query boundedness;
- list/export/top-five flows use server pagination and bounded top-five selection rather than loading an unbounded result into popup logic;
- document/import/backup byte/record limits are enforced before unsafe writes where the owning contract defines them.

Absolute production response-time and memory targets require deployed representative infrastructure and belong to C-09/C-10 observation. A slow but functionally bounded shared CI runner is not silently reclassified as a product acceptance failure.

## Local validation commands

C-08 is validated by the C-07 release matrix on the exact candidate SHA. The required hosted checks are:

- `Frontend Build`
- `E2E Tests (Playwright)`
- `Backend Compile Check`
- `Backend Tests (pytest)`
- `Backend Tests (SQLite)`
- `C-06 Browser Timezones`

The branch additionally adds the focused C-08 cross-feature backend regression. The exact final run IDs and head SHA are recorded on issue #170 / the C-08 PR after the final repository change, so an evidence-only commit cannot invalidate the SHA that was actually tested.

## External gates intentionally not closed by C-08

The following stay explicit rather than being converted to false local PASS results:

1. real provider OAuth login/callback;
2. controlled SMTP receipt in an authorized inbox;
3. durable private document storage surviving deployed restart/redeploy;
4. staging backup export/restore against disposable staging data;
5. deployed frontend/backend smoke and real Chrome popup policy;
6. old-code/schema-compatible rollback rehearsal;
7. provider/runtime observation and production release evidence.

These are C-09/C-10 requirements. C-08 completion means local product acceptance is closed and the staging candidate is evidence-ready.

## C-08 final verdict

**PASS when the exact C-08 PR head is green across the required C-07 matrix.**

No local P1/P2 product defect may be silently deferred. If hosted validation exposes one, this document returns to pending until the failure is reproduced, repaired, and the affected matrix is green again.
