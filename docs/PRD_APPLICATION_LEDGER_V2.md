# Product Requirements Document: JobGrid Application Ledger 2.0

**Document status:** Proposed, implementation not started
**Version:** 1.0
**Prepared:** November 14, 2026
**Owner:** JobGrid
**Workstream:** AL-01 through AL-22
**Execution tracker:** [development.md](../development.md)
**Prior related contracts:** [Application memory plan](application-memory-plan.md), [JobGrid build guide](JOBGRID_BUILD_GUIDE.md), [Extension pilot README](../extension/README.md)

## 1. Problem and outcome

The product already tracks job links and includes an Applications page, application lifecycle events, company history, and an extension pilot. Users still cannot reliably answer: **Which jobs have I submitted, when did I submit them, and what happened afterward?** A submitted job may move from Applied to Interview or Rejected, and a filter based only on current status no longer shows it as a past application. Opening or saving a job is also easily confused with submitting one. The Chrome release extension is inactive, so browsing external sites does not automatically capture confirmed applications.

**Outcome:** An account-owned, durable, searchable history of explicitly confirmed submissions. It remains discoverable after a stage change, reload, sign-in, or deletion of its source CSV row, and never claims that opening a page is proof of application.

## 2. Goals and measurable acceptance

1. The Ever Applied view and lifetime export include every known confirmed submission, including records whose current status is Interview, Rejected, or Offer.
2. A normal status change never clears `applied_at` or deletes a `first_applied` event. Corrections are reasoned and auditable.
3. A user can record a real submission without first importing a CSV.
4. Existing CSV-backed and manual entries are deduplicated conservatively with clear warnings instead of silent merge or overwrite.
5. History persists across sessions and survives source CSV deletion. Access is scoped to the authenticated owner.
6. Historical records can be backfilled with preview, validation, and source provenance, with no fabricated dates.
7. All user-visible counts, filters, exports, and lifetime definitions agree for the same scope.

**Release indicators:** All applicable acceptance tests pass on PostgreSQL and SQLite, frontend build and browser tests pass, staging checks use a consented test account, and production is promoted only after separate approval. No target count of applications is invented.

## 3. Existing system and verified gaps

- `backend/app/models.py` already provides `JobTrack` with owner, URL, status, `opened_at`, `applied_at`, and optional `csv_row_id`. Owner/URL is unique, so the existing track model represents one current track per exact URL.
- `backend/app/services/lifecycle.py` records `first_applied` facts and preserves the first date on ordinary status changes.
- `backend/app/services/row_queries.py` supports `applied_only` using non-null `applied_at`, but current status filtering is independent.
- `frontend/src/pages/Applications.jsx` implements an Applied-only export by sending `status='applied'`, which excludes transitioned records. The existing query serializer already exposes `appliedOnly`.
- `frontend/src/pages/Dashboard.jsx` uses `showAppStatus={!isAnmolView}`, hiding the application-status column in that preset. "Send to Applications" creates a track without confirming submission; "Mark applied" confirms it.
- `frontend/src/pages/Capture.jsx` saves a job without recording either a visit or a submission. Preserve that distinction.
- Company history, application evidence/timeline, reminders, CSV export, authentication, duplicate matching, and portable backup/restore already exist. Reuse them.
- The release Chrome extension manifest is inert. Its development popup can ask for confirmation, but production Chrome acceptance and release gates are separate.

This PRD describes required changes, not a claim that deployed application persistence or all production workflows were tested.

## 4. Core vocabulary and invariant

| Concept | Definition | Must not imply |
| --- | --- | --- |
| Saved | Job information captured from CSV or manually | Opened, submitted |
| Visited | A job page was opened or a distinct visit was recorded | Submitted |
| Tracked | A JobTrack entry exists | Confirmed submission |
| Ever Applied | Durable, explicit confirmation of at least one real submission for that role | Current status is necessarily Applied |
| First applied | Original submission date/fact, not overwritten on routine stage changes | Date of last status update |
| Current stage | Present workflow state: opened, applied, follow_up, interview, rejected, offer, not_applying | Entire history |
| Possible match | Exact/canonical or company-level prior evidence requiring review | Definitive duplicate without proof |

**Initial data contract:** For existing dated tracks, `applied_at IS NOT NULL` is the existing read-side Ever Applied predicate. Reconcile it with `first_applied` ledger evidence as part of AL-01. Do not silently backfill missing dates or replace facts based on status alone. Any historical unknown-date records require an explicit model decision in AL-19.

**Semantics:** `not_applying` or `rejected` may legitimately describe the current stage of a previously submitted application. "Ever Applied" must still include such records when an explicit prior submission exists. If a status says `applied` but no first-applied evidence/date exists, flag it for reconciliation rather than inventing a fact.

## 5. User journeys

### A. Find every application I submitted

1. Open Applications > My Applications > **Ever Applied**.
2. Default scope is **all time**, sorted by first applied date descending, with stable tie-breaks; missing dates appear separately and clearly.
3. Search company, title, or URL; optionally filter current stage, company, submission date, and due follow-up.
4. Open a row to see first applied date, current stage, lifecycle timeline, evidence, notes, and follow-up.
5. Export **Ever Applied** to CSV/JSON with the same account-scoped result semantics as the view, regardless of page boundaries.

### B. Track an application from a CSV

1. Select one or more jobs on Job Links.
2. **Send to Applications** creates an entry to track, but does not mark it submitted.
3. **Mark applied** is a distinct explicit confirmation that records the submission and first applied date.
4. Later interview, rejection, or offer updates change only current stage, not historical submission existence.
5. A clear success receipt is shown only after the server confirms persistence; errors or uncertain write outcomes are not labeled success.

### C. Add a real application outside the imported CSV

1. Select **Add application**, not **Capture job**.
2. Enter a safe HTTP(S) job URL, employer name, role title, and known submission date. Notes/follow-up are optional.
3. Before saving, check exact/canonical prior application matches and possible company history. Present conflicting or uncertain results without an automatic destructive merge.
4. User reviews the account, target URL, fields, and explicit applied confirmation.
5. The API creates or intentionally reuses the account-owned track and first-applied fact in one transaction, with an idempotent request key and a clear persisted receipt.
6. No external application is submitted, and no synthetic visit or CSV click is recorded.

### D. Recover older applications

1. Upload a CSV export of historical records, or map records from an existing verified import path.
2. Run no-write preview, showing schema errors, missing dates/URLs, exact/canonical matches, potential company duplicates, and proposed changes.
3. Confirm only valid records with explicit submission provenance. Keep unknown-date and repeated-submission cases out of automatic mutation until AL-19 architecture is approved.
4. Commit in a bounded, idempotent owner-scoped transaction; show per-record receipts, rejected reasons, and a recovery strategy.
5. Verify export, lifecycle history, backup, and restore round-trip after acceptance.

## 6. Interface requirements

- Tabs or views: **Ever Applied**, **All Tracked**, **Follow-ups**. Status remains a separate facet; changing stage does not remove an item from lifetime history.
- Cards: lifetime submitted, interviews, offers, and due follow-ups with tooltips documenting exact scope. Cards must not derive lifetime applications solely from current status.
- Table: employer, role, first applied date, current stage, last change, follow-up, and application link. Include sorting, owner-safe pagination, and clear unknown-date labels.
- Add Application form: progressive validation, duplicate context, disabled concurrent submit, accessible errors, retry guidance, and a confirmed save receipt.
- Existing company/timeline/evidence views remain linked. First-date corrections require a reason through existing correction flows.
- Keep App Status visible in Anmol's View. Distinguish **Visited**, **Saved**, **Send to Applications**, and **Mark applied** in copy.
- List, filtered export, lifetime export, saved-view URLs, and analytics must use compatible query rules and full-result semantics, not just the current page.
- Empty state must distinguish no tracked jobs, no confirmed applications, empty filtered results, and failed loading.

## 7. API and data contract plan

### 7.1 Reuse before adding

- Reuse `GET /crm/applications` with `applied_only=true` and existing `date_applied_from` / `date_applied_to`, pagination, sort, and stage filters.
- Reuse `GET /crm/export/applications` with `applied_only=true` for Ever Applied exports. Eliminate the frontend-only `status='applied'` shortcut. Confirm the actual route prefix in `frontend/src/api/client.js` before implementation.
- Reuse `POST /crm/from-rows/bulk` for explicit CSV-backed Mark applied, and `PATCH /crm/applications/{item_id}` for stage changes and reasoned corrections.
- Reuse canonical identity matching and `first_applied` lifecycle services, with existing owner and idempotency boundaries.

### 7.2 Proposed manual add endpoint

Proposed `POST /crm/applications`, subject to final collision audit, with validated body: `url`, `company`, `title`, `applied_at` (known dated submission), optional `notes` and `follow_up_at`. Require an existing authenticated session and stable idempotency/operation key. Server returns a persisted application ID, saved status/date, and a clear new-vs-existing result. Missing or foreign IDs, unsafe URLs, invalid dates, ambiguous duplicate matches, and conflicting retries must fail without partial writes. Reject duplicate exact/canonical applications unless the user explicitly chooses a reviewed supported action. Do not overwrite curated metadata or earlier dates.

Do not add a new public write endpoint until existing capture, browser-memory apply, and external import writers are evaluated for reuse.

### 7.3 Unknown-date and repeat-submission architecture gate

`JobTrack` currently requires a URL and has one track per owner/exact URL. Existing metrics and `first_applied` facts use timestamps. Those constraints cannot honestly encode every historical "applied, date unknown" or a later reapplication to the same role.

For AL-19, approve an ADR comparing:
- A separate owner-scoped submission fact with nullable known submission time and explicit `date_precision` / source provenance.
- An additive extension to the existing track/ledger if it can preserve first-applied semantics and backup compatibility.

No fake URL, synthetic submission date, synthetic first-applied lifecycle event, or silent historical count increase is allowed. Until the ADR is approved, imports with unknown dates or unresolvable role identity remain in a review queue. Do not loosen the invariant just to make a backfill pass.

## 8. Integrity, privacy, security, and resilience

- All read and write queries require the authenticated user and filter by `user_id`; never rely on client-provided owner IDs.
- Persist original first-applied facts and dates through stage changes, source CSV deletion, re-import, restoration, and pagination.
- Request replay is idempotent. A lost response is "save result unknown" until server confirmation or re-query.
- Show exact/canonical and company-level matches with confidence boundaries. Do not infer definitive submission or employer from a visit or ATS hostname.
- Never automatically read application form answers, submit external job applications, or collect OAuth cookies/credentials in new features.
- Limit payload size and CSV row count, validate schema, refuse formula-injection on CSV export, and avoid logging private URLs, notes, or application contents.
- Validate timezone transformations, date range boundaries, owner isolation, unique constraints, and concurrency on SQLite and PostgreSQL.
- Preserve existing backup version compatibility or explicitly version a new format. Migration must be additive with documented recovery, no destructive rollback.

## 9. Delivery phases and scoped PRs

| PR | Work items | Deliverable | Dependency |
| --- | --- | --- | --- |
| 1: Existing history correctness | AL-01 to AL-06 | Reliable Ever Applied query/export, dates, visible status, regressions | None |
| 2: My Applications UX | AL-07 to AL-12 | Lifetime dashboard, detail workflow, filters, view tests | PR 1 |
| 3: Manual record of submission | AL-13 to AL-17 | Validated submission endpoint, safe UI and idempotency | PR 1 and 2 |
| 4: Historical recovery | AL-18 to AL-22 | ADR, preview, safe import, backup/restore and staging acceptance | PR 1 through 3 |
| Separate Chrome extension | Existing EXT release tickets | Real-user opt-in Chrome integration | Independent staged acceptance, never assumed live |

Each AL item is a small reviewable commit with a targeted test or evidence artifact. All start open. This document is a proposed contract, not implementation or deployment evidence.

## 10. Implementation backlog and definition of done

- [ ] **AL-01 | P1 | Audit application truth:** Inventory JobTrack, first_applied lifecycle events, status transitions, query/export/analytics contracts; document existing bad or ambiguous records without mutating data.
- [ ] **AL-02 | P1 | Canonical Ever Applied filter:** Use applied_only and recorded first-applied evidence, independent of current stage; document legacy exceptions; keep current status filtering separate.
- [ ] **AL-03 | P1 | Correct Applied-only export:** Make CSV/JSON export use the same lifetime applied predicate and date boundaries as list view; include transitioned interview, offer, and rejected roles.
- [ ] **AL-04 | P1 | Separate application and open dates:** Support applied_at date filtering and sorting, preserve opened_at filters, clarify quick-range meanings, and default My Applications to all-time.
- [ ] **AL-05 | P1 | Show status in Anmol's View:** Remove the preset-specific showAppStatus suppression and keep bulk Mark applied vs Send to Applications actions clear.
- [ ] **AL-06 | P1 | Protect historical truth with tests:** Add PostgreSQL/SQLite and browser regressions for transitions, replays, deletion, auth, and list/export parity.
- [ ] **AL-07 | P2 | Build My Applications views:** Provide Ever Applied, All Tracked, and Follow-ups views with stable URLs, pagination, search, and accessible empty/error states.
- [ ] **AL-08 | P2 | Add accurate summary cards:** Show lifetime applied, interview, offer, and due-follow-up counts using documented semantics; reconcile with analytics without double counting.
- [ ] **AL-09 | P2 | Design application list:** Show company, role, first applied date, latest stage, last update, and follow-up; sort predictably and show unknown values explicitly.
- [ ] **AL-10 | P2 | Improve detail and history:** Reuse existing timeline/evidence, follow-up, and company history components; preserve deep links and date corrections requiring reasons.
- [ ] **AL-11 | P2 | Unify filters and export:** Keep saved-view query serialization, full-results filtering, and selected/filtered/lifetime exports consistent under pagination.
- [ ] **AL-12 | P2 | Complete UI acceptance:** Run keyboard, narrow-screen, browser, stale request, error, and server pagination tests; verify no regressions to Dashboard.
- [ ] **AL-13 | P3 | Specify manual submission contract:** Add explicit submission confirmation using a valid job URL, company, title, application date, and account ownership, separate from Capture.
- [ ] **AL-14 | P3 | Implement safe application create API:** Add owner-scoped POST /crm/applications with validated fields and stable request idempotency; write JobTrack and first_applied fact atomically.
- [ ] **AL-15 | P3 | Prevent duplicate or destructive edits:** Reuse exact/canonical lookup, show company-level possible matches, return conflicts for uncertain matches, and never silently overwrite a prior date.
- [ ] **AL-16 | P3 | Ship Add Application UI:** Support manual entry without CSV, date/time zone handling, clear validation, pending/unknown results, and explicit save receipt.
- [ ] **AL-17 | P3 | Verify manual-entry behavior:** Test new and existing links, auth isolation, retries, conflicting writes, no synthetic click/visit, and audit/backup parity.
- [ ] **AL-18 | P4 | Audit existing import and backup paths:** Evaluate /crm/import/external, CSV source independence, portable backups, evidence, and first-applied migration constraints before designing bulk backfill.
- [ ] **AL-19 | P4 | Resolve unknown date and reapplication ADR:** Choose a nonfabricating, owner-scoped model for date-unknown submissions and repeated applications; approve any additive migration before implementation.
- [ ] **AL-20 | P4 | Implement historical import preview:** Accept reviewed CSV mapping, explicit provenance, duplicate detection, missing-field warnings, and a no-write preview for all candidate rows.
- [ ] **AL-21 | P4 | Add safe commit and recovery:** Require explicit confirmation; write idempotent owner-scoped application facts transactionally, avoid changing existing curated statuses/dates, and support recovery.
- [ ] **AL-22 | P4 | Close import and release acceptance:** Verify backup/restore, exact/canonical collisions, unknown-date cases, PostgreSQL/SQLite CI, staging and documented rollout/rollback gates.

Every task must include a code or evidence change, a focused test command/result, owner and date-safety assessment, scoped diff review, docs update when contracts change, and a Git commit. For PR completion, require applicable backend PostgreSQL/SQLite suites, frontend production build, Playwright E2E, release-contract tests, a staging verification report, and explicit rollback instructions. CI-green is not evidence of a real Chrome session or live external submission.

## 11. Scenario-based acceptance matrix

| Test | Expected result |
| --- | --- |
| Mark a CSV job applied, then set Interview, Rejected, or Offer | Remains in Ever Applied and lifetime export with original date |
| Set current stage to Applied, then retry | No duplicate first-applied event or silently shifted date |
| Open or capture a job without application confirmation | Not counted as applied |
| Delete source CSV row | Application, lifecycle event, and company history survive |
| Search and export across more than one page | Same matching full-result set and stable order |
| Saved filters plus export after stage change | Lifetime scope and stage facet remain distinct |
| Manual submission on an unimported URL | One durable owner record, no fake click/visit |
| Replay/timeout and concurrent duplicate create | No double insert, no false success, no metadata clobber |
| Second authenticated account reads/writes another's ID | Denied with no leaked metadata |
| Import legacy record with unknown date | Held for review without invented timestamp |
| Backup/export and isolated restore | Owner, first date, provenance, and source independence survive |
| Backend unavailable or rate-limited | Explicit error/retry state, no claim of successful submission |

## 12. Non-goals and release boundaries

- No application autopilot, external submission, scraping of private form data, or automatic guessing that a page visit means applying.
- No new paid service or cloud provider.
- No automatic activation or publication of the existing Chrome extension.
- No retroactive rewriting of lifetime statistics, fabricated application dates, or speculative backfill.
- No production migration, deployment, or data writes as part of documentation planning.

## 13. Open product decisions

1. Should a genuine reapplication to one exact job URL create a new submission event or a separate application instance? Default: flag for AL-19 and preserve existing record.
2. How should first-applied date precision be represented for a valid historic submission with an unknown day? Resolve in AL-19 before import.
3. Which stage categories belong in cards named "Interviews" and "Offers": current stage or ever reached? Label counts explicitly and align with analytics.
4. What is the approved import limit and recovery receipt retention? Decide before shipping AL-20 and AL-21.

## 14. Authoritative references and history

- [`development.md`](../development.md) tracks the active AL tasks.
- [`docs/application-memory-plan.md`](application-memory-plan.md) is the prior application-memory contract. Its completed items are not reopened.
- [`jg.md`](../jg.md) remains the broad project completion guide.
- [Prior `development.md` snapshot at 20424e5](https://github.com/anmolsansi/CSV_Website/blob/20424e540c4dbe6479da237f8df77abf37fb76a6/development.md) preserves the earlier large roadmap before the November 14 reset.
- [`extension/README.md`](../extension/README.md) owns the separate Chrome extension release and privacy gates.
