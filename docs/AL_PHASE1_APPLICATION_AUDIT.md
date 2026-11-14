# AL Phase 1: Application truth audit and compatibility decision

**Baseline:** main at `bbc6a10a076509e22c010dbf8cbdae9498fc5707` (November 14, 2026)
**Status:** Static repository audit only. No production database, account, or hosted persistence was inspected.
**Track:** [AL-01–AL-06](../development.md), [PRD](PRD_APPLICATION_LEDGER_V2.md), [issue #204](https://github.com/anmolsansi/CSV_Website/issues/204)

## What the current code guarantees

| Concern | Existing implementation | Phase 1 decision |
| --- | --- | --- |
| Submission identity | `JobTrack` is scoped by `user_id`; it stores `status`, `applied_at`, `csv_row_id`, and URL in `backend/app/models.py`. | Reuse these fields and keep owner scope. No schema migration. |
| First submission | `apply_job_track_changes` in `backend/app/services/lifecycle.py` records the first `applied_at` and writes `first_applied` on first confirmation; stage transitions do not clear the date. | Never infer submission from opening or saving. Preserve first date and ledger. |
| Lifetime list | `build_application_query` in `backend/app/services/row_queries.py` implements `applied_only` with `JobTrack.applied_at.isnot(None)`. `GET /crm/applications` passes that filter. | Make it discoverable in UI as **Ever applied**. Keep stage as an independent filter. |
| Lifetime export | `GET /crm/export/applications` reuses `build_application_query` for filtered exports, including `applied_only`. | Reuse `scope=filtered&applied_only=true`, never substitute current `status=applied`. |
| Actual frontend bug | `Applications.jsx` Applied-only scope overrides filters with `status: 'applied'`. | Correct frontend request; preserve active search, company and application-date bounds. |
| Date dimensions | `date_from` and quick ranges compare **opened_at**. `date_applied_from` / `date_applied_to` compare **applied_at**. Sort `applied_at` already supported. | Label opened and applied dates clearly and expose application-date range controls without changing API. Date-to comparison is exclusive. |
| Dashboard status | `Dashboard.jsx` suppresses `showAppStatus` when Anmol's View is active. | Always show the existing App Status display; keep explicit Mark applied separate from Send to Applications. |
| CSV source deletion | `test_application_memory.py` asserts `JobTrack` survives source row deletion. | Add proof that Ever applied still lists/exports it after deletion. |
| Existing validation | `GET /crm/applications/validation-report` reports legacy invalid counts with `repair_mode: manual_only`. | Keep audit and repair manual. Do not auto-repair historical dates or status. |

## Ledger consistency and missing-date limitation

`JobTrack.applied_at IS NOT NULL` is the existing dated-submission read predicate. `first_applied` is the immutable historical event. If a legacy or restored record has one but not the other, **do not silently repair it**. Surface the existing authenticated, read-only `/crm/applications/validation-report` and investigate a real account-owned discrepancy before proposing a backfill. A historical submission with unknown date is outside Phase 1 and awaits AL-19's ADR. A current status of `applied` alone does **not** prove a dated submission.

**Two options considered:**
1. **Reuse applied_at and existing query/export contracts (selected).** Low change risk, no migration, owner-scoped, predictable and reversible. It does not pretend that corrupt legacy records are fixed.
2. **Make an OR join to lifecycle events or create a new application fact table (deferred).** Could expose event-only legacy records, but requires resolving mismatched status/date data, possible duplicate identities and new sorting/backup semantics. Not justified for the narrow frontend bug.

**Needs Architect Decision (future):** A portable read model for genuinely confirmed submissions with unknown date or repeated applications to the same URL. AL-19 owns this decision; do not fabricate dates.

## Phase 1 contracts

- List: `GET /crm/applications?applied_only=true`, optionally `status=interview`, `date_applied_from=<ISO UTC>`, `date_applied_to=<ISO UTC>`, `sort_by=applied_at&sort_dir=desc`. Page and page size affect only listing.
- Export: `GET /crm/export/applications?scope=filtered&applied_only=true` with identical filters and sort; no page limiting. CSV and JSON use the same owner-scoped query, and `scope=all` intentionally ignores filters.
- UI: status filter affects current stage only. **Ever applied** checkbox affects historical submission existence. **Opened, not applied** is incompatible with Ever applied and should be disabled automatically when the other is chosen.
- Time: browser `datetime-local` input is local wall time, converted to UTC ISO for applied-date filter requests. Backend `parse_dt` normalizes aware ISO to UTC naive timestamps. Both applied-date upper and lower bounds use existing half-open [from, to) semantics.
- Sort: existing `order_application_query` has `JobTrack.id.desc()` tie-break for equal/null applied timestamps.

## Risk, staging, recovery

No backend write path or public API needs modification. Branch rollback is a normal revert of frontend, tests and docs; durable history is untouched. A green build/CI does not prove historical data in a hosted account is complete. Verify with a consented staging account before production release, including a job that moves Applied > Interview > Rejected and has its CSV row deleted. Validate both JSON/CSV exports, page 2, a second user, and an applied-date boundary. The browser extension is outside this workstream.

## Where to verify

- Backend: `backend/tests/test_application_memory.py` and `backend/tests/test_filtered_exports.py`
- Frontend: `frontend/tests/applications.spec.ts`, `frontend/tests/filter-export-parity.spec.ts`, `frontend/tests/dashboard.spec.ts`
- Build/CI: repository workflows; the existing `docs/JOBGRID_BUILD_GUIDE.md` documents runtime, export contracts and staging requirements.
