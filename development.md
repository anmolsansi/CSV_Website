# JobGrid Development Roadmap

**Updated:** November 14, 2026  
**Status:** AL Phase 1 code and CI merged in PR #205, hosted acceptance not verified. AL Phase 2 implementation is in review on branch `al-phase2-my-applications`. Phases 3 and 4 remain planned.  
**Repository:** [anmolsansi/CSV_Website](https://github.com/anmolsansi/CSV_Website)

## Current priority: Application Ledger 2.0

**Product Requirements Document:** [`docs/PRD_APPLICATION_LEDGER_V2.md`](docs/PRD_APPLICATION_LEDGER_V2.md)

**Phase 1 implementation review:** [PR #205](https://github.com/anmolsansi/CSV_Website/pull/205) · [tracking issue #204](https://github.com/anmolsansi/CSV_Website/issues/204) · [contract audit](docs/AL_PHASE1_APPLICATION_AUDIT.md)

The branch `al-phase1-application-ledger` includes the Ever Applied filter,
historical CSV/JSON export correction, separate opened/applied date controls,
Anmol View status visibility, and backend/Playwright regressions.
Implementation commits and passing individual checks do **not** authorize a
production release. Keep AL-01–AL-06 checkboxes open until the focused CI gate,
integration review, and approved staging verification are recorded. No
production history was repaired or migrated.


**Phase 2 implementation:** [tracking issue #206](https://github.com/anmolsansi/CSV_Website/issues/206) · [architecture](docs/AL_PHASE2_ARCHITECTURE.md) · [UI usage and test guide](docs/AL_PHASE2_UI_GUIDE.md). Phase 2 work is on a dedicated branch. Keep AL-07–AL-12 checklist entries unchecked until the final CI/acceptance gate is recorded. No production/staging rollout is authorized.\n\n**Goal:** Make every explicitly confirmed job application discoverable for life, independent of its current stage, source CSV, or browser session. An opened or saved job is not an applied job.

**Why:** JobGrid already stores `JobTrack` state, `applied_at`, first-applied lifecycle events, company history, and export data, but the Applied-only UI export filters current `status='applied'`. That omits previously submitted jobs now in Interview, Rejected, or Offer. The Dashboard's Anmol's View also hides App Status. The existing Chrome extension is not an active production submission tracker.

**Implementation boundary:** This is a documentation-only roadmap. No production mutation, data backfill, deployment, or active Chrome release is authorized here. Preserve existing historical facts, owner isolation, and compatibility.

### Delivery order

| PR | Tasks | Purpose | Exit gate |
| --- | --- | --- | --- |
| PR 1 | AL-01 to AL-06 | Fix Ever Applied truth, export parity, date filters, and status visibility | Backend and UI parity regressions pass |
| PR 2 | AL-07 to AL-12 | My Applications lifetime view, details, counts, search, exports | UI, accessibility, and browser tests pass |
| PR 3 | AL-13 to AL-17 | Explicit Add Application flow without a CSV | Atomic persistence, identity and replay checks pass |
| PR 4 | AL-18 to AL-22 | Historical import, missing-date ADR, safety and recovery | Approved schema decision, preview/commit and restore tests pass |
| Separate | Existing EXT tickets | Optional Chrome-assisted warnings and explicit saves | Real Chrome, permissions, account, staging, and release gates |

### Microtask checklist

#### P1 · Correct the existing ledger

- [ ] **AL-01 — Audit application truth:** Inventory JobTrack, first_applied lifecycle events, status transitions, query/export/analytics contracts; document existing bad or ambiguous records without mutating data.
- [ ] **AL-02 — Canonical Ever Applied filter:** Use applied_only and recorded first-applied evidence, independent of current stage; document legacy exceptions; keep current status filtering separate.
- [ ] **AL-03 — Correct Applied-only export:** Make CSV/JSON export use the same lifetime applied predicate and date boundaries as list view; include transitioned interview, offer, and rejected roles.
- [ ] **AL-04 — Separate application and open dates:** Support applied_at date filtering and sorting, preserve opened_at filters, clarify quick-range meanings, and default My Applications to all-time.
- [ ] **AL-05 — Show status in Anmol's View:** Remove the preset-specific showAppStatus suppression and keep bulk Mark applied vs Send to Applications actions clear.
- [ ] **AL-06 — Protect historical truth with tests:** Add PostgreSQL/SQLite and browser regressions for transitions, replays, deletion, auth, and list/export parity.

#### P2 · My Applications user experience

- [ ] **AL-07 — Build My Applications views:** Provide Ever Applied, All Tracked, and Follow-ups views with stable URLs, pagination, search, and accessible empty/error states.
- [ ] **AL-08 — Add accurate summary cards:** Show lifetime applied, interview, offer, and due-follow-up counts using documented semantics; reconcile with analytics without double counting.
- [ ] **AL-09 — Design application list:** Show company, role, first applied date, latest stage, last update, and follow-up; sort predictably and show unknown values explicitly.
- [ ] **AL-10 — Improve detail and history:** Reuse existing timeline/evidence, follow-up, and company history components; preserve deep links and date corrections requiring reasons.
- [ ] **AL-11 — Unify filters and export:** Keep saved-view query serialization, full-results filtering, and selected/filtered/lifetime exports consistent under pagination.
- [ ] **AL-12 — Complete UI acceptance:** Run keyboard, narrow-screen, browser, stale request, error, and server pagination tests; verify no regressions to Dashboard.

#### P3 · Manual application submission

- [ ] **AL-13 — Specify manual submission contract:** Add explicit submission confirmation using a valid job URL, company, title, application date, and account ownership, separate from Capture.
- [ ] **AL-14 — Implement safe application create API:** Add owner-scoped POST /crm/applications with validated fields and stable request idempotency; write JobTrack and first_applied fact atomically.
- [ ] **AL-15 — Prevent duplicate or destructive edits:** Reuse exact/canonical lookup, show company-level possible matches, return conflicts for uncertain matches, and never silently overwrite a prior date.
- [ ] **AL-16 — Ship Add Application UI:** Support manual entry without CSV, date/time zone handling, clear validation, pending/unknown results, and explicit save receipt.
- [ ] **AL-17 — Verify manual-entry behavior:** Test new and existing links, auth isolation, retries, conflicting writes, no synthetic click/visit, and audit/backup parity.

#### P4 · Historical backfill and recovery

- [ ] **AL-18 — Audit existing import and backup paths:** Evaluate /crm/import/external, CSV source independence, portable backups, evidence, and first-applied migration constraints before designing bulk backfill.
- [ ] **AL-19 — Resolve unknown date and reapplication ADR:** Choose a nonfabricating, owner-scoped model for date-unknown submissions and repeated applications; approve any additive migration before implementation.
- [ ] **AL-20 — Implement historical import preview:** Accept reviewed CSV mapping, explicit provenance, duplicate detection, missing-field warnings, and a no-write preview for all candidate rows.
- [ ] **AL-21 — Add safe commit and recovery:** Require explicit confirmation; write idempotent owner-scoped application facts transactionally, avoid changing existing curated statuses/dates, and support recovery.
- [ ] **AL-22 — Close import and release acceptance:** Verify backup/restore, exact/canonical collisions, unknown-date cases, PostgreSQL/SQLite CI, staging and documented rollout/rollback gates.

### Key invariants and decisions

- **Ever Applied** is historical proof of an explicit application, not the current stage. Reuse the existing `applied_only` predicate initially and reconcile it with `first_applied` event evidence. Do not silently invent missing dates.
- **Track, open, and apply remain separate.** "Send to Applications" must not imply submission, and captured/saved/visited jobs are not counted as applied.
- **Historical evidence is durable.** First applied date and lifecycle events remain through status changes, reload, CSV deletion, and restore. Date corrections require a reason.
- **Account isolation is mandatory.** Owner-scoped queries, idempotent writes, safe duplicates and confirmed save receipts are release blockers.
- **Unknown dates and reapplications need an ADR.** The existing unique owner/URL track and timestamp-ledger contracts cannot encode both safely without a reviewed design. AL-19 must settle that before Phase 4 mutation work.
- **Export/list/analytics semantics must agree.** Lifetime submissions are not equivalent to `status='applied'`; current status is an independent facet.
- **Chrome release is separate.** The existing production extension shell is inert and must not be reported as automatic application capture.

### Working agreement and acceptance

Each AL microtask receives a scoped commit, narrow tests, code review, documentation impact check, and recorded evidence. Keep every checkbox open until its acceptance passes. Review each phase in a focused pull request. An approved PR or green CI is not proof of production/staging acceptance.

Before production release, prove: applied to interview/rejected/offer stays in lifetime view and export; first date is preserved across retries; a CSV source deletion does not erase history; manual submission creates no synthetic visit; full pagination/search/export remain consistent; foreign account access fails; unknown dates are never fabricated; backup and isolated restore retain facts. Run applicable PostgreSQL/SQLite backend tests, frontend build, Playwright E2E and staging checks. No production deployment without separate approval.

### Related roadmap and historical reference

- [Product requirements and complete AL-01 through AL-22 acceptance contract](docs/PRD_APPLICATION_LEDGER_V2.md)
- [Original completed application-memory plan](docs/application-memory-plan.md)
- [Broad existing project completion guide](jg.md)
- [Current JobGrid engineering build guide](docs/JOBGRID_BUILD_GUIDE.md)
- [Existing Chrome extension acceptance and release gates](extension/README.md)
- [Prior large `development.md` snapshot before the November 14 reset](https://github.com/anmolsansi/CSV_Website/blob/20424e540c4dbe6479da237f8df77abf37fb76a6/development.md)

**Backlog status:** 0/22 AL items complete. All IDs and planned PR groupings are defined here, not yet assigned to implementation commits.
