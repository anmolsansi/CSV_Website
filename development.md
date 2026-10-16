# JobGrid — Development, Verification, and Deployment Guide

Updated: **2026-10-16** (Chrome extension plan added; existing release audit remains dated September 30)\
Release-audit main: **`c56cb83195ab1ac5cd691860c77cf1e85e1805dc`**\
Overall: **Local product acceptance complete; branch enforcement, live operations, staging acceptance, and final release closeout remain.**

This is the primary execution guide. C-01–C-06 and C-08 are completed for their repository/local scope. C-07 workflows pass, but branch protection is missing. C-09 is repository-ready with external proof outstanding; C-10–C-12 remain open. A historical deployment does not establish complete staging or release acceptance.

The September 30 audit compared current source, merged PRs, hosted checks, open issues, and repository settings. It did not rerun the full application suite or certify all live providers. The two unrelated untracked files were preserved. Older audit findings below are historical, not a fresh list of defects.

Current hosted evidence at the audited SHA:

- [Standard CI](https://github.com/anmolsansi/CSV_Website/actions/runs/36488146501): success.
- [SQLite release](https://github.com/anmolsansi/CSV_Website/actions/runs/36488146479): success.
- [Browser timezones](https://github.com/anmolsansi/CSV_Website/actions/runs/36488146485): success.
- GitHub reports `main` unprotected and no repository rulesets.
- No open PRs. Issues #172 (C-09) and #125 (JG-036) remain open; #125 is stale because PR #127 merged its implementation/tests.
- The live `/ready` request timed out after 45 seconds. Readiness remains unverified by this audit; one timeout is not a confirmed outage.

Use [C-08 acceptance](docs/C08_PRODUCT_ACCEPTANCE.md) for all 17 local feature packs. The [original specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md) and [jg.md](jg.md) retain historical planning detail. Their stale labels must not cause completed features to be rebuilt. Current `render.yaml` and PR #174 supersede older paid-disk and direct-S3 setup instructions.

<a id="remaining-work"></a>
## Remaining work in execution order

Every item below is **Not completed**. Retain the existing C/JG IDs; these rows are execution steps, not new feature tickets.

| Order | Owning task | What, why, and how | Completion proof |
|---|---|---|---|
| 1 | C-07.08 | Protect `main` and require Frontend Build, E2E Tests (Playwright), Backend Compile Check, Backend Tests (pytest), Backend Tests (SQLite), and C-06 Browser Timezones. Passing workflows currently do not prevent unchecked merges. | Read back protection/rulesets and verify the exact required job names. |
| 2 | C-09.02/05 | Verify the deployed candidate's `/ready`, synthetic upload/download hash, storage audit, restart/cache loss, redeploy, and ZIP document bytes. Health alone proves only liveness. | Same candidate, matching hashes before/after restart and redeploy, readiness and backup evidence. |
| 3 | C-09.02 | Record/version the actual storage gateway server source and deployment procedure in an agreed repository. This checkout contains the client and tests but no gateway server source. Include token rotation and rollback procedure without secrets. | Another operator can reproduce the deployed gateway and verify private access. |
| 4 | C-09.01/03/06 | Resolve the active frontend URL/project; verify API proxy, HTTPS, CORS, cookies, OAuth callbacks, and controlled synthetic accounts. Keep staging isolated from production data. | Recorded environment inventory plus controlled real login/account-isolation evidence. |
| 5 | C-09.07, C-10.01 | Agree RPO/RTO, backup schedule, retention, destination and owner; back up both PostgreSQL and private object bytes, then restore to disposable staging. Existing database-only scripts are insufficient for disaster recovery. | Compare schema, counts, relationships, object sizes/hashes and measured recovery time against agreed targets. |
| 6 | JG-040, C-10.03/04 | Resolve email transport for the selected free hosting topology. Code currently uses SMTP; the C-09 runbook flags standard SMTP-port restrictions. Verify provider support before choosing a supported transport or implementing an HTTP email adapter. | Explicitly authorized controlled inbox receipt, correct timezone/content, bounded retry and restart/deduplication evidence. |
| 7 | JG-024, C-10.02/05/06 | Run real OAuth and deployed original journeys, Today, imports, contacts, documents, backup and archive/undo on one candidate. Test actual Chrome popup allowance/blocking and capture in declared supported browsers. | Concrete expected/actual results with deployed frontend/backend revisions; local mocks are not provider proof. |
| 8 | C-09.04/08, C-10.07/08 | Rehearse old-code rollback and return to current code; verify history/files, worker claims/restart behavior, and visibility of an induced safe failure. | Unchanged data/hash comparisons, no lost work, documented ambiguous sends, visible operator signal. |
| 9 | C-11 | Reconcile remaining guides, roadmap labels, evidence links and issues. Close stale #125 against merged PR #127; rewrite #172's superseded paid-disk assumptions. Keep JG-024/JG-040 external gates open until proven. | Consistent status/evidence index and no contradictory topology or completion claims. |
| 10 | C-12 | After mandatory staging gates pass, record exact deployed revisions/IDs, perform production smoke, observe a defined window including scheduled execution, and hand over ownership/runbooks. | Production acceptance, observation results, rollback criteria, backup and operational owners recorded. |

## Navigation

- [Current remaining work](#remaining-work)
- [Scope and completion](#completion-definition)
- [Audit evidence](#audit-evidence)
- [Status rules](#status-rules)
- [Ordered work packages C-01–C-12](#work-order)
- [Repeatable local test commands](#test-commands)
- [All 64 original tickets and their development steps](#original-tickets)
- [GitHub, staging, and production deployment runbook](#deployment-runbook)
- [Final handover](#final-handover)
- [Chrome extension: product, contracts, and 50 microtasks](#chrome-extension-plan)
- [Detailed EXT-01–50 execution tickets](#extension-detailed-tickets)

<a id="completion-definition"></a>
## 1. What “complete” means

JobGrid is complete for this scope when the two original workflows and all 17 roadmap groups satisfy their acceptance contracts, the defects below have regression coverage, the supported database/browser combinations pass, and the same release candidate passes staging and production smoke checks.

- Remember applied jobs and companies durably per account. Application history survives reload, sign-in, and deletion of source CSV rows.
- Open at most five eligible unopened HTTP(S) links from the **entire active filtered and sorted result**, including jobs outside the visible page. Opening a link does not mean applying to a job.
- Deliver reliable backup/restore, filtering, analytics, retention, validation, numeric sorting, release gates, Today, identity matching, evidence, reminders, documents, capture, availability, contacts/interviews, imports, and undo/archive.
- Preserve ownership, reference integrity, deterministic ordering, retry behavior, and existing data through failures and releases.
- Record external acceptance separately. A merged PR, green CI, or local dev login is not proof of a production release.

**Boundary:** the browser opens tabs in the browser running the application. A website cannot force the user's separate Google Chrome installation to open. Test the requested workflow in Chrome and document popup permissions/manual fallback.

**Excluded from the original release scope:** new AI features, automated applications, new cloud services, enabling automatic purge by default, and large architectural rewrites. The Chrome extension is now a separately requested feature plan in [section 9](#chrome-extension-plan); it does not reopen completed C/JG work or establish extension implementation/release acceptance. No actual code fixes, staging actions, or deployment are performed by writing this guide.

<a id="audit-evidence"></a>
## 2. Evidence baseline and its limits

These historical results were obtained in the September 23 audit at `31d51d3e2d61626a13c1b02bc6c4126d3710e542`, using synthetic users and disposable databases. They are not the September 30 results; use the current evidence links above and focused C-package records for resolved defects.

| Check | Recorded result | Meaning |
|---|---|---|
| PostgreSQL backend suite | 580 passed | Current tests pass; independent probes still exposed defects |
| SQLite backend suite | 564 passed, 2 failed, 14 skipped | Two datetime assertion failures; PostgreSQL-only skips are not SQLite acceptance |
| Chromium full browser suite | 177 passed, 2 failed | Both failures concern timezone-dependent assertions |
| UTC rerun of the two browser failures plus setup | 3 passed | Supports test-timezone diagnosis; does not replace a multi-zone full run |
| Link helper tests | 8 passed | Helper behavior verified, separate from real popup policy |
| Frontend build | Passed | Bundle-size warning remains; build success is not workflow acceptance |
| Fresh PostgreSQL migration chain | 001–018 passed | A fresh migration chain was exercised, separate from old-code rollback |
| Manual browser smoke | 14 routes rendered without crashes | Route smoke does not exercise every action |
| Manual capture | Job saved successfully | Real local API flow was exercised |
| Today responsive check | No overflow at 390px in final check | One screen/state, not whole-app accessibility certification |
| Hosted CI | Passed for audited SHA | [GitHub Actions evidence](https://github.com/anmolsansi/CSV_Website/actions/runs/35892537517) |

Original local artifacts were saved under `/private/tmp/jobgrid-audit-20260923/`: `postgres.xml`, `sqlite.xml`, `playwright.json`, `today-utc.json`, `recovery-probe.json`, `queue-probe.json`, and `route-smoke.json`. Temporary files are not durable release evidence. The reproductions are restated below so this guide remains useful if those artifacts disappear.

The audit did not establish real OAuth, actual SMTP delivery, production-sized performance, every browser engine, production deployment, or old-code rollback. Some browser tests mock APIs; retain real API integration checks as well.

<a id="status-rules"></a>
## 3. Status, ownership, and execution rules

C-package statuses below reflect the September 30 reconciliation. The original JG tickets use a separate status vocabulary so implemented features are not presented as absent:

| Original-ticket status | Meaning | Next action |
|---|---|---|
| Local acceptance passed | C-08 maps local requirements to code/tests; external gates remain separate | Preserve regressions and run deployed acceptance |
| Local acceptance passed; external gate pending | Local code is accepted but provider/release proof is outstanding | Complete C-09/C-10 |
| Implemented—verification pending | Implementation is present, but full requirement-level proof is missing | Verify existing behavior; repair only demonstrated gaps |
| Needs repair | The audit demonstrated a failure affecting the ticket's acceptance | Reproduce, fix, and add regression coverage |
| Externally blocked | Local tooling exists, but real staging/provider proof is missing | Complete the specified external gate |

All 64 tickets have mapped local acceptance in C-08. JG-024 and JG-040 retain explicit external gates; other deployed smoke and recovery requirements remain in C-09/C-10. The prior roadmap label and original implementation checklist are retained as historical references. An integration defect can require repair without invalidating every part of an otherwise implemented ticket.

Use these evidence states in records: `not-started`, `in-progress`, `local-ready`, `staging-accepted`, `released`, `blocked`. Use **Completed** in the checklist only when the task's stated exit criteria are satisfied at a recorded SHA. Never count a blocked external gate as passed.

1. Before work, inspect branch, diff, current main, applicable instructions, and migration head. Preserve unrelated changes; the audit left `backend/queries.md` and `backend/scraper.py` untouched.
2. Prefer the code knowledge graph for discovery. File paths below are source anchors, not permission to rewrite entire modules.
3. Assign an implementer and reviewer to each task. The release operator owns staging, secrets, deployment, and recovery evidence. Record actual names when work starts; no owner is assigned by this document.
4. Use a small independent change per coherent outcome. Capture a failing reproduction before fixing a confirmed defect, then run the relevant existing suite. Do not create new abstractions merely to match a checklist.
5. Keep backups backward compatible. If a schema/format change is unavoidable, specify version negotiation, missing-section behavior, upgrade tests, and rollback before changing writers.
6. Freeze contracts in the owning task before touching dependent features. Do not change lifecycle semantics, backup identifiers, or timestamp interpretation silently.
7. This is a documentation request. Publication, messages to others, and deployment are separate actions; apply the user's authorization at execution time rather than inventing blanket approval requirements for ordinary local work.

<a id="work-order"></a>
## 4. Priority order and completion checklist

The original roadmap's sequential build order was appropriate before these features existed. For the current implemented baseline, use the repair-and-acceptance order below. Original JG IDs retain their meaning; `C-01`–`C-12` are local completion work packages, not external issue IDs.

| Order | Status | Task | Dependency | Original ticket focus |
|---|---|---|---|---|
| 1 | Completed | [C-01 — Preserve reproductions and freeze recovery contracts](#c-01) | None | JG-001–004, JG-023 |
| 2 | Completed | [C-02 — Make every restore atomic](#c-02) | C-01 | JG-003, JG-056, JG-058, JG-064 |
| 3 | Completed | [C-03 — Deliver one complete recoverable backup](#c-03) | C-02 | JG-002, JG-004, JG-044, JG-056–058, JG-064 |
| 4 | Completed (local) | [C-04 — Fix mixed-source Today pagination](#c-04) | C-01 | JG-026–028, JG-051, JG-055–056 |
| 5 | Completed | [C-05 — Normalize SQLite timestamp contracts](#c-05) | C-02 | JG-010, JG-019–020, JG-025, JG-037 |
| 6 | Completed (local) | [C-06 — Make browser time tests deterministic](#c-06) | C-04, C-05 | JG-010, JG-023, JG-027–028, JG-038–040 |
| 7 | Not completed | [C-07 — Enforce the corrected release test matrix](#c-07) | C-02–06 | JG-019–023 |
| 8 | Completed (local) | [C-08 — Close every product acceptance contract](#c-08) | C-07 | All 64 original tickets |
| 9 | Not completed | [C-09 — Prepare staging and prove durable operations](#c-09) | C-08 | JG-012–014, JG-022, JG-024, JG-040, JG-044, JG-064 |
| 10 | Not completed | [C-10 — Execute real staging acceptance](#c-10) | C-09 | JG-024, JG-040, JG-048 |
| 11 | Not completed | [C-11 — Reconcile documentation and ticket evidence](#c-11) | C-08–10 | All 64 original tickets |
| 12 | Not completed | [C-12 — Release, observe, and close the project](#c-12) | C-11 | Final release |

Test-harness preparation may happen while a feature is repaired, but dependent acceptance cannot close early. C-08 defects become bounded follow-ups linked to their original ticket; rerun affected gates before advancing. Do not silently add them to a future wishlist.

<a id="c-01"></a>
## C-01 — Preserve reproductions and freeze recovery contracts

**Priority:** P1 prerequisite. **When:** before restore changes. **Owner:** backend implementer plus reviewer. **Status:** Completed.

**What and why:** turn the independent failures into durable regression inputs and define exactly which data “complete backup” preserves. Otherwise the next repair can pass tests while losing a later feature's records.

**Where:** `backend/app/services/backups.py`, `contact_backups.py`, `import_backups.py`, `backend/app/routers/backup.py`, `backend/tests/test_backup_contract.py`, `docs/BACKUP_STRATEGY.md`, and the existing feature-specific recovery tests discovered through the graph. New test function names below are proposed assertions, not claims of existing tests.

**Implementation checkpoints:**

- [x] C-01.01 Record baseline SHA, migration head, runtime versions, working-tree scope, and test database names in the evidence record.
- [x] C-01.02 Recreate a synthetic source account with an applied track, notes/dates, contact, association, interview, saved import mapping, manual task/snooze, document/version/selection, and undo audit metadata. Include two accounts to detect ownership leaks.
- [x] C-01.03 Export v2 JSON, alter only the contacts-extension checksum, then import into an empty destination. Assert HTTP rejection **and zero new rows in every affected table**. Baseline behavior: rejection still leaves one application committed.
- [x] C-01.04 Export both JSON and ZIP. Inventory section names, backup-local references, file members, checksums, and declared exclusions. Baseline behavior: JSON has contact/mapping extensions but no document bytes; ZIP has document bytes but omits those extensions.
- [x] C-01.05 Create three future interviews on the same account-local day and request Today with limit two. Assert all three are reachable through cursors. Baseline behavior: two items, total three, null next cursor.
- [x] C-01.06 Create a persisted-data coverage table from current ORM models: exported, reconstructed, or deliberately excluded with reason. Include data introduced after the base backup schema; do not infer coverage from table counts alone.
- [x] C-01.07 Preserve deliberate exclusions: authentication secrets, transient upload previews, and executable undo before-images must not be made portable by accident. Restored undo metadata remains non-actionable. Document whether pending deliveries are disabled/replanned so restore never silently resends messages.
- [x] C-01.08 Specify compatibility for v1, early v2, current extensions, missing optional sections, unknown required sections, and metadata-only restores. Reject unsupported required data before writes.
- [x] C-01.09 Keep regression fixtures small, deterministic, and synthetic; promote the reproductions into versioned tests. Record both the expected failure and the later passing result.

**Failure/retry:** fixtures must use fresh destinations or rolled-back test transactions. A prior failed restore may have polluted the destination; do not reuse it unknowingly. Never point tests at production.

**Completion evidence (2026-09-27):** The late-extension checksum/partial-restore and composed-ZIP metadata failures were preserved and repaired in PR #159, with durable regression coverage in `backend/tests/test_complete_backup.py`, `test_backup_contract.py`, and `test_document_backup.py`. The remaining independent reproduction, three scheduled interviews with `limit=2`, is now versioned in `backend/tests/test_interview_today.py`; continuation freezes the base queue `as_of`, applies the signed ordering boundary to interview items, and emits the next cursor from the final mixed-source item. `backend/app/backup_schemas.py::MODEL_FIELD_INVENTORY` is the persisted-data coverage table, and `docs/BACKUP_STRATEGY.md` records portable coverage, deliberate exclusions, compatibility, side-effect rules, and retry/reconciliation behavior. C-04 subsequently closed the broader bounded/context-aware mixed-source pagination acceptance; see its current evidence below.

**Completion proof:** three independent baseline failures are reproduced, and the data-coverage/compatibility contract is reviewed. Capture deliberately failing regressions on the repair branch, then make them pass with C-02–C-06 before merging. Never merge a knowingly failing required CI check as a standalone foundation change. C-01 evidence can be ready before its dependent fixes; final publication requires the combined repair to be green.

<a id="c-02"></a>
## C-02 — Make every restore atomic

**Priority:** P1 data integrity. **When:** immediately after C-01. **Owner:** backend implementer. **Status:** Completed.

**Observed defect:** `restore_backup_payload_with_contacts` calls the base restore before validating the contacts extension. The base can commit using its own session. Later wrappers add further independent commit boundaries. An outer `rollback()` on the request session cannot undo an already committed inner session.

**Where:** `backend/app/services/backups.py` (`restore_backup_payload`, `restore_backup_v2`, transaction helpers, bundle restore), `contact_backups.py`, `import_backups.py`, and `backend/app/routers/backup.py`. Verify how `backend/app/main.py` wires wrapped functions before changing dispatch.

**Required behavior:** preflight validates the complete document without writes. An actual restore either installs all intended database records or installs none. Repeating a successful restore is idempotent. Conflicts never become silent overwrites.

**Implementation checkpoints:**

- [x] C-02.01 Trace the JSON, legacy, and ZIP entry points to all session creation, flush, commit, rollback, receipt, and filesystem operations. Record a compact call/transaction map.
- [x] C-02.02 Parse/version-route once; validate checksums, sizes, identifiers, duplicate references, all present extensions, ownership, and cross-section references before applying records.
- [x] C-02.03 Separate pure validation and destination conflict classification from mutation. Use a typed validated restore plan or an existing equivalent; do not introduce a general workflow engine.
- [x] C-02.04 Give one restore orchestrator ownership of the transaction/session. Child writers accept that same session and flush when IDs are needed; they do not independently commit or close it.
- [x] C-02.05 Account for SQLAlchemy autobegin from earlier reads. Do not blindly wrap an already active request transaction in `begin()`; choose an explicit dedicated restore session or the established caller-owned transaction pattern consistently.
- [x] C-02.06 Move contact, interview, association, import-mapping, and allowed undo-metadata writes into that transaction. Apply parent references before children and remap using backup references rather than source integer IDs.
- [x] C-02.07 Lock/revalidate destination conflicts inside the write transaction. Preflight is advisory if another request changes the account before commit.
- [x] C-02.08 Commit imported data, required lifecycle/history entries, and restore identity receipts together. No successful receipt or event survives a rolled-back restore.
- [x] C-02.09 Make verification mode side-effect free: no rows, receipt increments, document publication, reminders, or external messages.
- [x] C-02.10 On validation/constraint/commit errors, roll back all database state and return the existing structured safe error. Do not expose raw SQL or call the result successful with a warning.
- [x] C-02.11 Preserve replay rules: same backup identity and content is a no-op/reported replay; changed content under the same identity conflicts. Concurrent identical restores must not duplicate relationships.
- [x] C-02.12 Inject failures after base writes, after contacts, after mappings, after undo metadata, and immediately before commit. Re-query through a separate session to prove durable state is unchanged.
- [x] C-02.13 Test nonempty destinations, missing optional legacy sections, broken references, wrong-owner references, changed payload replay, and two concurrent PostgreSQL attempts.

**Files and database are not one ACID transaction:** C-03 must coordinate immutable document staging/publication with database commit. Preserve existing files; remove only newly staged/published files owned by the failed attempt, or leave a documented recoverable state with a reconciler. A cleanup failure must be visible and retryable.

**Completion evidence (2026-09-27):** PR #159 introduced `backend/app/services/backup_sessions.py` as the shared restore transaction/snapshot boundary. Base v1/v2, contacts/interviews/associations, import mappings, non-actionable F10 metadata, and bundle restore now participate in the caller-owned transaction instead of committing child layers independently. Preflight validates extensions before writes, verify-only is side-effect free, replay conflicts are checked, PostgreSQL account locking serializes competing restores, and late injected failures are re-queried from fresh sessions to prove no durable partial graph. Existing legacy readers remain supported.

**Completion proof:** original checksum reproduction leaves zero imported records; every injected late failure preserves before/after counts and normalized content; successful full restores and retries pass on PostgreSQL and the supported SQLite path. Existing legacy restore tests remain green.

**Rollback:** keep format compatibility and revert the application change if needed; never repair partial imports by deleting a user's account. Record an explicit reconciliation approach for any already-affected data before running it on real accounts.

<a id="c-03"></a>
## C-03 — Deliver one complete recoverable backup

**Priority:** P1 recovery. **When:** after C-02 establishes transaction ownership. **Owner:** backend and frontend implementer. **Status:** Completed.

**Observed defect:** `export_backup_bundle` calls the base exporter, bypassing later extensions. The UI calls JSON export and labels it complete even though document bytes are excluded.

**Where:** `backend/app/services/backups.py`, `contact_backups.py`, `import_backups.py`, `backend/app/routers/backup.py`, `frontend/src/components/BackupRestore.jsx`, its existing API client, and backup/document recovery tests.

**Implementation checkpoints:**

- [x] C-03.01 Create one explicitly composed metadata export path covering all portable current sections. Reuse it for JSON and ZIP; avoid circular imports or behavior that relies on changing an imported function indirectly.
- [x] C-03.02 Produce metadata from one consistent database snapshot. All section references must describe the same account state; sequential independent snapshots can invent broken relationships during concurrent edits.
- [x] C-03.03 Add a capability/manifest declaration that accurately identifies included metadata and files. Retain compatibility with existing versioned validators and checksums.
- [x] C-03.04 Verify each included immutable document's ownership, storage key, byte count, and checksum. Handle missing/quarantined/deleted files according to an explicit contract; never silently call a missing-file package complete.
- [x] C-03.05 Enforce compressed and expanded byte limits, member count, duplicate member rejection, path traversal/symlink rejection, and per-file hash validation before writes. Do not extract untrusted paths directly under the live document root.
- [x] C-03.06 Route ZIP restore through the same complete metadata validator/transaction orchestrator as JSON. Merely fixing ZIP export without import dispatch still loses data.
- [x] C-03.07 Stage new files privately using attempt-owned names. Verify all bytes before metadata becomes ready. Preserve preexisting immutable files during retry/rollback; reconcile interruption between file publication and DB commit.
- [x] C-03.08 Expose “Complete backup — records and files” for ZIP and “Records only — excludes document files” for JSON. Update explanatory text, download names, busy state, errors, and success notifications together.
- [x] C-03.09 Accept supported JSON/ZIP inputs in the restore UI and show preflight counts, format, capabilities, file exclusions, conflicts, and failures before applying. Keep a selected file/draft after a recoverable failure.
- [x] C-03.10 Use one busy guard against double-submit. Do not report complete until the API has committed. If the response is lost after commit, an idempotent retry must report the existing result.
- [x] C-03.11 Round-trip the C-01 rich fixture into an empty account and compare normalized content, references, timestamps, relationships, and file hashes. Source/destination integer IDs need not match.
- [x] C-03.12 Round-trip into a nonempty account and repeat the import; assert deterministic conflict/replay behavior and zero duplicate contacts, mappings, document versions, or events.
- [x] C-03.13 Simulate missing file, changed hash, disk full/write failure, process interruption, and cleanup failure. Verify a safe retry/reconciliation path and an accurate user message.
- [x] C-03.14 Perform a real browser download → upload → preview → restore flow against the local backend, not only mocked responses. Download restored documents and verify bytes.
- [x] C-03.15 Update backup documentation with data categories, intentional exclusions, restore compatibility, limits, and operator recovery steps. Use the same definitions in UI and docs.

**Completion evidence (2026-09-27):** PR #159 made the ZIP exporter reuse the composed v2 metadata graph and shared snapshot, added manifest/member/hash validation, routed ZIP restore through the same composed metadata/transaction orchestration, and added failed-attempt file cleanup. `BackupRestore.jsx` distinguishes complete ZIP backup from records-only JSON and supports verify/apply for both. `backend/tests/test_document_backup.py` covers bytes/links round-trip, unsafe ZIP members, missing members, changed hashes, publish/write failure, final-commit rollback and retry; `test_complete_backup.py` proves later metadata extensions survive the bundle. `docs/BACKUP_STRATEGY.md` now documents the portable data categories, exclusions, version compatibility, limits, cross-resource crash/reconciliation boundary, retry procedure, and operator disaster-recovery distinction.

**Completion proof:** a single supported user-facing backup path restores all portable metadata **and** document bytes. Metadata-only export is clearly labeled. Failure/retry and legacy-format tests pass. Restored undo records cannot execute old destructive operations; restoring data does not send email.

**Rollback:** preserve old readers until new packages are versioned and compatibility-tested. Retain a known-good recovery package before deploying; reverting code must not delete newly uploaded files.

<a id="c-04"></a>
## C-04 — Fix mixed-source Today pagination

**Priority:** P2 unreachable work. **When:** after reproductions are durable; before Today acceptance. **Owner:** backend implementer. **Status:** Completed (local).

**Observed defect:** the interview wrapper merges interviews into only the first already-paginated base page, truncates to `limit`, and keeps the base cursor. With three interviews and limit two it returns two with no cursor. Mixed queues can also displace base items behind an incorrect cursor.

**Current evidence:** [C04_TODAY_PAGINATION](docs/C04_TODAY_PAGINATION.md), plus the current green CI matrix. External acceptance remains C-09/C-10.

**Where:** `backend/app/services/today.py`, `backend/app/services/today_f8.py`, existing Today schemas/routes, and Today/interview tests. Preserve the current public response shape unless a justified versioned change is required.

**Implementation checkpoints:**

- [x] C-04.01 Define one ordering tuple across manual actions, follow-ups, deadlines, and interview preparation. Preserve due-time/null ordering, priority, source type, and stable source ID tie-breakers.
- [x] C-04.02 Use the same frozen `as_of`, account timezone, snooze policy, archive policy, and visibility filters across every source and continuation page.
- [x] C-04.03 Normalize source candidates before pagination. Remove the special case that skips interviews when a cursor is present.
- [x] C-04.04 Apply the decoded cursor's ordering boundary to every source. Fetch only the bounded candidates required to produce `limit + 1` merged results; do not scan an unbounded account graph just to fetch one page.
- [x] C-04.05 Merge and sort once. Emit at most `limit` items. Build the next cursor from the final **emitted mixed-source item** only when another item exists.
- [x] C-04.06 Validate and sign cursor contents. Bind account and relevant query context, including timezone/include-snoozed behavior, or explicitly reject incompatible reuse. Do not permit a cursor to widen ownership.
- [x] C-04.07 Version incompatible cursor formats. Document controlled rejection/reload of old cursors rather than silently returning the wrong page.
- [x] C-04.08 Calculate counts from the same eligible population; separate total from page length. Verify count semantics when snoozed/archived/terminal records are hidden.
- [x] C-04.09 Define mutation-between-pages behavior. Freezing `as_of` does not freeze mutable database rows; either document best-effort pagination with refresh or implement a justified stronger snapshot policy. Do not claim an immutable snapshot without storing one.
- [x] C-04.10 Test interview-only queues of size 0, 1, exactly limit, limit+1, and several pages. Test all source types mixed, identical due times, null due times, snoozes, cancellations, archive changes, and account-local midnight.
- [x] C-04.11 Traverse all pages of an unchanged fixture and compare the emitted ordered keys to the expected complete set: no missing items, no duplicates, no infinite cursor loop.
- [x] C-04.12 Test tampered/wrong-account/context-mismatched cursors. Inspect query counts and boundedness with a larger fixture; record measured results instead of inventing a latency guarantee.
- [x] C-04.13 Exercise actual Today Load more/navigation and an interview mutation in the browser. Verify refreshed cards, counts, focus, and empty states.

**Completion proof:** the three-interview reproduction returns a valid second page; mixed-source traversal is complete and stable for unchanged data; all old Today behavior remains covered.

**Failure/retry:** invalid or stale cursor yields a clear refresh path without losing the user's draft. A failed page load retains previously loaded cards and enables retry.

<a id="c-05"></a>
## C-05 — Normalize SQLite timestamp contracts

**Priority:** P2 supported-runtime correctness. **When:** after restore repair, before the matrix is enforced. **Owner:** backend implementer. **Status:** Completed.

**Observed failures:** `test_backup_round_trip_retains_snooze_and_manual_action` in `backend/tests/test_backup_contract.py` and `test_illegal_state_transition_rejected` in `backend/tests/test_reminder_models.py` compare naive SQLite values with timezone-aware UTC values. PostgreSQL passed. This is not evidence of lost timestamps by itself.

**Implementation checkpoints:**

- [x] C-05.01 State the intended contract at three boundaries: stored legacy columns, internal Python values, and wire/export timestamps. Distinguish UTC instants from date-only deadlines and local scheduled wall times.
- [x] C-05.02 Trace `WorkItemOverride.snoozed_until` and `ReminderDelivery.sent_at` from input through persistence, reload, comparison, export, restore, and response serialization.
- [x] C-05.03 If stored naive values mean UTC, normalize explicitly to UTC at the chosen boundary. Never attach the host timezone to a legacy naive UTC value.
- [x] C-05.04 Reuse an existing appropriate helper; add a small shared helper only if production consumers require it. If production behavior already honors the contract and only assertions are wrong, fix assertions to compare canonical instants without changing schema.
- [x] C-05.05 Test persistence after session expiration/new session, not only the in-memory object. Preserve actual instant, microseconds, and null behavior.
- [x] C-05.06 Add UTC, positive-offset, negative-offset, DST-boundary, legacy-naive, and backup round-trip examples. Reject ambiguous inputs according to the existing API contract.
- [x] C-05.07 Run both failing tests, then related reminder/Today/backup tests on both databases. Do not remove timezone checks or add blanket skips to get a green result.
- [x] C-05.08 Change a database column only if demonstrated necessary. Any migration requires explicit conversion semantics and previous-data verification on a disposable clone.

**Completion evidence (2026-09-27):** PR #163 (`C-05: normalize SQLite timestamp contracts`) was validated and merged into `main` at `57f6e1767f96bc00c6c97109050fb78f42c54f57`. C-05 adds an explicit persisted-UTC normalization boundary for SQLite reloads without changing schema or migrations. The hosted run passed 615 PostgreSQL backend tests, the two original C-05 regressions through an explicit SQLite subprocess, all focused timestamp-contract coverage, frontend build, 8/8 tab-helper tests, 2/2 focused browser checks, and 181/181 Chromium tests. See [C-05 SQLite timestamp contract evidence](docs/C05_SQLITE_TIMESTAMP_CONTRACTS.md).

**Completion proof:** both original tests pass for a documented reason on SQLite and PostgreSQL, and wire/export values represent the same instant after reload and restore.

**Rollback:** prefer boundary normalization over data rewrites. If a migration is required, retain a backup and demonstrate old-code compatibility or a documented recovery route before rollout.

<a id="c-06"></a>
## C-06 — Make browser time tests deterministic

**Priority:** P2 release confidence. **When:** after C-04/C-05. **Owner:** frontend implementer. **Status:** Completed (local).

**Observed failures:** `keyboard_snooze_persists_after_reload` and `followup_reschedule_updates_application_drawer` in `frontend/tests/today.spec.ts`. A helper derives a `datetime-local` input using UTC `toISOString()`, and the assertion compares that wall-clock text directly with the outgoing UTC timestamp. Asia/Kolkata exposes the mismatch; UTC masks it.

**Implementation checkpoints:**

- [x] C-06.01 Decide whether each fixture represents a local wall time or a fixed instant. Construct it accordingly using local calendar fields or an explicit conversion, never a UTC string with its timezone suffix removed by accident.
- [x] C-06.02 Compute the expected outgoing instant from the intended local input and configured browser timezone. Assert instant equality, then separately assert the displayed local value.
- [x] C-06.03 Configure browser-context timezone explicitly in Playwright for UTC, Asia/Kolkata, and a DST-observing zone such as America/New_York. Host `TZ` diagnostics alone are not a portable browser-timezone configuration.
- [x] C-06.04 Test account timezone differing from browser timezone, with expected day boundaries specified. Freeze a clock where midnight or “tomorrow” would make the test flaky.
- [x] C-06.05 Ensure mock handlers return responses and capture payloads for test assertions; do not hide a handler assertion as a dialog timeout.
- [x] C-06.06 Add coverage for valid future snooze, invalid/past input, reschedule, reload persistence, cancellation, failed request draft retention, and keyboard focus restoration.
- [x] C-06.07 Exercise at least one snooze and reschedule against the real API to separate serialization behavior from mock expectations.
- [x] C-06.08 Rerun the targeted failures in each configured timezone, then the complete required browser matrix. Do not enforce UTC-only execution as the fix.

**Completion proof:** payload instant, persisted instant, and local display match the contract in all declared zones; no host-specific test failures remain.

**Rollback:** test changes should not alter product semantics. If this work exposes a real product-time conversion bug, add a separate failing product regression and repair that conversion explicitly.

<a id="c-07"></a>
## C-07 — Enforce the corrected release test matrix

**Priority:** release gate. **When:** after C-02–06. **Owner:** test/CI implementer. **Status:** Not completed — workflows and hosted validation complete; C-07.08 branch enforcement remains.

**Where:** `.github/workflows/ci.yml`, `frontend/playwright.config.ts`, existing test fixtures, `docs/RELEASE_ACCEPTANCE.md`.

**Implementation checkpoints:**

- [x] C-07.01 Preserve a PostgreSQL job with real migrations and separate explicitly disposable databases for regular tests and migration/concurrency tests.
- [x] C-07.02 Add/retain a SQLite job with clear expected PostgreSQL-only skips. A supported SQLite runtime must not silently disappear from release coverage.
- [x] C-07.03 Enforce the new restore/backup/queue regression cases and multi-zone browser checks. Collect tests before running; an empty selection must fail.
- [x] C-07.04 Build with the intended API configuration. Start local E2E services with explicit frontend origin/CORS, disabled external workers, and isolated document storage; do not inherit hosted `.env` values accidentally.
- [x] C-07.05 Preserve unit/helper tests, production build, actual backend routes, and focused real-API browser workflows. Mark mocked tests clearly so they cannot substitute for integration acceptance.
- [x] C-07.06 Fail the job on test errors, failed migrations, failed readiness, unexpected skips, or missing required evidence. Retries must remain visible; repeated flaky retries are an issue, not proof of correctness.
- [x] C-07.07 Attach JUnit/browser reports, traces on failure, sanitized service logs, runtime/dependency versions, source SHA, and migration revision. Do not publish private backup contents or credentials.
- [ ] C-07.08 Ensure required status checks match the actual job names and protect the target branch using authorized repository settings. A workflow file alone does not establish branch protection.
- [x] C-07.09 Run the full matrix once for the final candidate. Repeat affected coverage after any subsequent change, then require green CI on the exact deployable SHA.

**Completion proof:** no failures in supported local paths, all required CI checks green on the candidate, and new independent regressions are enforced rather than residing only in `/tmp`.

**Failure/retry:** preserve the first failure's artifacts, fix the cause, and rerun. Environment failures must be labeled separately from application defects, as the earlier local CORS mismatch was.

<a id="c-08"></a>
## C-08 — Close every product acceptance contract

**Priority:** required project acceptance. **When:** after corrected CI. **Owner:** feature implementer with reviewer. **Status:** Completed (local).

**Current evidence:** [C-08 acceptance](docs/C08_PRODUCT_ACCEPTANCE.md), plus the current green CI matrix.

**What:** validate existing functionality rather than rebuilding it. Run the local portions of the 17 acceptance packs below plus the two original user journeys. Compare current code to every original ticket's acceptance checklist; a passing broad suite does not certify untested prose requirements. Record external portions as pending C-09/C-10; they do not block preparing staging, but they do block final ticket/release closeout. This distinction prevents a dependency cycle between local acceptance and staging setup.

**Procedure for each original ticket:**

1. Read its current specification and the coverage entry in this guide.
2. Locate the actual implementation and existing tests through the graph; verify proposed historical file names against the current repository.
3. Map each requirement to code plus a concrete assertion/manual evidence step. Mark unmapped requirements as gaps.
4. Use a nonempty owner fixture and a second account; include at least one failure/retry condition for stateful behavior.
5. Reuse passing implementation. If a requirement fails, create a bounded repair under its original JG ID with reproduction, expected result, affected files, and regression command.
6. Verify dependencies again after repairs. Record exact SHA, command, expected/actual results, evidence path, remaining external gate, and reviewer.
7. Close only the ticket's delivered scope. A later integration fix may reopen acceptance without meaning the original schema/service never existed.

### Original journey A — durable applications and companies

- [ ] Create an application from a CSV row; record source row ID and distinct track ID.
- [ ] Save company, role, notes, application date, and status; reload and sign out/in.
- [ ] Delete the source row/CSV; verify history is retained and source references detach safely.
- [ ] Find the application in company history, applications, pipeline, and applicable analytics.
- [ ] Reimport/capture an equivalent job; show an accurate applied-before warning without merging unrelated jobs.
- [ ] Verify a second account cannot read or mutate the history through guessed IDs, list filters, exports, documents, or backups.

### Original journey B — top five unopened filtered links

- [ ] Seed more than one page of jobs with ties, invalid URLs, previously visited jobs, and distinct filter matches.
- [ ] Apply multiple filters and a stable sort; compare selected links to the first five eligible records across the full server result.
- [ ] Test 0, 1, 4, 5, and more than 5 eligible jobs; unused blank tabs close.
- [ ] Test Chrome with popups allowed, blocked, and partially available; mark visits only for successful navigations.
- [ ] Check `window.opener` isolation and rejection of unsafe protocols; a network-loaded page is not required to claim an application was submitted.
- [ ] Test rapid double click, failed API load, rerun, and reload; preserve accurate visit state and a manual fallback.

### Acceptance packs for the 17 roadmap groups

| Pack | Original tickets | Required checks beyond “page opens” | Exit evidence |
|---|---|---|---|
| A01 Recovery | JG-001–004 | Full graph and files, invalid late extension, empty/nonempty destinations, replay, conflicts, legacy formats, owner isolation | C-02/C-03 rich round-trip, atomic failure assertions, browser restore |
| A02 Shared filtering | JG-005–007 | Same membership/order across list pages, CSV/JSON exports, saved views, batch opening; nulls, ties, malformed filters, account boundary | Compare ordered IDs over full result sets |
| A03 Lifecycle metrics | JG-008–011 | Every writer emits correct events once; legacy unknown dates stay unknown; account-local midnight/DST; analytics/goals/report agreement | Fixed-clock event fixtures and exact metric totals |
| A04 Retention | JG-012–014 | Disabled default, opt-in boundaries, bounded batches, concurrent workers, visible failure, history survives source cleanup | Worker state/count assertions and operator health view |
| A05 Validation | JG-015–017 | Invalid status/date/URL/bulk input rejected atomically by every writer; import feedback and retained drafts | No partial writes plus field-error UI checks |
| A06 Numeric/database behavior | JG-018–020 | Numeric not lexical order; negatives, blanks, invalid strings, decimal/exponent cases per contract; both databases and migrated schema | Identical ordered expectations, C-05, actual Alembic evidence |
| A07 Release foundation | JG-021–024 | Correct CI paths/readiness, production config fail-fast, real OAuth/SMTP, restore and old-code rollback | C-07 and C-09/C-10 evidence on one candidate |
| A08 Today | JG-025–028 | Manual/follow-up/deadline/interview actions, mixed pagination, snooze, reschedule, stale versions, keyboard use, timezone boundaries | C-04/C-06 plus a real daily workflow |
| A09 Identity | JG-029–032 | URL alias preservation, tracking parameter policy, conservative company matching, false positives/negatives, applied-before context | Positive and negative identity fixtures; no silent destructive merge |
| A10 Evidence history | JG-033–036 | Immutable timeline, owned evidence changes, stable ordering, replay, lifecycle/source deletion/archive/restore | Exact ordered event payloads before/after recovery |
| A11 Reminders | JG-037–040 | Explicit opt-in, fixed-clock planning, claims/leases/restarts, unsubscribe, history, timezone/DST, authorized receipt | Deterministic delivery tests and controlled SMTP receipt |
| A12 Documents | JG-041–044 | Private immutable versions, limits, invalid content, download ownership, selection history, interrupted upload/reconciliation, full recovery | File hash equality and isolation; C-03 |
| A13 Capture | JG-045–048 | Manual URL and bookmarklet, duplicates, replay, malformed payload, popup fallback, no implicit visit/application | Real capture flows in declared browsers |
| A14 Availability | JG-049–052 | Explicit dates, stale/unknown/manual labels, disabled automatic checks, conservative closure, redirect/private-network resistance | Deterministic fetch fakes and account-local Today deadline checks |
| A15 People/interviews | JG-053–056 | Owned contacts/links, cancelled/rescheduled interviews, stable calendar IDs/escaping/timezones, preparation cards, recovery | Privacy negatives, calendar consumer check, C-02–04 |
| A16 Imports | JG-057–060 | Reusable mappings, preview ownership/expiry, duplicate decisions, atomic commit, repeated import, byte/row limits, malformed files | Preview→commit→retry against real API and restored mappings |
| A17 Undo/archive | JG-061–064 | Optimistic versions across all writers, conflict-aware undo, expired actions, archive filtering/restoration, no automatic purge, non-actionable restored undo metadata | Concurrent/stale mutation assertions, recovery, Archive UI |

**Cross-feature checks that must not be forgotten:** apply → follow-up → Today → reminder → archive; interview reschedule → Today → calendar; import → duplicate warning → company history → backup; document selection → application history → restore; bulk archive → undo conflict after another edit. For Today snooze versus reminder delivery, explicitly confirm the intended product contract and test it; absence of that verification is not itself a proven reminder bug.

**Accessibility and UI acceptance:** use keyboard-only navigation on dialogs/forms, verify labels and inline errors, restore focus after cancellation, test loading/empty/error states, refresh deep links, and inspect 390px and desktop widths for all core workflows. Capture emitted console errors. The bookmarklet's React `javascript:` warning and build-size warning require classification and a decision, not automatic architectural rewrites. Record a follow-up only if compatibility or measured performance warrants it.

**Performance acceptance:** use a declared representative large fixture and record counts, response times, query counts, memory/limits, and import/export durations. Choose explicit release thresholds with the product owner before testing. Do not call unmeasured unlimited data “supported.”

**Completion proof:** every local requirement has a mapped passing assertion or reviewed manual evidence; external requirements have explicit owners and C-09/C-10 gate mappings. Unresolved local findings have been repaired or explicitly removed from promised scope with rationale. No P1/P2 defect remains silently deferred. Completing C-08 means local product acceptance, not final closure of external requirements.

<a id="c-09"></a>
## C-09 — Prepare staging and prove durable operations

**Priority:** release gate. **When:** after local acceptance. **Owner:** release operator. **Status:** Not completed.

**Where:** [release acceptance](docs/RELEASE_ACCEPTANCE.md), [deployment runbook](docs/CLOUD_DEPLOYMENT_VERCEL_RENDER_SUPABASE.md), [backup strategy](docs/BACKUP_STRATEGY.md), existing deployment manifests and scripts. These documents describe repository configuration; verify current hosting capabilities and prices when executing. This guide does not assume a free hosting plan provides durable file storage.

**Current implementation:** PRs #173/#174 supply repository readiness and private object storage through the gateway. Keep the zero-dollar topology; live durability/recovery proof remains open.

**Implementation/operation checkpoints:**

- [ ] C-09.01 Record the actual frontend/backend/database/storage providers, staging URLs, deployment owner, candidate SHA, previous known-good SHA, and intended runtime versions. Reuse the chosen deployment topology unless it cannot meet a requirement.
- [ ] C-09.02 Configure private persistent document storage. Prove an uploaded file survives process restart and redeployment, and that backup/restore reaches both database and files. Ephemeral filesystem storage cannot satisfy document durability.
- [ ] C-09.03 Set production-mode configuration without dev authentication. Keep keys in the host secret store; align frontend API URL, allowed CORS origins, OAuth callbacks, cookie settings, and HTTPS behavior with actual domains.
- [ ] C-09.04 Configure one designated maintenance/reminder execution arrangement and prove leases/claims survive restart. Keep external URL checks and automatic purge disabled unless the delivered scope explicitly opts into them.
- [ ] C-09.05 Confirm schema migration deployment order, connection capacity, startup/readiness behavior, and compatibility of frontend/backend versions during rollout. Do not run several uncoordinated migration processes.
- [ ] C-09.06 Create nonempty synthetic staging accounts and a controlled inbox. Use private access to staging where appropriate; never copy private production job data into public artifacts.
- [ ] C-09.07 Record backup schedule, retention, storage access, restore destination, owner, and agreed recovery-point/recovery-time objectives. Measure a rehearsal against those objectives rather than claiming an untested guarantee.
- [ ] C-09.08 Create alerts or documented checks for failed scheduled work, repeated delivery failures, storage exhaustion, unhealthy services, and failed backups. Validate an induced failure is visible to the operator.
- [ ] C-09.09 Prepare the release evidence file using the existing validator. Record missing credentials/targets as exact blockers; local harness success is not a substitute.

**Completion proof:** the environment is reproducible, document storage is durable, jobs have an owner and restart behavior, backup/restore tooling is available, and all required external credentials/test accounts are ready for C-10.

**Rollback:** keep previous images/builds and a tested recovery package. Document which settings are reversible and which migrations require compatibility checks. Never downgrade schema automatically to recover an application deployment.

<a id="c-10"></a>
## C-10 — Execute real staging acceptance

**Priority:** release gate. **When:** after C-09, on one fixed candidate. **Owner:** release operator and reviewer. **Status:** Not completed.

**Run the existing acceptance procedure rather than replacing it with screenshots.** Extend it to cover all current data categories and files added after the original runbook.

- [ ] C-10.01 **Restore:** export a nonempty staging fixture, restore into a separate disposable destination, and compare normalized records/references plus file hashes. Record checksum, counts, elapsed time, and any exclusions. Include C-02's negative failure case.
- [ ] C-10.02 **OAuth:** sign in through a configured real provider with a controlled account, verify callback and authenticated `/auth/me`, refresh/deep links, logout, cookie clearing, and cross-account isolation. Dev login is invalid evidence. Verify secure cookie/CORS behavior for the actual deployment topology.
- [ ] C-10.03 **Email:** after verifying a supported transport for the selected runtime and obtaining explicit authorization to send to the controlled inbox, trigger the supported delivery flow, confirm actual inbox receipt, record provider/message identifier without secrets, and check content/timezone. `logged` or queued is not delivered.
- [ ] C-10.04 **Reminder lifecycle:** opt in, schedule a due reminder, deliver once, restart/retry, and verify recorded state. Document ambiguous provider outcomes and deduplication limits; do not claim exactly-once external email without provider support.
- [ ] C-10.05 **Deployment smoke:** exercise original journeys A/B and representative Today, import, people, documents, backup, archive/undo workflows through deployed frontend/backend. Refresh all 14 routes and inspect failures.
- [ ] C-10.06 **Chrome/popup acceptance:** run the real top-five workflow in Chrome, including blocked-popup fallback. Execute capture in every declared supported browser; do not claim Safari/Firefox based on Chromium alone.
- [ ] C-10.07 **Rollback:** record current data/hash and schema, run the previous known-good application against the migrated disposable database without dropping new columns, verify startup/read-only history, return to current code, and compare data/file hashes again.
- [ ] C-10.08 **Restart/durability:** restart workers/backend and redeploy; verify document downloads, scheduler recovery, session policy, and absence of duplicate sends or lost history.
- [ ] C-10.09 Validate the release evidence file, inspect the actual gate statuses, and require every mandatory gate PASS. The existing validator can exit successfully with BLOCKED gates; exit code alone must never authorize release.

**Completion proof:** reviewer can trace every gate to the same staging SHA, concrete expected/actual values, and durable sanitized artifacts. Unknown, failed, or blocked gates keep staging acceptance open.

**Failure/retry:** stop promotion, preserve failure artifacts, repair the cause, and rerun affected gates at the new SHA. Never “retry” SMTP repeatedly without understanding whether the first attempt reached the recipient.

<a id="c-11"></a>
## C-11 — Reconcile documentation and ticket evidence

**Priority:** completion accuracy. **When:** after local and staging acceptance. **Owner:** implementer/reviewer. **Status:** Not completed.

- [ ] C-11.01 Update the original roadmap's inventory, per-ticket status, TOC/checklists, and evidence links consistently. Its opening summary currently lags later implementation; several “proposed” headings coexist with implemented code.
- [ ] C-11.02 Reconcile JG-003, JG-027, JG-056–058 specifically against current implementation and the new audit repairs. Never change a checkbox simply because a similarly named function exists.
- [ ] C-11.03 Separate JG-024 local tooling from real staging acceptance and JG-040 local delivery logic from controlled external receipt.
- [ ] C-11.04 Update the build guide, F8/F9/F10 guides, backup strategy, and release/deployment documentation only where behavior changed. Remove stale proposed API/model claims that conflict with current code.
- [ ] C-11.05 Add a release evidence index with SHA, migration revision, test matrix, feature acceptance mapping, external gates, and reviewer. Preserve historical failures as resolved records rather than erasing them.
- [ ] C-11.06 Keep durable sanitized reports in the agreed repository/CI artifact location; do not rely on this machine's `/private/tmp` directory. Do not commit tokens, user backups, inbox contents, or private documents.
- [ ] C-11.07 If external issues/PRs are used, reconcile their actual state and reuse existing issues. These document IDs do not automatically create 64 new GitHub/Linear issues.
- [ ] C-11.08 Validate all links, task counts, status vocabulary, command working directories, and evidence references. Record “Completed” only with proof of the specific scope.

**Completion proof:** another engineer can determine what shipped, what was tested, what remains blocked, and how to recover without reading the conversation. All 64 tickets have disposition/evidence; documentation contains no contradictory global completion claim.

<a id="c-12"></a>
## C-12 — Release, observe, and close the project

**Priority:** final gate. **When:** after C-11 and explicit release authorization applicable to the target. **Owner:** release operator. **Status:** Not completed.

- [ ] C-12.01 Confirm the deployable SHA is exactly the reviewed/staging-accepted candidate and required hosted checks are green. New commits invalidate relevant acceptance until rechecked.
- [ ] C-12.02 Verify a recent complete backup and restore rehearsal, previous known-good build, migration compatibility, storage persistence, and operator availability.
- [ ] C-12.03 Deploy in the established dependency order, coordinating migration execution and compatible frontend/backend rollout. Record deployment IDs and URLs separately from GitHub publication.
- [ ] C-12.04 Run post-deploy health and representative read/write smoke with controlled accounts: application persistence, filtered opening, Today, document download, and backup capability labels.
- [ ] C-12.05 Observe health/errors, latency, scheduled work, failed deliveries, and storage over an agreed observation window that includes one scheduled execution cycle. Record the window and thresholds before release.
- [ ] C-12.06 Roll back on failed history/recovery integrity, ownership breach, broken login/core workflow, or agreed sustained error thresholds. Disable affected external workers if needed; preserve data and evidence.
- [ ] C-12.07 After rollback, verify login/history/files and record the incident; do not call the project complete while a failed release remains unresolved.
- [ ] C-12.08 After successful observation, record the release SHA/IDs, reviewer, production evidence, known accepted low-risk limitations, backup owner, and operating runbook location.

**Completion proof:** all required completion tasks are complete, all 64 original tickets have accepted scope or an explicitly approved scope decision, staging passed, production was actually deployed and verified, and recovery/operations have named owners.

### Contract decisions to preserve during implementation

| Boundary | Required contract | Compatibility proof |
|---|---|---|
| Restore orchestration | One logical database transaction across base and all accepted extensions; validation before writes; no independent child commit | Late-failure before/after content comparison from a separate session |
| Backup format | One composed portable metadata graph; ZIP adds verified immutable bytes; JSON clearly declares file exclusion | Legacy v1/early v2 acceptance, full current round-trip, unknown-required-section rejection |
| Restore response/UI | Existing error envelope/status semantics remain; success means committed result, not partial writes | Negative preflight/import UI and lost-response retry |
| Today response | Preserve items/counts/next_cursor shape; cursor covers all source types in one ordering and query context | Full unchanged-fixture traversal; invalid/old cursor has an explicit refresh path |
| Timestamp boundaries | Preserve UTC instants, distinct date-only values, and account-local display/day boundaries | SQLite/PostgreSQL reload, export/restore, multi-zone browser assertions |
| Ownership and identity | Authenticated owner scopes every private read/write; JobTrack IDs never substitute for CsvRow IDs | Two-account negatives, source deletion preserving application memory |
| Import/undo | Preview and commit stay deliberate; retries respect stored identity; undo rejects stale versions; restored undo history is non-actionable | Replay/concurrency/archive/restore assertions |
| Deployment configuration | Environment-specific API proxy and credentials; no database secrets in Vite build variables | Staging proxy cannot reach production; secret scan of published artifacts |

No new public route or schema migration is mandated merely by writing this guide. Prefer compatible internal repair. If an implementation proves a wire/schema change necessary, add its exact request/response or migration contract to the owning task before coding dependents, and cover previous-reader/previous-data behavior. New test names in the original ticket scenarios are descriptive until matched to actual test functions.

<a id="test-commands"></a>
## 5. Repeatable verification commands

Commands below are execution recipes, not new results. Run from the repository root unless a block changes directory. Use a fresh virtual environment and the pinned dependency files. The audit used Python 3.12, PostgreSQL 16, and the repository's locked frontend dependencies.

**Critical test boundary:** `backend/tests/conftest.py` drops/recreates tables for PostgreSQL. Both `DATABASE_URL` and `TEST_DATABASE_URL` must point to explicitly disposable test databases. Do not use the browser's populated database for the unit suite and do not use any production connection string.

### Install and compile

```bash
python3.12 -m venv /tmp/jobgrid-completion-venv
/tmp/jobgrid-completion-venv/bin/python -m pip install -r backend/requirements.txt
/tmp/jobgrid-completion-venv/bin/python -m compileall backend/app
source /tmp/jobgrid-completion-venv/bin/activate
cd frontend
npm ci
node --test unit/open-jobs.test.mjs
npm run build
npx playwright install chromium
```

### Backend — SQLite

From `backend`, with the temporary venv active:

```bash
unset TEST_DATABASE_URL
export DATABASE_URL='sqlite:///:memory:'
export ENVIRONMENT=test TEST_AUTH=true
export SECRET_KEY='jobgrid-local-test-only-not-production'
export FRONTEND_URL='http://localhost:5173'
export CORS_ORIGINS='http://localhost:5173'
export RUN_MAINTENANCE_JOBS=false RUN_REMINDER_WORKER=false
export JOB_URL_CHECKS_ENABLED=false
export DOCUMENT_STORAGE_DIR="$(mktemp -d /tmp/jobgrid-completion-docs.XXXXXX)"
mkdir -p /tmp/jobgrid-completion-evidence
python -m pytest tests -q --tb=short \
  --junitxml=/tmp/jobgrid-completion-evidence/sqlite.xml
```

Review every skip. Only database-specific exclusions are expected; do not blanket-ignore skipped feature acceptance. The two historical timezone failures were closed by C-05 and are preserved as regressions; the full supported SQLite path remains a C-07 release-matrix gate.

### Backend — PostgreSQL and migrations

Provision two separate disposable databases and supply their connection strings through environment variables. Names should include `test` to satisfy fixture guards. These placeholders intentionally prevent accidentally reusing an assumed credential or host.

```bash
# From backend, with venv active and a provisioned disposable PostgreSQL runtime:
export DATABASE_URL="$JOBGRID_DISPOSABLE_TEST_DSN"
export TEST_DATABASE_URL="$JOBGRID_DISPOSABLE_SCHEMA_TEST_DSN"
: "${DATABASE_URL:?Set an isolated test database DSN}"
: "${TEST_DATABASE_URL:?Set a separate disposable schema-test DSN}"
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m pytest tests -q --tb=short \
  --junitxml=/tmp/jobgrid-completion-evidence/postgres.xml
```

Set the same test-only flags/storage as the SQLite block. Apply migrations against a fresh isolated database before running the suite; ORM `create_all` in test fixtures does not establish migration correctness. Also exercise upgrade from the previous released schema and concurrency tests. Use the existing test names discovered in the repository; do not assume proposed names in the old roadmap are executable selectors.

### Browser — real local backend

Use a **third** disposable PostgreSQL database for browser fixtures. In one terminal, from `backend`, with the venv active:

```bash
export DATABASE_URL="$JOBGRID_DISPOSABLE_BROWSER_TEST_DSN"
: "${DATABASE_URL:?Set an isolated browser-test database DSN}"
export ENVIRONMENT=test TEST_AUTH=true
export SECRET_KEY='jobgrid-local-browser-only-not-production'
export FRONTEND_URL='http://localhost:5173'
export CORS_ORIGINS='http://localhost:5173'
export RUN_MAINTENANCE_JOBS=false RUN_REMINDER_WORKER=false
export JOB_URL_CHECKS_ENABLED=false SMTP_HOST=''
export DOCUMENT_STORAGE_DIR="$(mktemp -d /tmp/jobgrid-browser-docs.XXXXXX)"
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from `frontend`:

```bash
export VITE_API_URL='http://localhost:8000'
npx playwright test --list --project=chromium
npx playwright test --project=chromium
```

The checked-in Playwright configuration starts Vite on port 5173 and uses one worker. Ensure those ports belong to this test run. Run C-06's added explicit browser-timezone projects after they exist; the current configuration defines only setup and Chromium. The diagnostic `TZ=UTC` rerun is not the desired final timezone matrix.

### Release runbook verification

From the root, with backend dependencies available:

```bash
python scripts/smoke_jobgrid.py --self-test-release-acceptance
python scripts/smoke_jobgrid.py --release-evidence "$JOBGRID_RELEASE_EVIDENCE_FILE"
```

Provide the actual evidence path. Inspect the statuses in the validated file: BLOCKED is not PASS even when validation exits zero. Use the existing [release runbook](docs/RELEASE_ACCEPTANCE.md) for authorized staging backup/restore commands; verify its destination before execution.

### Evidence template for each task or gate

```text
Task / original JG IDs:
Implementer / reviewer:
Source SHA / working-tree changes:
Environment / dependency versions / migration revision:
Fixture and isolation boundary:
Command or manual steps:
Expected result:
Actual result and counts:
Artifact path or CI URL:
Failure injection / retry proof:
Compatibility / rollback result:
External dependencies and exact blocker, if any:
Status: not-started | in-progress | local-ready | staging-accepted | released | blocked
Checked at:
```

No secrets or private payloads belong in this record. Persist the evidence index in the repository or agreed durable artifact store when the task is closed.

<a id="original-tickets"></a>
## 6. All 64 original tickets — completion mapping

The entries below retain each ticket's original implementation scope and add its current closeout route. The scope bullets are **requirements to verify**, not a claim that they all need rebuilding. The current assessment distinguishes implemented work needing verification, confirmed repairs, and external blockers. A historical “completed” roadmap label is not overwritten with a claim that its implementation never existed.

For every entry, execute C-08's requirement-to-evidence procedure, follow its acceptance pack above, and record proof using the evidence template. Dependencies mentioning C-09/C-10 apply to the final external closeout, not to the start of local verification in C-08. Use the linked original specification for its full contracts, file scope, and historical microtasks; revalidate historical proposed names against current code before acting.

The index contains 64 original tickets with local acceptance mapped by C-08. JG-024 and JG-040 retain external acceptance gates. Other deployment/recovery obligations remain in C-09/C-10; local acceptance is not production certification.

### Ticket index

| Ticket | Scope | Closeout status |
|---|---|---|
| [JG-001](#jg-001-closeout) | Freeze and validate the complete backup v2 record schema | Local acceptance passed |
| [JG-002](#jg-002-closeout) | Add import identity mapping and complete v2 export | Local acceptance passed |
| [JG-003](#jg-003-closeout) | Implement preflight and transactional full restore | Local acceptance passed |
| [JG-004](#jg-004-closeout) | Build restore preview and prove recoverability in the UI | Local acceptance passed |
| [JG-005](#jg-005-closeout) | Extract one account-scoped query builder without changing list behavior | Local acceptance passed |
| [JG-006](#jg-006-closeout) | Route every export through the shared filter contract | Local acceptance passed |
| [JG-007](#jg-007-closeout) | Unify browser and saved-view query serialization | Local acceptance passed |
| [JG-008](#jg-008-closeout) | Define metric semantics and add durable lifecycle event storage | Local acceptance passed |
| [JG-009](#jg-009-closeout) | Wire every mutation into the lifecycle ledger | Local acceptance passed |
| [JG-010](#jg-010-closeout) | Add user timezone and safely backfill known historical facts | Local acceptance passed |
| [JG-011](#jg-011-closeout) | Switch analytics goals weekly reports and digest to shared definitions | Local acceptance passed |
| [JG-012](#jg-012-closeout) | Introduce explicit archive timestamps and disabled-by-default retention | Local acceptance passed |
| [JG-013](#jg-013-closeout) | Replace broken cleanup with a bounded observable archive job | Local acceptance passed |
| [JG-014](#jg-014-closeout) | Expose retention policy and maintenance health safely | Local acceptance passed |
| [JG-015](#jg-015-closeout) | Create reusable status timestamp URL and bulk validators | Local acceptance passed |
| [JG-016](#jg-016-closeout) | Apply validation atomically to every application writer | Local acceptance passed |
| [JG-017](#jg-017-closeout) | Render field errors and fix asynchronous import feedback | Local acceptance passed |
| [JG-018](#jg-018-closeout) | Define one numeric parsing contract and dialect adapters | Local acceptance passed |
| [JG-019](#jg-019-closeout) | Register SQLite functions in app and test engines and add real schema checks | Local acceptance passed |
| [JG-020](#jg-020-closeout) | Document and verify both runtime paths | Local acceptance passed |
| [JG-021](#jg-021-closeout) | Correct CI paths readiness and PostgreSQL test composition | Local acceptance passed |
| [JG-022](#jg-022-closeout) | Add fail-fast production configuration checks | Local acceptance passed |
| [JG-023](#jg-023-closeout) | Promote audit reproductions into enforced release regressions | Local acceptance passed |
| [JG-024](#jg-024-closeout) | Run staging login delivery restore and rollback acceptance | Local acceptance passed; external gate pending |
| [JG-025](#jg-025-closeout) | Model manual actions and follow-up overrides | Local acceptance passed |
| [JG-026](#jg-026-closeout) | Build the stable daily queue and guarded mutations | Local acceptance passed |
| [JG-027](#jg-027-closeout) | Build the Today screen and accessible action controls | Local acceptance passed |
| [JG-028](#jg-028-closeout) | Prove the daily queue improves a real work session | Local acceptance passed |
| [JG-029](#jg-029-closeout) | Implement conservative URL and company identity rules | Local acceptance passed |
| [JG-030](#jg-030-closeout) | Persist aliases and backfill derived identity safely | Local acceptance passed |
| [JG-031](#jg-031-closeout) | Expose matching and show applied-before context | Local acceptance passed |
| [JG-032](#jg-032-closeout) | Validate duplicate warnings against false positives | Local acceptance passed |
| [JG-033](#jg-033-closeout) | Add evidence records and immutable event payload rules | Local acceptance passed |
| [JG-034](#jg-034-closeout) | Build evidence mutations and merged timeline API | Local acceptance passed |
| [JG-035](#jg-035-closeout) | Build timeline and evidence entry in application detail | Local acceptance passed |
| [JG-036](#jg-036-closeout) | Prove history survives lifecycle and recovery operations | Local acceptance passed |
| [JG-037](#jg-037-closeout) | Model reminder preferences and delivery state machine | Local acceptance passed |
| [JG-038](#jg-038-closeout) | Implement clock-safe planning claiming and delivery | Local acceptance passed |
| [JG-039](#jg-039-closeout) | Expose opt-in preferences and delivery history | Local acceptance passed |
| [JG-040](#jg-040-closeout) | Verify reminder recovery and controlled real delivery | Local acceptance passed; external gate pending |
| [JG-041](#jg-041-closeout) | Model immutable document versions and private storage boundaries | Local acceptance passed |
| [JG-042](#jg-042-closeout) | Implement bounded upload download and storage reconciliation | Local acceptance passed |
| [JG-043](#jg-043-closeout) | Add document library and per-application version selection | Local acceptance passed |
| [JG-044](#jg-044-closeout) | Extend recoverable backups to document bytes | Local acceptance passed |
| [JG-045](#jg-045-closeout) | Add manual capture schema and replay identity | Local acceptance passed |
| [JG-046](#jg-046-closeout) | Implement capture API with identity warnings | Local acceptance passed |
| [JG-047](#jg-047-closeout) | Build quick-add page and user-invoked bookmarklet | Local acceptance passed |
| [JG-048](#jg-048-closeout) | Validate capture across browsers and lifecycle transitions | Local acceptance passed |
| [JG-049](#jg-049-closeout) | Model explicit deadlines and availability evidence | Local acceptance passed |
| [JG-050](#jg-050-closeout) | Implement manual freshness and a disabled-by-default safe check adapter | Local acceptance passed |
| [JG-051](#jg-051-closeout) | Show deadlines freshness labels and Today actions | Local acceptance passed |
| [JG-052](#jg-052-closeout) | Validate freshness limits and false-closure resistance | Local acceptance passed |
| [JG-053](#jg-053-closeout) | Model contacts associations and scheduled interviews | Local acceptance passed |
| [JG-054](#jg-054-closeout) | Build private workspace APIs and safe calendar downloads | Local acceptance passed |
| [JG-055](#jg-055-closeout) | Build application people and interview panels | Local acceptance passed |
| [JG-056](#jg-056-closeout) | Verify contact privacy scheduling and recovery | Local acceptance passed |
| [JG-057](#jg-057-closeout) | Model private import previews and reusable column mappings | Local acceptance passed |
| [JG-058](#jg-058-closeout) | Implement preview parsing and transactional reconciliation | Local acceptance passed |
| [JG-059](#jg-059-closeout) | Build column mapping and deliberate commit preview | Local acceptance passed |
| [JG-060](#jg-060-closeout) | Validate reimport repeatability and bounded resource use | Local acceptance passed |
| [JG-061](#jg-061-closeout) | Add optimistic versions and bounded undo journals | Local acceptance passed |
| [JG-062](#jg-062-closeout) | Implement transactional bulk changes and conflict-aware undo | Local acceptance passed |
| [JG-063](#jg-063-closeout) | Build Archive and explicit Undo conflict handling | Local acceptance passed |
| [JG-064](#jg-064-closeout) | Prove recovery and decide whether automatic purge is safe | Local acceptance passed |

<a id="jg-001-closeout"></a>
### JG-001 — Freeze and validate the complete backup v2 record schema

**Source entry points (present in inspected checkout):** [backups.py](backend/app/services/backups.py), [contact_backups.py](backend/app/services/contact_backups.py), [import_backups.py](backend/app/services/import_backups.py), [BackupRestore.jsx](frontend/src/components/BackupRestore.jsx). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-001 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-001).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-001.01 Create strict Pydantic v2 backup models with extra=forbid and an explicit section field allowlist
- [x] JG-001.02 List every current model column as exported, reconstructed, deliberately excluded with reason, or an unresolved migration blocker; include UrlHistory and preference/goal rows
- [x] JG-001.03 Define backup-local references and canonical checksum serialization; use allow_nan=False and reject duplicate JSON object keys
- [x] JG-001.04 Validate lengths, total-record limits, section uniqueness and reference targets before constructing ORM objects
- [x] JG-001.05 Implement a v1-to-internal-format adapter that records which fields were absent; never infer first application dates
- [x] JG-001.06 Write the v2 example and version compatibility table in the build guide

**Required assertion scenarios from the original ticket:** `assert_complete_model_field_inventory`, `test_null_empty_false_zero_round_trip`, `test_unknown_section_or_ownership_field`, `test_duplicate_refs_and_bad_checksum`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-002-closeout"></a>
### JG-002 — Add import identity mapping and complete v2 export

**Source entry points (present in inspected checkout):** [backups.py](backend/app/services/backups.py), [contact_backups.py](backend/app/services/contact_backups.py), [import_backups.py](backend/app/services/import_backups.py), [BackupRestore.jsx](frontend/src/components/BackupRestore.jsx). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-002 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-002).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-002.01 Add BackupImportMap with account foreign key, backup UUID, section and source reference; unique index prevents duplicate replay identities
- [x] JG-002.02 Generate deterministic per-record backup_ref values within the export without exposing them as reusable authorization identifiers
- [x] JG-002.03 Read all sections within one consistent database snapshot; use PostgreSQL repeatable-read for export and an equivalent read transaction in SQLite
- [x] JG-002.04 Serialize exact CSV and track fields using JG-001 schema; translate every supported FK to a backup-local reference
- [x] JG-002.05 Add version=2 branch to GET export while retaining old v1 output for compatibility
- [x] JG-002.06 Include declared section counts and checksum; close cursors and transaction on serialization failure; never commit unrelated state from GET

**Required assertion scenarios from the original ticket:** `test_export_every_section`, `test_foreign_user_absent`, `test_export_reference_graph`, `test_migration_up_down_empty`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-003-closeout"></a>
### JG-003 — Implement preflight and transactional full restore

**Source entry points (present in inspected checkout):** [backups.py](backend/app/services/backups.py), [contact_backups.py](backend/app/services/contact_backups.py), [import_backups.py](backend/app/services/import_backups.py), [BackupRestore.jsx](frontend/src/components/BackupRestore.jsx). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-003 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-003).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-003.01 Read at most 20 MiB plus one byte; use application body limits as a second guard and do not call unbounded file.read
- [x] JG-003.02 Parse and validate the entire record graph and checksum before beginning destination writes
- [x] JG-003.03 Build a preflight plan of creates, natural-key skips, conflicts and remapped references; verify_only returns that plan
- [x] JG-003.04 Insert sessions and rows before dependent tracks, batches and events; resolve duplicate_of after all source rows have mapped IDs
- [x] JG-003.05 Insert restored rows, preferences, goals and import identity mapping in one transaction; use savepoints or an upsert for concurrent map uniqueness
- [x] JG-003.06 On retry return stable mapping results without repeating mutations; on any insert/reference failure roll back every section
- [x] JG-003.07 Preserve destination-owned records on merge conflicts and report exact counts; v1 omissions produce explicit incomplete warnings

**Required assertion scenarios from the original ticket:** `test_restore_applied_company_notes_and_dates`, `test_retry_and_concurrent_retry`, `test_failure_on_last_section_rolls_back_all`, `test_merge_preserves_newer_destination`, `test_wrong_account_and_reference_injection`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-004-closeout"></a>
### JG-004 — Build restore preview and prove recoverability in the UI

**Source entry points (present in inspected checkout):** [backups.py](backend/app/services/backups.py), [contact_backups.py](backend/app/services/contact_backups.py), [import_backups.py](backend/app/services/import_backups.py), [BackupRestore.jsx](frontend/src/components/BackupRestore.jsx). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-004 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-004).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-004.01 Add export-v2 and restore entry points next to existing backup export; keep the ordinary data export separate
- [x] JG-004.02 Present section counts, legacy limitations and merge policy after verify_only; require a deliberate Restore click to write
- [x] JG-004.03 Retain selected file in memory only; disable duplicate submissions, reset result when a different file is chosen
- [x] JG-004.04 Render uploading, validating, ready, importing, completed-with-warnings and error states with retry guidance; never show success on HTTP failure
- [x] JG-004.05 After completion refresh Applications and Companies from the server and offer a summary download without embedded private records
- [x] JG-004.06 Exercise the group manual QA with two disposable accounts; save expected/actual evidence and update backup limitations in README and build guide

**Required assertion scenarios from the original ticket:** `backup-restore.spec.ts`, `test_invalid_file_has_no_restore_button`, `test_legacy_backup_warning`, `test_import_failure_does_not_clear_selection`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-005-closeout"></a>
### JG-005 — Extract one account-scoped query builder without changing list behavior

**Source entry points (present in inspected checkout):** [row_queries.py](backend/app/services/row_queries.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-005 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-005).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-005.01 Capture all existing query arguments and expected defaults from active routes and client mapping
- [x] JG-005.02 Create RowQuery and ApplicationQuery models separate from output serializers; bind user_id from get_current_user only
- [x] JG-005.03 Move predicates and stable ordering into pure query-building functions returning SQLAlchemy queries; keep serializers at route boundary
- [x] JG-005.04 Replace list_rows and application list use incrementally while preserving count, page_size and has_next behavior
- [x] JG-005.05 Keep numeric sort expression delegated to the current adapter; do not conceal the SQLite failure scheduled for JG-018
- [x] JG-005.06 Prove generated row IDs are unchanged for supported existing filters before enabling export reuse

**Required assertion scenarios from the original ticket:** `test_each_filter_and_pair`, `test_two_users_same_url`, `test_null_and_empty_columns`, `test_page_boundaries_and_ties`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-006-closeout"></a>
### JG-006 — Route every export through the shared filter contract

**Source entry points (present in inspected checkout):** [row_queries.py](backend/app/services/row_queries.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-006 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-006).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-006.01 Add all shared filter parameters to dashboard and applications exports with documented aliases
- [x] JG-006.02 Apply scope and ownership checks before querying; selected scope rejects absent, malformed or foreign IDs
- [x] JG-006.03 Use the same order expression as the table, omit offset/limit for filtered export, and stream bounded chunks instead of reading every record into an additional large list
- [x] JG-006.04 Validate requested columns against CSV_COLUMNS and preserve explicit column order
- [x] JG-006.05 Add spreadsheet-safe CSV escaping only at serialization; keep JSON lossless and document the distinction
- [x] JG-006.06 Return no export body on validation errors; event metadata records only count, format and bounded filter-presence flags

**Required assertion scenarios from the original ticket:** `test_filtered_export_equals_all_list_pages`, `test_selected_empty_never_exports_all`, `test_selected_foreign_id`, `test_formula_cells_escaped_in_csv_only`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-007-closeout"></a>
### JG-007 — Unify browser and saved-view query serialization

**Source entry points (present in inspected checkout):** [row_queries.py](backend/app/services/row_queries.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #45; CI run #70 passed\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-007 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-007).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-007.01 Create one serializer for each shared query model with known camelCase aliases and explicit false/null handling
- [x] JG-007.02 Use it for list loads, filtered export, top-five fetches and saved-view application
- [x] JG-007.03 Make export scope and sort explicit, and ensure export from page 2 does not inherit page parameters
- [x] JG-007.04 Read saved-view filters from the actual navigation URL/state on initial load, validate them and show a recoverable error for unsupported keys
- [x] JG-007.05 Capture the exact query at click time; disable export until the matching request state has settled and surface network errors
- [x] JG-007.06 Exercise the group manual QA and add an ID-based assertion rather than checking only that a file downloaded

**Required assertion scenarios from the original ticket:** `filter-export-parity.spec.ts`, `test_selected_scope_exact_ids`, `test_sort_changes_export_order`, `test_error_response_not_downloaded_as_csv`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-008-closeout"></a>
### JG-008 — Define metric semantics and add durable lifecycle event storage

**Source entry points (present in inspected checkout):** [lifecycle.py](backend/app/services/lifecycle.py), [models.py](backend/app/models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #47; CI run #74 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-008 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-008).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-008.01 Add the table, uniqueness constraints and user/time/kind composite index from CCR-LIFECYCLE-1
- [x] JG-008.02 Implement write_event within a caller-owned transaction; never commit inside the helper
- [x] JG-008.03 Define pure event-key generation and per-kind payload validation; reject unknown kinds
- [x] JG-008.04 Implement first-visit and first-application insert-on-conflict semantics for PostgreSQL and SQLite
- [x] JG-008.05 Expose saved,visited,applied definitions as named service functions; avoid reusing count(JobTrack) for visits
- [x] JG-008.06 Extend backup v2 schema/export/import maps for lifecycle events in the same ticket and assert no restore emits new first events

**Required assertion scenarios from the original ticket:** `first_event_replay`, `event_owner`, `transaction_rollback`, `backup_lifecycle_roundtrip`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-009-closeout"></a>
### JG-009 — Wire every mutation into the lifecycle ledger

**Source entry points (present in inspected checkout):** [lifecycle.py](backend/app/services/lifecycle.py), [models.py](backend/app/models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #49; CI run #80 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-009 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-009).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-009.01 List active writers: click, from-row, from-rows bulk, application patch, bulk patch, follow-up presets, external import and ApplyPilot result import
- [x] JG-009.02 Route state changes through common service methods receiving a transaction, authenticated user and stable operation ID
- [x] JG-009.03 Record first_visited once at actual visit write; record first_applied once when missing applied_at becomes known
- [x] JG-009.04 Record status_changed only if the value actually changes, with from/to and source; date correction uses an explicit correction kind
- [x] JG-009.05 Validate every bulk target belongs to the user before any mutation, then commit state and events once
- [x] JG-009.06 Ensure imports preserve declared dates and do not treat restore/replay as a fresh application; surface uniqueness conflicts as retryable 409 rather than blind re-execution

**Required assertion scenarios from the original ticket:** `all_writer_paths_emit_same_facts`, `repeat_patch_same_status`, `bulk_partial_failure`, `applypilot_replay`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-010-closeout"></a>
### JG-010 — Add user timezone and safely backfill known historical facts

**Source entry points (present in inspected checkout):** [lifecycle.py](backend/app/services/lifecycle.py), [models.py](backend/app/models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #52; CI run #97 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-010 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-010).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [x] JG-010.01 Add timezone default UTC for existing users and validate new selections with zoneinfo; accept neither an arbitrary offset nor an invalid zone name
- [x] JG-010.02 Implement profile read/update routes and common UTC-boundary calculation for daily and rolling-week metrics
- [x] JG-010.03 Write a resumable backfill command with --dry-run and --after-id; process at most 500 rows per transaction
- [x] JG-010.04 Create historical first events only from nonnull clicked_at/applied_at; record source=legacy_backfill and preserve original dates
- [x] JG-010.05 Detect conflicting URL duplicates and missing dates; produce aggregate warning counts and a private review query, not a public list of user records
- [x] JG-010.06 Extend backup of profile timezone and compare dry-run counts before applying to a disposable copy

**Required assertion scenarios from the original ticket:** `kolkata_midnight`, `dst_23_and_25_hour_days`, `backfill_twice`, `missing_applied_date`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-011-closeout"></a>
### JG-011 — Switch analytics goals weekly reports and digest to shared definitions

**Source entry points (present in inspected checkout):** [lifecycle.py](backend/app/services/lifecycle.py), [models.py](backend/app/models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #55; CI run #103 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-011 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-011).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-011.01 Replace independent event/track/csv counting with shared metric service calls while preserving response field compatibility
- [ ] JG-011.02 Show distinct labels Visited jobs, Saved jobs and Applied jobs; do not silently rename a response key without documenting its corrected meaning
- [ ] JG-011.03 Add timezone selection and an explanation that historical records with unknown dates are excluded from dated totals
- [ ] JG-011.04 Use the same boundaries in goals, weekly report and digest data collection; do not send a real email during automated tests
- [ ] JG-011.05 Avoid per-row counting queries; group in SQL with bounded dimensions and account scoping
- [ ] JG-011.06 Run the group QA and verify exact numeric assertions across pages after retries and a source-row deletion

**Required assertion scenarios from the original ticket:** `metric-consistency.spec.ts`, `daily_boundary_api`, `historical_delete`, `digest_preview_matches_weekly`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-012-closeout"></a>
### JG-012 — Introduce explicit archive timestamps and disabled-by-default retention

**Source entry points (present in inspected checkout):** [retention.py](backend/app/services/retention.py), [config.py](backend/app/config.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-012 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-012).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-012.01 Add archived_at and nullable user retention preference with documented migration defaults
- [ ] JG-012.02 Keep legacy archived flags but leave unknown archived_at null; do not backdate them
- [ ] JG-012.03 Change manual archive to update only rows transitioning false to true; preserve application snapshots and duplicate links
- [ ] JG-012.04 Add non-destructive retention configuration with allowed days 0 or 7..3650; reject invalid negative/too-small values
- [ ] JG-012.05 Extend backup v2 for archive metadata and retention preferences
- [ ] JG-012.06 Document the retirement of implicit two-day cleanup and keep all purge activation off

**Required assertion scenarios from the original ticket:** `archive_twice_preserves_timestamp`, `existing_archived_unknown_date_is_not_purgeable`, `migration_does_not_hide_unvisited_rows`, `backup_preserves_archive_state`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-013-closeout"></a>
### JG-013 — Replace broken cleanup with a bounded observable archive job

**Source entry points (present in inspected checkout):** [retention.py](backend/app/services/retention.py), [config.py](backend/app/config.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-013 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-013).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-013.01 Remove the nonexistent updated_at access and the current hard-delete branch
- [ ] JG-013.02 Select only policy-eligible visited nonarchived rows using clicked_at and account policy; old created_at alone is insufficient
- [ ] JG-013.03 Page deterministically in batches of 500; update state/timestamp in a single transaction per batch
- [ ] JG-013.04 Add process job registration guard and database lease/lock where more than one scheduler instance is possible; log lease contention as skipped
- [ ] JG-013.05 Return or record the structured result and propagate a bounded failure state to logging/metrics; do not catch and pretend success
- [ ] JG-013.06 Exercise eligibility, clock boundaries, repeated runs, lock expiry and mid-batch rollback

**Required assertion scenarios from the original ticket:** `old_unvisited_is_preserved`, `500_row_batch_limit_and_resume`, `cleanup_failure_not_zero_success`, `two_workers_do_not_double_count`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-014-closeout"></a>
### JG-014 — Expose retention policy and maintenance health safely

**Source entry points (present in inspected checkout):** [retention.py](backend/app/services/retention.py), [config.py](backend/app/config.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-014 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-014).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-014.01 Add GET/PATCH /crm/profile/retention with {archive_after_days:0
- [ ] JG-014.02 7..3650}; document that purge is unavailable until the final archive tranche
- [ ] JG-014.03 Show disabled-by-default control, eligible-row count preview and last successful cleanup time
- [ ] JG-014.04 Require an explicit Save for policy changes; do not run cleanup merely by opening settings
- [ ] JG-014.05 Display failed/stale maintenance state as unavailable rather than reporting zero eligible jobs
- [ ] JG-014.06 Add a link to preserved archived rows only once JG-062 exists; until then explain archive recovery is an API/operator action and do not enable auto archive in production
- [ ] JG-014.07 Run policy UI validation and record the operational owner/run command in the guide

**Required assertion scenarios from the original ticket:** `retention-settings.spec.ts`, `cross_account_policy_write_is_denied`, `preview_has_no_side_effect`, `failed_health_does_not_look_healthy`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-015-closeout"></a>
### JG-015 — Create reusable status timestamp URL and bulk validators

**Source entry points (present in inspected checkout):** [validation.py](backend/app/services/validation.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-015 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-015).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-015.01 Create reusable enums and validators without changing domain data storage types
- [ ] JG-015.02 Separate omitted fields from explicit clear using model_fields_set/exclude_unset semantics
- [ ] JG-015.03 Parse date-only values only with an explicit user timezone supplied by the service; do not use server local time
- [ ] JG-015.04 Validate URL scheme/host/credential limits and lengths before constructing a JobTrack
- [ ] JG-015.05 Normalize bulk IDs while retaining source indices for error reporting
- [ ] JG-015.06 Add a compatibility error formatter that accepts legacy string/dict and new field lists

**Required assertion scenarios from the original ticket:** `parameterized_status_allowed_and_rejected`, `omitted_null_empty_date_semantics`, `date_only_kolkata_conversion`, `bulk_duplicate_missing_foreign_and_max_count`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-016-closeout"></a>
### JG-016 — Apply validation atomically to every application writer

**Source entry points (present in inspected checkout):** [validation.py](backend/app/services/validation.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-016 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-016).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-016.01 Inventory and update single patch, bulk patch, from-row, from-rows, external import and ApplyPilot result paths
- [ ] JG-016.02 Preload ownership of all referenced rows/tracks; validate the whole batch before mutations
- [ ] JG-016.03 Preserve first applied_at on ordinary retries; use explicit correction commands for date edits
- [ ] JG-016.04 Catch only expected parse/constraint errors and map to 400/409/422; unexpected failures stay 500 with a request ID and rollback
- [ ] JG-016.05 Reject invalid JSON backup bodies using the JG-001 parser instead of exposing a stack trace
- [ ] JG-016.06 Add a read-only legacy-invalid-data report; keep repair as deliberate user correction

**Required assertion scenarios from the original ticket:** `endpoint_matrix_invalid_status_never_200`, `second_invalid_record_rolls_back_batch`, `date_clear_with_applied_status_rejected`, `concurrent_duplicate_returns_safe_conflict_or_existing_record`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-017-closeout"></a>
### JG-017 — Render field errors and fix asynchronous import feedback

**Source entry points (present in inspected checkout):** [validation.py](backend/app/services/validation.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-017 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-017).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-017.01 Use await file.text() and one awaited API call inside a single try/catch/finally for external import
- [ ] JG-017.02 Clear stale preview/result when file changes or parsing fails; disable Import until a valid parse exists
- [ ] JG-017.03 Display full file row count and preview count separately instead of saying 10 of 10 for larger files
- [ ] JG-017.04 Use the shared error formatter for application fields and import errors; keep user input on failure
- [ ] JG-017.05 Prevent duplicate form submission and confirm displayed state from server response, then refresh persisted values
- [ ] JG-017.06 Test keyboard submission and focus return to the first invalid field; preserve read-only dates until the user explicitly edits

**Required assertion scenarios from the original ticket:** `application-validation.spec.ts`, `file_reader_and_network_failure`, `pending_request_button_disabled`, `preview_10_of_25_and_invalid_replacement_file`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-018-closeout"></a>
### JG-018 — Define one numeric parsing contract and dialect adapters

**Source entry points (present in inspected checkout):** [numeric_values.py](backend/app/services/numeric_values.py), [database.py](backend/app/database.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-018 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-018).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-018.01 Write a table of accepted and rejected numeric strings and expected Decimal/null values
- [ ] JG-018.02 Implement the deterministic parser with a length cap of 128 characters and finite-number check
- [ ] JG-018.03 Select a PostgreSQL numeric expression or SQLite jobgrid_numeric expression by bound dialect
- [ ] JG-018.04 Apply consistent nulls-last and deterministic ID tie-breakers
- [ ] JG-018.05 Cover each numeric CSV field and salary filters without modifying stored text

**Required assertion scenarios from the original ticket:** `numeric_order_not_lexical`, `invalid_values_last_both_directions`, `negative_decimal_percentage_currency`, `long_or_nonfinite_value_is_null`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-019-closeout"></a>
### JG-019 — Register SQLite functions in app and test engines and add real schema checks

**Source entry points (present in inspected checkout):** [numeric_values.py](backend/app/services/numeric_values.py), [database.py](backend/app/database.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-019 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-019).

**Historical audit finding (superseded by C-08 local acceptance):** The C-05 timestamp regressions are closed with PostgreSQL and explicit SQLite evidence. JG-019 remains open for its broader SQLite function/schema and C-07 matrix acceptance; the old audit failures are historical.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-019.01 Create an engine-configuration helper or engine connect listener that registers SQLite functions on every connection
- [ ] JG-019.02 Call the same setup from fixture-created engines and background session factories
- [ ] JG-019.03 Use per-test disposable DB naming and foreign_keys=ON in SQLite acceptance fixtures
- [ ] JG-019.04 Add a PostgreSQL-only test marker that requires a supplied isolated TEST_DATABASE_URL and fails visibly when mandatory CI cannot supply it
- [ ] JG-019.05 Use SQLAlchemy inspector to compare actual tables, nullability, indexes and critical uniqueness/FK constraints after alembic upgrade head
- [ ] JG-019.06 Do not count a skipped PostgreSQL check as schema acceptance

**Required assertion scenarios from the original ticket:** `new_connection_has_function`, `foreign_key_fixture_enforced`, `fresh_postgres_matches_metadata`, `migration_replay_is_noop`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-020-closeout"></a>
### JG-020 — Document and verify both runtime paths

**Source entry points (present in inspected checkout):** [numeric_values.py](backend/app/services/numeric_values.py), [database.py](backend/app/database.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-020 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-020).

**Historical audit finding (superseded by C-08 local acceptance):** C-05 is closed. JG-020 remains open until C-07 enforces the complete supported runtime matrix and separate migration evidence.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-020.01 Document SQLite quick start separately from PostgreSQL migration and release acceptance
- [ ] JG-020.02 Add a browser test clicking Resume Score and asserting exact row order rather than only a header arrow
- [ ] JG-020.03 Run the numeric test suite on SQLite and PostgreSQL; capture server errors if either fails
- [ ] JG-020.04 Verify a new DB connection and application restart do not lose function registration
- [ ] JG-020.05 State migration rollback limitations and the approved production DB version without claiming unrun evidence

**Required assertion scenarios from the original ticket:** `numeric-sort.spec.ts`, `both_dialect_api_responses_are_200`, `startup_and_new_connection_smoke`, `release_requires_real_postgres_result`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-021-closeout"></a>
### JG-021 — Correct CI paths readiness and PostgreSQL test composition

**Source entry points (present in inspected checkout):** [ci.yml](.github/workflows/ci.yml), [config.py](backend/app/config.py), [RELEASE_ACCEPTANCE.md](docs/RELEASE_ACCEPTANCE.md). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-021 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-021).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-021.01 Change the backend start step to the real backend working directory; remove cd ../backend
- [ ] JG-021.02 Run alembic upgrade head before starting the API and print only the revision, not the DSN credentials
- [ ] JG-021.03 Replace fixed sleep with bounded health polling and capture sanitized server logs on failure
- [ ] JG-021.04 Start PostgreSQL tests with explicit isolated environment variables; never use production secrets in PR jobs
- [ ] JG-021.05 Keep browser auth setup as a dependency and verify test collection is nonempty
- [ ] JG-021.06 Attach test and trace artifacts on failure with retention appropriate for synthetic data

**Required assertion scenarios from the original ticket:** `workflow_command_resolves_backend_directory`, `health_timeout_fails_job`, `postgres_suite_and_browser_suite_run`, `zero_tests_or_failed_setup_is_not_success`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-022-closeout"></a>
### JG-022 — Add fail-fast production configuration checks

**Source entry points (present in inspected checkout):** [ci.yml](.github/workflows/ci.yml), [config.py](backend/app/config.py), [RELEASE_ACCEPTANCE.md](docs/RELEASE_ACCEPTANCE.md). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-022 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-022).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-022.01 Add a pure configuration validator invoked before route-serving startup
- [ ] JG-022.02 Reject TEST_AUTH in production and empty/default signing secrets; keep real secret value out of exceptions
- [ ] JG-022.03 Require valid HTTPS public origins in production and explicit CORS allowlist; preserve localhost only for development/test
- [ ] JG-022.04 Test cookie Secure and expected SameSite options for production OAuth login/logout
- [ ] JG-022.05 Make dev-login return 404 under production regardless of the request payload
- [ ] JG-022.06 Document required deployment environment checks and how to generate/store a signing secret outside the repo

**Required assertion scenarios from the original ticket:** `production_test_auth_rejected_before_serving`, `default_or_empty_key_rejected`, `https_and_cors_validation`, `test_environment_dev_login_preserved`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-023-closeout"></a>
### JG-023 — Promote audit reproductions into enforced release regressions

**Source entry points (present in inspected checkout):** [ci.yml](.github/workflows/ci.yml), [config.py](backend/app/config.py), [RELEASE_ACCEPTANCE.md](docs/RELEASE_ACCEPTANCE.md). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-023 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-023).

**Historical audit finding (superseded by C-08 local acceptance):** The current release suite missed the independent restore and pagination reproductions. C-07 must enforce them.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-023.01 Turn each audit failure into an unconditional assertion with a nonempty synthetic fixture
- [ ] JG-023.02 Include backup round trip, multi-filter export, metric reconciliation, invalid inputs, cleanup failure and numeric sort
- [ ] JG-023.03 Replace conditional if-data assertions within touched tests; fail setup when expected fixtures are missing
- [ ] JG-023.04 Require all tests on the migrated PostgreSQL runtime and keep SQLite functional coverage separately
- [ ] JG-023.05 Record application/library/browser versions and current SHA beside test evidence
- [ ] JG-023.06 Define the local-ready, staging-accepted and released status vocabulary; never collapse them into Done

**Required assertion scenarios from the original ticket:** `break_each_contract_then_test_fails`, `cross_user_scenarios_remain_denied`, `test_count_nonzero`, `no_manual_skip_counts_as_pass`, `original_company_history_survives_source_delete_and_slash_name`, `top5_complete_filters_sort_safe_url_popup_blocking_and_click_recording`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-024-closeout"></a>
### JG-024 — Run staging login delivery restore and rollback acceptance

**Source entry points (present in inspected checkout):** [ci.yml](.github/workflows/ci.yml), [config.py](backend/app/config.py), [RELEASE_ACCEPTANCE.md](docs/RELEASE_ACCEPTANCE.md). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed; external gate pending.
**Prior roadmap label:** COMPLETED / checked — local acceptance tooling merged and CI-verified; external staging gates remain BLOCKED, so no staging-accepted or released claim is made\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-024 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-024).

**Historical audit finding (superseded by C-08 local acceptance):** Local acceptance tooling exists; external staging gates remain unverified. C-09/C-10 must close them before release.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-024.01 Create an evidence checklist with owner, environment, command, expected and actual result for each gate
- [ ] JG-024.02 Use a disposable PostgreSQL DB to prove backup restore retains rows, tracks, notes, dates and references; compare row counts plus content hashes
- [ ] JG-024.03 Test additive migration followed by old-code startup while retaining new columns, then restore current code
- [ ] JG-024.04 Exercise configured OAuth login/logout with a staging test account; verify account linkage and cookie behavior
- [ ] JG-024.05 With explicit sending authorization, deliver one SMTP message to a controlled sandbox and inspect received content; do not treat status=logged as delivered
- [ ] JG-024.06 Run smoke requests after backend/frontend deployment and document rollback trigger; leave external gates blocked if credentials/environment are unavailable

**Required assertion scenarios from the original ticket:** `staging_restore_content_comparison`, `oauth_real_provider_not_dev_login`, `smtp_received_not_merely_queued`, `rollback_preserves_user_history`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-025-closeout"></a>
### JG-025 — Model manual actions and follow-up overrides

**Source entry points (present in inspected checkout):** [today.py](backend/app/services/today.py), [today_f8.py](backend/app/services/today_f8.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked — schema/contract foundation merged and CI-verified; Today API/navigation remains owned by JG-026–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-025 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-025).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-025.01 Add WorkItem and WorkItemOverride with owner indexes, timezone-aware timestamps and positive version constraints
- [ ] JG-025.02 Keep derived follow-ups out of WorkItem; define and validate source action keys against owned source records
- [ ] JG-025.03 Constrain description to1..500 trimmed characters, priority0..3 and the two states; done requires completed_at
- [ ] JG-025.04 Write an additive migration and test foreign-key detachment without deleting work items
- [ ] JG-025.05 Extend backup v2 with work_items and work_item_overrides, including remapped track refs; old v2 files omit these sections safely
- [ ] JG-025.06 Add nullable row/source-view references and origin_key uniqueness for explicit shortlist actions; preserve description after source deletion

**Required assertion scenarios from the original ticket:** `owned_action_key_rejects_foreign_track`, `migration_preserves_existing_followups`, `done_timestamp_constraint`, `backup_round_trip_retains_snooze_and_manual_action`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-026-closeout"></a>
### JG-026 — Build the stable daily queue and guarded mutations

**Source entry points (present in inspected checkout):** [today.py](backend/app/services/today.py), [today_f8.py](backend/app/services/today_f8.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked — backend Today API/service merged and CI-verified; Today UI/navigation remains owned by JG-027–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-026 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-026).

**Historical audit finding (superseded by C-08 local acceptance):** Confirmed integration defect: the interview wrapper can truncate the queue with no continuation cursor. Close C-04.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-026.01 Compute local-day UTC bounds using the validated account timezone from JG-010
- [ ] JG-026.02 Build owned manual and derived-follow-up queries with snooze exclusion and the frozen deterministic order
- [ ] JG-026.03 Implement cursor decoding and limits; include counts with exactly the same membership filters
- [ ] JG-026.04 Implement create/edit/snooze using version compare-and-update in one transaction; return409 without overwriting newer state
- [ ] JG-026.05 Resolve follow-ups through the existing validated follow-up writer and lifecycle ledger; reject terminal or disappeared sources
- [ ] JG-026.06 Register the router and document response examples for empty, overdue and conflict states
- [ ] JG-026.07 Implement bounded from-view creation using the R2 server query, preserving sort and deduplicating pending origin keys

**Required assertion scenarios from the original ticket:** `queue_local_midnight_and_dst`, `pagination_no_duplicates_for_fixed_fixture`, `stale_version_returns409_without_write`, `followup_completion_does_not_increment_applied`, `foreign_action_returns404`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-027-closeout"></a>
### JG-027 — Build the Today screen and accessible action controls

**Source entry points (present in inspected checkout):** [today.py](backend/app/services/today.py), [today_f8.py](backend/app/services/today_f8.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-027 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-027).

**Historical audit finding (superseded by C-08 local acceptance):** Today UI exists despite the stale proposed status. Close C-06 timezone assertions and C-08 keyboard/real-API acceptance.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-027.01 Add a Today route and navigation item with overdue, due today and undated group labels
- [ ] JG-027.02 Display company, role, source, due time and one primary action; link to the existing application drawer
- [ ] JG-027.03 Add manual action creation and explicit complete, snooze and reschedule dialogs with keyboard focus return
- [ ] JG-027.04 Show initial loading, empty success, network retry, per-item pending and stale-version conflict states
- [ ] JG-027.05 Refresh after server success and on window focus; preserve form drafts on failures and never optimistically mark application status
- [ ] JG-027.06 Use a fake account timezone/clock fixture to exercise day boundaries rather than depending on wall-clock today
- [ ] JG-027.07 Add Add to Today in saved views and application/row detail; display origin and exact count before creating at most20 actions

**Required assertion scenarios from the original ticket:** `today.spec.ts`, `keyboard_snooze_persists_after_reload`, `failed_complete_preserves_item`, `followup_reschedule_updates_application_drawer`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-028-closeout"></a>
### JG-028 — Prove the daily queue improves a real work session

**Source entry points (present in inspected checkout):** [today.py](backend/app/services/today.py), [today_f8.py](backend/app/services/today_f8.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-028 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-028).

**Historical audit finding (superseded by C-08 local acceptance):** A successful small queue does not prove mixed-source pagination. Include C-04 and the full daily-workflow acceptance.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-028.01 Create an acceptance fixture with60 mixed due/manual/snoozed/terminal actions and record exact expected membership
- [ ] JG-028.02 Check query plans on PostgreSQL for owner/due indexes and confirm no per-item ORM query loop
- [ ] JG-028.03 Rehearse five actions from Today through application detail and back; count clicks and unresolved decisions
- [ ] JG-028.04 Verify deletion/detachment, timezone changes, tab conflicts and backup restore using the same fixture
- [ ] JG-028.05 Record baseline and new session results without inventing a speed improvement; keep feature acceptance conditional on understandable actions

**Required assertion scenarios from the original ticket:** `fixed_fixture_membership_and_count_parity`, `no_n_plus_one_queue_queries`, `restore_reconstructs_today_items`, `five_action_workflow_no_lost_changes`, `saved_view_page_two_uses_full_filtered_order_and_no_duplicate_actions`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-029-closeout"></a>
### JG-029 — Implement conservative URL and company identity rules

**Source entry points (present in inspected checkout):** [job_identity.py](backend/app/services/job_identity.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-029 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-029).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-029.01 Implement a pure canonicalizer with explicit version and unchanged original URL output
- [ ] JG-029.02 Write examples for tracking parameters, multiple query values, case-sensitive paths, fragments, ports and international domains
- [ ] JG-029.03 Implement company alias key normalization independently from job identity
- [ ] JG-029.04 Return confidence plus reason codes; never turn fuzzy company/title similarity into equality
- [ ] JG-029.05 Document how provider rules are added with fixtures and a collision report before deployment

**Required assertion scenarios from the original ticket:** `utm_variants_same_canonical_key`, `different_requisition_query_values_remain_distinct`, `path_case_and_duplicate_query_order_preserved`, `credentialed_or_invalid_url_rejected`, `company_similarity_is_possible_only`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-030-closeout"></a>
### JG-030 — Persist aliases and backfill derived identity safely

**Source entry points (present in inspected checkout):** [job_identity.py](backend/app/services/job_identity.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-030 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-030).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-030.01 Add nullable canonical columns and nonunique account/hash indexes plus CompanyAlias table
- [ ] JG-030.02 Create a resumable500-record backfill with --dry-run and --after-id; emit counts not full URLs
- [ ] JG-030.03 Report canonical collisions without merging or changing status, notes or original URLs
- [ ] JG-030.04 Write identity fields on new and edited records through the common service
- [ ] JG-030.05 Extend backup with aliases and preserve original URLs; rebuild derived canonical keys using the recorded rule version after restore

**Required assertion scenarios from the original ticket:** `backfill_retry_is_idempotent`, `canonical_collision_retains_two_tracks`, `aliases_are_account_scoped`, `backup_restores_alias_grouping`, `dry_run_writes_nothing`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-031-closeout"></a>
### JG-031 — Expose matching and show applied-before context

**Source entry points (present in inspected checkout):** [job_identity.py](backend/app/services/job_identity.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-031 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-031).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-031.01 Implement scoped match and alias routes with bounded results and constant-count queries
- [ ] JG-031.02 Filter matches to actual applied history; label canonical and possible results separately with dates and statuses
- [ ] JG-031.03 Show drawer warning before Mark applied and link to the prior application without overwriting the current row
- [ ] JG-031.04 Add explicit company alias create/remove controls and show affected history counts before confirmation
- [ ] JG-031.05 Use encoded route params for slash-containing company names and return404 for foreign records
- [ ] JG-031.06 Handle stale alias conflicts with409 and preserve the users proposed label for retry

**Required assertion scenarios from the original ticket:** `visited_only_has_no_applied_warning`, `exact_match_returns_prior_application_date`, `canonical_warning_does_not_block_reapply`, `slash_company_navigation_works`, `foreign_alias_cannot_be_deleted`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-032-closeout"></a>
### JG-032 — Validate duplicate warnings against false positives

**Source entry points (present in inspected checkout):** [job_identity.py](backend/app/services/job_identity.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-032 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-032).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-032.01 Build a labeled synthetic matrix with exact, canonical, same-company-new-role and unrelated matches
- [ ] JG-032.02 Assert zero automatic merges and exact expected confidence/reason for every case
- [ ] JG-032.03 Exercise upload, row drawer, company aliases and mark-applied paths without duplicating writers
- [ ] JG-032.04 Verify changing a URL or deleting a source CSV leaves prior applied history discoverable
- [ ] JG-032.05 Document observed precision on the fixture and make no claim about real-world matching accuracy until reviewed data exists

**Required assertion scenarios from the original ticket:** `applied-before.spec.ts`, `new_requisition_not_exact_duplicate`, `source_delete_retains_warning`, `alias_remove_changes_grouping_only`, `matching_query_bounded_for_large_fixture`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-033-closeout"></a>
### JG-033 — Add evidence records and immutable event payload rules

**Source entry points (present in inspected checkout):** [evidence.py](backend/app/services/evidence.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-033 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-033).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-033.01 Add evidence table with owner/track indexes, version and explicit soft-delete state
- [ ] JG-033.02 Extend lifecycle kind validation with evidence_added, evidence_edited and evidence_deleted payload allowlists
- [ ] JG-033.03 Define correction events with old/new timestamps and a bounded reason; avoid placing full private evidence in log payloads
- [ ] JG-033.04 Specify retained audit metadata versus removable evidence body in the build guide
- [ ] JG-033.05 Extend backup schemas and reference mapping for evidence and new event kinds
- [ ] JG-033.06 Add EvidenceCreateReceipt and30-day soft-delete body retention/purge semantics; document recovery-export treatment

**Required assertion scenarios from the original ticket:** `evidence_track_owner_checked`, `unknown_event_payload_field_rejected`, `original_event_immutable_after_correction`, `backup_preserves_evidence_event_references`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-034-closeout"></a>
### JG-034 — Build evidence mutations and merged timeline API

**Source entry points (present in inspected checkout):** [evidence.py](backend/app/services/evidence.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #122\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-034 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-034).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-034.01 Create evidence and ledger events in one transaction using a unique account/operation idempotency key
- [ ] JG-034.02 Merge lifecycle and evidence history with stable timestamp/type/ID pagination; bound pages at100
- [ ] JG-034.03 Implement version-guarded edit and idempotent soft-delete with redacted read serialization
- [ ] JG-034.04 Route applied-date correction through the common lifecycle writer and require a reason
- [ ] JG-034.05 Return404 for foreign/missing tracks,409 for stale edits and422 for invalid evidence without partial events
- [ ] JG-034.06 Implement latest-status correction with expected event ID and row lock; reject intervening status edits and append compensation

**Required assertion scenarios from the original ticket:** `create_retry_one_evidence_one_event`, `pagination_same_timestamp_stable`, `soft_deleted_body_absent`, `foreign_timeline_returns404`, `correction_preserves_original_event_and_metrics`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-035-closeout"></a>
### JG-035 — Build timeline and evidence entry in application detail

**Source entry points (present in inspected checkout):** [evidence.py](backend/app/services/evidence.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #124\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-035 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-035).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-035.01 Add a timeline section showing source label, event date and separate recorded-at tooltip
- [ ] JG-035.02 Show Unknown for missing occurrence dates and avoid assuming imported timestamps are application dates
- [ ] JG-035.03 Add plain-text/confirmation-URL evidence form with field errors and pending controls
- [ ] JG-035.04 Require a correction reason when editing applied date and preview how daily metrics will move
- [ ] JG-035.05 Implement load more, empty, error/retry and stale edit states; preserve drafts and return focus after dialogs
- [ ] JG-035.06 Offer Correct latest status with a reason and preview; show409 as a newer-change conflict, not generic failure

**Required assertion scenarios from the original ticket:** `application-timeline.spec.ts`, `unknown_import_date_label`, `script_like_text_rendered_literally`, `stale_edit_draft_preserved`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-036-closeout"></a>
### JG-036 — Prove history survives lifecycle and recovery operations

**Source entry points (present in inspected checkout):** [evidence.py](backend/app/services/evidence.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #127\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-036 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-036).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-036.01 Create a complete timeline fixture with imported history, application, status changes, evidence and correction
- [ ] JG-036.02 Delete only the source CSV and compare the remaining application timeline content
- [ ] JG-036.03 Export and restore into a different empty account, checking remapped evidence and event references
- [ ] JG-036.04 Inject a failure between evidence insertion and event insertion and require complete rollback
- [ ] JG-036.05 Document known uncertainty for legacy dates and the distinction between user-recorded evidence and verified submission

**Required assertion scenarios from the original ticket:** `source_row_delete_retains_evidence`, `restored_timeline_semantic_equivalence`, `event_insert_failure_rolls_back_evidence`, `deleted_evidence_body_not_in_normal_read`, `individual_status_correction_preserves_original_and_rejects_stale_event`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-037-closeout"></a>
### JG-037 — Model reminder preferences and delivery state machine

**Source entry points (present in inspected checkout):** [reminders.py](backend/app/services/reminders.py), [email_transport.py](backend/app/services/email_transport.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #132\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-037 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-037).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-037.01 Add preference/delivery tables with unique occurrence/channel constraint and owner/schedule indexes
- [ ] JG-037.02 Define legal status transitions and immutable sent_at after acceptance
- [ ] JG-037.03 Keep preferences disabled by default for existing and new accounts
- [ ] JG-037.04 Add backup sections for preferences and delivery history; restored pending records stay paused until explicit re-enable
- [ ] JG-037.05 Validate local times, channel, timezone availability and quiet-hour behavior including equal start/end meaning no quiet period

**Required assertion scenarios from the original ticket:** `duplicate_occurrence_unique_constraint`, `illegal_state_transition_rejected`, `default_opt_out`, `restore_does_not_replay_sent_or_pending_email`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-038-closeout"></a>
### JG-038 — Implement clock-safe planning claiming and delivery

**Source entry points (present in inspected checkout):** [reminders.py](backend/app/services/reminders.py), [email_transport.py](backend/app/services/email_transport.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-038 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-038).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-038.01 Implement a pure due-occurrence planner accepting injected UTC clock and account timezone
- [ ] JG-038.02 Upsert deterministic occurrence keys and cancel ineligible unsent rows after source edits
- [ ] JG-038.03 Claim bounded batches with leases and atomic owner checks; test actual PostgreSQL concurrent transactions
- [ ] JG-038.04 Wrap the existing email transport behind an outcome adapter distinguishing accepted, known-rejected and unknown
- [ ] JG-038.05 Apply bounded backoff only to known retryable failures and quarantine ambiguous outcomes
- [ ] JG-038.06 Expose processed/sent/failed/unknown/lease counts with safe error codes and stop gracefully on shutdown

**Required assertion scenarios from the original ticket:** `dst_gap_and_overlap_one_daily_occurrence`, `two_workers_one_claim`, `crash_after_acceptance_becomes_unknown`, `known_transient_failure_bounded_retry`, `rescheduled_followup_cancels_old_delivery`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-039-closeout"></a>
### JG-039 — Expose opt-in preferences and delivery history

**Source entry points (present in inspected checkout):** [reminders.py](backend/app/services/reminders.py), [email_transport.py](backend/app/services/email_transport.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-039 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-039).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-039.01 Implement owner-scoped preference and paginated history APIs with version guards
- [ ] JG-039.02 Add explicit reminder opt-in UI explaining channel, local delivery time and quiet hours
- [ ] JG-039.03 Display in-app unread reminders and truthful pending, sent, failed and uncertain labels
- [ ] JG-039.04 Add deliberate retry for unknown delivery with duplicate warning, new operation ID and audit event
- [ ] JG-039.05 Keep email unavailable with a clear configuration reason if verified destination or transport is absent
- [ ] JG-039.06 Disable pending occurrences when the user opts out and retain historical delivery results

**Required assertion scenarios from the original ticket:** `opt_out_cancels_unsent_only`, `unverified_destination_cannot_enable_email`, `unknown_retry_requires_explicit_action`, `foreign_delivery_hidden`, `ui_does_not_label_queued_as_sent`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-040-closeout"></a>
### JG-040 — Verify reminder recovery and controlled real delivery

**Source entry points (present in inspected checkout):** [reminders.py](backend/app/services/reminders.py), [email_transport.py](backend/app/services/email_transport.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed; external gate pending.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134; controlled external email remains disabled pending explicit staging authorization/credentials\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-040 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-040).

**Historical audit finding (superseded by C-08 local acceptance):** Local delivery tests are not inbox receipt. Controlled real delivery remains an external C-10 gate.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-040.01 Run fake-clock integration coverage across due-date edits, timezone edits and quiet hours
- [ ] JG-040.02 Stop a worker after claim, restart after lease expiry and check safe recovery states
- [ ] JG-040.03 Exercise the UI through opt-in, due notification, opt-out and page reload
- [ ] JG-040.04 With explicit sending authorization and staging credentials send one controlled test email and record received evidence
- [ ] JG-040.05 Document on-call steps for failed/unknown queues and a disable-worker rollback drill; do not bulk retry unknown records

**Required assertion scenarios from the original ticket:** `reminders.spec.ts`, `restart_does_not_duplicate_accepted_delivery`, `timezone_change_replans_unsent`, `controlled_inbox_receipt_or_explicit_blocked_gate`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-041-closeout"></a>
### JG-041 — Model immutable document versions and private storage boundaries

**Source entry points (present in inspected checkout):** [documents.py](backend/app/services/documents.py), [backups.py](backend/app/services/backups.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-041 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-041).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-041.01 Add version/link tables and constraints with UUID identifiers and explicit owner references
- [ ] JG-041.02 Define immutable content fields and ready-only attachment rule; preserve original display filename separately from storage key
- [ ] JG-041.03 Add private durable storage directory configuration and readiness check; no default inside a served directory
- [ ] JG-041.04 Reserve quota under an account-level lock so concurrent uploads cannot exceed100 MiB
- [ ] JG-041.05 Extend backup metadata with document checksums and application refs while explicitly marking byte coverage incomplete
- [ ] JG-041.06 Add family-scoped version allocation, used/reference association semantics and DocumentCreateReceipt with one-used-version-per-kind constraint

**Required assertion scenarios from the original ticket:** `referenced_version_cannot_be_overwritten`, `cross_user_link_rejected`, `quota_concurrency_one_reservation_wins`, `ephemeral_or_public_path_configuration_rejected`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-042-closeout"></a>
### JG-042 — Implement bounded upload download and storage reconciliation

**Source entry points (present in inspected checkout):** [documents.py](backend/app/services/documents.py), [backups.py](backend/app/services/backups.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-042 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-042).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-042.01 Stream multipart upload with byte quota and actual PDF/UTF-8 checks; reject unsupported formats before ready state
- [ ] JG-042.02 Generate random internal keys, hash and persist through staging/atomic rename with explicit pending/failed states
- [ ] JG-042.03 Implement authenticated downloads with attachment headers, no-store and no public file URLs
- [ ] JG-042.04 Implement link/detach and guarded deletion; never delete a file still linked to an application
- [ ] JG-042.05 Add bounded reconciliation for old staging files, pending rows and missing ready bytes; report safe IDs/error codes
- [ ] JG-042.06 Use idempotency keys to return an existing upload result after a retry without duplicating quota or versions

**Required assertion scenarios from the original ticket:** `oversize_stream_stops_without_ready_file`, `crash_before_and_after_rename_reconciles`, `foreign_uuid_download404`, `download_headers_and_hash_match`, `retry_upload_single_version`, `filename_path_traversal_cannot_escape_storage`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-043-closeout"></a>
### JG-043 — Add document library and per-application version selection

**Source entry points (present in inspected checkout):** [documents.py](backend/app/services/documents.py), [backups.py](backend/app/services/backups.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-043 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-043).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-043.01 Add a document library with kind, label, version, uploaded time and size; hide internal storage keys
- [ ] JG-043.02 Add upload progress, cancel-before-completion behavior, validation messages and quota feedback
- [ ] JG-043.03 Add application attachment picker showing immutable version and download action
- [ ] JG-043.04 Explain detach versus delete and show referencing applications when server returns409
- [ ] JG-043.05 Show missing-file recovery state without substituting the latest document version
- [ ] JG-043.06 Ensure keyboard upload/selection works and preserve application context when opening the library
- [ ] JG-043.07 Show applications and existing outcome statuses for each version; distinguish Used from Reference and require deliberate correction when replacing the recorded used version

**Required assertion scenarios from the original ticket:** `document_versions.spec.ts`, `failed_upload_never_appears_ready`, `referenced_delete_conflict_explained`, `download_requires_current_session`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-044-closeout"></a>
### JG-044 — Extend recoverable backups to document bytes

**Source entry points (present in inspected checkout):** [documents.py](backend/app/services/documents.py), [backups.py](backend/app/services/backups.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-044 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-044).

**Historical audit finding (superseded by C-08 local acceptance):** The document ZIP omits later metadata extensions. C-03 must compose export and import paths, not only add files.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-044.01 Add explicit bundle format with manifest metadata and per-file size/hash; keep JSON-only export labeled metadata-only for documents
- [ ] JG-044.02 Validate ZIP member names, type, count, duplicate entries and expanded byte total before extraction
- [ ] JG-044.03 Restore file bytes into isolated staging then finalize with DB mapping; reconcile failure paths without publishing half-ready files
- [ ] JG-044.04 Require exact hash comparison on restore and reject missing/corrupt required bytes
- [ ] JG-044.05 Exercise v1/v2 JSON compatibility and complete bundle round-trip; update recovery runbook and scripts integration before calling the feature recoverable

**Required assertion scenarios from the original ticket:** `bundle_restores_bytes_and_links`, `zip_slip_symlink_and_zip_bomb_rejected`, `missing_member_fails_before_ready`, `json_only_reports_document_bytes_excluded`, `failed_restore_reclaims_staging`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-045-closeout"></a>
### JG-045 — Add manual capture schema and replay identity

**Source entry points (present in inspected checkout):** [capture.py](backend/app/services/capture.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-045 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-045).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-045.01 Add source/captured_at/capture_notes fields with nullable defaults for legacy rows
- [ ] JG-045.02 Add CaptureRequest unique owner/key mapping and payload hash, detaching row ref if later removed
- [ ] JG-045.03 Define strict manual input models using shared URL/text validators
- [ ] JG-045.04 Document exact defaults for every required CsvRow column and prove schema parity
- [ ] JG-045.05 Extend backups to preserve capture provenance and notes; omit expired replay keys or document their safe reconstruction
- [ ] JG-045.06 Create RequestWindowCounter with fixed hourly policy and48-hour cleanup; isolate counter commit from capture rollback

**Required assertion scenarios from the original ticket:** `legacy_rows_unchanged_after_migration`, `capture_required_column_defaults_valid`, `request_key_conflicting_payload_rejected`, `capture_notes_round_trip`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-046-closeout"></a>
### JG-046 — Implement capture API with identity warnings

**Source entry points (present in inspected checkout):** [capture.py](backend/app/services/capture.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-046 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-046).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-046.01 Validate payload and authenticate before duplicate/match lookup
- [ ] JG-046.02 Use F2 identity service for exact/canonical/possible matches and preserve original URL
- [ ] JG-046.03 Create row plus request mapping in one transaction; concurrent exact-URL captures resolve using a documented account-level lock
- [ ] JG-046.04 Return existing exact row for repeat capture and never mutate its clicked/applied state
- [ ] JG-046.05 Wire deliberate capture-notes transfer into later save/apply writer only when target notes are empty or user selects append
- [ ] JG-046.06 Rate-limit bounded capture requests per account using shared server enforcement; avoid process-local-only guarantees

**Required assertion scenarios from the original ticket:** `capture_not_visited_or_applied`, `concurrent_repeat_creates_one_row`, `same_key_different_payload409`, `foreign_existing_url_not_disclosed`, `existing_notes_not_overwritten`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-047-closeout"></a>
### JG-047 — Build quick-add page and user-invoked bookmarklet

**Source entry points (present in inspected checkout):** [capture.py](backend/app/services/capture.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-047 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-047).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-047.01 Add short URL/title/company/notes form and immediate server-side match context before final save
- [ ] JG-047.02 Provide a generated bookmarklet for the configured app origin with properly encoded fragment JSON
- [ ] JG-047.03 Read and validate fragment size/schema, strip it from history and preserve an expiring login draft in sessionStorage
- [ ] JG-047.04 Restrict login return route to same-origin /capture; discard malformed or expired drafts
- [ ] JG-047.05 Show saved/existing-row result and links to row/application history; preserve edits on network errors
- [ ] JG-047.06 Explain browser behavior and manual-copy fallback without promising forced Chrome tabs

**Required assertion scenarios from the original ticket:** `capture.spec.ts`, `expired_or_malformed_draft_discarded`, `login_preserves_valid_draft`, `external_return_url_rejected`, `repeat_submit_one_row`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-048-closeout"></a>
### JG-048 — Validate capture across browsers and lifecycle transitions

**Source entry points (present in inspected checkout):** [capture.py](backend/app/services/capture.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-048 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-048).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-048.01 Test manual form in the supported browser and bookmarklet via a synthetic source page with hostile title text
- [ ] JG-048.02 Exercise logged-out return, popup-blocked fallback and two rapid clicks
- [ ] JG-048.03 Capture then visit then apply; verify exactly one distinct lifecycle event for each real action
- [ ] JG-048.04 Delete source CSV rows and confirm any created application history persists
- [ ] JG-048.05 Measure a five-job capture walkthrough against the under-one-minute-per-job acceptance goal and record actual timings only

**Required assertion scenarios from the original ticket:** `capture_visit_apply_counts_separate`, `title_markup_rendered_as_text`, `popup_blocked_copy_fallback`, `duplicate_warning_survives_capture_flow`, `backup_restores_capture_provenance`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-049-closeout"></a>
### JG-049 — Model explicit deadlines and availability evidence

**Source entry points (present in inspected checkout):** [availability.py](backend/app/services/availability.py), [safe_job_fetch.py](backend/app/services/safe_job_fetch.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-049 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-049).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-049.01 Add independent URL-scoped availability records, version guards and source fields
- [ ] JG-049.02 Define user-confirmed closed precedence and nonauthoritative checker status mapping
- [ ] JG-049.03 Reuse timezone validators and require explicit date-only deadline conversion
- [ ] JG-049.04 Add backup section and URL mapping that survives source row deletion
- [ ] JG-049.05 Document exact Today eligibility for deadlines and interaction with terminal application states
- [ ] JG-049.06 Add JobCheckRequest with indexed durable rate/lease state and7-day metadata cleanup; exclude transient checks from portable backup

**Required assertion scenarios from the original ticket:** `user_closed_not_overwritten_by_reachable`, `date_only_conversion_visible_and_dst_safe`, `source_delete_preserves_availability`, `backup_keeps_deadline_source`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-050-closeout"></a>
### JG-050 — Implement manual freshness and a disabled-by-default safe check adapter

**Source entry points (present in inspected checkout):** [availability.py](backend/app/services/availability.py), [safe_job_fetch.py](backend/app/services/safe_job_fetch.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-050 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-050).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-050.01 Implement manual availability routes with owner/version checks independently of outbound networking
- [ ] JG-050.02 Implement injectable DNS/transport interfaces with strict public-address validation and pinned connection semantics
- [ ] JG-050.03 Enforce redirect count, total time, byte budget and no credential forwarding for every hop
- [ ] JG-050.04 Map response outcomes conservatively and preserve user-confirmed closed state
- [ ] JG-050.05 Persist/claim bounded check requests and per-account limits; keep JOB_URL_CHECKS_ENABLED=false until safety tests pass
- [ ] JG-050.06 Document a manual-only release path if safe transport or destination-policy evidence is unavailable

**Required assertion scenarios from the original ticket:** `ipv4_ipv6_private_and_mixed_dns_answers_blocked`, `dns_rebinding_cannot_change_pinned_destination`, `redirect_private_target_blocked`, `timeout_and403_unknown`, `404_unavailable_not_closed`, `body_limit_stops_read`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-051-closeout"></a>
### JG-051 — Show deadlines freshness labels and Today actions

**Source entry points (present in inspected checkout):** [availability.py](backend/app/services/availability.py), [safe_job_fetch.py](backend/app/services/safe_job_fetch.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-051 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-051).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-051.01 Add deadline editor with explicit timezone and closed/reopen confirmation controls
- [ ] JG-051.02 Display last checked timestamp, source and cautious reachable/unavailable/unknown labels
- [ ] JG-051.03 Expose Check link only when server capability is enabled and show pending/rate-limit/failure states
- [ ] JG-051.04 Add derived deadline actions using stable keys and owner-safe snooze handling
- [ ] JG-051.05 Recompute unsent reminders on deadline changes without changing already-sent delivery history
- [ ] JG-051.06 Do not hide all manual tasks merely because a related job is closed; show source state and allow explicit resolution

**Required assertion scenarios from the original ticket:** `closed_job_deadline_excluded_but_manual_task_retained`, `deadline_edit_updates_today_and_unsent_reminder`, `disabled_check_capability_has_manual_fallback`, `timezone_label_visible`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-052-closeout"></a>
### JG-052 — Validate freshness limits and false-closure resistance

**Source entry points (present in inspected checkout):** [availability.py](backend/app/services/availability.py), [safe_job_fetch.py](backend/app/services/safe_job_fetch.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-052 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-052).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-052.01 Build a local mock transport matrix for statuses, redirects, DNS changes, byte limits and timeouts
- [ ] JG-052.02 Assert unknown outcomes never set confirmed_closed_at or remove unrelated application history
- [ ] JG-052.03 Test repeated checks across two processes against durable rate/claim state
- [ ] JG-052.04 Exercise manual deadline, snooze, close, reopen and restore through UI
- [ ] JG-052.05 Record network-check enablement evidence separately from manual freshness acceptance; no real-site crawling is required for automated tests

**Required assertion scenarios from the original ticket:** `job-freshness.spec.ts`, `ambiguous_network_response_never_closes`, `concurrent_rate_limit_enforced`, `restore_preserves_user_confirmation`, `unsafe_request_count_zero`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-053-closeout"></a>
### JG-053 — Model contacts associations and scheduled interviews

**Source entry points (present in inspected checkout):** [contacts.py](backend/app/services/contacts.py), [calendar_export.py](backend/app/services/calendar_export.py), [contact_models.py](backend/app/contact_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-053 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-053).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-053.01 Add Contact, ApplicationContact and Interview with owned indexes, bounded fields and versions
- [ ] JG-053.02 Enforce matching owners for every association before insert and make duplicate role links idempotent
- [ ] JG-053.03 Define soft-delete behavior for contacts and source-less applications without cascading private history
- [ ] JG-053.04 Validate meeting/profile URLs and timezone-aware time ranges through shared validators
- [ ] JG-053.05 Extend backup schema/reference mapping for contact links and interviews; preserve UTC instant and display timezone
- [ ] JG-053.06 Add MutationReceipt replay storage and explicit interview round/preparation plus referral-source fields; include only durable user data in backups

**Required assertion scenarios from the original ticket:** `cross_user_association_rejected`, `duplicate_role_link_single_row`, `end_before_start422`, `contact_delete_preserves_interview_marker`, `backup_maps_all_relationships`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-054-closeout"></a>
### JG-054 — Build private workspace APIs and safe calendar downloads

**Source entry points (present in inspected checkout):** [contacts.py](backend/app/services/contacts.py), [calendar_export.py](backend/app/services/calendar_export.py), [contact_models.py](backend/app/contact_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-054 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-054).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-054.01 Implement owner-scoped paginated contact search and version-guarded edits with explicit association routes
- [ ] JG-054.02 Implement idempotent interview create/edit/cancel and nonblocking overlap warnings
- [ ] JG-054.03 Generate ICS with stable UID, incrementing sequence, UTC instants, line folding and escaped CRLF/commas/semicolons
- [ ] JG-054.04 Exclude notes/emails from calendar descriptions by default and use authenticated attachment download
- [ ] JG-054.05 Emit safe lifecycle events for interview scheduling and cancel unsent reminder occurrences after edits

**Required assertion scenarios from the original ticket:** `foreign_contact_and_ics404`, `ics_injection_cannot_add_second_event`, `ics_dst_instant_correct`, `stale_interview_edit409`, `cancel_suppresses_unsent_reminder`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-055-closeout"></a>
### JG-055 — Build application people and interview panels

**Source entry points (present in inspected checkout):** [contacts.py](backend/app/services/contacts.py), [calendar_export.py](backend/app/services/calendar_export.py), [contact_models.py](backend/app/contact_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-055 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-055).

**Historical audit finding (superseded by C-08 local acceptance):** People panels exist; associated Today interview actions can be unreachable. C-04 is required integration acceptance.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-055.01 Add linked people list with role, optional contact fields and private notes disclosure
- [ ] JG-055.02 Support selecting existing contacts or creating a new one without duplicating by default
- [ ] JG-055.03 Add interview editor showing chosen timezone plus account-local preview and overlap warning
- [ ] JG-055.04 Provide Download calendar event with wording that no invitation is sent
- [ ] JG-055.05 Add preparation action to Today using stable interview source keys and existing snooze rules
- [ ] JG-055.06 Show empty/loading/error/conflict states and retain unsaved interview notes on failed requests
- [ ] JG-055.07 Expose interview round, preparation notes and referral source beside the linked application; never put private preparation notes in default ICS

**Required assertion scenarios from the original ticket:** `contacts-interviews.spec.ts`, `interview_timezone_preview_matches_server`, `calendar_download_not_sent_message`, `cancel_removes_today_interview_action`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-056-closeout"></a>
### JG-056 — Verify contact privacy scheduling and recovery

**Source entry points (present in inspected checkout):** [contacts.py](backend/app/services/contacts.py), [calendar_export.py](backend/app/services/calendar_export.py), [contact_models.py](backend/app/contact_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-056 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-056).

**Historical audit finding (superseded by C-08 local acceptance):** Confirmed gaps in restore atomicity and interview pagination. C-02/C-03/C-04 are required before full acceptance.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-056.01 Use two accounts with similar names to prove search/results/links never cross ownership boundaries
- [ ] JG-056.02 Test DST overlap/gap inputs, explicit offsets and ICS round-trip using an independent parser
- [ ] JG-056.03 Exercise contact soft-delete and interview cancel without losing application history
- [ ] JG-056.04 Restore backup into an empty account and compare contact associations, notes and UTC times
- [ ] JG-056.05 Review default export/calendar payloads for unnecessary private fields and document exact retention behavior

**Required assertion scenarios from the original ticket:** `foreign_search_zero_results`, `ics_parser_reads_exactly_one_correct_event`, `restored_interview_links_and_notes_match`, `deleted_contact_notes_absent_from_normal_read`, `no_outbound_message_side_effect`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-057-closeout"></a>
### JG-057 — Model private import previews and reusable column mappings

**Source entry points (present in inspected checkout):** [imports.py](backend/app/services/imports.py), [import_mapping.py](backend/app/services/import_mapping.py), [import_models.py](backend/app/import_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-057 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-057).

**Historical audit finding (superseded by C-08 local acceptance):** Mappings exist despite the stale proposed heading. Complete ZIP recovery must include reusable mappings through C-03.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-057.01 Add preview and mapping tables with owner/expiry/status indexes and version constraints
- [ ] JG-057.02 Define bounded stored normalized row shape and checksum/fingerprint algorithms
- [ ] JG-057.03 Define allowed update fields excluding all user lifecycle and application-memory fields
- [ ] JG-057.04 Add24h preview and30-day committed-result cleanup rules; remove raw rows after commit
- [ ] JG-057.05 Extend backup with saved mappings only and document transient preview exclusions
- [ ] JG-057.06 Store bounded original rejected rows with24-hour download expiry; remove valid raw rows after commit and exclude both from portable backups

**Required assertion scenarios from the original ticket:** `preview_expiry_and_owner_constraints`, `duplicate_headers_preserved_by_index`, `forbidden_update_fields_rejected`, `committed_payload_raw_rows_removed`, `backup_includes_mapping_not_uploaded_preview`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-058-closeout"></a>
### JG-058 — Implement preview parsing and transactional reconciliation

**Source entry points (present in inspected checkout):** [imports.py](backend/app/services/imports.py), [import_mapping.py](backend/app/services/import_mapping.py), [import_models.py](backend/app/import_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-058 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-058).

**Historical audit finding (superseded by C-08 local acceptance):** Preview/reconciliation code exists despite the stale heading. Verify current behavior and close cross-feature restore composition.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-058.01 Bound incoming bytes/records before loading normalized payload and reject unsupported encoding/shape
- [ ] JG-058.02 Parse headers by position, apply explicit mapping and shared field/identity validation
- [ ] JG-058.03 Compute exact/possible duplicate plan with per-row reasons and a bounded preview sample
- [ ] JG-058.04 On commit recheck owner, expiry, version and destination conflict fingerprint under the account lock
- [ ] JG-058.05 Apply create/update-selected with explicit empty replacement policy and no lifecycle field writes in one transaction
- [ ] JG-058.06 Persist final counts and replay result atomically; on conflict409 require regenerated preview rather than silent replan
- [ ] JG-058.07 Add authenticated rejected.csv download preserving original invalid values and header order with spreadsheet-safe output; return410 after expiry

**Required assertion scenarios from the original ticket:** `invalid_reject_zero_writes`, `skip_invalid_counts_exact`, `update_title_preserves_notes_clicked_applied`, `destination_changed_after_preview409`, `replayed_commit_identical_result`, `last_row_failure_rolls_back_all`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-059-closeout"></a>
### JG-059 — Build column mapping and deliberate commit preview

**Source entry points (present in inspected checkout):** [imports.py](backend/app/services/imports.py), [import_mapping.py](backend/app/services/import_mapping.py), [import_models.py](backend/app/import_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-059 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-059).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-059.01 Add upload then map then review then commit stages without writing during preview
- [ ] JG-059.02 Show source columns by label and position, required URL target and unmapped-column warning
- [ ] JG-059.03 Show create/update/skip/invalid counts with downloadable safe row-number error report
- [ ] JG-059.04 Default to insert-only/reject-invalid and make field update plus empty replacement deliberate controls
- [ ] JG-059.05 Handle expired preview, changed destination conflict and lost response using server replay identity
- [ ] JG-059.06 Refresh rows and aggregate counts after completed commit while preserving active filters
- [ ] JG-059.07 Offer Download rejected rows with exact expiry and source values, separately from the compact error summary

**Required assertion scenarios from the original ticket:** `import-mapping.spec.ts`, `preview_only_no_rows_written`, `explicit_title_update_preserves_user_fields`, `expired_preview_requires_regenerate`, `lost_response_retry_no_duplicates`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-060-closeout"></a>
### JG-060 — Validate reimport repeatability and bounded resource use

**Source entry points (present in inspected checkout):** [imports.py](backend/app/services/imports.py), [import_mapping.py](backend/app/services/import_mapping.py), [import_models.py](backend/app/import_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-060 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-060).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-060.01 Run fixtures for BOM, quoted commas/newlines, duplicate headers, blank values and malformed JSON
- [ ] JG-060.02 Exercise maximum2000 rows and reject2001/over10 MiB before destination writes
- [ ] JG-060.03 Run two commits for the same account concurrently and verify conflict/replay behavior
- [ ] JG-060.04 Round-trip saved mappings through backup and test incompatible header fingerprint warning
- [ ] JG-060.05 Record actual counts/query counts/runtime for the maximum fixture and document limit escalation as a future separate design

**Required assertion scenarios from the original ticket:** `parser_fixture_matrix_expected_values`, `over_limit_zero_destination_writes`, `concurrent_commit_no_lost_updates`, `saved_mapping_header_mismatch_not_silent`, `spreadsheet_error_report_formula_safe`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-061-closeout"></a>
### JG-061 — Add optimistic versions and bounded undo journals

**Source entry points (present in inspected checkout):** [bulk_actions.py](backend/app/services/bulk_actions.py), [undo_foundation.py](backend/app/services/undo_foundation.py), [undo_models.py](backend/app/undo_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-061 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-061).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-061.01 Add row/track versions and bulk action/effect models with uniqueness, expiry and snapshot limits
- [ ] JG-061.02 Inventory every CsvRow/JobTrack writer including bulk SQL, imports, backup merge and background cleanup
- [ ] JG-061.03 Create a shared compare-and-update helper and define fields that require version increments
- [ ] JG-061.04 Store only changed allowlisted fields in before-images; avoid copying unrelated private data
- [ ] JG-061.05 Document expiry cleanup and backup behavior; require the writer inventory complete before exposing Undo

**Required assertion scenarios from the original ticket:** `version_changes_on_each_mutation_path`, `snapshot_over_limit_rejected_before_write`, `duplicate_operation_key_single_journal`, `expired_before_images_removed`, `foreign_effect_reference_rejected`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-062-closeout"></a>
### JG-062 — Implement transactional bulk changes and conflict-aware undo

**Source entry points (present in inspected checkout):** [bulk_actions.py](backend/app/services/bulk_actions.py), [undo_foundation.py](backend/app/services/undo_foundation.py), [undo_models.py](backend/app/undo_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-062 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-062).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-062.01 Route archive/update bulk operations through shared versioning and journal creation in one transaction
- [ ] JG-062.02 Integrate version increments into every inventoried writer before enabling undo endpoints
- [ ] JG-062.03 Implement preflight version/owner/expiry checks for all_or_nothing and deliberate restore_unchanged modes
- [ ] JG-062.04 Restore fields through domain writers, emitting compensating lifecycle events for application corrections
- [ ] JG-062.05 Persist per-effect outcomes so retries never reapply undo and report restored/conflict/missing counts
- [ ] JG-062.06 Expose operation ID and server undo expiry in bulk response; preserve legacy response fields additively

**Required assertion scenarios from the original ticket:** `bulk_failure_rolls_back_changes_and_journal`, `one_conflict_default_zero_restore`, `partial_mode_restores_only_unchanged`, `retry_undo_no_second_mutation`, `expired410_foreign404`, `metric_correction_matches_undo`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-063-closeout"></a>
### JG-063 — Build Archive and explicit Undo conflict handling

**Source entry points (present in inspected checkout):** [bulk_actions.py](backend/app/services/bulk_actions.py), [undo_foundation.py](backend/app/services/undo_foundation.py), [undo_models.py](backend/app/undo_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-063 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-063).

**Historical audit finding (superseded by C-08 local acceptance):** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-063.01 Add paginated Archive screen using the same complete filter/sort contract as active rows
- [ ] JG-063.02 Show archived time or Unknown and allow selected owned rows to restore without changing application status
- [ ] JG-063.03 Display bulk result counts, operation link and server-based undo deadline; preserve result across route changes
- [ ] JG-063.04 On409 show changed/missing counts and offer deliberate restore-unchanged with clear partial result
- [ ] JG-063.05 After410 keep Archive recovery available and explain that only immediate undo expired
- [ ] JG-063.06 Ensure keyboard access, per-operation pending state and refresh after success across active/archive/application views

**Required assertion scenarios from the original ticket:** `archive-undo.spec.ts`, `two_tab_conflict_no_silent_overwrite`, `partial_undo_counts_visible`, `expired_undo_archive_still_recoverable`, `filters_work_over_all_archived_pages`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-064-closeout"></a>
### JG-064 — Prove recovery and decide whether automatic purge is safe

**Source entry points (present in inspected checkout):** [bulk_actions.py](backend/app/services/bulk_actions.py), [undo_foundation.py](backend/app/services/undo_foundation.py), [undo_models.py](backend/app/undo_models.py). Trace callers/tests before editing shared behavior.

**Current assessment:** Local acceptance passed.
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-064 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-064).

**Historical audit finding (superseded by C-08 local acceptance):** Recovery cannot be certified while complete backup and transaction defects remain. Keep purge disabled by default.

**Original implementation checklist (historical; current acceptance is mapped in [C-08](docs/C08_PRODUCT_ACCEPTANCE.md)):**

- [ ] JG-064.01 Run archive/undo/restore with applied tracks, evidence, documents, availability, aliases, contacts and reminders present
- [ ] JG-064.02 Verify every source-row FK detaches safely and no durable application/company memory cascades away
- [ ] JG-064.03 Rehearse database and document-bundle recovery on disposable storage before any purge decision
- [ ] JG-064.04 Implement selected-row permanent-delete preview/confirmation only after the preceding assertions pass; keep application/document deletion out of scope
- [ ] JG-064.05 If automatic purge is requested later require explicit per-account opt-in, archived_at older than30 days, known timestamp and bounded batches; otherwise keep it disabled
- [ ] JG-064.06 Record operational owner, disable switch, counts and recovery evidence; stop rollout on any missing-history or stale-version failure

**Required assertion scenarios from the original ticket:** `purge_source_preserves_complete_application_graph`, `unknown_archive_timestamp_never_purged`, `default_automatic_purge_disabled`, `undo_cannot_overwrite_newer_import`, `restored_backup_matches_pre_purge_history`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="deployment-runbook"></a>
## 7. GitHub, staging, and production deployment runbook

This section expands C-09–C-12. These are future execution steps, not actions taken while creating this guide. Perform them only after the local repair/acceptance gates, using the authorized deployment accounts.

### 7.1 Fixed deployment design and current gaps

Use the existing topology: React/Vite on Vercel, one FastAPI instance on Render, and Supabase as PostgreSQL only. Keep application authentication and account ownership in FastAPI. Do not introduce Supabase Auth, Realtime, or a second migration system; existing Alembic history remains authoritative.

Keep the accepted zero-dollar topology: Vercel Free, Render Free, Supabase PostgreSQL and private Supabase Storage. `render.yaml` selects `DOCUMENT_STORAGE_BACKEND=gateway`; `/tmp/jobgrid-document-cache` is disposable cache, not durable storage. PR #174 makes the gateway compatible with the existing Render start command and derives its token from the existing database credential when an explicit token is absent. Keep credentials server-side. Verify actual gateway deployment/authentication and document durability before release; record rotation and rollback procedures.

Use one backend instance and retain database leases/claims. Keep maintenance, reminder delivery, URL checks, automatic archive and purge disabled until their controlled activation is authorized and verified. The repository also supports direct S3 storage, but it is not the current Blueprint transport. Paid disks and new S3 credentials are not prerequisites for this selected gateway topology.

Use a Supabase **session-mode pooler** connection for this long-running SQLAlchemy backend when the direct database endpoint is not reachable from Render; obtain the exact URI from the selected project's Connect panel. Verify connectivity and TLS from the actual runtime. Do not substitute a transaction-mode pooler without separately validating session-dependent behavior and migrations. [Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres).

Use the existing Vercel `/api` proxy topology: browser requests go to the frontend origin under `/api`, and Vercel forwards to that environment's Render service. The repository currently hardcodes the production Render destination in `frontend/vercel.json`. Staging must override that destination to a staging backend; changing only `VITE_API_URL=/api` does not isolate it.

External documentation was checked on September 24 while authoring. Revalidate provider capabilities at execution time. This guide does not state current prices or assume that credentials, paid capacity, domains, or SMTP authorization already exist.

### 7.2 Environment inventory — complete before connecting services

Record these values in the private release record. Public identifiers can be documented; credentials stay in the provider secret stores.

| Required input | Staging | Production | Acceptance condition |
|---|---|---|---|
| Frontend project and HTTPS origin | Dedicated staging project/origin | Existing or designated production project | Each proxy targets its own backend |
| Render service and HTTPS origin | Separate staging service | Production service | Record service ID and deployed SHA |
| Supabase project/database | Dedicated synthetic staging project | Production project | No shared database with automated tests |
| Private object storage/gateway | Isolated staging objects/access | Private production bucket/gateway | Authenticated bytes survive cache loss, restart and redeploy |
| Signing key | Unique staging secret | Unique stable production secret | No cross-environment reuse |
| Google OAuth app/account | Staging callback and controlled account | Production callback | Callback matches constructed application URL |
| SMTP credentials/recipient | Controlled authorized sandbox | Approved sender configuration | Actual receipt is proven before email activation |
| Candidate and rollback SHA | Exact reviewed candidate | Same accepted source | Previous compatible artifact remains available |
| Operators | Named implementer and reviewer | Named release and recovery operators | Ownership recorded before promotion |
| Recovery objectives and limits | Rehearsed fixture size and elapsed time | Agreed RPO/RTO, capacity, alert thresholds | Measured rehearsal meets recorded targets |

The real URLs, credentials, capacity budget, and recovery objectives are external inputs. Missing values block the affected deployment step; they are not decisions for a coding agent to invent. They do not prevent finishing local implementation.

### 7.3 Runtime and build variable matrix

Use exact names from current settings. Do not paste database URIs or signing secrets into GitHub comments, build logs, screenshots, or this file.

| Name | Location | Staging value / rule | Production value / rule |
|---|---|---|---|
| `VITE_API_URL` | Vercel build | `/api` with staging rewrite destination | `/api` with production rewrite destination |
| `ENVIRONMENT` | Render | `production` to exercise production validation | `production` |
| `TEST_AUTH` | Render | `false`; use real provider login | `false` |
| `APP_SECRET_KEY` | Render secret | Generated strong secret, unique to staging | Generated strong secret, stable across ordinary deploys |
| `SECRET_KEY` | Legacy/local configuration | Do not rely on it overriding `APP_SECRET_KEY` | Prefer `APP_SECRET_KEY`; remove conflicting stale configuration after verification |
| `DATABASE_URL` | Render secret | Staging PostgreSQL SQLAlchemy URI | Production PostgreSQL SQLAlchemy URI |
| `FRONTEND_URL` | Render | Exact staging HTTPS origin | Exact production HTTPS origin |
| `CORS_ORIGINS` | Render | Explicit staging origin allowlist | Explicit production origin allowlist; no wildcard |
| `OAUTH_REDIRECT_BASE` | Render | Staging frontend origin plus `/api` | Production frontend origin plus `/api` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Render | Controlled provider application credentials | Production provider credentials |
| `DOCUMENT_STORAGE_BACKEND` | Render | `gateway` | `gateway` |
| `DOCUMENT_STORAGE_GATEWAY_URL` | Render | Isolated staging gateway URL | Verified production gateway URL |
| `DOCUMENT_STORAGE_GATEWAY_TOKEN` | Render secret/runtime | Explicit secret or derived by existing bootstrap | Derived from existing DB credential when absent; verify coordinated rotation |
| `DOCUMENT_STAGING_DIR` | Render | `/tmp/jobgrid-document-cache` | Disposable `/tmp/jobgrid-document-cache`; not durable storage |
| `RUN_MAINTENANCE_JOBS` | Render | Initially `false`; enable during controlled worker acceptance | Enable only on designated instance after worker acceptance |
| `RUN_REMINDER_WORKER` | Render | Initially `false`; enable for controlled acceptance | Enable after scheduling/restart acceptance |
| `REMINDER_EMAIL_DELIVERY_ENABLED` | Render | `false` until authorized sandbox delivery step | Enable only for the accepted email rollout |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM` | Render secrets/configuration | Authorized sandbox sender settings | Verified production sender settings |
| `AUTO_ARCHIVE_AFTER_DAYS`, `AUTO_PURGE_AFTER_DAYS` | Render | `0` initially | `0` by default; no implicit destructive retention |
| `JOB_URL_CHECKS_ENABLED` | Render | `false` | `false` unless separately activated and accepted |
| `TEST_DATABASE_URL` | Local/CI only | Separate disposable schema test DSN in CI | Never configure the production application as a test target |

Read the provider callback routes in the current backend and register the exact generated URLs. Do not guess a callback suffix. Keep Microsoft/Apple credentials disabled unless those providers are part of the declared supported release; if enabled, run their real-provider acceptance too.

### 7.4 Development branches, review, and GitHub publication

1. Inspect `git status --short`, current branch, and remote main. Preserve unrelated files. Refresh main and identify changes since the audit; rerun affected reproductions instead of assuming the old findings remain unchanged.
2. Create a focused branch from the current main. Keep repair groups coherent: transaction ownership and its tests together, complete backup composition and UI together, pagination and its tests together, then time/matrix fixes. Document-only changes can be reviewed separately.
3. Implement the work package's numbered steps. Run focused tests, then required related integration coverage. Keep failed reproductions as regressions rather than deleting them after the fix.
4. Inspect the diff and stage explicit paths only. Verify no `.env`, private backup, database file, auth storage state, or unrelated scratch script is included.
5. Before creating the commit, inspect the configured author email. Use the account's verified GitHub no-reply address if privacy protection requires it. Do not disable GitHub email privacy to make a push succeed.
6. Write a PR body describing the actual defect, resulting behavior, compatibility/rollback implications, tests run, and any external gate still blocked. Write multiline descriptions to a file and use `--body-file`.
7. Push the branch and create a PR against `main`. Confirm the remote diff contains the intended files and attach the PR to the task when working through Codex.
8. Require green checks for the exact PR head and a review of the failure/rollback tests. A failing required check blocks merge; empty test selection is not a pass.
9. Before merging release-affecting changes, execute 7.5. Merging can trigger deployment under the current configuration; branch review and production promotion must remain distinct.
10. After merge, record the final main SHA. If merge resolution changes code, or the staged candidate differs from that SHA, repeat affected verification and staging acceptance before production promotion.

Useful inspection commands from the repository root:

```bash
git status --short
git diff --check
git diff --cached --stat
gh pr view "$JOBGRID_PR_NUMBER" --json url,headRefOid,mergeStateStatus,statusCheckRollup
gh pr checks "$JOBGRID_PR_NUMBER"
```

`JOBGRID_PR_NUMBER` is the actual PR being reviewed, not an invented issue ID. Check execution results; these examples are not a script that should continue after a failed command.

### 7.5 Prevent accidental production deployment

1. Inspect both checked-in configuration **and live provider settings**. Currently Render has `autoDeployTrigger: checksPass`; Vercel enables Git deployments on `main` and disables other branches in the checked-in configuration.
2. Before merging infrastructure changes or a candidate not yet accepted in staging, place production deployment under explicit manual promotion/control in both providers. Record the previous settings. Apply the chosen control consistently in manifests and live settings so the next Blueprint sync does not undo it.
3. Configure a dedicated staging frontend project and staging backend service. Deploy the candidate branch/SHA there explicitly; do not assume the production Vercel project creates branch previews under the current config.
4. Ensure the staging build's rewrite sends `/api/*` only to the staging service. Add a configuration assertion or inspect the generated deployment configuration before testing with credentials.
5. Confirm that staging has no production database, object bucket/access, signing key, provider callback, or unrestricted production mail sender.
6. Retain manual production promotion for the release described here. Re-enabling automatic deployment is a later explicit operating-policy change after equivalent gates can be enforced automatically.

**Exit:** merging a repair PR cannot unexpectedly deploy an unaccepted candidate to production.

### 7.6 Provision and deploy staging

1. Create the dedicated Supabase staging project and copy its connection URI into the staging Render secret store. Disable the unused Supabase Data API for this backend-only design, or otherwise prove that anonymous/authenticated Data API roles cannot access JobGrid tables. Do not assume FastAPI owner checks protect a separately exposed database API.
2. Provision the staging Render service using Python 3.12 and the current pinned backend requirements. Use the existing `backend` root and Uvicorn start command; keep the selected Free plan and one instance. Revisit capacity only through an explicit architecture/billing decision.
3. Configure the private storage gateway and settings in 7.3. Verify authenticated remote write/read and `/ready`. Local cache is disposable; document bytes must not depend on it or be publicly served.
4. With workers initially disabled, deploy the reviewed candidate. The current application starts Alembic for PostgreSQL; inspect that startup path before changing migration orchestration. Retain one migration owner and one service instance, and require a successful migration revision/readiness record. Do not introduce a second uncoordinated migration runner.
5. Create the staging Vercel project with `frontend` as root, `npm run build`, and `dist` output. Set the environment-specific proxy destination and `/api` build value. Deploy the same candidate SHA.
6. Register exact staging OAuth callback URLs and validate redirect behavior through the frontend proxy. Verify authentication cookies, logout, `/auth/me`, refresh, and deep links in a real browser.
7. Populate synthetic fixture accounts through supported application flows. Do not run destructive pytest fixtures against this staging database.
8. Enable the designated workers for acceptance only after verifying their configuration. Authorize sandbox email separately before enabling delivery. Keep automatic purge and URL checks off.
9. Upload a synthetic document, record its hash, restart and redeploy the backend, then download and compare. Demonstrate that missing storage is a visible failure, not a falsely successful upload.
10. Run C-10 in full and store sanitized evidence outside ephemeral runtime storage. Include full graph/file recovery, interview pagination, import/replay, source deletion, undo conflicts, Chrome popups, and scheduled-worker restart behavior.

**Exit:** all required staging gates PASS on the candidate. “Health endpoint is green” and “the release evidence JSON validates” are insufficient by themselves.

### 7.7 Full system backup and rollback rehearsal

The in-app owner-scoped ZIP is a portable user backup. It does not replace an operator's complete database-and-files disaster recovery plan.

1. On the dedicated staging environment, establish a controlled write pause for a consistent rehearsal backup. Stop reminder/maintenance mutations and document writes during capture; resume after the snapshot completes.
2. Capture the database with the approved provider backup or a PostgreSQL-compatible logical backup, and capture the corresponding private object bucket through the approved export path. Record timestamps, schema revision, file manifest/hashes, and encryption/access controls.
3. Store the package outside the instance and outside the only storage provider being protected. Confirm that the operator can retrieve/decrypt it. An object copy alone does not establish consistency with an independently captured database.
4. Restore to a separate disposable destination. Compare nonempty counts, normalized record graph, file hashes, and reference integrity. Measure restoration time against the agreed objective.
5. Deploy the previous application build against the staging migrated schema without removing new columns. Verify startup, login, history, and document access; return to the candidate and compare data again.
6. For a real failed application deployment, stop promotion and restore the known-good frontend/backend versions first. Preserve schema and data. A destructive schema downgrade or backup restore needs an explicit incident decision because it can discard newer user writes.
7. If the previous build cannot read the migrated schema, the candidate fails rollback acceptance. Implement compatible additive migration/application behavior before release; do not waive the gate silently.

**Exit:** both application rollback and full recovery have exercised evidence. No production restore is implied by this rehearsal.

### 7.8 Promote the accepted release

1. Confirm all C-01–C-11 gates and original-ticket acceptance dispositions. Resolve P1/P2 defects. Record explicitly approved scope changes instead of marking omitted functionality complete.
2. Record the exact accepted main SHA, successful CI run, staging deployment IDs, operator, reviewer, current backup, rollback artifacts, and observation window.
3. Ensure production settings match the accepted configuration with production-specific credentials/origins. Confirm object-storage durability and migrations are compatible with the previous application revision.
4. Create the GitHub release/tag for the accepted SHA using the repository's established naming convention; inspect existing tags before selecting a name. Publication itself does not deploy the application.
5. Manually deploy that SHA to the production Render service, watch migration/startup/readiness, and verify the recorded schema revision. Record actual restart/cold-start behavior and any maintenance window; do not infer zero downtime from a successful build.
6. Deploy the production Vercel build from the same SHA with production `/api` routing. Verify its deployment ID and API destination; do not promote a staging build containing staging configuration.
7. Run controlled production smoke: real login/logout, persisted application/company history, five-link selection, Today, document upload/download, accurate backup labels, and Archive/Undo. Avoid broad destructive fixtures or unsolicited email.
8. Enable accepted scheduled functionality on the designated instance. Verify one scheduled cycle, lease recovery, failure visibility, and opt-in delivery behavior.
9. Observe the agreed window, including at least one applicable scheduled cycle. Roll back for history/file integrity failure, ownership leak, broken login/core workflow, failed migrations, or agreed sustained error thresholds. Record the specific trigger and actions.
10. Close C-12 only after production evidence and operational handover are accepted. Record production URLs, source SHA, deployment IDs, backup schedule, recovery owner, alert owner, and accepted limitations.

### 7.9 Release decision table

| Condition | Allowed next action | Status that must remain open |
|---|---|---|
| Implementation exists but requirement proof is absent | Run C-08 verification | Original ticket acceptance |
| Invalid restore changes data or backup omits required content | Repair C-02/C-03 | Recovery acceptance and release |
| Required test or migration fails | Diagnose and fix; retain artifacts | Local-ready |
| Provider credentials or durable object storage unavailable | Continue independent local work; record exact dependency | Staging and release |
| Test email queued/logged but no receipt | Inspect controlled provider/inbox outcome | Delivery acceptance |
| Staging passes, production not deployed | Publish/promote only through authorized process | Released |
| Production health passes but data/file smoke fails | Stop and roll back safely | Production acceptance |
| All gates pass on recorded SHA and observation completes | Sign off and hand over | None within the accepted scope |


<a id="final-handover"></a>
## 8. Final handover checklist

- [ ] C-01–C-12 have evidence-backed final status.
- [ ] All JG-001–JG-064 entries have requirement-level acceptance or a documented approved scope decision.
- [ ] Restore rollback, complete record/file recovery, and mixed-source pagination reproductions remain in the enforced suite.
- [ ] SQLite, PostgreSQL, helper, browser timezone, build, and migration checks pass on the release SHA.
- [ ] Real OAuth, controlled SMTP receipt, deployed smoke, durable files, and old-code rollback have actual evidence.
- [ ] Production release identifiers and observation results are recorded separately from the Git commit.
- [ ] Backup/recovery objectives, schedule, operator, alerts, and rollback procedure are handed over.
- [ ] Remaining low-risk limitations are explicit; no failed or blocked mandatory gate is described as complete.

**Stopping rule:** finish this scope when these checks are satisfied. New feature ideas do not automatically extend the project.

<a id="chrome-extension-plan"></a>
## 9. Chrome extension — job and company memory

**Planning baseline:** 2026-10-16, local `main` and fetched `origin/main` at `48bf33c16c9cc541ec709988d7ca29cf084385de`. **Status: planned; 0/50 implementation microtasks complete.** This section is the authoritative extension plan. Existing C-07/C-09–C-12 release gates remain separate and must be revalidated when a release candidate is selected. No new GitHub issue, Linear task, branch, commit, PR, migration, extension package or deployment is created by this document.

### 9.1 Staff Engineer Assessment and product definition

**Executive verdict: Ready to plan.** The user needs a warning before repeating an application, including jobs opened outside JobGrid. A company warning is context, not a reason to block a different role. The existing application matcher solves much of the identity problem; the missing pieces are Chrome integration and durable visits for URLs without CSV rows.

**Material risks and decisions:**

| Risk / challenged assumption | Decision, prevention, and recovery |
|---|---|
| A page visit, import, save, or Apply-button click proves submission | Only an explicit **Mark applied** confirmation writes application evidence. No submission inference in V1. Existing imports and `UrlHistory.first_seen_at` never become visit/application timestamps. |
| All jobs on `greenhouse.io` or `lever.co` belong to one company | Employer names come from editable page metadata or an explicit user entry. Shared ATS domains and board slugs are not company identities. Reuse owner-scoped aliases; never auto-create aliases. |
| Different URLs always mean different jobs | Reuse conservative exact/canonical matching. Preserve unknown query parameters and job IDs. Similar company/title is **Possible duplicate**, never a silent merge. |
| A signed-in website means a background extension can use its cookies everywhere | Use a content script on an open, explicitly selected JobGrid tab and its same-origin `/api` proxy. Do not export session cookies or depend on third-party-cookie access from the extension worker. Prove this flow in real Chrome first. |
| Browsing history can be uploaded indiscriminately | Tracking starts disabled. User enables a supported site; only recognized job-detail URLs are sent. No Chrome history import, incognito tracking, general browsing log, form text, resume content, or cookies. |
| No match means safe to apply | Show **No recorded application** only after a successful complete lookup. Offline, timeout, partial lookup, login failure and unsupported sites must never show that state. |
| Warning data can leak through the job page | History stays in the extension popup/badge. Job-site content scripts extract public metadata only; they never receive application/company history. |
| Extension release is just a frontend deployment | Versioned unpacked pilot first; Chrome Web Store submission is a later release gate with privacy disclosures and review. Existing installed versions must tolerate additive backend changes. |

**Problem / users / outcome:** A signed-in JobGrid job seeker opens a job in Chrome, learns whether they visited it or applied before, sees prior applications to the employer, and deliberately records a new application without leaving a duplicate record. There is no separate extension administrator role. Anonymous users can open JobGrid login but cannot read or write history. Each account can access only its own records.

**V1 scope:**

1. Chrome Manifest V3 extension with a popup and tab-specific badge. Installation alone does not track browsing.
2. Optional automatic checks/visit recording for recognized job-detail pages on `boards.greenhouse.io`, `job-boards.greenhouse.io`, and `jobs.lever.co`. Each site permission and tracking toggle is opt-in. Only HTTPS detail routes qualify: Greenhouse `/{board}/jobs/{job_id}` and Lever `/{board}/{posting_id}`. Listing pages, apply forms and unknown routes do not auto-record. Additional routes need fixtures and a contract update.
3. For other public HTTP(S) job pages, **Check this job** runs only when the user opens the popup. Title/company are editable; saving or recording a visit requires a deliberate action. Explain **Manual check only**. No promise of automatic coverage on LinkedIn, Indeed, Workday or company career sites.
4. User chooses one trusted JobGrid tab for this browser session and sees its current account before enabling tracking. Account changes, missing tab, logout, worker restart, or ambiguous multiple tabs suspend tracking until reconnection; never silently switch accounts. Keeping JobGrid open is an explicit pilot requirement.
5. Server-owned visits survive browser restart/reinstall and CSV deletion. Extension local storage holds settings only; no durable duplicate application database. V1 does not import Chrome's past history and cannot reconstruct unrecorded past applications.
6. **Mark applied** requires company and title, shows current URL/account and any duplicate/company warning, then confirms once. Exact/canonical existing application evidence is returned unchanged; same-company/different-role remains allowed. Existing advanced pipeline status must not regress to `applied` on retry.
7. **Open in JobGrid**, **Pause tracking**, **Forget visits**, and **Disconnect** are accessible popup/settings actions. Forget visits never removes applications. Disconnect clears all transient private state immediately.

**Short UI copy:** `Checking…`, `Visited before`, `Already applied · {date}`, `Applied to this company · {count}`, `Possible duplicate`, `No recorded application`, `Company unknown`, `Sign in to JobGrid`, `Open JobGrid to connect`, `Tracking paused`, `Manual check only`, `Couldn’t check · Retry`, `Saving…`, `Saved`, `Visit limit reached`. Use text/icons as well as color. Applied warning outranks possible duplicate, company history, visit, then no recorded application; the popup can display multiple relevant facts. Dates use the user's locale with the UTC instant available in details.

**Non-goals:** AI/LLMs, autofill, automated submission, reading application answers, scraping authenticated ATS APIs, hidden DOM injection, blocking applications, universal employer identification, cross-browser support, historical browser-history ingestion, team/shared accounts, a separate token/pairing service, new hosting, paid infrastructure, a full visit analytics dashboard, and tracking while JobGrid is closed. Later requests can reconsider these after pilot evidence.

**Success criteria:** All identity/security fixture cases below pass; zero application writes from visit/check; one application and one first application timestamp after retries/concurrent requests; no cross-account history; server visits remain after reinstall/source deletion; keyboard-only popup flow works; warm check p95 <=2 seconds over 30 synthetic checks with environment recorded. Render cold starts are reported separately, with an 8-second client timeout. No production browsing telemetry is needed to measure pilot timing.

### 9.2 Evidence, alternatives, and architecture decision

**Confirmed at the baseline:** See the focused extension refresh in `docs/repo_context.md`. `crm.py::_find_application_matches` already limits matches and company counts to non-null `applied_at`, uses company aliases, and distinguishes exact/canonical/possible. `services/capture.py` saves without visiting/applying. `crm.py::bulk_create_from_rows` uses lifecycle writers. `models.py::UrlHistory` is import memory, not visit evidence. `frontend/vercel.json` has the same-origin API proxy. No tracked extension package exists. Migration head is `018`; choose the next free revision at implementation time.

| Option | Complexity / delivery / maintenance | Reliability / security / cost | Migration / reversibility |
|---|---|---|---|
| A. Local-only extension with exported/imported history | Smallest isolated prototype; duplicates matcher/storage logic | Works without app tab, but stale imports miss applications and reinstall loses unsynced history; private data duplicated; no service cost | No server migration, but hard to reconcile two truth sources |
| B. Account history through open JobGrid tab (**selected for V1**) | Moderate; native JS extension and thin server routes; reuse cookie auth and identity/lifecycle services | Live account truth, no browser-readable token; unavailable when app tab is closed; existing hosting cost only | Additive visit/receipt tables plus backup extension; rollback disables new feature while preserving records |
| C. Extension-scoped tokens and device pairing | Largest scope; new credential issuance, storage, rotation/revocation and support | Can work without app tab; additional credential theft/revocation risk; more backend/support load | New auth schema/lifecycle and security review; postpone until pilot demonstrates need |

**ADR-EXT-01 (proposed implementation decision):** Select B, with server-side durable visits and explicit application confirmation. No new framework or runtime dependency. Plain ES modules/HTML/CSS under `extension/`, existing pytest/Playwright plus Node's test runner. No web-accessible resources, external messaging, remotely hosted executable code, arbitrary-URL fetch relay, or inline/eval scripts. The open-tab dependency is intentionally visible in onboarding. If real OAuth/proxy tests fail, stop the auth-dependent work and revise this ADR; do not weaken cookies/CORS or silently implement token authentication.

**Assumptions to validate:** users accept an open JobGrid tab for the pilot; supported ATS routes and metadata fixtures reflect current pages; the chosen deployment authenticates through its same-origin proxy. Wrong assumptions cause paused/unavailable states, never fabricated history. **Needs Architect Decision before a public release:** exact trusted frontend origins and selected deployment; stable store extension ID/distribution owner; privacy/support URLs and approved store disclosures. These are external release inputs, not excuses to block local fixture-based work.

Official Chrome references checked for this plan: [permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions), [content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts), [message passing](https://developer.chrome.com/docs/extensions/develop/concepts/messaging), [network requests and relay restrictions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests), and [extension E2E testing](https://developer.chrome.com/docs/extensions/how-to/test/end-to-end-testing). Host permission does not make a job-site content script a safe place to fetch private JobGrid history.

### 9.3 Micro-architecture units and file ownership

All `extension/` paths and browser-memory modules listed below are **proposed new files**. Existing files are reuse anchors, not permission for broad rewrites.

| Unit | Responsibility / input → output | Owned files and data | Failure, security, tests, observability |
|---|---|---|---|
| MAS-EXT-1 Memory API | Validated job identity → visit/application/company context; explicit writes → durable receipts | NEW `backend/app/browser_memory_schemas.py`, `backend/app/services/browser_memory.py`, `backend/app/routers/browser_memory.py`; EDIT `models.py`, `main.py`; new next Alembic revision | Cookie account required; bounded reads/writes; two-account/concurrency tests; aggregate outcome/latency only |
| MAS-EXT-2 Browser transport | Extension command → selected trusted JobGrid tab → fixed same-origin API route → response | NEW `extension/manifest.json`, `extension/background.js`, `extension/jobgrid-bridge.js`, `extension/config.js` | No selected authenticated tab = paused; internal messages only; forged-sender/account-switch tests; no cookies or URLs in logs |
| MAS-EXT-3 Job-page detection | Allowed site/detail route or user gesture → public URL/title/company candidate | NEW `extension/job-page.js`, `extension/site-rules.js` | Missing/ambiguous employer stays unknown; never read input values; hostile DOM/route tests; no private results sent to this unit |
| MAS-EXT-4 Popup and controls | Current tab/context + explicit gesture → concise state or command | NEW `extension/popup.html`, `extension/popup.js`, `extension/popup.css` | Safe text rendering, keyboard/focus/live status; validation/failure/accessibility tests; no private persistent cache |
| MAS-EXT-5 Recovery and delivery | Visit data/versioned package → portable recovery and reproducible pilot | EDIT backup schemas/services/tests, existing CI; NEW `extension/README.md`, `extension/tests/`, `frontend/tests/extension.spec.ts` | Legacy/malformed restore tests; manifest permissions review; real Chrome pilot; sanitized release evidence |

Reuse `services/job_identity.py`, `services/lifecycle.py`, `services/capture.py`, existing validation and request-window machinery. If shared logic must move out of `routers/crm.py`, preserve public signatures/return values, query ordering, limits and errors; trace all callers first. Do not call HTTP handlers or introduce nested commits. No background queue or new scheduler: MV3 events initiate a check/visit; application writes require a popup confirmation.

### 9.4 Contracts — CCR-EXT-01

**Current shape:** no browser-memory endpoints, extension protocol or durable visit table. Existing `/crm/application-matches`, capture, row-click, lifecycle, aliases and backup contracts retain their meanings. **New shape:** additive contracts below. **Breaking:** no existing routes/fields removed or repurposed. **Downstream:** EXT-01–50; models, router registration, identity/lifecycle consumers, backup inventory, extension transport/popup, tests and docs. **Compatibility:** old clients keep working; feature disabled/unsupported server returns an unavailable state; keep protocol v1 throughout pilot. Architect updates this section, affected tasks and `docs/repo_context.md` together for any contract change.

#### A. Durable data and identity

NEW table `job_visits`: `id` integer primary key; `user_id` required FK `users.id` with account deletion cascade; `canonical_url` Text required; `canonical_url_hash` String(64) required; `first_visited_at` UTC DateTime required with server time; unique `(user_id, canonical_url_hash)` plus owner/time index. A hash collision with a different canonical URL is rejected as `409 identity_conflict`, never merged. No company/title/form/body/token stored in this table. No FK to CSV rows. Canonicalization version is the existing `ccr-identity-1`; version changes require a migration/CCR. Store canonical URLs with the current tracking/fragment removal; reject URL userinfo, private/loopback hosts, unsupported schemes and credential-like query keys (`token`, `access_token`, `auth`, `authorization`, `code`, `password`, `session`, `session_token`, case-insensitive) on these new routes. Do not fetch submitted URLs server-side. Arbitrary query strings can still contain private values: disclose URL storage and allow forgetting visits.

A visit is one remembered job, not an event stream: insert once; retry/revisit does not change first time, increase a counter or emit repeated lifecycle events. Per-account maximum 10,000 remembered URLs; existing visits remain readable at capacity and repeated writes succeed. New URL at capacity returns `409 visit_limit_reached`; no automatic eviction/purge. **Forget visits** deletes this table's rows for the authenticated account only. Server evidence can outlive a deleted source row. Account deletion includes visits. Existing backup restore may restore user-selected forgotten history; disclose that behavior.

`CsvRow.clicked` remains the source of row discovery state. Browser visits also set matching owned existing rows clicked through the shared row-visit mutation, preserving first clicked time; they do not create rows/tracks, apply jobs, or inflate session counters. Existing clicked rows/tracks can provide conservative legacy visit evidence at lookup; `UrlHistory` and imported/saved-only records cannot. The new visit table is the durable source for external URLs. No inferred bulk backfill from import history.

`JobTrack.applied_at != null` remains application evidence even if current status is rejected/withdrawn/archived; archive is not forgetting. Permanent application deletion follows existing product semantics; do not silently reconstruct deleted applications from visit memory. Alias grouping is account-owned. Company count means application records with non-null `applied_at`, not unique employers, saved jobs or visits.

#### B. HTTP routes and limits

All NEW routes live under `/crm/browser-memory`; extension transport uses `/api/crm/browser-memory` on the trusted frontend tab. Guard with `get_current_user`; derive owner from cookie, never client input. Requests require JSON, disallow unknown fields, and accept `url` public HTTP(S) <=2048 characters, optional `company` <=320 and `title` <=500. `apply` requires nonblank company/title. Reuse existing URL/text validation with these stricter browser-memory privacy checks; never alter existing canonicalization policy globally.

| Route | Request | Success response |
|---|---|---|
| `POST /check` | `{url, company?:string|null, title?:string|null}` | `200 {protocol_version:1, checked_at:UTC, account_id:int, visit:{visited:bool, first_visited_at:UTC|null}, matches:[{track_id:int, confidence:"exact"|"canonical"|"possible", reason:string, company:string|null, title:string|null, status:string, applied_at:UTC}], company_history_count:int, company_known:bool, lookup_complete:bool}` |
| `POST /visit` | `{url}` | `200 {protocol_version:1, account_id:int, created:bool, first_visited_at:UTC}`; repeats return `created:false` |
| `POST /apply` | `{url, company:string, title:string, confirmed:true}` with required UUID `Idempotency-Key` | `200 {protocol_version:1, account_id:int, application_id:int, created:bool, already_applied:bool, applied_at:UTC}` |
| `DELETE /visits` | No body; explicit popup confirmation | `200 {protocol_version:1, account_id:int, deleted:int}`; repeat returns zero |
| `GET /session` | No body | `200 {protocol_version:1, account_id:int, account_label:string}`; use current user display label, no token/cookie/email dump |

`UTC` means canonical RFC3339 string with `Z`, using existing timestamp helpers. Matches return at most 20 records, exact then canonical then possible, newest application then ID for stable ties. Exact/canonical candidates must be fetched separately from bounded company/title candidates so a scan cap cannot hide a known applied URL. `lookup_complete:false` is required when possible-match search hits its cap (500 candidates); still show definite results, but never imply complete clearance. Count uses a separate owner-scoped aggregate. Shared matcher changes require existing regression parity.

`apply` locks the account using the existing mutation pattern, validates the complete request, checks exact/canonical applied evidence first and returns it without timestamp/status changes. Otherwise create/update an exact URL track using existing lifecycle validation/event writing; a matching never-applied exact track may be marked applied. A canonical but never-applied separate track is not silently merged. Possible/company-only matches never select an application target. No captured CSV row is required. Event and first `applied_at` commit in the same transaction. Unique owner/URL constraints plus lock/retry resolve races; test SQLite and PostgreSQL separately. Do not use `upsert_from_row`, which synthesizes an open and increments counts.

An exact-match never-applied track keeps its existing metadata unless empty; supplied metadata cannot overwrite notes or unrelated fields. A new track records supplied company/title, an explicit application time and lifecycle event with no synthetic open.

Existing receipts are domain-specific (capture, evidence and documents), so reuse their transaction/digest pattern, not their tables. Add `browser_apply_receipts`: `id` integer PK; `user_id` required FK with account deletion cascade; `request_key` String(36) required UUID; `payload_hash` String(64) required; `response_json` JSON required containing only the frozen apply response; `created_at` UTC DateTime required. Unique `(user_id, request_key)` and owner/time index. Same key/payload returns original result; changed payload returns `409 idempotency_conflict`. If the recorded application was permanently deleted, return `409 application_deleted`, never resurrect it from a receipt. Prune expired receipts under the write lock after 30 days; maximum 10,000 active receipts/account, otherwise `409 receipt_limit_reached`. Preserve first application time even after receipt expiry by checking durable application evidence. Store no credential data in receipts; classify them as excluded operational state in the backup inventory. A lost response leaves **Save status unknown · Retry** and retains the same key/payload in session storage; never retry a changed payload/key silently. User closes/restarts browser: recheck durable history before offering a fresh confirmation; no offline application queue.

New-route errors use `{detail:{code:string,message:string,field?:string}}`; session-auth 401 keeps existing `get_current_user` response compatibility. `422 invalid_browser_memory_payload` covers missing/wrong/extra fields, `confirmed` other than literal true, invalid URL/text/key; `403 origin_not_allowed` rejects missing/untrusted browser Origin or browser header; absent/invalid expected-account header is 422 invalid_browser_memory_payload; `409` codes above cover deterministic conflicts; `429 browser_memory_rate_limited` includes `Retry-After`; `503 browser_memory_unavailable` hides provider details. Foreign IDs/records are never returned. Do not log payloads. Fixed per-account shared limits: 120 checks/minute; 60 visit attempts/minute; 20 apply attempts/minute; 5 forget attempts/hour. Rejected authenticated attempts count; unauthenticated requests do no private query. Rate-limiter failure fails closed with 503. Reuse persistent request windows, not in-process counters. Session checks are debounced to at most once per 5 seconds per selected tab.

Require `X-JobGrid-Account-ID` with the connected account ID on all new writes; compare it with the cookie-derived owner before any mutation/receipt lookup and return `409 account_changed` on mismatch. This is an expected-account assertion, never owner authority. Require exact configured trusted frontend `Origin` on new write routes and a fixed `X-JobGrid-Browser: 1` header; the header is a CSRF boundary component, not authentication. No wildcard CORS, no extension origins in cookie CORS allowlists, no GET mutations. Verify real proxy Origin behavior before accepting the deployed configuration. Authentication/session routes remain backward compatible.

#### C. Chrome transport, permissions and lifecycle

Manifest v3: `storage`, `activeTab`, `scripting`; optional host permissions restricted to the three named ATS hosts and the exact selected JobGrid frontend origin. Request host access only from onboarding/site-enable gestures. Avoid `tabs`, `history`, `cookies`, `<all_urls>`, wildcard JobGrid subdomains and external messaging. Dynamically register job-site scripts after permission grant; `chrome.tabs` events can inspect only accessible hosts. Unknown page metadata uses a current-tab `activeTab` gesture. Packaged config contains public exact origins only; local development uses a separate localhost manifest/config, never shipping localhost in the release artifact. Origin selection is a build/release input, not a popup text box accepting arbitrary API servers.

Background-owned protocol: `{version:1, request_id:UUID, kind:"session"|"check"|"visit"|"apply"|"forget_visits", account_id?:int, payload:object}`. Response `{version:1, request_id, ok:boolean, data?:object, error?:{code,message,retry_after?:int}}`. Bound message JSON to 8 KiB. Validate message kind/fields/sender/extension ID; apply/forget mutations accepted from the packaged popup only; automatic visit writes originate inside the worker only after validated opted-in navigation and a successful same-context check. Page scripts cannot request visit writes. Page scripts may send a metadata candidate for their own top-level tab only; background re-reads accessible tab URL and ignores supplied owner/account/visit/action flags. Reject subframes, mismatched URL/tab/document, external senders and unsupported protocol.

`jobgrid-bridge.js` runs isolated on the exact trusted JobGrid frontend only, receives internal runtime messages, and maps an enumerated command to a hard-coded method/path above with `credentials:'same-origin'`, JSON, the fixed header and the expected-account header for writes. It never accepts an arbitrary destination/method/headers and never exposes a `window.postMessage` relay. It returns private responses only to background. Backend session identity is checked against selected account before every write and every displayed response; changed identity cancels the action, clears private UI and requires reconnection. The worker never reads a cookie and never sends private results back to a job tab.

8-second timeout for bridge/API calls; no periodic polling or keep-alive loop. Debounce navigation by 500 ms, one request per tab/URL in flight; discard responses if tab URL/document/account/request generation changed. On a qualifying navigation: check first, then record visit; retain the pre-write result so the first visit does not display **Visited before**. A failed check records no automatic visit. A failed visit after a good check leaves warnings visible and says **Visit not saved · Retry**. Only a user Retry reattempts; 429 respects `Retry-After`. Permission revocation unregisters the relevant script and stops tracking immediately. MV3 restart clears the connection/private context, requiring explicit reconnect; persisted settings never imply an authenticated account binding.

No pending browser-wide queue. `chrome.storage.local` stores site opt-ins, pause state and selected public environment only. `chrome.storage.session` holds selected tab/account, bounded in-flight state and one unresolved apply payload/key (maximum 24 hours; delete on success/disconnect/account change). Never `chrome.storage.sync` private data. Use session storage restricted to trusted extension contexts. Worker suspension resets the active connection/private results and requires explicit reconnect; unresolved apply key/payload can remain in trusted storage.session for deliberate same-key retry after fresh account/URL verification. A full browser restart clears storage.session. Never replay a mutation automatically.

#### D. Recovery, deletion and compatibility

Add `job_visits_v1` as a checksummed optional backup extension using the repository's composed extension pattern; do not append an unversioned base section that strict old readers will reject. Each entry contains canonical URL/hash and first visit UTC; portable backup-local references replace source IDs and destination owner comes from the restore session. The exact proposed extension shape is `{schema_revision:1,visits:[{backup_ref:UUID,canonical_url:string,canonical_url_hash:string(64),first_visited_at:UTC}],checksum_sha256:string(64)}`; checksum signs canonical sorted-key compact UTF-8 JSON with checksum_sha256 omitted and allow_nan=false. Retain the complete-backup aggregate record/byte limits as well as the per-account visit cap. Version is exactly integer 1; duplicate canonical hashes with mismatched URL, invalid time, >10,000 entries, or invalid checksum reject the whole restore before any write. Recompute hashes server-side; earliest first-visit time wins on replay/union with existing visits; reject a union over quota atomically. Missing extension in old backups means no visits, not a fabricated history. JSON and ZIP include this metadata; no bytes/secrets/browser settings are required.

Before enabling the new exporter, verify what existing readers do with unknown optional extensions. If legacy code cannot safely read/skip it, add a capability/version rejection with a clear compatibility message and retain export-to-old-format only when omissions are explicit. Never claim silent loss is a complete restore. Test this decision against real legacy fixtures. Visit delete/restore does not mutate application history, import memory, CSV row state or analytics. Clearing visits therefore does not clear a separately retained row click; UI must explain which evidence remains.

Alembic adds only the visit/receipt tables/indexes; existing records/timestamps are unchanged, no speculative backfill. Preserve old-code rollback by leaving both added tables in place and disabling extension calls. Downgrade that drops visit data is a deliberate export-first operator action, never automatic rollback. Restore receipts/rate windows/session settings are operational state, not recoverable private application truth; preserve existing backup exclusions and document any new receipt policy explicitly.

### 9.5 Fifty implementation microtasks and builder handoff

**Execution variables:** MAIN_TASK = Chrome job/company memory; REPOSITORY = `anmolsansi/CSV_Website`; BASE_BRANCH = revalidate remote default (`main` at planning); WORK_BRANCH / MAIN_GITHUB_ISSUE / MAIN_LINEAR_TASK / TARGET_VERSION / PULL_REQUEST = **not selected/created for this documentation request**. When implementation is authorized, discover and reuse existing task work, then choose a valid repository-convention branch if needed. Use one main issue with this checklist, not 50 issues; reuse project Linear work only if applicable. Do not manufacture tracking IDs.

Each unchecked row is one ~2% microtask, not completed work. Percentage is a planning aid, not measured effort. Split a row if implementation exceeds one logical change; do not pad commits to preserve the count. Execute dependency order. The five-task bands are review checkpoints, not large commits.

**Packet rules applying to every row:** Objective is its stated deliverable; rationale is the stated failure prevented. The detailed packet owns the complete allowed file list; index paths are short source anchors, not a substitute for that list; existing source may be inspected but unrelated edits are forbidden. Inspect current `docs/repo_context.md`, the relevant 9.4 contract, and actual callers/tests first. The contract below each band names test files/inspection anchors. New files are marked NEW in 9.3. Use the corresponding detailed execution ticket in section 9.7; before dispatch attach its current source contents, confirm the repeated contracts against CCR-EXT-01 and recheck its exact allowed paths, tests and prerequisite evidence. Include the skill's builder wrapper, relevant backend/API/database/security/testing/frontend rules, and current source contents. Run ticket intake with zero FAILs. These are planned tasks with detailed specifications, **not pre-approved or dispatched builder sessions**; dependencies must be accepted on the work branch before use (and merged before a separate branch consumes them).

**Every row's Definition of Done:** deliverable exists; specified positive and failure validation passes; documentation impact is recorded; diff contains only allowed scope/no secrets; one meaningful commit references the main issue and `[NN/50]`; issue checklist/evidence and applicable Linear status agree. Documentation = update the owning section of `docs/JOBGRID_BUILD_GUIDE.md` when behavior/setup changes, and correct this plan/context if contracts change. Pure fixture/test rows record “None — regression only, no behavior/setup change” in the main issue. Commit scope = row's artifact/test/doc delta only. No runtime tests are claimed by writing this checklist.

#### Band 1 — Freeze inputs and prove the auth seam (MAS-EXT-2)

Inspect `auth.py`, `routers/auth_router.py`, `frontend/vercel.json`, `frontend/src/api/client.js`, current environment runbook; rules: security/API/testing.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-01](#ext-01) | Record selected pilot origins/account expectations; prevents connecting to the wrong service. | `extension/README.md`, `extension/config.js`; validate exact origin parsing, no credentials/wildcards; dep: none. Docs: setup. |
| [ ] [EXT-02](#ext-02) | Add minimal loadable MV3 shell and separate dev config; prevents accidental broad permissions. | `extension/manifest.json`, `extension/popup.html`, `extension/README.md`; load unpacked, assert permission allowlist; dep: 01. Docs: installation. |
| [ ] [EXT-03](#ext-03) | Implement isolated fixed-route session bridge; proves cookie reuse without token export. | `extension/jobgrid-bridge.js`, `extension/tests/bridge.test.mjs`; mocked trusted/untrusted sender and fixed-path assertions; dep: 02, protocol in 9.4. Docs: transport. |
| [ ] [EXT-04](#ext-04) | Add authenticated `/session` route and router registration; proves selected account binding. | `backend/app/routers/browser_memory.py`, `backend/app/main.py`, `backend/tests/test_browser_memory_api.py`; 200/401/no secret fields; dep: 01. Docs: API. |
| [ ] [EXT-05](#ext-05) | Run real Chrome signed-in proxy/session spike and account switch; retire the biggest uncertainty first. | `extension/README.md`, `frontend/tests/extension.spec.ts`; document dev plus selected deployed OAuth expected/actual, missing tab/401; dep: 03,04. No auth-dependent implementation until local spike passes; deployed proof remains a release gate if unavailable. |

#### Band 2 — Durable visits (MAS-EXT-1)

Inspect `models.py`, `routers/rows.py::record_click`, `services/validation.py`, `services/job_identity.py`, `018_bulk_undo_foundation.py`; rules: database/backend/testing. New test file: `backend/tests/test_browser_visits.py`.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-06](#ext-06) | Add visit/receipt models and next migration with owner uniqueness; external jobs need durable memory. | `models.py`, `backup_schemas.py` inventory, new `backend/alembic/versions/019_browser_visits.py` if still free, `test_browser_visits.py`; empty/populated upgrade and both tables/indexes SQLite/PostgreSQL; dep: 05 local proof. Docs: schema. |
| [ ] [EXT-07](#ext-07) | Add strict browser-memory request schemas and privacy URL validation; rejects unsafe input without fetching it. | `browser_memory_schemas.py`, `test_browser_visits.py`; wrong types/unknown fields/private host/userinfo/token query/2048 boundary; dep: 06. Docs: validation. |
| [ ] [EXT-08](#ext-08) | Insert once/replay one visit under owner lock and 10,000 cap; avoids duplicate events and unbounded growth. | `services/browser_memory.py`, `test_browser_visits.py`; duplicate/concurrent insert, collision, quota and rollback; dep: 07. Docs: visit semantics. |
| [ ] [EXT-09](#ext-09) | Reuse/extract row-visit mutation so an external visit updates matching existing rows only. | `routers/rows.py`, `services/browser_memory.py`, `test_browser_visits.py`, existing `test_rows.py`; first click preserved, no row/track/application/session-count creation; dep: 08. Docs: row relationship. |
| [ ] [EXT-10](#ext-10) | Add owner-only forget-visits service and account deletion coverage; provides privacy recovery. | `services/browser_memory.py`, `test_browser_visits.py`; A deletes own visits, B unaffected, repeats zero, application/row state unchanged; dep: 08. Docs: delete limits. |

#### Band 3 — Accurate history lookup (MAS-EXT-1)

Inspect `crm.py::_find_application_matches`, `services/job_identity.py`, `routers/company_aliases.py`, `test_application_memory.py`; rules: backend/API/testing. New test file: `backend/tests/test_browser_memory_matches.py`.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-11](#ext-11) | Move shared applied-match query into its owning identity service without changing existing API behavior. | `routers/crm.py`, `services/job_identity.py`, `test_application_memory.py`; trace every caller and assert response/error/order parity; dep: 07. Docs: source ownership only. |
| [ ] [EXT-12](#ext-12) | Guarantee exact/canonical lookups cannot be hidden by company scan limits. | `services/job_identity.py`, `test_browser_memory_matches.py`; >500 same-company newer records still find old exact job; bounded possible scan returns completeness; dep: 11. Docs: cap/completeness. |
| [ ] [EXT-13](#ext-13) | Compose visit evidence with application matches and alias-aware count; keeps saved/imported state distinct. | `services/browser_memory.py`, `test_browser_memory_matches.py`; clicked legacy record, external visit, imported-only/saved-only and account negatives; dep: 08,12. Docs: lookup. |
| [ ] [EXT-14](#ext-14) | Add `/check` route with frozen response and common errors. | `routers/browser_memory.py`, `browser_memory_schemas.py`, `backend/tests/test_browser_memory_api.py`; schema, timestamps/nulls, unauthenticated/no mutation; dep: 13. Docs: API. |
| [ ] [EXT-15](#ext-15) | Add identity matrix for different employer/role/job ID and tracking variants; prevents dangerous false certainty. | `test_browser_memory_matches.py`, `backend/tests/test_job_identity.py`; canonical positive, unknown query/path distinctions, aliases, advanced/archived statuses, no automatic merges; dep: 14. Docs: none, regression only. |

#### Band 4 — Explicit and retry-safe application writes (MAS-EXT-1)

Inspect `crm.py::bulk_create_from_rows`, `services/lifecycle.py`, `services/undo_foundation.py`, existing mutation receipt model and capture lock/retry; rules: backend/database/security/testing. New test file: `backend/tests/test_browser_memory_apply.py`.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-16](#ext-16) | Add service that explicitly applies a URL without CSV capture or synthetic opens. | `services/browser_memory.py`, `test_browser_memory_apply.py`; valid first application/event atomicity, validation failure zero writes; dep: 11,07. Docs: apply semantics. |
| [ ] [EXT-17](#ext-17) | Return existing applied exact/canonical track unchanged; preserves original timestamp and advanced status. | `services/browser_memory.py`, `test_browser_memory_apply.py`; retry after rejection/archive, same-company new role and possible match create separately; dep: 16. Docs: duplicate outcomes. |
| [ ] [EXT-18](#ext-18) | Bind apply request UUID/digest to bounded `browser_apply_receipts`. | `services/browser_memory.py`, `test_browser_memory_apply.py`; replay, altered payload 409, deleted target, expiry/cap and rollback/no stale success receipt; dep: 17. Docs: retry/receipt exclusions. |
| [ ] [EXT-19](#ext-19) | Expose `/visit`, `/apply`, `DELETE /visits` with literal confirmation and account guard. | `routers/browser_memory.py`, `browser_memory_schemas.py`, `test_browser_memory_api.py`; missing confirmation/key, no client owner override, 200 replay and error shape; dep: 10,18. Docs: endpoints. |
| [ ] [EXT-20](#ext-20) | Prove concurrent apply and lost-response retry across supported databases. | `test_browser_memory_apply.py`, `test_application_memory.py`; fresh sessions assert one application/event/first time, no click/count side effects, injected late rollback; dep: 19. Docs: none, regression only. |

#### Band 5 — API security and portable history (MAS-EXT-1/5)

Inspect request-window models/services, `backup_schemas.py`, `services/backup_sessions.py`, composed contact/mapping extensions; rules: security/API/database/testing. Keep existing unrelated routes/backups backward compatible.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-21](#ext-21) | Enforce per-account shared rate windows and exact write Origin/header checks. | `routers/browser_memory.py`, `services/browser_memory.py`, `backend/tests/test_browser_memory_security.py`; all limits, cross-process counter/rejected attempt, spoofed origin, account changed between session check and write, limiter failure 503; dep: 19. Docs: quotas/errors. |
| [ ] [EXT-22](#ext-22) | Define optional `job_visits_v1` schema/checksum and inventory classification. | `backup_schemas.py`, NEW `backend/app/browser_memory_backup_schemas.py`, `test_backup_contract.py`; invalid shape/time/hash/quota and missing extension; dep: 06. Docs: recovery format. |
| [ ] [EXT-23](#ext-23) | Compose visit metadata into JSON/ZIP exporters and enforce legacy-reader negotiation. | NEW `backend/app/services/browser_memory_backup.py`, owning composed exporter registration in `main.py`, `test_complete_backup.py`; both exports carry equivalent metadata and legacy fixtures give explicit compatibility outcome; dep: 22. Docs: export compatibility. |
| [ ] [EXT-24](#ext-24) | Preflight and restore visits within existing caller transaction. | `services/browser_memory_backup.py`, `services/backup_sessions.py`, `test_complete_backup.py`; owner remap, replay earliest time, invalid late section/union quota zero writes; dep: 23. Docs: restore. |
| [ ] [EXT-25](#ext-25) | Prove source deletion, restore and account purge preserve the intended memory boundaries. | `test_browser_visits.py`, `test_complete_backup.py`, `docs/BACKUP_STRATEGY.md`; source CSV delete retains visits/applications, forget visits keeps applications, account delete removes visits, restored backup can restore forgotten visits; dep: 24,10. Docs: recovery/privacy. |

#### Band 6 — Connection and page metadata (MAS-EXT-2/3)

Inspect Chrome references, frozen protocol and `extension/config.js`; rules: security/frontend/testing. Node tests under `extension/tests/` use native `node:test`; DOM behavior uses existing Playwright tooling.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-26](#ext-26) | Implement selected JobGrid tab/account connection and internal command dispatcher. | `extension/background.js`, `extension/tests/bridge.test.mjs`; exact host/tab/version/request limit, reject external/subframe/forged popup writes; dep: 05,14,19. Docs: connection. |
| [ ] [EXT-27](#ext-27) | Enforce account recheck, timeouts and stale-response cancellation. | `background.js`, `jobgrid-bridge.js`, `tests/bridge.test.mjs`; URL/account/tab changes mid-request and missing tab never display other account data; dep: 26. Docs: failure states. |
| [ ] [EXT-28](#ext-28) | Add exact ATS detail route classifier with safe URL handling. | `extension/site-rules.js`, `extension/tests/site-rules.test.mjs`; three hosts, spoofed suffix, listing/form/private scheme/query negatives; dep: 02. Docs: supported routes. |
| [ ] [EXT-29](#ext-29) | Extract editable public title/company candidates without reading forms. | `extension/job-page.js`, `extension/tests/fixtures/job-pages.html`, `frontend/tests/extension.spec.ts`; metadata/JSON-LD/display text, ambiguous/missing company null, hostile markup text only; dep: 28. Docs: metadata limits. |
| [ ] [EXT-30](#ext-30) | Register/unregister scripts per granted host and site opt-in. | `background.js`, `manifest.json`, `tests/bridge.test.mjs`; deny/revoke permission stops collection, install defaults off, unknown sites manual only; dep: 27,29. Docs: permissions. |

#### Band 7 — Navigation and visit transport (MAS-EXT-2/3)

Inspect selected-tab worker state and 9.4C; rules: security/testing. Never send full application/company history to `job-page.js`.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-31](#ext-31) | Trigger one check on qualifying top-level navigation with 500 ms debounce. | `background.js`, `extension/tests/navigation.test.mjs`; reload, SPA URL change, tab activation, duplicate events, subframe rejection; dep: 30. Docs: navigation. |
| [ ] [EXT-32](#ext-32) | Save visit only after successful check and preserve the pre-write warning. | `background.js`, `tests/navigation.test.mjs`; first visit not labeled previous, revisit yes, failed lookup zero visit; dep: 31,21. Docs: visit flow. |
| [ ] [EXT-33](#ext-33) | Implement current-tab gesture fallback for unsupported public pages. | `background.js`, `site-rules.js`, `tests/navigation.test.mjs`; no silent navigation monitoring, invalid URL rejection and explicit metadata input path; dep: 28,27. Docs: manual mode. |
| [ ] [EXT-34](#ext-34) | Bound session-only pending apply state and clear it on account/disconnect changes. | `background.js`, `tests/bridge.test.mjs`; worker suspension revalidates, restart disconnects, expiry <=24h, no private `storage.local`/sync; dep: 27. Docs: persistence. |
| [ ] [EXT-35](#ext-35) | Add pause/disconnect lifecycle and per-tab badge invalidation. | `background.js`, `tests/navigation.test.mjs`; old badge removed on navigation/revocation and detected logout (next session check; no promise of push logout detection), pause zero writes, no queue after reconnect; dep: 32,34. Docs: controls. |

#### Band 8 — Concise popup and deliberate writes (MAS-EXT-4)

Inspect 9.1 copy/priority and 9.4 messages; rules: frontend/security/testing. NEW `extension/tests/popup.test.mjs`; actual rendered states exercised by `frontend/tests/extension.spec.ts`.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-36](#ext-36) | Render check/loading/visited/applied/company/possible states with safe text. | `popup.html`, `popup.js`, `popup.css`, `tests/popup.test.mjs`; priority, null company/date and malicious title no HTML execution; dep: 26,33. Docs: user copy. |
| [ ] [EXT-37](#ext-37) | Render partial/offline/401/403/429/timeout/unsupported states honestly. | `popup.js`, `tests/popup.test.mjs`; no false no-history, Retry-After enforced, visit-save failure distinct from check; dep: 36,32. Docs: troubleshooting. |
| [ ] [EXT-38](#ext-38) | Add editable employer/title and one explicit account/URL confirmation before apply. | `popup.html`, `popup.js`, `tests/popup.test.mjs`; required fields, possible/company warning can proceed, already applied offers open history; dep: 36,19. Docs: apply flow. |
| [ ] [EXT-39](#ext-39) | Send apply once with stable session UUID/payload and recover ambiguous save result. | `popup.js`, `background.js`, `tests/popup.test.mjs`; double-click disabled, lost response same-key retry, edited payload requires fresh confirmation; dep: 38,34,20. Docs: retry. |
| [ ] [EXT-40](#ext-40) | Add pause/disconnect/forget visit confirmation and safe Open in JobGrid link. | `popup.html`, `popup.js`, `tests/popup.test.mjs`; account-bound delete, application preserved, navigation origin allowlist, 401 clears history; dep: 35,37,10. Docs: privacy controls. |

#### Band 9 — Integration, privacy and accessibility gates (MAS-EXT-5)

Inspect existing Playwright config/fixtures and 9.6 evidence matrix; rules: testing/security/frontend. Synthetic profiles/accounts and disposable databases only.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] [EXT-41](#ext-41) | Exercise unpacked extension → real local backend from a persistent Chromium profile. | `frontend/tests/extension.spec.ts`, `extension/README.md`; visit/check/confirm/apply/revisit and source-row deletion end-to-end, no mocked API acceptance claim; dep: 40,25. Docs: local harness. |
| [ ] [EXT-42](#ext-42) | Exercise two-account switch, forged messages and hostile site privacy negatives. | `frontend/tests/extension.spec.ts`, `backend/tests/test_browser_memory_security.py`; never leak counts/IDs to foreign account/job page, untrusted sites cannot trigger writes; dep: 41. Docs: none, regression only. |
| [ ] [EXT-43](#ext-43) | Exercise keyboard/screen-reader labels and every popup failure state. | `frontend/tests/extension.spec.ts`, `popup.html`, `popup.css`; focus return, live status, zoom/no overflow, controls without color; dep: 41. Docs: accessibility. |
| [ ] [EXT-44](#ext-44) | Verify worker suspension/restart, offline recovery, reload/SPA and permission revocation. | `frontend/tests/extension.spec.ts`, `extension/README.md`; no phantom visited/applied/clearance, repeated apply one track/time, no auto-replay after restart; dep: 41. Docs: lifecycle recovery. |
| [ ] [EXT-45](#ext-45) | Run timed matrix and verify bounded API/log behavior. | `backend/tests/test_browser_memory_matches.py`, `extension/README.md`; 30 warm checks p95, cold-start/timeout separately, 10k visits/query plan, no payload/cookie/query URL in logs; dep: 42–44. Docs: measured limits, not guessed results. |

#### Band 10 — Packaging, rollout and handover (MAS-EXT-5)

Inspect `.github/workflows/ci.yml`, section 7 deployment runbook, C-09/C-10 evidence and the selected release environment. No release action is authorized merely by this checklist.

| Task (~2% each) | Deliverable and reason | Allowed files / validation / dependencies |
|---|---|---|
| [ ] EXT-46 | Add extension contract/permission/Node-test checks and local extension E2E to existing CI. | `.github/workflows/ci.yml`, `frontend/package.json`, `extension/README.md`; clean install, existing suites intact, extension test reports actually collected; dep: 41–45. Docs: commands. |
| [ ] EXT-47 | Produce versioned pilot ZIP and privacy/install/remove instructions without dev hosts/secrets. | `extension/manifest.json`, `extension/README.md`, NEW `extension/package.mjs`, `extension/tests/package.test.mjs`; assert allowlisted members/dev-host and secret exclusions, deterministic package, archive manifest/hash review and unpack/install test; dep: 46. Docs: artifact/version/checksum. |
| [ ] EXT-48 | Accept migration/backup rollback and real Chrome/deployed OAuth pilot on one candidate. | `extension/README.md`, `development.md` evidence record; two controlled accounts, proxy auth, store-free unpacked installation, warm/cold checks, restart, first-time application preserved, old-code rollback with visit table retained; dep: 47,24, C-09/C-10 prerequisites. External failures remain blocked, not passed. |
| [ ] EXT-49 | Prepare store submission inputs, exact permissions/disclosures and privacy policy for human review. | `extension/README.md`, NEW `docs/CHROME_EXTENSION_PRIVACY.md`; verify store ID/origins/owner/support URL and stored-data disclosure; dep: 48. Submission/publication is separate from local completion; do not invent store approval. |
| [ ] EXT-50 | Review full feature diff, evidence/checklist and release/rollback handoff. | `development.md`, `docs/JOBGRID_BUILD_GUIDE.md`, `docs/repo_context.md`, `extension/README.md`; all applicable tests/CI green, no unresolved critical/high findings, PR/installed-version/deployed-revision states recorded separately; dep: 49 and all prior acceptance. Docs: current system, no task diary. |

**Checkpoints:** after 05/10/15/20/25/30/35/40/45/50 review cumulative diff, real contract parity, migration/backup safety, completed checklist evidence and remaining scope. Narrow checks run per row. Broaden only at checkpoints or when shared logic changes. A test failure must be repaired or reported with exact scope; never count an unrun external gate as complete.

**Dependency/parallel map:** 01→02→03 and 01→04 join at 05; after local 05, 06–10 visit work and 11–15 lookup work share frozen identity inputs; 16–20 requires 07/11. After schema 06, backup 22–25 can proceed independently of extension UI. Site fixtures 28–29 can proceed after 02. 26–35 require the accepted API/auth seam; 36–40 consume it; 41–50 are integration/release gates. These are possible independent work lanes, not a request to spawn agents. If a dependency changes a contract, stop its consumers and update the CCR/packets before resuming.

### 9.6 Verification, rollout and second-guess review

| Acceptance scenario | Required proof / failure assertion |
|---|---|
| Never seen, imported-only, saved-only, clicked-only, applied job | Separate expected copy and database state for each; never manufacture applied/visited evidence |
| Same job with tracking variants; distinct role IDs/query values | Canonical duplicate positive plus distinct-job negatives; original application URL/time/status retained |
| Same employer other role; aliases; shared ATS host | Correct applied record count; employer/role uncertainty explicit; no domain-level company merge |
| Rejected/withdrawn/archived application | Applied-before warning remains while saved-only archive does not become applied |
| Deleted CSV source, reinstall/profile restart, forget visits, account purge | Correct durable records and independent row/application/visit semantics from fresh database sessions |
| API/worker response lost, repeated confirmation, simultaneous tabs | One application/first time/event; stable replay key; no fake success; recover through check/retry |
| Offline/cold start/429/permission denied/revoked/missing tab | Honest unavailable/paused state, bounded requests, no automatic write queue |
| Two accounts and account switch during check/write | No cross-account results, receipt/key reuse or background writes; reconnection required |
| Malicious job URL/title/DOM/sender/frame | No HTML execution, arbitrary fetch, cookie export, form read or history disclosure to page |
| New and legacy JSON/ZIP backups; late invalid extension; quota union | Compatible explicit behavior; zero partial writes; visits survive valid restore with destination ownership |
| Real Chrome and provider login | Record actual Chrome version, OS, extension version/hash, frontend/backend SHA and synthetic fixtures; Chromium mocks are not Chrome/provider proof |

**Planned commands:** `cd backend && pytest tests/test_browser_visits.py tests/test_browser_memory_api.py tests/test_browser_memory_matches.py tests/test_browser_memory_apply.py tests/test_browser_memory_security.py tests/test_application_memory.py tests/test_capture_api.py tests/test_job_identity.py tests/test_backup_contract.py tests/test_complete_backup.py`; run against disposable SQLite and PostgreSQL according to section 5. `node --test extension/tests/*.test.mjs`; `cd frontend && npx playwright test tests/extension.spec.ts`; `cd frontend && npm run build`. The named new files/extension harness do not exist yet, so these are future commands, not recorded passes. EXT-46 must make the persistent-profile harness reproducible with the installed Playwright version and required headed/Xvfb setup. Run the full applicable existing CI matrix before release, especially row/opening/capture/lifecycle/backup regressions after shared changes.

**Rollout:** local fixture tests → backend migration and additive routes with extension disconnected → rollback/backup checks → trusted-origin dev/pilot package → two controlled accounts and real Chrome/OAuth/proxy proof → bounded unpacked pilot → privacy/store review → public distribution if authorized. No automatic extension publishing from GitHub main. Feature defaults off at installation; disabling/revoking tracking stops future collection. Preserve existing release-gate blockers, select exact services before hosted changes, and record extension version separately from frontend/backend revisions.

**Observability/cost:** existing structured logging/metrics only: action, outcome/error code, HTTP status, duration and aggregate counts. Redact request URL/body/account label and never log cookies, page URLs, company/title or application content. Synthetic evidence may reference fake fixture URLs. No new paid services or telemetry SDK. Monitor 401/429/503 rates, timeout rate and query latency; cap visits and per-account request rates. Owner and observation duration are assigned at pilot start: observe 48 hours including a cold start and reconnect. Roll back for any cross-account disclosure, phantom applied status, duplicate application creation, or sustained >5% lookup failures in 100 controlled attempts; low-volume pilot errors are reviewed individually rather than treated as statistically meaningful.

**Rollback:** pause/disconnect extension, remove its host grants or distribute disabled package, and disable/remove new router registration in old-compatible backend code. Leave added visit/receipt tables and data intact. Existing application history and old routes continue to work. Reconcile any ambiguous apply response through application history, never by deleting/reapplying. Verify backups/old-client compatibility before code rollback; a bad restore rolls back its whole transaction. Store rollback/update timing is external: a published extension cannot be recalled instantly, so unsupported server versions must fail closed. Retain migration and backup artifacts with the release record.

**Second-guess changes already incorporated:** Do not reuse `UrlHistory` (it is import memory); do not reuse `upsert_from_row` (it creates synthetic opens); do not show first navigation's newly saved visit as a previous visit; retrieve definite URL matches outside the company scan cap; do not guess an employer from an ATS host; avoid extension cookie/token copying by requiring an open trusted app tab; no private result cache or offline mutation queue. The weakest remaining assumption is same-origin deployed auth behavior. The most likely operational failure is a missing/suspended app tab or cold backend; the UI therefore pauses/times out honestly. The hardest later change is identity/backup compatibility, so those contracts require architect review.

**Readiness:** Detailed ticket specifications are written in section 9.7; none is dispatched or implemented, and the feature is not production-ready. EXT-01–05 validate release inputs/auth before dependent work. Packet intake, real proxy/OAuth evidence, privacy/store inputs, migration/backup compatibility, and existing release gates remain explicit prerequisites at the appropriate stage. No unresolved product/security choice may be delegated silently: report `Needs Architect Decision: <contract and evidence>` and continue only independent work.

<a id="extension-detailed-tickets"></a>
### 9.7 Detailed extension execution tickets

These packets expand the EXT-01–50 index to the JG-009 execution format. **All 50 are PLANNED / not implemented / no acceptance evidence. Detailed packets currently written: EXT-01–45; later entries remain in the index pending the next documentation commits.** Keep the same IDs and dependency order; a detailed packet does not create another task or issue. Relative size estimates are not calendar promises. P0 means a correctness/security prerequisite within this feature, P1 means a required V1 deliverable; neither changes the original app release priorities.

Read one selected packet together with `docs/repo_context.md` and its named current source. Contracts needed by that task are repeated below. The matching section-9.4 CCR remains the authoritative owner; if a copied extract drifts, update both before coding. This expansion records contract clarifications: explicit optional-backup envelope/checksum, missing-header error mapping, worker-only automatic visit authorization and worker-suspension versus browser-restart behavior. These are part of CCR-EXT-01 and are copied into the affected packets. Each packet still needs current source contents and the applicable skill rules attached for a separate builder session. A future file is not evidence that its dependency is implemented. Recheck snapshot states, migration head and fixtures at intake. No existing JG completed status, historical PR, test count or merge evidence transfers to an EXT ticket.

**Navigation:** [EXT-01](#ext-01), [EXT-02](#ext-02), [EXT-03](#ext-03), [EXT-04](#ext-04), [EXT-05](#ext-05), [EXT-06](#ext-06), [EXT-07](#ext-07), [EXT-08](#ext-08), [EXT-09](#ext-09), [EXT-10](#ext-10), [EXT-11](#ext-11), [EXT-12](#ext-12), [EXT-13](#ext-13), [EXT-14](#ext-14), [EXT-15](#ext-15), [EXT-16](#ext-16), [EXT-17](#ext-17), [EXT-18](#ext-18), [EXT-19](#ext-19), [EXT-20](#ext-20), [EXT-21](#ext-21), [EXT-22](#ext-22), [EXT-23](#ext-23), [EXT-24](#ext-24), [EXT-25](#ext-25), [EXT-26](#ext-26), [EXT-27](#ext-27), [EXT-28](#ext-28), [EXT-29](#ext-29), [EXT-30](#ext-30), [EXT-31](#ext-31), [EXT-32](#ext-32), [EXT-33](#ext-33), [EXT-34](#ext-34), [EXT-35](#ext-35), [EXT-36](#ext-36), [EXT-37](#ext-37), [EXT-38](#ext-38), [EXT-39](#ext-39), [EXT-40](#ext-40), [EXT-41](#ext-41), [EXT-42](#ext-42), [EXT-43](#ext-43), [EXT-44](#ext-44), [EXT-45](#ext-45), EXT-46, EXT-47, EXT-48, EXT-49, EXT-50.

<a id="ext-01"></a>

#### EXT-01 — Freeze pilot environments and account expectations

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Configuration\
**Execution position:** 1/50; band 1/10 — Connection proof; group step 1/5.

##### Goal — what to complete

Record selected pilot origins/account expectations; prevents connecting to the wrong service.

##### Why this exists

Prevents connecting to the wrong service. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

No predecessor; start here. Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/auth_router.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/vercel.json` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/src/api/client.js` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/C09_STAGING_OPERATIONS.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED NEW in EXT-01; inspect current behavior/fixtures if present.
- `extension/config.js` — PROPOSED NEW in EXT-01; inspect current behavior/fixtures if present.
- `extension/tests/config.test.mjs` — PROPOSED NEW in EXT-01; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `testing_rules.md, security_rules.md, product_quality_bar.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Record the repository baseline and select a disposable local frontend/API pair; list deployed pilot origin as unverified until the operator identifies it.
- Represent allowed frontend origins as exact parsed origins, including scheme and port; reject paths, credentials, wildcard hosts and arbitrary server overrides.
- Record supported ATS hosts and the open-JobGrid-tab requirement; distinguish local-only config from release config.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/README.md` | PROPOSED NEW in EXT-01 | Current-system documentation for this task only |
| `extension/config.js` | PROPOSED NEW in EXT-01 | Task-owned implementation/configuration boundary |
| `extension/tests/config.test.mjs` | PROPOSED NEW in EXT-01 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change or production record mutation. Only public configuration, manifest, source/package metadata or release evidence is owned here.

##### API / event / cache / integration contracts

Public config contract: `extension/config.js` exports `APP_ORIGIN` (one validated exact HTTPS frontend origin) and `PROTOCOL_VERSION=1`. The allowlist comparison uses the configured origin; it does not accept any arbitrary syntactically valid host. Local fixture builds copy the package to a temporary directory and overlay only APP_ORIGIN with the selected localhost origin; never write local origins into the release source/package. The fixture package must pass the separate dev-manifest checks. A still-unknown production origin remains a release blocker, not a guessed constant.

MV3 required permissions storage/activeTab/scripting; optional hosts only boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co and exact selected JobGrid origin. No tabs/history/cookies/<all_urls>/externally_connectable. Grant via user gesture, then independent per-site opt-in; defaults off. Register content script dynamically in top frame only; revoke/disable unregisters and stops collection. Dev manifest `extension/manifest.dev.json` may allow localhost; release artifact must exclude it. Public exact origins only, no arbitrary API host input. Native ES modules, packaged scripts, no inline/eval/remote executable code.

`GET /crm/browser-memory/session` (bridge: `/api/crm/browser-memory/session`), cookie auth via `get_current_user`, no body → `200 {"protocol_version":1,"account_id":101,"account_label":"Pilot A"}`. Example is synthetic. Missing/expired cookie → existing auth-compatible `401 {"detail":"Not authenticated"}` / invalid-token equivalent; no session token, cookie or raw email is returned. Identity comes from the server, not a client `user_id`.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-01.01** — Record the repository baseline and select a disposable local frontend/API pair; list deployed pilot origin as unverified until the operator identifies it.
2. **EXT-01.02** — Represent allowed frontend origins as exact parsed origins, including scheme and port; reject paths, credentials, wildcard hosts and arbitrary server overrides.
3. **EXT-01.03** — Record supported ATS hosts and the open-JobGrid-tab requirement; distinguish local-only config from release config.
4. **EXT-01.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_01_case_01` — https://jobgrid.example.test is accepted as a synthetic exact HTTPS origin; https://jobgrid.example.test.attacker.test is rejected.
- `ext_01_case_02` — A URL containing userinfo, a path or a wildcard is rejected; release config contains no localhost or credential value.
- `ext_01_case_03` — No pilot deployment is labeled verified when its URL/account owner is still unknown.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/config.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Review the config using a synthetic origin and a local disposable app; verify that the README states which environment is selected.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] https://jobgrid.example.test is accepted as a synthetic exact HTTPS origin; https://jobgrid.example.test.attacker.test is rejected.
- [ ] A URL containing userinfo, a path or a wildcard is rejected; release config contains no localhost or credential value.
- [ ] No pilot deployment is labeled verified when its URL/account owner is still unknown.
- [ ] Every numbered EXT-01 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No production URL is guessed. Missing deployed origin blocks only deployed validation; local fixture configuration can proceed. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No production URL is guessed. Missing deployed origin blocks only deployed validation; local fixture configuration can proceed.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-01 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[01/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-01`; title: **Freeze pilot environments and account expectations**; parent: one Chrome job/company memory main issue; band 1: Connection proof; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-02"></a>

#### EXT-02 — Create a loadable Manifest V3 extension shell

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Extension foundation\
**Execution position:** 2/50; band 1/10 — Connection proof; group step 2/5.

##### Goal — what to complete

Add minimal loadable MV3 shell and separate dev config; prevents accidental broad permissions.

##### Why this exists

Prevents accidental broad permissions. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-01](#ext-01) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/auth_router.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/vercel.json` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/src/api/client.js` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/C09_STAGING_OPERATIONS.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED NEW in EXT-02; inspect current behavior/fixtures if present.
- `extension/popup.html` — PROPOSED NEW in EXT-02; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED NEW in EXT-02; inspect current behavior/fixtures if present.
- `extension/tests/manifest.test.mjs` — PROPOSED NEW in EXT-02; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Create a manifest with manifest_version 3, a named action and packaged popup.html; use the public configuration from EXT-01.
- Declare storage, activeTab and scripting only; declare exact optional supported-host access and keep installation tracking off.
- Declare extension/package.json as private with type=module (no dependencies) so native Node tests load ES modules. Create a separate extension/manifest.dev.json containing localhost access for local tests; the production manifest must not contain it. No worker is required for this shell.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/manifest.json` | PROPOSED NEW in EXT-02 | Task-owned implementation/configuration boundary |
| `extension/popup.html` | PROPOSED NEW in EXT-02 | Task-owned implementation/configuration boundary |
| `extension/README.md` | PROPOSED; supplied by EXT-01 before use | Current-system documentation for this task only |
| `extension/package.json` | PROPOSED NEW in EXT-02 | Private type=module marker for native Node tests; no runtime dependency |
| `extension/manifest.dev.json` | PROPOSED NEW in EXT-02 | Task-owned implementation/configuration boundary |
| `extension/tests/manifest.test.mjs` | PROPOSED NEW in EXT-02 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change or production record mutation. Only public configuration, manifest, source/package metadata or release evidence is owned here.

##### API / event / cache / integration contracts

MV3 required permissions storage/activeTab/scripting; optional hosts only boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co and exact selected JobGrid origin. No tabs/history/cookies/<all_urls>/externally_connectable. Grant via user gesture, then independent per-site opt-in; defaults off. Register content script dynamically in top frame only; revoke/disable unregisters and stops collection. Dev manifest `extension/manifest.dev.json` may allow localhost; release artifact must exclude it. Public exact origins only, no arbitrary API host input. Native ES modules, packaged scripts, no inline/eval/remote executable code.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-02.01** — Create a manifest with manifest_version 3, a named action and packaged popup.html; use the public configuration from EXT-01.
2. **EXT-02.02** — Declare storage, activeTab and scripting only; declare exact optional supported-host access and keep installation tracking off.
3. **EXT-02.03** — Declare extension/package.json as private with type=module (no dependencies) so native Node tests load ES modules. Create a separate extension/manifest.dev.json containing localhost access for local tests; the production manifest must not contain it. No worker is required for this shell.
4. **EXT-02.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_02_case_01` — Chrome loads the unpacked shell without a manifest or CSP error and opens the named popup.
- `ext_02_case_02` — The release manifest has no history, cookies, tabs, <all_urls>, externally_connectable or localhost entry.
- `ext_02_case_03` — No network request or tracking write occurs on install or popup-shell load.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/manifest.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Use chrome://extensions with a temporary Chrome profile, enable developer mode, load the local shell and open its popup.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Chrome loads the unpacked shell without a manifest or CSP error and opens the named popup.
- [ ] The release manifest has no history, cookies, tabs, <all_urls>, externally_connectable or localhost entry.
- [ ] No network request or tracking write occurs on install or popup-shell load.
- [ ] Every numbered EXT-02 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Unload the shell to disable it; no account data or backend change exists. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Unload the shell to disable it; no account data or backend change exists.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-02 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[02/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-02`; title: **Create a loadable Manifest V3 extension shell**; parent: one Chrome job/company memory main issue; band 1: Connection proof; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-03"></a>

#### EXT-03 — Implement the fixed-route JobGrid session bridge

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Extension transport\
**Execution position:** 3/50; band 1/10 — Connection proof; group step 3/5.

##### Goal — what to complete

Implement isolated fixed-route session bridge; proves cookie reuse without token export.

##### Why this exists

Proves cookie reuse without token export. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-02](#ext-02) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/auth_router.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/vercel.json` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/src/api/client.js` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/C09_STAGING_OPERATIONS.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED NEW in EXT-03; inspect current behavior/fixtures if present.
- `extension/tests/bridge.test.mjs` — PROPOSED NEW in EXT-03; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Create an isolated content script that accepts only internal extension messages and validates version, request ID and allowed command shape.
- Map session to GET /api/crm/browser-memory/session using same-origin credentials; define the remaining fixed route map but do not expose arbitrary fetch/method/header inputs.
- Return bounded data/errors only through runtime messaging to the extension; use no DOM/window message relay or cookie reads. Exercise the bridge through a test harness before the worker exists.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/jobgrid-bridge.js` | PROPOSED NEW in EXT-03 | Task-owned implementation/configuration boundary |
| `extension/tests/bridge.test.mjs` | PROPOSED NEW in EXT-03 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change or production record mutation. Session/transport proof must not export cookies or create application history.

##### API / event / cache / integration contracts

Internal request `{version:1,request_id:UUID,kind:"session"|"check"|"visit"|"apply"|"forget_visits",account_id?:int,payload:object}` → `{version:1,request_id,ok:bool,data?:object,error?:{code,message,retry_after?:int}}`; max8192 UTF-8 bytes. Worker accepts apply/forget only from its own packaged popup sender. Automatic visit is worker-internal, derived from successful check + opted-in current top-frame detail navigation; page candidate may never request a write. Bridge validates own extension sender and maps only fixed routes/methods under same-origin `/api/crm/browser-memory`, credentials same-origin, fixed browser/expected-account headers on writes; no arbitrary URL/method/headers, external messaging or window relay. Response remains in worker/popup, never a job page. Version/shape/sender mismatch fails closed with a safe protocol error, no fetch. Timeout8s; response must match selected account/tab/document/URL/generation. Check account again before writing or displaying response.

`GET /crm/browser-memory/session` (bridge: `/api/crm/browser-memory/session`), cookie auth via `get_current_user`, no body → `200 {"protocol_version":1,"account_id":101,"account_label":"Pilot A"}`. Example is synthetic. Missing/expired cookie → existing auth-compatible `401 {"detail":"Not authenticated"}` / invalid-token equivalent; no session token, cookie or raw email is returned. Identity comes from the server, not a client `user_id`.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-03.01** — Create an isolated content script that accepts only internal extension messages and validates version, request ID and allowed command shape.
2. **EXT-03.02** — Map session to GET /api/crm/browser-memory/session using same-origin credentials; define the remaining fixed route map but do not expose arbitrary fetch/method/header inputs.
3. **EXT-03.03** — Return bounded data/errors only through runtime messaging to the extension; use no DOM/window message relay or cookie reads. Exercise the bridge through a test harness before the worker exists.
4. **EXT-03.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_03_case_01` — A valid session command calls exactly the fixed same-origin route and preserves request_id in the response.
- `ext_03_case_02` — An external sender, unsupported version, extra destination field or message over 8192 UTF-8 bytes is rejected with zero fetch calls.
- `ext_03_case_03` — An HTML/error body is returned as a safe unavailable result; no private response is written into the page DOM.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/bridge.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run the bridge test harness with one synthetic 200 response and one 401 response; inspect that it never reads document.cookie.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] A valid session command calls exactly the fixed same-origin route and preserves request_id in the response.
- [ ] An external sender, unsupported version, extra destination field or message over 8192 UTF-8 bytes is rejected with zero fetch calls.
- [ ] An HTML/error body is returned as a safe unavailable result; no private response is written into the page DOM.
- [ ] Every numbered EXT-03 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Session-only live use until the write routes and their guards exist; never work around cookie failures by exporting a token. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Session-only live use until the write routes and their guards exist; never work around cookie failures by exporting a token.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-03 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[03/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-03`; title: **Implement the fixed-route JobGrid session bridge**; parent: one Chrome job/company memory main issue; band 1: Connection proof; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-04"></a>

#### EXT-04 — Expose the authenticated extension session endpoint

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** API\
**Execution position:** 4/50; band 1/10 — Connection proof; group step 4/5.

##### Goal — what to complete

Add authenticated `/session` route and router registration; proves selected account binding.

##### Why this exists

Proves selected account binding. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-01](#ext-01) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/auth_router.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/vercel.json` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/src/api/client.js` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/C09_STAGING_OPERATIONS.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED NEW in EXT-04; inspect current behavior/fixtures if present.
- `backend/app/main.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_api.py` — PROPOSED NEW in EXT-04; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md, api_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Create GET /crm/browser-memory/session and register the router once in main.py.
- Resolve the account with get_current_user and return protocol_version, account_id and a bounded display label without cookie/token/email fields.
- Return the existing compatible unauthenticated response; do not change login, JWT/cookie settings or other auth routes.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/browser_memory.py` | PROPOSED NEW in EXT-04 | Task-owned implementation/configuration boundary |
| `backend/app/main.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_api.py` | PROPOSED NEW in EXT-04 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change or production record mutation. Session/transport proof must not export cookies or create application history.

##### API / event / cache / integration contracts

`GET /crm/browser-memory/session` (bridge: `/api/crm/browser-memory/session`), cookie auth via `get_current_user`, no body → `200 {"protocol_version":1,"account_id":101,"account_label":"Pilot A"}`. Example is synthetic. Missing/expired cookie → existing auth-compatible `401 {"detail":"Not authenticated"}` / invalid-token equivalent; no session token, cookie or raw email is returned. Identity comes from the server, not a client `user_id`.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-04.01** — Create GET /crm/browser-memory/session and register the router once in main.py.
2. **EXT-04.02** — Resolve the account with get_current_user and return protocol_version, account_id and a bounded display label without cookie/token/email fields.
3. **EXT-04.03** — Return the existing compatible unauthenticated response; do not change login, JWT/cookie settings or other auth routes.
4. **EXT-04.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_04_case_01` — Authenticated account A receives 200 with protocol_version=1 and its own account_id.
- `ext_04_case_02` — No cookie and invalid/expired cookie return the existing 401 auth response; no private account fields are returned.
- `ext_04_case_03` — A second signed-in account receives its own identity, never a cached response for A.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_api.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Call the endpoint with two disposable sessions and without a session; compare exact fields and response statuses.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Authenticated account A receives 200 with protocol_version=1 and its own account_id.
- [ ] No cookie and invalid/expired cookie return the existing 401 auth response; no private account fields are returned.
- [ ] A second signed-in account receives its own identity, never a cached response for A.
- [ ] Every numbered EXT-04 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Unregister the new router to disable the endpoint; existing login/session consumers remain unchanged. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Unregister the new router to disable the endpoint; existing login/session consumers remain unchanged.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-04 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[04/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-04`; title: **Expose the authenticated extension session endpoint**; parent: one Chrome job/company memory main issue; band 1: Connection proof; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-05"></a>

#### EXT-05 — Prove the Chrome login bridge with two accounts

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Integration spike\
**Execution position:** 5/50; band 1/10 — Connection proof; group step 5/5.

##### Goal — what to complete

Run real Chrome signed-in proxy/session spike and account switch; retire the biggest uncertainty first.

##### Why this exists

Retire the biggest uncertainty first. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-03](#ext-03), [EXT-04](#ext-04) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/auth_router.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/vercel.json` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/src/api/client.js` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/C09_STAGING_OPERATIONS.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED NEW in EXT-05; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED NEW in EXT-05; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Build the smallest persistent-profile Playwright extension fixture and a minimal packaged worker dispatch sufficient for the session bridge only.
- Copy the runtime source into a temporary profile package, install manifest.dev.json as its manifest.json and overlay config.js APP_ORIGIN with the verified local frontend origin without editing release source. Run that dev manifest against an open local JobGrid tab; sign in to account A, check identity, switch to B, close the app tab and repeat.
- Record local expected/actual results and extension/browser/source versions. Run selected deployed OAuth/proxy proof only when its exact environment is known; preserve that separate pending gate otherwise.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/README.md` | PROPOSED; supplied by EXT-01 before use | Current-system documentation for this task only |
| `frontend/tests/extension.spec.ts` | PROPOSED NEW in EXT-05 | Task-owned regression/fixture |
| `extension/background.js` | PROPOSED NEW in EXT-05 | Task-owned implementation/configuration boundary |
| `extension/manifest.dev.json` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change or production record mutation. Session/transport proof must not export cookies or create application history.

##### API / event / cache / integration contracts

`GET /crm/browser-memory/session` (bridge: `/api/crm/browser-memory/session`), cookie auth via `get_current_user`, no body → `200 {"protocol_version":1,"account_id":101,"account_label":"Pilot A"}`. Example is synthetic. Missing/expired cookie → existing auth-compatible `401 {"detail":"Not authenticated"}` / invalid-token equivalent; no session token, cookie or raw email is returned. Identity comes from the server, not a client `user_id`.

Internal request `{version:1,request_id:UUID,kind:"session"|"check"|"visit"|"apply"|"forget_visits",account_id?:int,payload:object}` → `{version:1,request_id,ok:bool,data?:object,error?:{code,message,retry_after?:int}}`; max8192 UTF-8 bytes. Worker accepts apply/forget only from its own packaged popup sender. Automatic visit is worker-internal, derived from successful check + opted-in current top-frame detail navigation; page candidate may never request a write. Bridge validates own extension sender and maps only fixed routes/methods under same-origin `/api/crm/browser-memory`, credentials same-origin, fixed browser/expected-account headers on writes; no arbitrary URL/method/headers, external messaging or window relay. Response remains in worker/popup, never a job page. Version/shape/sender mismatch fails closed with a safe protocol error, no fetch. Timeout8s; response must match selected account/tab/document/URL/generation. Check account again before writing or displaying response.

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-05.01** — Build the smallest persistent-profile Playwright extension fixture and a minimal packaged worker dispatch sufficient for the session bridge only.
2. **EXT-05.02** — Copy the runtime source into a temporary profile package, install manifest.dev.json as its manifest.json and overlay config.js APP_ORIGIN with the verified local frontend origin without editing release source. Run that dev manifest against an open local JobGrid tab; sign in to account A, check identity, switch to B, close the app tab and repeat.
3. **EXT-05.03** — Record local expected/actual results and extension/browser/source versions. Run selected deployed OAuth/proxy proof only when its exact environment is known; preserve that separate pending gate otherwise.
4. **EXT-05.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_05_case_01` — The real local browser bridge returns account A from the server, then reports B after account switch with no stale A display.
- `ext_05_case_02` — Closing the selected JobGrid tab or logging out produces unavailable/401 and never a private cached identity.
- `ext_05_case_03` — Browser fixture uses a disposable profile, loads the real manifest and calls the real local API; a mocked fetch test is not accepted as this spike.

```bash

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Install unpacked in actual Chrome, open JobGrid, sign in and inspect the returned account. Repeat with the second synthetic account and with the app tab closed.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] The real local browser bridge returns account A from the server, then reports B after account switch with no stale A display.
- [ ] Closing the selected JobGrid tab or logging out produces unavailable/401 and never a private cached identity.
- [ ] Browser fixture uses a disposable profile, loads the real manifest and calls the real local API; a mocked fetch test is not accepted as this spike.
- [ ] Every numbered EXT-05 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

If local same-origin cookie/proxy behavior fails, block auth-dependent tasks and revise ADR-EXT-01. Do not relax CORS/cookies. Deployed-only credentials block only the deployed proof. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- If local same-origin cookie/proxy behavior fails, block auth-dependent tasks and revise ADR-EXT-01. Do not relax CORS/cookies. Deployed-only credentials block only the deployed proof.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-05 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[05/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-05`; title: **Prove the Chrome login bridge with two accounts**; parent: one Chrome job/company memory main issue; band 1: Connection proof; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-06"></a>

#### EXT-06 — Add durable visit and apply-receipt tables

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Database migration\
**Execution position:** 6/50; band 2/10 — Durable visits; group step 1/5.

##### Goal — what to complete

Add visit/receipt models and next migration with owner uniqueness; external jobs need durable memory.

##### Why this exists

External jobs need durable memory. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-05](#ext-05) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/alembic/versions/018_bulk_undo_foundation.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/alembic/versions/019_browser_visits.py` — PROPOSED NEW in EXT-06; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED NEW in EXT-06; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Recheck Alembic head; use 019_browser_visits.py only if 019 is still free, with down_revision equal to the actual preceding revision.
- Add job_visits and browser_apply_receipts exactly as CCR-EXT-01 defines, including owner cascades, required fields and owner-scoped unique/time indexes.
- Extend model-field inventory: visits are recoverable product data and apply receipts are operational exclusions. Do not backfill imported or saved URLs as visits.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/models.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/app/backup_schemas.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/alembic/versions/019_browser_visits.py` | PROPOSED NEW in EXT-06 | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_visits.py` | PROPOSED NEW in EXT-06 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

NEW `job_visits`: id integer PK; user_id required FK users.id ON DELETE CASCADE; canonical_url Text required; canonical_url_hash String(64) required; first_visited_at UTC DateTime required server time; unique(user_id,canonical_url_hash), owner/time index. NEW `browser_apply_receipts`: id integer PK; user_id same owner FK/cascade; request_key String(36) UUID required; payload_hash String(64) required; response_json JSON frozen apply response required; created_at UTC DateTime required; unique(user_id,request_key), owner/time index. No source-row FK and no import-history backfill. Canonicalization version ccr-identity-1. Visits are backup product data; receipts are excluded operational state. Additive migration only; preserve existing rows/times.

##### API / event / cache / integration contracts

NEW `job_visits`: id integer PK; user_id required FK users.id ON DELETE CASCADE; canonical_url Text required; canonical_url_hash String(64) required; first_visited_at UTC DateTime required server time; unique(user_id,canonical_url_hash), owner/time index. NEW `browser_apply_receipts`: id integer PK; user_id same owner FK/cascade; request_key String(36) UUID required; payload_hash String(64) required; response_json JSON frozen apply response required; created_at UTC DateTime required; unique(user_id,request_key), owner/time index. No source-row FK and no import-history backfill. Canonicalization version ccr-identity-1. Visits are backup product data; receipts are excluded operational state. Additive migration only; preserve existing rows/times.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-06.01** — Recheck Alembic head; use 019_browser_visits.py only if 019 is still free, with down_revision equal to the actual preceding revision.
2. **EXT-06.02** — Add job_visits and browser_apply_receipts exactly as CCR-EXT-01 defines, including owner cascades, required fields and owner-scoped unique/time indexes.
3. **EXT-06.03** — Extend model-field inventory: visits are recoverable product data and apply receipts are operational exclusions. Do not backfill imported or saved URLs as visits.
4. **EXT-06.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_06_case_01` — Fresh and populated disposable SQLite/PostgreSQL upgrades create both tables and constraints without changing existing row/application counts or timestamps.
- `ext_06_case_02` — Same owner/hash visit and same owner/request key receipt cannot duplicate; a second account can use the same hash/key independently.
- `ext_06_case_03` — Deleting a disposable owner removes its visits/receipts and the inventory test has no missing or stale fields.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Upgrade a populated disposable database, compare existing counts and inspect the new indexes; verify old code can still read its original tables.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Fresh and populated disposable SQLite/PostgreSQL upgrades create both tables and constraints without changing existing row/application counts or timestamps.
- [ ] Same owner/hash visit and same owner/request key receipt cannot duplicate; a second account can use the same hash/key independently.
- [ ] Deleting a disposable owner removes its visits/receipts and the inventory test has no missing or stale fields.
- [ ] Every numbered EXT-06 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Old-code rollback retains both additive tables. Destructive downgrade requires export-first approval; do not drop live visit evidence. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Old-code rollback retains both additive tables. Destructive downgrade requires export-first approval; do not drop live visit evidence.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-06 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[06/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-06`; title: **Add durable visit and apply-receipt tables**; parent: one Chrome job/company memory main issue; band 2: Durable visits; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-07"></a>

#### EXT-07 — Validate browser-memory input and private URL boundaries

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Schema and validation\
**Execution position:** 7/50; band 2/10 — Durable visits; group step 2/5.

##### Goal — what to complete

Add strict browser-memory request schemas and privacy URL validation; rejects unsafe input without fetching it.

##### Why this exists

Rejects unsafe input without fetching it. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-06](#ext-06) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/browser_memory_schemas.py` — PROPOSED NEW in EXT-07; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED; supplied by EXT-06 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md, api_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Define strict request models for check, visit and apply; forbid unknown fields and client-supplied user_id.
- Reuse URL/text helpers while adding new-route-only rejection for userinfo, private/loopback hosts and the frozen credential-like query keys; never fetch the submitted URL.
- Require company/title for apply, literal confirmed=true and a valid UUID key; preserve nullable optional company/title for check.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/browser_memory_schemas.py` | PROPOSED NEW in EXT-07 | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_visits.py` | PROPOSED; supplied by EXT-06 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. Validation is pure and writes nothing.

##### API / event / cache / integration contracts

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-07.01** — Define strict request models for check, visit and apply; forbid unknown fields and client-supplied user_id.
2. **EXT-07.02** — Reuse URL/text helpers while adding new-route-only rejection for userinfo, private/loopback hosts and the frozen credential-like query keys; never fetch the submitted URL.
3. **EXT-07.03** — Require company/title for apply, literal confirmed=true and a valid UUID key; preserve nullable optional company/title for check.
4. **EXT-07.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_07_case_01` — Public synthetic HTTPS detail URL is accepted; chrome:, file:, javascript:, userinfo and localhost/private literal addresses are rejected.
- `ext_07_case_02` — A 2048-character valid URL passes the length rule; 2049 fails. Company/title limits are 320/500 and missing/blank apply fields fail.
- `ext_07_case_03` — confirmed=1, confirmed="true", extra owner fields and credential query keys in mixed case fail with 422 invalid_browser_memory_payload.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Submit the valid synthetic check payload, then malformed/unsafe variants through the schema harness and confirm no outbound request is attempted.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Public synthetic HTTPS detail URL is accepted; chrome:, file:, javascript:, userinfo and localhost/private literal addresses are rejected.
- [ ] A 2048-character valid URL passes the length rule; 2049 fails. Company/title limits are 320/500 and missing/blank apply fields fail.
- [ ] confirmed=1, confirmed="true", extra owner fields and credential query keys in mixed case fail with 422 invalid_browser_memory_payload.
- [ ] Every numbered EXT-07 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Keep existing global canonicalization behavior unchanged. If validation requires DNS requests or a new transport, stop for an architect decision. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Keep existing global canonicalization behavior unchanged. If validation requires DNS requests or a new transport, stop for an architect decision.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-07 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[07/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-07`; title: **Validate browser-memory input and private URL boundaries**; parent: one Chrome job/company memory main issue; band 2: Durable visits; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-08"></a>

#### EXT-08 — Persist one first visit per owner and canonical job

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Service\
**Execution position:** 8/50; band 2/10 — Durable visits; group step 3/5.

##### Goal — what to complete

Insert once/replay one visit under owner lock and 10,000 cap; avoids duplicate events and unbounded growth.

##### Why this exists

Avoids duplicate events and unbounded growth. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-07](#ext-07) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED NEW in EXT-08; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED; supplied by EXT-06 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Implement caller-owned insert/replay with existing canonical identity; lock/resolve uniqueness using the repository dialect patterns.
- Return created=true only for the first committed visit and keep first_visited_at unchanged on revisit or concurrent retry.
- Enforce 10,000 visits per account, permit existing-visit retries at capacity, and reject a hash collision with a different canonical URL.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED NEW in EXT-08 | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_visits.py` | PROPOSED; supplied by EXT-06 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use job_visits and its owner/hash uniqueness from EXT-06. No new schema or application/CSV mutation is authorized.

##### API / event / cache / integration contracts

NEW `job_visits`: id integer PK; user_id required FK users.id ON DELETE CASCADE; canonical_url Text required; canonical_url_hash String(64) required; first_visited_at UTC DateTime required server time; unique(user_id,canonical_url_hash), owner/time index. NEW `browser_apply_receipts`: id integer PK; user_id same owner FK/cascade; request_key String(36) UUID required; payload_hash String(64) required; response_json JSON frozen apply response required; created_at UTC DateTime required; unique(user_id,request_key), owner/time index. No source-row FK and no import-history backfill. Canonicalization version ccr-identity-1. Visits are backup product data; receipts are excluded operational state. Additive migration only; preserve existing rows/times.

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-08.01** — Implement caller-owned insert/replay with existing canonical identity; lock/resolve uniqueness using the repository dialect patterns.
2. **EXT-08.02** — Return created=true only for the first committed visit and keep first_visited_at unchanged on revisit or concurrent retry.
3. **EXT-08.03** — Enforce 10,000 visits per account, permit existing-visit retries at capacity, and reject a hash collision with a different canonical URL.
4. **EXT-08.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_08_case_01` — First visit creates one record; second visit and concurrent identical visit return the same first timestamp and one durable row.
- `ext_08_case_02` — At 10,000 visits, an existing URL succeeds and a new URL returns 409 visit_limit_reached without deleting any history.
- `ext_08_case_03` — Injected failure rolls back the insert; forced hash collision returns 409 identity_conflict with no merge.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Call the service twice for one synthetic job with a fresh session between calls and compare first timestamp, count and created flags.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] First visit creates one record; second visit and concurrent identical visit return the same first timestamp and one durable row.
- [ ] At 10,000 visits, an existing URL succeeds and a new URL returns 409 visit_limit_reached without deleting any history.
- [ ] Injected failure rolls back the insert; forced hash collision returns 409 identity_conflict with no merge.
- [ ] Every numbered EXT-08 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

The caller commits once. A retry must not increment a visit/event/session counter or create a JobTrack. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- The caller commits once. A retry must not increment a visit/event/session counter or create a JobTrack.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-08 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[08/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-08`; title: **Persist one first visit per owner and canonical job**; parent: one Chrome job/company memory main issue; band 2: Durable visits; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-09"></a>

#### EXT-09 — Share row-visit mutation without inventing applications

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Service extraction\
**Execution position:** 9/50; band 2/10 — Durable visits; group step 4/5.

##### Goal — what to complete

Reuse/extract row-visit mutation so an external visit updates matching existing rows only.

##### Why this exists

Reuse/extract row-visit mutation so an external visit updates matching existing rows only. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-08](#ext-08) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED; supplied by EXT-06 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Trace record_click and its callers; extract only the row clicked/first timestamp mutation into the existing browser-memory service boundary if a reusable helper is needed.
- Update owned existing rows for the exact or same stored canonical identity; the extension write records its external visit in the same transaction.
- Preserve the existing row-click API response, lifecycle idempotency and original callers; suppress extension-specific session-count inflation and do not create new rows/tracks.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/rows.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_visits.py` | PROPOSED; supplied by EXT-06 before use | Task-owned regression/fixture |
| `backend/tests/test_rows.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use job_visits and its owner/hash uniqueness from EXT-06. Only matching owned existing CsvRow clicked/first-time fields may also change; preserve lifecycle ownership.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-09.01** — Trace record_click and its callers; extract only the row clicked/first timestamp mutation into the existing browser-memory service boundary if a reusable helper is needed.
2. **EXT-09.02** — Update owned existing rows for the exact or same stored canonical identity; the extension write records its external visit in the same transaction.
3. **EXT-09.03** — Preserve the existing row-click API response, lifecycle idempotency and original callers; suppress extension-specific session-count inflation and do not create new rows/tracks.
4. **EXT-09.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_09_case_01` — An unclicked matching owned row becomes clicked; a previously clicked row retains its first click time.
- `ext_09_case_02` — A browser visit with no source row creates only job_visits; JobTrack, applied_at and application totals remain unchanged.
- `ext_09_case_03` — Foreign rows and different job IDs do not change; existing record_click regression responses/events still pass.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py tests/test_rows.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Visit a job already in a synthetic CSV, then an external-only job. Reload dashboard and applications to verify row clicks and application totals independently.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] An unclicked matching owned row becomes clicked; a previously clicked row retains its first click time.
- [ ] A browser visit with no source row creates only job_visits; JobTrack, applied_at and application totals remain unchanged.
- [ ] Foreign rows and different job IDs do not change; existing record_click regression responses/events still pass.
- [ ] Every numbered EXT-09 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

If extraction changes original row-click event/count semantics, retain the old call contract and revise the helper rather than rewriting all callers. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- If extraction changes original row-click event/count semantics, retain the old call contract and revise the helper rather than rewriting all callers.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-09 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[09/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-09`; title: **Share row-visit mutation without inventing applications**; parent: one Chrome job/company memory main issue; band 2: Durable visits; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-10"></a>

#### EXT-10 — Forget visit memory for the authenticated owner

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Service and privacy\
**Execution position:** 10/50; band 2/10 — Durable visits; group step 5/5.

##### Goal — what to complete

Add owner-only forget-visits service and account deletion coverage; provides privacy recovery.

##### Why this exists

Provides privacy recovery. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-08](#ext-08) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED; supplied by EXT-06 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Delete job_visits only for the authenticated account and return the affected count.
- Leave JobTrack, UrlHistory, CsvRow.clicked and application evidence untouched; expose that limitation in user documentation.
- Cover owner deletion cascade and repeat deletion with zero remaining visits. Route transport is owned by EXT-19.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_visits.py` | PROPOSED; supplied by EXT-06 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use job_visits and its owner/hash uniqueness from EXT-06. No new schema or application/CSV mutation is authorized.

##### API / event / cache / integration contracts

`DELETE /crm/browser-memory/visits`, no body, explicit popup confirmation → `200 {protocol_version:1,account_id:int,deleted:int}`. Only job_visits of the cookie owner are deleted; repeat returns zero. Retain JobTrack/application evidence, UrlHistory and CsvRow.clicked. Older user-selected backup may restore forgotten visits. `Open in JobGrid` uses only the selected exact trusted origin and validated returned application ID; never accept an arbitrary destination/return URL.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-10.01** — Delete job_visits only for the authenticated account and return the affected count.
2. **EXT-10.02** — Leave JobTrack, UrlHistory, CsvRow.clicked and application evidence untouched; expose that limitation in user documentation.
3. **EXT-10.03** — Cover owner deletion cascade and repeat deletion with zero remaining visits. Route transport is owned by EXT-19.
4. **EXT-10.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_10_case_01` — Account A forgets its two visits: deleted=2, A visit count=0 and B visit count stays unchanged.
- `ext_10_case_02` — Repeat forget returns deleted=0; both original applications and clicked source rows retain their values.
- `ext_10_case_03` — Deleting the owner cascades only that owner visit/receipt records with no orphan or foreign delete.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Seed separate A/B visits, forget A through the service harness and compare fresh-session counts plus unchanged application state.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Account A forgets its two visits: deleted=2, A visit count=0 and B visit count stays unchanged.
- [ ] Repeat forget returns deleted=0; both original applications and clicked source rows retain their values.
- [ ] Deleting the owner cascades only that owner visit/receipt records with no orphan or foreign delete.
- [ ] Every numbered EXT-10 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Forget cannot be undone from a hidden extension cache; a user-chosen older backup may restore visits and must be disclosed. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Forget cannot be undone from a hidden extension cache; a user-chosen older backup may restore visits and must be disclosed.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-10 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[10/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-10`; title: **Forget visit memory for the authenticated owner**; parent: one Chrome job/company memory main issue; band 2: Durable visits; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-11"></a>

#### EXT-11 — Extract the existing application matcher without API drift

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Service extraction\
**Execution position:** 11/50; band 3/10 — Accurate lookup; group step 1/5.

##### Goal — what to complete

Move shared applied-match query into its owning identity service without changing existing API behavior.

##### Why this exists

Move shared applied-match query into its owning identity service without changing existing API behavior. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-07](#ext-07) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/company_aliases.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_matches.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_memory.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Trace _find_application_matches callers and snapshot their response, ordering, alias use and errors.
- Move the shared query to services/job_identity.py; keep compatible router adapters and all original field/default/status meanings.
- Keep filtering applied_at!=null and owner scope; do not use capture matches that include never-applied tracks.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/crm.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/app/services/job_identity.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/tests/test_application_memory.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. No persisted write is permitted.

##### API / event / cache / integration contracts

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-11.01** — Trace _find_application_matches callers and snapshot their response, ordering, alias use and errors.
2. **EXT-11.02** — Move the shared query to services/job_identity.py; keep compatible router adapters and all original field/default/status meanings.
3. **EXT-11.03** — Keep filtering applied_at!=null and owner scope; do not use capture matches that include never-applied tracks.
4. **EXT-11.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_11_case_01` — Existing GET/POST application-match endpoints return identical fields, order and error shapes for fixed fixtures.
- `ext_11_case_02` — Saved-only and foreign-account tracks do not appear as applied matches or increase company_history_count.
- `ext_11_case_03` — Alias-aware possible matches and rejected/withdrawn application history remain available after extraction.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_application_memory.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Call the existing match endpoints before/after extraction with the same fixture and compare JSON and status, not just 200.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Existing GET/POST application-match endpoints return identical fields, order and error shapes for fixed fixtures.
- [ ] Saved-only and foreign-account tracks do not appear as applied matches or increase company_history_count.
- [ ] Alias-aware possible matches and rejected/withdrawn application history remain available after extraction.
- [ ] Every numbered EXT-11 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No new endpoint/schema change belongs here. If parity fails, repair the extraction before enabling the new caller. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No new endpoint/schema change belongs here. If parity fails, repair the extraction before enabling the new caller.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-11 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[11/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-11`; title: **Extract the existing application matcher without API drift**; parent: one Chrome job/company memory main issue; band 3: Accurate lookup; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-12"></a>

#### EXT-12 — Keep definite matches visible beyond company scan limits

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Query correctness\
**Execution position:** 12/50; band 3/10 — Accurate lookup; group step 2/5.

##### Goal — what to complete

Guarantee exact/canonical lookups cannot be hidden by company scan limits.

##### Why this exists

Guarantee exact/canonical lookups cannot be hidden by company scan limits. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-11](#ext-11) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/company_aliases.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_matches.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_matches.py` — PROPOSED NEW in EXT-12; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Run owner-scoped exact/canonical applied lookups separately from the bounded possible company/title scan.
- Return at most 20 matches in exact/canonical/possible then newest-time/ID order; surface lookup_complete=false if the 500 candidate cap is reached.
- Keep company application count as an independent aggregate, without scanning/fetching the entire history in Python.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/job_identity.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_matches.py` | PROPOSED NEW in EXT-12 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. No persisted write is permitted.

##### API / event / cache / integration contracts

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-12.01** — Run owner-scoped exact/canonical applied lookups separately from the bounded possible company/title scan.
2. **EXT-12.02** — Return at most 20 matches in exact/canonical/possible then newest-time/ID order; surface lookup_complete=false if the 500 candidate cap is reached.
3. **EXT-12.03** — Keep company application count as an independent aggregate, without scanning/fetching the entire history in Python.
4. **EXT-12.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_12_case_01` — One old exact job remains returned when more than 500 newer same-company jobs exist.
- `ext_12_case_02` — Known canonical job is never hidden by possible results; distinct IDs/unknown query parameters remain distinct.
- `ext_12_case_03` — A capped possible search reports incomplete, returns <=20 matches, and count still reflects all owner applied records.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_matches.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Seed the 501-plus same-company fixture and inspect the oldest known URL result, ordering, count and completeness flag.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] One old exact job remains returned when more than 500 newer same-company jobs exist.
- [ ] Known canonical job is never hidden by possible results; distinct IDs/unknown query parameters remain distinct.
- [ ] A capped possible search reports incomplete, returns <=20 matches, and count still reflects all owner applied records.
- [ ] Every numbered EXT-12 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not widen global query limits to hide the defect. Shared public response additions need explicit compatible adapter tests. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not widen global query limits to hide the defect. Shared public response additions need explicit compatible adapter tests.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-12 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[12/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-12`; title: **Keep definite matches visible beyond company scan limits**; parent: one Chrome job/company memory main issue; band 3: Accurate lookup; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-13"></a>

#### EXT-13 — Compose separate visit, applied and company facts

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Query service\
**Execution position:** 13/50; band 3/10 — Accurate lookup; group step 3/5.

##### Goal — what to complete

Compose visit evidence with application matches and alias-aware count; keeps saved/imported state distinct.

##### Why this exists

Keeps saved/imported state distinct. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-08](#ext-08), [EXT-12](#ext-12) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/company_aliases.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_matches.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_matches.py` — PROPOSED; supplied by EXT-12 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Combine durable external visits with legacy row-click/open evidence using canonical identity and the shared applied matcher.
- Set company_known=false when company is absent/ambiguous and do not derive employer from an ATS host or slug.
- Return independent visit facts, matches, company_history_count and lookup completeness without writing state.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_matches.py` | PROPOSED; supplied by EXT-12 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. No persisted write is permitted.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-13.01** — Combine durable external visits with legacy row-click/open evidence using canonical identity and the shared applied matcher.
2. **EXT-13.02** — Set company_known=false when company is absent/ambiguous and do not derive employer from an ATS host or slug.
3. **EXT-13.03** — Return independent visit facts, matches, company_history_count and lookup completeness without writing state.
4. **EXT-13.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_13_case_01` — Imported-only and captured/saved-only fixtures report no visited/applied facts.
- `ext_13_case_02` — Clicked-only fixture reports visited=true and no applied match; applied-only fixture reports application evidence without manufacturing a visit.
- `ext_13_case_03` — Same employer/different role contributes company history; foreign records and shared ATS domain alone do not.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_matches.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run one check each for imported-only, clicked-only, saved-only, applied and external-visit fixtures; compare every fact independently.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Imported-only and captured/saved-only fixtures report no visited/applied facts.
- [ ] Clicked-only fixture reports visited=true and no applied match; applied-only fixture reports application evidence without manufacturing a visit.
- [ ] Same employer/different role contributes company history; foreign records and shared ATS domain alone do not.
- [ ] Every numbered EXT-13 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No backfill or click/apply mutation in this read. Uncertain metadata remains unknown. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No backfill or click/apply mutation in this read. Uncertain metadata remains unknown.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-13 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[13/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-13`; title: **Compose separate visit, applied and company facts**; parent: one Chrome job/company memory main issue; band 3: Accurate lookup; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-14"></a>

#### EXT-14 — Expose the read-only browser-memory check endpoint

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** API\
**Execution position:** 14/50; band 3/10 — Accurate lookup; group step 4/5.

##### Goal — what to complete

Add `/check` route with frozen response and common errors.

##### Why this exists

Add `/check` route with frozen response and common errors. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-13](#ext-13) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/company_aliases.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_matches.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `backend/app/browser_memory_schemas.py` — PROPOSED; supplied by EXT-07 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_api.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md, api_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Add POST /crm/browser-memory/check with the strict request and frozen response schema.
- Populate UTC checked_at and account_id from the server; pass independent match/visit/completeness facts through without mutation.
- Map invalid input/unavailable failures to the frozen safe error shape and preserve existing session-auth 401 compatibility.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/browser_memory.py` | PROPOSED; supplied by EXT-04 before use | Task-owned implementation/configuration boundary |
| `backend/app/browser_memory_schemas.py` | PROPOSED; supplied by EXT-07 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_api.py` | PROPOSED; supplied by EXT-04 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. No persisted write is permitted.

##### API / event / cache / integration contracts

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-14.01** — Add POST /crm/browser-memory/check with the strict request and frozen response schema.
2. **EXT-14.02** — Populate UTC checked_at and account_id from the server; pass independent match/visit/completeness facts through without mutation.
3. **EXT-14.03** — Map invalid input/unavailable failures to the frozen safe error shape and preserve existing session-auth 401 compatibility.
4. **EXT-14.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_14_case_01` — Authenticated valid URL returns the exact protocol v1 shape with UTC-Z timestamps, booleans, nulls and integer company count.
- `ext_14_case_02` — Missing authentication returns 401; invalid/extra fields return 422 and no private query result.
- `ext_14_case_03` — Counts of visits/tracks/events/receipts are unchanged by repeated checks, including errors.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_api.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Use two synthetic sessions to call the same URL, then invalid/no-session cases; compare response owner and database before/after.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Authenticated valid URL returns the exact protocol v1 shape with UTC-Z timestamps, booleans, nulls and integer company count.
- [ ] Missing authentication returns 401; invalid/extra fields return 422 and no private query result.
- [ ] Counts of visits/tracks/events/receipts are unchanged by repeated checks, including errors.
- [ ] Every numbered EXT-14 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

The endpoint is additive; an old extension/server combination fails unavailable rather than showing no recorded application. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- The endpoint is additive; an old extension/server combination fails unavailable rather than showing no recorded application.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-14 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[14/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-14`; title: **Expose the read-only browser-memory check endpoint**; parent: one Chrome job/company memory main issue; band 3: Accurate lookup; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-15"></a>

#### EXT-15 — Freeze the positive and negative job identity matrix

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Regression tests\
**Execution position:** 15/50; band 3/10 — Accurate lookup; group step 5/5.

##### Goal — what to complete

Add identity matrix for different employer/role/job ID and tracking variants; prevents dangerous false certainty.

##### Why this exists

Prevents dangerous false certainty. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-14](#ext-14) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/company_aliases.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_application_matches.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_matches.py` — PROPOSED; supplied by EXT-12 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_job_identity.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Create nonempty fixture pairs for original/canonical URL, tracker variants, meaningful query/path differences and company aliases.
- Assert exact returned match confidence/reason/order and company counts, including advanced/archived statuses and duplicate titles.
- Preserve underlying objects and verify no lookup merges, rewrites or updates them.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/tests/test_browser_memory_matches.py` | PROPOSED; supplied by EXT-12 before use | Task-owned regression/fixture |
| `backend/tests/test_job_identity.py` | EXISTS at planning baseline | Task-owned regression/fixture |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Read existing JobTrack/CsvRow/owner aliases and (after EXT-06) job_visits. Only non-null JobTrack.applied_at proves an application; never reinterpret UrlHistory.first_seen_at. No new migration in this task. No persisted write is permitted.

##### API / event / cache / integration contracts

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-15.01** — Create nonempty fixture pairs for original/canonical URL, tracker variants, meaningful query/path differences and company aliases.
2. **EXT-15.02** — Assert exact returned match confidence/reason/order and company counts, including advanced/archived statuses and duplicate titles.
3. **EXT-15.03** — Preserve underlying objects and verify no lookup merges, rewrites or updates them.
4. **EXT-15.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_15_case_01` — utm/gclid/fbclid variants of the same supported identity yield a canonical applied match.
- `ext_15_case_02` — Different job IDs, path case/trailing slash and unknown query values stay distinct under existing canonical policy.
- `ext_15_case_03` — Same alias employer/title yields possible only; same ATS host/different employer yields no company identity claim.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_matches.py tests/test_job_identity.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Review the fixture matrix with one positive and one negative per rule; inspect unchanged stored original URL and applied time.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] utm/gclid/fbclid variants of the same supported identity yield a canonical applied match.
- [ ] Different job IDs, path case/trailing slash and unknown query values stay distinct under existing canonical policy.
- [ ] Same alias employer/title yields possible only; same ATS host/different employer yields no company identity claim.
- [ ] Every numbered EXT-15 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

This ticket changes tests only unless a failing behavior is separately approved as a bounded fix; do not silently change matching contracts. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- This ticket changes tests only unless a failing behavior is separately approved as a bounded fix; do not silently change matching contracts.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-15 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

None — regression assertions only; no runtime/setup behavior change. Record that reason in the main issue; a discovered runtime fix needs its own bounded scope.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[15/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-15`; title: **Freeze the positive and negative job identity matrix**; parent: one Chrome job/company memory main issue; band 3: Accurate lookup; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-16"></a>

#### EXT-16 — Write an explicit application without a CSV row

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Application service\
**Execution position:** 16/50; band 4/10 — Explicit application writes; group step 1/5.

##### Goal — what to complete

Add service that explicitly applies a URL without CSV capture or synthetic opens.

##### Why this exists

Add service that explicitly applies a URL without CSV capture or synthetic opens. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-11](#ext-11), [EXT-07](#ext-07) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/lifecycle.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contacts.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_lifecycle_mutations.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_apply.py` — PROPOSED NEW in EXT-16; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Validate all input before changing state; resolve the owner and take the existing account mutation lock.
- Create or update only an exact URL never-applied JobTrack using apply_job_track_changes; first applied time and lifecycle event join one transaction.
- Preserve existing nonempty metadata/notes; no row capture, synthetic open, visited record or session increment occurs.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_apply.py` | PROPOSED NEW in EXT-16 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Account locks/unique owner identities and caller-owned transactions apply; no independent child commit.

##### API / event / cache / integration contracts

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-16.01** — Validate all input before changing state; resolve the owner and take the existing account mutation lock.
2. **EXT-16.02** — Create or update only an exact URL never-applied JobTrack using apply_job_track_changes; first applied time and lifecycle event join one transaction.
3. **EXT-16.03** — Preserve existing nonempty metadata/notes; no row capture, synthetic open, visited record or session increment occurs.
4. **EXT-16.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_16_case_01` — New synthetic URL creates one applied track/event with company/title and no clicked row or job_visit.
- `ext_16_case_02` — Existing exact never-applied track becomes applied without overwriting notes/company/title already present.
- `ext_16_case_03` — Invalid fields or an injected lifecycle failure leave zero partial track/event writes from a fresh session.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_apply.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Apply an external-only synthetic job through the service and compare application, source-row, visit and event counts separately.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] New synthetic URL creates one applied track/event with company/title and no clicked row or job_visit.
- [ ] Existing exact never-applied track becomes applied without overwriting notes/company/title already present.
- [ ] Invalid fields or an injected lifecycle failure leave zero partial track/event writes from a fresh session.
- [ ] Every numbered EXT-16 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not call committing route handlers or upsert_from_row. Unexpected lifecycle schema/status requirements need architect review. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not call committing route handlers or upsert_from_row. Unexpected lifecycle schema/status requirements need architect review.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-16 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[16/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-16`; title: **Write an explicit application without a CSV row**; parent: one Chrome job/company memory main issue; band 4: Explicit application writes; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-17"></a>

#### EXT-17 — Return prior applications without regressing history

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Application identity\
**Execution position:** 17/50; band 4/10 — Explicit application writes; group step 2/5.

##### Goal — what to complete

Return existing applied exact/canonical track unchanged; preserves original timestamp and advanced status.

##### Why this exists

Preserves original timestamp and advanced status. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-16](#ext-16) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/lifecycle.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contacts.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_lifecycle_mutations.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_apply.py` — PROPOSED; supplied by EXT-16 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Check exact/canonical already-applied evidence before any new application mutation.
- Return the existing application ID/time with already_applied=true and preserve advanced/rejected/archived status.
- Treat possible/company-only matches as warnings; only exact never-applied URL tracks can be updated, and separate canonical never-applied records are not silently merged.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_apply.py` | PROPOSED; supplied by EXT-16 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Account locks/unique owner identities and caller-owned transactions apply; no independent child commit.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

Existing `/crm/application-matches` adapters stay backward compatible. Shared matcher consumes authenticated user_id, url, optional company/title and returns existing matches/company_history_count; new internal lookup completeness is adapted only for the browser-memory response. Only JobTrack.applied_at!=null counts as applied. Exact original/canonical identity outranks possible company+title; owner aliases only, never ATS hostname as employer. Canonical policy removes default ports/fragments/utm_*/gclid/fbclid only, preserving path bytes/case/trailing slash and all unknown query order/values. Original URLs are never rewritten. Definite lookups bypass the 500 possible scan; browser results max20 in confidence/newest-time/ID order.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-17.01** — Check exact/canonical already-applied evidence before any new application mutation.
2. **EXT-17.02** — Return the existing application ID/time with already_applied=true and preserve advanced/rejected/archived status.
3. **EXT-17.03** — Treat possible/company-only matches as warnings; only exact never-applied URL tracks can be updated, and separate canonical never-applied records are not silently merged.
4. **EXT-17.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_17_case_01` — Canonical tracker-variant retry returns the existing ID/time/status and emits no new first-applied event.
- `ext_17_case_02` — A rejected/archived previously applied track still warns and remains rejected/archived.
- `ext_17_case_03` — Different role in the same company can create its own track; possible company/title match is not a merge target.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_apply.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Apply, advance status, retry the same/canonical URL, then apply another role at the same employer; compare IDs and original timestamps.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Canonical tracker-variant retry returns the existing ID/time/status and emits no new first-applied event.
- [ ] A rejected/archived previously applied track still warns and remains rejected/archived.
- [ ] Different role in the same company can create its own track; possible company/title match is not a merge target.
- [ ] Every numbered EXT-17 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Never reset status to applied or rewrite original URL/notes just to satisfy a repeated confirmation. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Never reset status to applied or rewrite original URL/notes just to satisfy a repeated confirmation.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-17 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[17/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-17`; title: **Return prior applications without regressing history**; parent: one Chrome job/company memory main issue; band 4: Explicit application writes; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-18"></a>

#### EXT-18 — Make apply confirmation replay-safe with bounded receipts

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Idempotency service\
**Execution position:** 18/50; band 4/10 — Explicit application writes; group step 3/5.

##### Goal — what to complete

Bind apply request UUID/digest to bounded `browser_apply_receipts`.

##### Why this exists

Bind apply request UUID/digest to bounded `browser_apply_receipts`. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-17](#ext-17) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/lifecycle.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contacts.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_lifecycle_mutations.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/contact_models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_apply.py` — PROPOSED; supplied by EXT-16 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Hash a normalized validated apply payload and reserve/read owner+request UUID under the same write lock.
- Commit the final frozen apply response and lifecycle mutation together; same key/payload replays and changed payload conflicts.
- Prune >30-day receipts on write, cap active receipts at 10,000 and return application_deleted when a recorded target no longer exists.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_apply.py` | PROPOSED; supplied by EXT-16 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-18.01** — Hash a normalized validated apply payload and reserve/read owner+request UUID under the same write lock.
2. **EXT-18.02** — Commit the final frozen apply response and lifecycle mutation together; same key/payload replays and changed payload conflicts.
3. **EXT-18.03** — Prune >30-day receipts on write, cap active receipts at 10,000 and return application_deleted when a recorded target no longer exists.
4. **EXT-18.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_18_case_01` — Lost-response same-key retry returns the same response/application/time and one first-applied event.
- `ext_18_case_02` — Same key with changed URL/title returns 409 idempotency_conflict; another account using that key gets no prior-owner data.
- `ext_18_case_03` — Injected late failure leaves no success receipt; deleted target returns application_deleted; receipt cap/expiry leaves application history intact.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_apply.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Simulate commit followed by client disconnect, then retry with the identical UUID and compare durable response/event counts.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Lost-response same-key retry returns the same response/application/time and one first-applied event.
- [ ] Same key with changed URL/title returns 409 idempotency_conflict; another account using that key gets no prior-owner data.
- [ ] Injected late failure leaves no success receipt; deleted target returns application_deleted; receipt cap/expiry leaves application history intact.
- [ ] Every numbered EXT-18 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not reuse evidence/document receipt tables or replay an operational receipt as restored product history. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not reuse evidence/document receipt tables or replay an operational receipt as restored product history.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-18 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[18/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-18`; title: **Make apply confirmation replay-safe with bounded receipts**; parent: one Chrome job/company memory main issue; band 4: Explicit application writes; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-19"></a>

#### EXT-19 — Expose guarded visit, apply and forget routes

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Mutation API\
**Execution position:** 19/50; band 4/10 — Explicit application writes; group step 4/5.

##### Goal — what to complete

Expose `/visit`, `/apply`, `DELETE /visits` with literal confirmation and account guard.

##### Why this exists

Expose `/visit`, `/apply`, `DELETE /visits` with literal confirmation and account guard. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-10](#ext-10), [EXT-18](#ext-18) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/lifecycle.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contacts.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_lifecycle_mutations.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `backend/app/browser_memory_schemas.py` — PROPOSED; supplied by EXT-07 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_api.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md, api_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Add POST /visit, POST /apply and DELETE /visits with cookie ownership and strict schemas.
- Require connected-account assertion, exact trusted Origin, fixed browser header and apply UUID before mutation; use caller-owned commit/rollback and map safe errors.
- Enforce the documented per-account attempt policies on these routes using persistent counters; EXT-21 adds adversarial/cross-process verification, not a period of publicly unguarded writes.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/browser_memory.py` | PROPOSED; supplied by EXT-04 before use | Task-owned implementation/configuration boundary |
| `backend/app/browser_memory_schemas.py` | PROPOSED; supplied by EXT-07 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_api.py` | PROPOSED; supplied by EXT-04 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Account locks/unique owner identities and caller-owned transactions apply; no independent child commit.

##### API / event / cache / integration contracts

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

`DELETE /crm/browser-memory/visits`, no body, explicit popup confirmation → `200 {protocol_version:1,account_id:int,deleted:int}`. Only job_visits of the cookie owner are deleted; repeat returns zero. Retain JobTrack/application evidence, UrlHistory and CsvRow.clicked. Older user-selected backup may restore forgotten visits. `Open in JobGrid` uses only the selected exact trusted origin and validated returned application ID; never accept an arbitrary destination/return URL.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-19.01** — Add POST /visit, POST /apply and DELETE /visits with cookie ownership and strict schemas.
2. **EXT-19.02** — Require connected-account assertion, exact trusted Origin, fixed browser header and apply UUID before mutation; use caller-owned commit/rollback and map safe errors.
3. **EXT-19.03** — Enforce the documented per-account attempt policies on these routes using persistent counters; EXT-21 adds adversarial/cross-process verification, not a period of publicly unguarded writes.
4. **EXT-19.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_19_case_01` — First/repeated visits and applies return the frozen 200 response shapes; forget returns the actual own deleted count.
- `ext_19_case_02` — Missing confirmation/key/browser header or invalid JSON fails safely; mismatched expected account returns account_changed before any receipt lookup/write.
- `ext_19_case_03` — Foreign owner fields, untrusted origin and unauthenticated calls reveal no private data; injected error leaves no partial write.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_api.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Call all three endpoints with one valid disposable session, then repeat with the other expected-account ID and an untrusted Origin.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] First/repeated visits and applies return the frozen 200 response shapes; forget returns the actual own deleted count.
- [ ] Missing confirmation/key/browser header or invalid JSON fails safely; mismatched expected account returns account_changed before any receipt lookup/write.
- [ ] Foreign owner fields, untrusted origin and unauthenticated calls reveal no private data; injected error leaves no partial write.
- [ ] Every numbered EXT-19 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not deploy an unguarded intermediate route. If persistent enforcement cannot be reused, keep routes unregistered until EXT-21 resolves it. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not deploy an unguarded intermediate route. If persistent enforcement cannot be reused, keep routes unregistered until EXT-21 resolves it.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-19 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[19/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-19`; title: **Expose guarded visit, apply and forget routes**; parent: one Chrome job/company memory main issue; band 4: Explicit application writes; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-20"></a>

#### EXT-20 — Prove concurrent application writes and lost responses

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Concurrency tests\
**Execution position:** 20/50; band 4/10 — Explicit application writes; group step 5/5.

##### Goal — what to complete

Prove concurrent apply and lost-response retry across supported databases.

##### Why this exists

Prove concurrent apply and lost-response retry across supported databases. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-19](#ext-19) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/routers/crm.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/lifecycle.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contacts.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_lifecycle_mutations.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_apply.py` — PROPOSED; supplied by EXT-16 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_application_memory.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Use two independent sessions/connections and a barrier for the same owner/job; include different valid request keys and canonical variants.
- Inject failure after event creation but before commit, then retry through the public API.
- Run SQLite and PostgreSQL independently and assert first timestamp, track identity, events and receipt outcomes from fresh sessions.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/tests/test_browser_memory_apply.py` | PROPOSED; supplied by EXT-16 before use | Task-owned regression/fixture |
| `backend/tests/test_application_memory.py` | EXISTS at planning baseline | Task-owned regression/fixture |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-20.01** — Use two independent sessions/connections and a barrier for the same owner/job; include different valid request keys and canonical variants.
2. **EXT-20.02** — Inject failure after event creation but before commit, then retry through the public API.
3. **EXT-20.03** — Run SQLite and PostgreSQL independently and assert first timestamp, track identity, events and receipt outcomes from fresh sessions.
4. **EXT-20.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_20_case_01` — Concurrent same-job confirmation commits exactly one applicable track and first-applied event; responses resolve the same durable application.
- `ext_20_case_02` — Canonical already-applied retry preserves original time/status without a duplicate or synthetic visit.
- `ext_20_case_03` — Late rollback produces zero partial event/receipt success; lost-response retry returns the original result.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_apply.py tests/test_application_memory.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run the concurrent fixture against disposable PostgreSQL and preserve expected/actual counts; SQLite success alone is not concurrency proof.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Concurrent same-job confirmation commits exactly one applicable track and first-applied event; responses resolve the same durable application.
- [ ] Canonical already-applied retry preserves original time/status without a duplicate or synthetic visit.
- [ ] Late rollback produces zero partial event/receipt success; lost-response retry returns the original result.
- [ ] Every numbered EXT-20 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

A PostgreSQL skip is pending evidence, not a pass. Do not delete duplicate history to make assertions green. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- A PostgreSQL skip is pending evidence, not a pass. Do not delete duplicate history to make assertions green.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-20 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

None — regression assertions only; no runtime/setup behavior change. Record that reason in the main issue; a discovered runtime fix needs its own bounded scope.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[20/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-20`; title: **Prove concurrent application writes and lost responses**; parent: one Chrome job/company memory main issue; band 4: Explicit application writes; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-21"></a>

#### EXT-21 — Verify shared rate enforcement and account-switch safety

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Security and limits\
**Execution position:** 21/50; band 5/10 — Security and recovery; group step 1/5.

##### Goal — what to complete

Enforce per-account shared rate windows and exact write Origin/header checks.

##### Why this exists

Enforce per-account shared rate windows and exact write Origin/header checks. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-19](#ext-19) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/import_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backup_sessions.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory.py` — PROPOSED; supplied by EXT-08 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_security.py` — PROPOSED NEW in EXT-21; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md, api_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Use the existing RequestWindowCounter pattern with separate check/visit/apply/forget scopes and fixed minute/hour windows.
- Exercise rejects across independent app/database sessions, including failed authenticated validation attempts and limiter-storage errors.
- Verify expected account, exact Origin and browser header at the transaction boundary; expose only aggregate action/outcome/latency diagnostics.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/routers/browser_memory.py` | PROPOSED; supplied by EXT-04 before use | Task-owned implementation/configuration boundary |
| `backend/app/services/browser_memory.py` | PROPOSED; supplied by EXT-08 before use | Task-owned implementation/configuration boundary |
| `backend/tests/test_browser_memory_security.py` | PROPOSED NEW in EXT-21 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

Use existing JobTrack and lifecycle records; browser_apply_receipts and job_visits come from EXT-06, not another migration. Account locks/unique owner identities and caller-owned transactions apply; no independent child commit.

##### API / event / cache / integration contracts

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-21.01** — Use the existing RequestWindowCounter pattern with separate check/visit/apply/forget scopes and fixed minute/hour windows.
2. **EXT-21.02** — Exercise rejects across independent app/database sessions, including failed authenticated validation attempts and limiter-storage errors.
3. **EXT-21.03** — Verify expected account, exact Origin and browser header at the transaction boundary; expose only aggregate action/outcome/latency diagnostics.
4. **EXT-21.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_21_case_01` — Attempt 121 check, 61 visit, 21 apply or 6 forget within its window returns 429 with Retry-After; A cannot consume B limits.
- `ext_21_case_02` — Counter enforcement survives independent process/session use; rejected authenticated attempts count and storage outage returns 503.
- `ext_21_case_03` — Switch cookie account after session check but before write: account_changed and zero writes/receipt disclosure to either account.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_security.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run at-limit/next-attempt calls with a frozen clock; switch the session between check and confirmation and inspect both accounts.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Attempt 121 check, 61 visit, 21 apply or 6 forget within its window returns 429 with Retry-After; A cannot consume B limits.
- [ ] Counter enforcement survives independent process/session use; rejected authenticated attempts count and storage outage returns 503.
- [ ] Switch cookie account after session check but before write: account_changed and zero writes/receipt disclosure to either account.
- [ ] Every numbered EXT-21 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No process-local-only counter, wildcard Origin exception or production auth bypass is acceptable. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No process-local-only counter, wildcard Origin exception or production auth bypass is acceptable.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-21 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[21/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-21`; title: **Verify shared rate enforcement and account-switch safety**; parent: one Chrome job/company memory main issue; band 5: Security and recovery; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-22"></a>

#### EXT-22 — Define portable visit backup metadata and inventory

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Backup schema\
**Execution position:** 22/50; band 5/10 — Security and recovery; group step 2/5.

##### Goal — what to complete

Define optional `job_visits_v1` schema/checksum and inventory classification.

##### Why this exists

Define optional `job_visits_v1` schema/checksum and inventory classification. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-06](#ext-06) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/import_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backup_sessions.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/contact_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/browser_memory_backup_schemas.py` — PROPOSED NEW in EXT-22; inspect current behavior/fixtures if present.
- `backend/tests/test_backup_contract.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Add optional checksummed job_visits_v1 extension schema with version=1, portable refs, canonical URL/hash and first_visited_at.
- Classify all visit fields as recoverable and all receipt fields as operationally excluded in inventory.
- Validate duplicate refs, hashes, timestamps and maximum 10,000 entries before any restore writer receives them.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/backup_schemas.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/app/browser_memory_backup_schemas.py` | PROPOSED NEW in EXT-22 | Task-owned implementation/configuration boundary |
| `backend/tests/test_backup_contract.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

job_visits is recoverable product data; browser_apply_receipts/session/rate state is excluded. No new schema migration; destination owner is never copied from an export. Export/schema work writes no application data.

##### API / event / cache / integration contracts

Optional top-level `job_visits_v1` extension: `{schema_revision:1,visits:[{backup_ref:UUID,canonical_url:string,canonical_url_hash:string(64),first_visited_at:UTC}],checksum_sha256:string(64)}`. No source IDs or owner IDs. Canonical bytes use sorted keys, compact separators, UTF-8, allow_nan=false; checksum SHA-256 signs the extension with checksum_sha256 omitted, matching existing composed extension practice. Version exactly integer1; unknown fields/version, invalid refs/time/hash/canonical identity or conflicting duplicates reject before writes. <=10,000 visits and existing complete-backup aggregate record/byte limits still apply. Missing extension in legacy backup means absent visit history. Validate entire graph before caller-owned restore writes; destination owner from auth, earliest first time wins on replay/union, union>quota rejects all. Export JSON/ZIP from same snapshot, excluding cookies/settings/receipts. Old-reader safety is proven against real fixtures or an explicit capability rejection; silent dropped required visit data is not a complete restore.

NEW `job_visits`: id integer PK; user_id required FK users.id ON DELETE CASCADE; canonical_url Text required; canonical_url_hash String(64) required; first_visited_at UTC DateTime required server time; unique(user_id,canonical_url_hash), owner/time index. NEW `browser_apply_receipts`: id integer PK; user_id same owner FK/cascade; request_key String(36) UUID required; payload_hash String(64) required; response_json JSON frozen apply response required; created_at UTC DateTime required; unique(user_id,request_key), owner/time index. No source-row FK and no import-history backfill. Canonicalization version ccr-identity-1. Visits are backup product data; receipts are excluded operational state. Additive migration only; preserve existing rows/times.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-22.01** — Add optional checksummed job_visits_v1 extension schema with version=1, portable refs, canonical URL/hash and first_visited_at.
2. **EXT-22.02** — Classify all visit fields as recoverable and all receipt fields as operationally excluded in inventory.
3. **EXT-22.03** — Validate duplicate refs, hashes, timestamps and maximum 10,000 entries before any restore writer receives them.
4. **EXT-22.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_22_case_01` — A valid extension parses and a legacy backup without it remains valid with no inferred visits.
- `ext_22_case_02` — Unknown extension version, mismatched hash, duplicate conflicting canonical identity, invalid time or 10,001 entries is rejected.
- `ext_22_case_03` — Schema/model inventory reports no unclassified fields; cookies/settings/receipt response data never enter the extension.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_backup_contract.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Inspect a synthetic parsed extension and an old fixture side by side; confirm missing visit data is explicitly absent.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] A valid extension parses and a legacy backup without it remains valid with no inferred visits.
- [ ] Unknown extension version, mismatched hash, duplicate conflicting canonical identity, invalid time or 10,001 entries is rejected.
- [ ] Schema/model inventory reports no unclassified fields; cookies/settings/receipt response data never enter the extension.
- [ ] Every numbered EXT-22 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No exporter/restore mutation is owned here. A format compatibility ambiguity must be recorded before new exports are enabled. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No exporter/restore mutation is owned here. A format compatibility ambiguity must be recorded before new exports are enabled.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-22 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[22/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-22`; title: **Define portable visit backup metadata and inventory**; parent: one Chrome job/company memory main issue; band 5: Security and recovery; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-23"></a>

#### EXT-23 — Export visits consistently in JSON and ZIP backups

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Backup export\
**Execution position:** 23/50; band 5/10 — Security and recovery; group step 3/5.

##### Goal — what to complete

Compose visit metadata into JSON/ZIP exporters and enforce legacy-reader negotiation.

##### Why this exists

Compose visit metadata into JSON/ZIP exporters and enforce legacy-reader negotiation. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-22](#ext-22) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/import_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backup_sessions.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory_backup.py` — PROPOSED NEW in EXT-23; inspect current behavior/fixtures if present.
- `backend/app/main.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_complete_backup.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Compose the new visit extension through the actual final export wrappers rather than an older base exporter.
- Use one account-scoped snapshot and deterministic ordering/checksum; leave documents and other extensions intact.
- Run real legacy-reader fixtures; either prove safe optional skip or reject unsupported capability explicitly before claiming complete restore.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory_backup.py` | PROPOSED NEW in EXT-23 | Task-owned implementation/configuration boundary |
| `backend/app/main.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/tests/test_complete_backup.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `backend/app/services/import_backups.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

job_visits is recoverable product data; browser_apply_receipts/session/rate state is excluded. No new schema migration; destination owner is never copied from an export. Export/schema work writes no application data.

##### API / event / cache / integration contracts

Optional top-level `job_visits_v1` extension: `{schema_revision:1,visits:[{backup_ref:UUID,canonical_url:string,canonical_url_hash:string(64),first_visited_at:UTC}],checksum_sha256:string(64)}`. No source IDs or owner IDs. Canonical bytes use sorted keys, compact separators, UTF-8, allow_nan=false; checksum SHA-256 signs the extension with checksum_sha256 omitted, matching existing composed extension practice. Version exactly integer1; unknown fields/version, invalid refs/time/hash/canonical identity or conflicting duplicates reject before writes. <=10,000 visits and existing complete-backup aggregate record/byte limits still apply. Missing extension in legacy backup means absent visit history. Validate entire graph before caller-owned restore writes; destination owner from auth, earliest first time wins on replay/union, union>quota rejects all. Export JSON/ZIP from same snapshot, excluding cookies/settings/receipts. Old-reader safety is proven against real fixtures or an explicit capability rejection; silent dropped required visit data is not a complete restore.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-23.01** — Compose the new visit extension through the actual final export wrappers rather than an older base exporter.
2. **EXT-23.02** — Use one account-scoped snapshot and deterministic ordering/checksum; leave documents and other extensions intact.
3. **EXT-23.03** — Run real legacy-reader fixtures; either prove safe optional skip or reject unsupported capability explicitly before claiming complete restore.
4. **EXT-23.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_23_case_01` — JSON and ZIP export identical visit metadata/count/checksum for the same fixture snapshot.
- `ext_23_case_02` — Foreign visits, receipt tables and browser state are excluded while existing contact/import/document sections remain present.
- `ext_23_case_03` — Legacy-reader case yields a tested explicit compatibility outcome; silent dropped visit history is not called complete.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_complete_backup.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Export the same synthetic account as JSON and ZIP; open only metadata locally and compare visit hashes and existing sections.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] JSON and ZIP export identical visit metadata/count/checksum for the same fixture snapshot.
- [ ] Foreign visits, receipt tables and browser state are excluded while existing contact/import/document sections remain present.
- [ ] Legacy-reader case yields a tested explicit compatibility outcome; silent dropped visit history is not called complete.
- [ ] Every numbered EXT-23 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not register the new exporter in production until legacy compatibility and matching restore support are accepted. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not register the new exporter in production until legacy compatibility and matching restore support are accepted.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-23 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[23/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-23`; title: **Export visits consistently in JSON and ZIP backups**; parent: one Chrome job/company memory main issue; band 5: Security and recovery; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-24"></a>

#### EXT-24 — Restore visits atomically with the composed backup

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Backup restore\
**Execution position:** 24/50; band 5/10 — Security and recovery; group step 4/5.

##### Goal — what to complete

Preflight and restore visits within existing caller transaction.

##### Why this exists

Preflight and restore visits within existing caller transaction. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-23](#ext-23) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/import_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backup_sessions.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/browser_memory_backup.py` — PROPOSED; supplied by EXT-23 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_complete_backup.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Preflight the full extension/checksum/references and recompute canonical hashes before writing.
- Join backup_sessions caller transaction; map ownership to destination and merge the earliest first visit under quota.
- Reject union over 10,000 or invalid late extension atomically; do not restore operational apply receipts or replay application lifecycle events.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/app/services/browser_memory_backup.py` | PROPOSED; supplied by EXT-23 before use | Task-owned implementation/configuration boundary |
| `backend/app/services/backup_sessions.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `backend/tests/test_complete_backup.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `backend/app/services/import_backups.py` | EXISTS at planning baseline | Task-owned implementation/configuration boundary |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

job_visits is recoverable product data; browser_apply_receipts/session/rate state is excluded. No new schema migration; destination owner is never copied from an export. This ticket may restore/delete only its explicitly owned data.

##### API / event / cache / integration contracts

Optional top-level `job_visits_v1` extension: `{schema_revision:1,visits:[{backup_ref:UUID,canonical_url:string,canonical_url_hash:string(64),first_visited_at:UTC}],checksum_sha256:string(64)}`. No source IDs or owner IDs. Canonical bytes use sorted keys, compact separators, UTF-8, allow_nan=false; checksum SHA-256 signs the extension with checksum_sha256 omitted, matching existing composed extension practice. Version exactly integer1; unknown fields/version, invalid refs/time/hash/canonical identity or conflicting duplicates reject before writes. <=10,000 visits and existing complete-backup aggregate record/byte limits still apply. Missing extension in legacy backup means absent visit history. Validate entire graph before caller-owned restore writes; destination owner from auth, earliest first time wins on replay/union, union>quota rejects all. Export JSON/ZIP from same snapshot, excluding cookies/settings/receipts. Old-reader safety is proven against real fixtures or an explicit capability rejection; silent dropped required visit data is not a complete restore.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-24.01** — Preflight the full extension/checksum/references and recompute canonical hashes before writing.
2. **EXT-24.02** — Join backup_sessions caller transaction; map ownership to destination and merge the earliest first visit under quota.
3. **EXT-24.03** — Reject union over 10,000 or invalid late extension atomically; do not restore operational apply receipts or replay application lifecycle events.
4. **EXT-24.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_24_case_01` — Valid restore into another account preserves canonical visit facts with destination ownership and replay chooses earliest timestamp.
- `ext_24_case_02` — Invalid late extension or union over quota leaves every affected table unchanged from a fresh connection.
- `ext_24_case_03` — Repeated restore does not duplicate visits or first-application events and legacy missing-extension backup fabricates none.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_complete_backup.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Restore rich JSON/ZIP fixtures into disposable destinations, repeat once, then attempt a malformed late section and compare full before/after state.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Valid restore into another account preserves canonical visit facts with destination ownership and replay chooses earliest timestamp.
- [ ] Invalid late extension or union over quota leaves every affected table unchanged from a fresh connection.
- [ ] Repeated restore does not duplicate visits or first-application events and legacy missing-extension backup fabricates none.
- [ ] Every numbered EXT-24 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Never independently commit a visit restore helper. Existing base/document restore recovery behavior must remain intact. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Never independently commit a visit restore helper. Existing base/document restore recovery behavior must remain intact.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-24 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[24/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-24`; title: **Restore visits atomically with the composed backup**; parent: one Chrome job/company memory main issue; band 5: Security and recovery; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-25"></a>

#### EXT-25 — Verify deletion, backup and account lifecycle boundaries

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Recovery acceptance\
**Execution position:** 25/50; band 5/10 — Security and recovery; group step 5/5.

##### Goal — what to complete

Prove source deletion, restore and account purge preserve the intended memory boundaries.

##### Why this exists

Prove source deletion, restore and account purge preserve the intended memory boundaries. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-24](#ext-24), [EXT-10](#ext-10) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `backend/app/models.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/capture.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/backup_schemas.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/import_backups.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/services/backup_sessions.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/app/routers/rows.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_visits.py` — PROPOSED; supplied by EXT-06 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_complete_backup.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `docs/BACKUP_STRATEGY.md` — EXISTS at planning baseline; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `backend_rules.md, database_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

No new screen; success/errors make only the owned backend behavior available. Later popup tasks own interactive presentation.

##### Frozen source requirements / exact scope

- Seed one source row, external visit, durable applied track and unrelated second-account records.
- Delete/archive source data, export/restore, forget visits and delete the account in separate controlled scenarios.
- Document the distinction between deleting visit memory, retained row clicks, application history and restoring an older backup.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/tests/test_browser_visits.py` | PROPOSED; supplied by EXT-06 before use | Task-owned regression/fixture |
| `backend/tests/test_complete_backup.py` | EXISTS at planning baseline | Task-owned regression/fixture |
| `docs/BACKUP_STRATEGY.md` | EXISTS at planning baseline | Current-system documentation for this task only |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

job_visits is recoverable product data; browser_apply_receipts/session/rate state is excluded. No new schema migration; destination owner is never copied from an export. This ticket may restore/delete only its explicitly owned data.

##### API / event / cache / integration contracts

Optional top-level `job_visits_v1` extension: `{schema_revision:1,visits:[{backup_ref:UUID,canonical_url:string,canonical_url_hash:string(64),first_visited_at:UTC}],checksum_sha256:string(64)}`. No source IDs or owner IDs. Canonical bytes use sorted keys, compact separators, UTF-8, allow_nan=false; checksum SHA-256 signs the extension with checksum_sha256 omitted, matching existing composed extension practice. Version exactly integer1; unknown fields/version, invalid refs/time/hash/canonical identity or conflicting duplicates reject before writes. <=10,000 visits and existing complete-backup aggregate record/byte limits still apply. Missing extension in legacy backup means absent visit history. Validate entire graph before caller-owned restore writes; destination owner from auth, earliest first time wins on replay/union, union>quota rejects all. Export JSON/ZIP from same snapshot, excluding cookies/settings/receipts. Old-reader safety is proven against real fixtures or an explicit capability rejection; silent dropped required visit data is not a complete restore.

`DELETE /crm/browser-memory/visits`, no body, explicit popup confirmation → `200 {protocol_version:1,account_id:int,deleted:int}`. Only job_visits of the cookie owner are deleted; repeat returns zero. Retain JobTrack/application evidence, UrlHistory and CsvRow.clicked. Older user-selected backup may restore forgotten visits. `Open in JobGrid` uses only the selected exact trusted origin and validated returned application ID; never accept an arbitrary destination/return URL.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-25.01** — Seed one source row, external visit, durable applied track and unrelated second-account records.
2. **EXT-25.02** — Delete/archive source data, export/restore, forget visits and delete the account in separate controlled scenarios.
3. **EXT-25.03** — Document the distinction between deleting visit memory, retained row clicks, application history and restoring an older backup.
4. **EXT-25.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_25_case_01` — Deleting the source CSV row preserves external visit and application evidence.
- `ext_25_case_02` — Forget visits removes only A job_visits; application history/legacy row-click evidence and account B remain unchanged.
- `ext_25_case_03` — Valid restore can restore forgotten visits; account deletion removes owner visits/receipts with no foreign effects.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_visits.py tests/test_complete_backup.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Follow delete-source → check → forget → check → restore → check with fresh sessions and record exact remaining evidence each time.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Deleting the source CSV row preserves external visit and application evidence.
- [ ] Forget visits removes only A job_visits; application history/legacy row-click evidence and account B remain unchanged.
- [ ] Valid restore can restore forgotten visits; account deletion removes owner visits/receipts with no foreign effects.
- [ ] Every numbered EXT-25 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Never call source-row deletion a forget-all-history feature; the UI must explain surviving facts. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- Never call source-row deletion a forget-all-history feature; the UI must explain surviving facts.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-25 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[25/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-25`; title: **Verify deletion, backup and account lifecycle boundaries**; parent: one Chrome job/company memory main issue; band 5: Security and recovery; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-26"></a>

#### EXT-26 — Build the account-bound extension command dispatcher

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Extension worker\
**Execution position:** 26/50; band 6/10 — Connection and metadata; group step 1/5.

##### Goal — what to complete

Implement selected JobGrid tab/account connection and internal command dispatcher.

##### Why this exists

Implement selected JobGrid tab/account connection and internal command dispatcher. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-05](#ext-05), [EXT-14](#ext-14), [EXT-19](#ext-19) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/config.js` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `extension/tests/bridge.test.mjs` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Extend the minimal spike worker with protocol-v1 message validation and explicit trusted JobGrid tab selection.
- Allow check/session plus popup-confirmed apply/forget and worker-derived visit commands only; a page candidate cannot request writes.
- Bind requests/responses to connected account/tab/request generation and pass fixed-route commands to the isolated JobGrid bridge.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/bridge.test.mjs` | PROPOSED; supplied by EXT-03 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

##### API / event / cache / integration contracts

Internal request `{version:1,request_id:UUID,kind:"session"|"check"|"visit"|"apply"|"forget_visits",account_id?:int,payload:object}` → `{version:1,request_id,ok:bool,data?:object,error?:{code,message,retry_after?:int}}`; max8192 UTF-8 bytes. Worker accepts apply/forget only from its own packaged popup sender. Automatic visit is worker-internal, derived from successful check + opted-in current top-frame detail navigation; page candidate may never request a write. Bridge validates own extension sender and maps only fixed routes/methods under same-origin `/api/crm/browser-memory`, credentials same-origin, fixed browser/expected-account headers on writes; no arbitrary URL/method/headers, external messaging or window relay. Response remains in worker/popup, never a job page. Version/shape/sender mismatch fails closed with a safe protocol error, no fetch. Timeout8s; response must match selected account/tab/document/URL/generation. Check account again before writing or displaying response.

`GET /crm/browser-memory/session` (bridge: `/api/crm/browser-memory/session`), cookie auth via `get_current_user`, no body → `200 {"protocol_version":1,"account_id":101,"account_label":"Pilot A"}`. Example is synthetic. Missing/expired cookie → existing auth-compatible `401 {"detail":"Not authenticated"}` / invalid-token equivalent; no session token, cookie or raw email is returned. Identity comes from the server, not a client `user_id`.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-26.01** — Extend the minimal spike worker with protocol-v1 message validation and explicit trusted JobGrid tab selection.
2. **EXT-26.02** — Allow check/session plus popup-confirmed apply/forget and worker-derived visit commands only; a page candidate cannot request writes.
3. **EXT-26.03** — Bind requests/responses to connected account/tab/request generation and pass fixed-route commands to the isolated JobGrid bridge.
4. **EXT-26.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_26_case_01` — Session/check command reaches only the explicitly selected exact-origin JobGrid tab.
- `ext_26_case_02` — Forged popup URL, external sender, subframe, extra route/header and >8192-byte messages cause zero API calls.
- `ext_26_case_03` — A job-site content script cannot invoke apply/forget or receive private matches/counts.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/bridge.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Connect with two open app tabs, choose one deliberately, and verify background does not silently choose another account.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Session/check command reaches only the explicitly selected exact-origin JobGrid tab.
- [ ] Forged popup URL, external sender, subframe, extra route/header and >8192-byte messages cause zero API calls.
- [ ] A job-site content script cannot invoke apply/forget or receive private matches/counts.
- [ ] Every numbered EXT-26 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No externally_connectable or window relay. Automatic visits originate only from the worker state machine accepted in EXT-32. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No externally_connectable or window relay. Automatic visits originate only from the worker state machine accepted in EXT-32.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-26 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[26/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-26`; title: **Build the account-bound extension command dispatcher**; parent: one Chrome job/company memory main issue; band 6: Connection and metadata; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-27"></a>

#### EXT-27 — Cancel stale requests and enforce transport timeouts

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Extension reliability\
**Execution position:** 27/50; band 6/10 — Connection and metadata; group step 2/5.

##### Goal — what to complete

Enforce account recheck, timeouts and stale-response cancellation.

##### Why this exists

Enforce account recheck, timeouts and stale-response cancellation. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-26](#ext-26) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/config.js` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/tests/bridge.test.mjs` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Capture selected account/tab/document/URL and request generation at dispatch; reject any response that no longer matches.
- Abort API fetch at 8 seconds and invalidate worker state on app-tab removal, account mismatch or malformed protocol.
- Debounce session checks to one per 5 seconds per selected tab; no keep-alive polling or silent reconnect.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/jobgrid-bridge.js` | PROPOSED; supplied by EXT-03 before use | Task-owned implementation/configuration boundary |
| `extension/tests/bridge.test.mjs` | PROPOSED; supplied by EXT-03 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

##### API / event / cache / integration contracts

Internal request `{version:1,request_id:UUID,kind:"session"|"check"|"visit"|"apply"|"forget_visits",account_id?:int,payload:object}` → `{version:1,request_id,ok:bool,data?:object,error?:{code,message,retry_after?:int}}`; max8192 UTF-8 bytes. Worker accepts apply/forget only from its own packaged popup sender. Automatic visit is worker-internal, derived from successful check + opted-in current top-frame detail navigation; page candidate may never request a write. Bridge validates own extension sender and maps only fixed routes/methods under same-origin `/api/crm/browser-memory`, credentials same-origin, fixed browser/expected-account headers on writes; no arbitrary URL/method/headers, external messaging or window relay. Response remains in worker/popup, never a job page. Version/shape/sender mismatch fails closed with a safe protocol error, no fetch. Timeout8s; response must match selected account/tab/document/URL/generation. Check account again before writing or displaying response.

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-27.01** — Capture selected account/tab/document/URL and request generation at dispatch; reject any response that no longer matches.
2. **EXT-27.02** — Abort API fetch at 8 seconds and invalidate worker state on app-tab removal, account mismatch or malformed protocol.
3. **EXT-27.03** — Debounce session checks to one per 5 seconds per selected tab; no keep-alive polling or silent reconnect.
4. **EXT-27.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_27_case_01` — Account A response arriving after switch to B is discarded and clears private UI.
- `ext_27_case_02` — URL/tab/document change before response discards old badges/results; closed app tab returns unavailable.
- `ext_27_case_03` — At 8 seconds the request resolves to safe timeout and no background retry/write occurs.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/bridge.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Delay a synthetic API response, navigate to another job and switch account before releasing it; verify the old warning never appears.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Account A response arriving after switch to B is discarded and clears private UI.
- [ ] URL/tab/document change before response discards old badges/results; closed app tab returns unavailable.
- [ ] At 8 seconds the request resolves to safe timeout and no background retry/write occurs.
- [ ] Every numbered EXT-27 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not reuse cached private results after reconnect. A failed transport cannot become No recorded application. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not reuse cached private results after reconnect. A failed transport cannot become No recorded application.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-27 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[27/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-27`; title: **Cancel stale requests and enforce transport timeouts**; parent: one Chrome job/company memory main issue; band 6: Connection and metadata; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-28"></a>

#### EXT-28 — Recognize only supported job-detail routes

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** URL classifier\
**Execution position:** 28/50; band 6/10 — Connection and metadata; group step 3/5.

##### Goal — what to complete

Add exact ATS detail route classifier with safe URL handling.

##### Why this exists

Add exact ATS detail route classifier with safe URL handling. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-02](#ext-02) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/config.js` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED NEW in EXT-28; inspect current behavior/fixtures if present.
- `extension/tests/site-rules.test.mjs` — PROPOSED NEW in EXT-28; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Match exact three supported HTTPS hosts and the frozen Greenhouse/Lever detail path shapes.
- Reject listing/apply/form routes, suffix-spoof hosts, private schemes and credential-like query inputs before automatic tracking.
- Return supported-site/detail identity only, not an employer identity inferred from a board slug.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/site-rules.js` | PROPOSED NEW in EXT-28 | Task-owned implementation/configuration boundary |
| `extension/tests/site-rules.test.mjs` | PROPOSED NEW in EXT-28 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

Automatic job detail patterns: HTTPS boards.greenhouse.io or job-boards.greenhouse.io `/{board}/jobs/{job_id}`, and jobs.lever.co `/{board}/{posting_id}`. No listing/apply forms, suffix-spoof hosts, subframes or unknown routes. Classifier returns supported/manual eligibility, not employer identity. Metadata candidate: `{url:string,title:string|null,company:string|null}` plus sender-derived tab/document context; title/company <=500/320; conflicting/missing public metadata → null. No form values, credentials, resume data or app history in candidate messages. Worker re-reads accessible top-level URL before trusting candidate.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-28.01** — Match exact three supported HTTPS hosts and the frozen Greenhouse/Lever detail path shapes.
2. **EXT-28.02** — Reject listing/apply/form routes, suffix-spoof hosts, private schemes and credential-like query inputs before automatic tracking.
3. **EXT-28.03** — Return supported-site/detail identity only, not an employer identity inferred from a board slug.
4. **EXT-28.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_28_case_01` — Each declared detail-route fixture qualifies and its original URL remains available for server validation.
- `ext_28_case_02` — Host suffix spoof, listing, apply route, javascript/file and token-bearing URLs do not auto-track.
- `ext_28_case_03` — Two companies using the same ATS host are not assigned the same employer by the classifier.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/site-rules.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run the positive/negative URL fixture table and inspect the reported supported/manual classification.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Each declared detail-route fixture qualifies and its original URL remains available for server validation.
- [ ] Host suffix spoof, listing, apply route, javascript/file and token-bearing URLs do not auto-track.
- [ ] Two companies using the same ATS host are not assigned the same employer by the classifier.
- [ ] Every numbered EXT-28 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

New host/path shapes require fixtures and an architect contract update, not a permissive catch-all regex. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- New host/path shapes require fixtures and an architect contract update, not a permissive catch-all regex.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-28 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[28/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-28`; title: **Recognize only supported job-detail routes**; parent: one Chrome job/company memory main issue; band 6: Connection and metadata; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-29"></a>

#### EXT-29 — Extract public editable job metadata without form access

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Page metadata\
**Execution position:** 29/50; band 6/10 — Connection and metadata; group step 4/5.

##### Goal — what to complete

Extract editable public title/company candidates without reading forms.

##### Why this exists

Extract editable public title/company candidates without reading forms. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-28](#ext-28) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/config.js` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/job-page.js` — PROPOSED NEW in EXT-29; inspect current behavior/fixtures if present.
- `extension/tests/fixtures/job-pages.html` — PROPOSED NEW in EXT-29; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Read bounded public JobPosting JSON-LD or unambiguous displayed job title/employer from the top-level detail page.
- Prefer one unambiguous employer; keep missing/conflicting metadata null and let the popup ask the user.
- Send metadata candidate and actual tab context only; never read input/textarea/select values, application answers or credentials.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/job-page.js` | PROPOSED NEW in EXT-29 | Task-owned implementation/configuration boundary |
| `extension/tests/fixtures/job-pages.html` | PROPOSED NEW in EXT-29 | Task-owned regression/fixture |
| `frontend/tests/extension.spec.ts` | PROPOSED; supplied by EXT-05 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

Automatic job detail patterns: HTTPS boards.greenhouse.io or job-boards.greenhouse.io `/{board}/jobs/{job_id}`, and jobs.lever.co `/{board}/{posting_id}`. No listing/apply forms, suffix-spoof hosts, subframes or unknown routes. Classifier returns supported/manual eligibility, not employer identity. Metadata candidate: `{url:string,title:string|null,company:string|null}` plus sender-derived tab/document context; title/company <=500/320; conflicting/missing public metadata → null. No form values, credentials, resume data or app history in candidate messages. Worker re-reads accessible top-level URL before trusting candidate.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-29.01** — Read bounded public JobPosting JSON-LD or unambiguous displayed job title/employer from the top-level detail page.
2. **EXT-29.02** — Prefer one unambiguous employer; keep missing/conflicting metadata null and let the popup ask the user.
3. **EXT-29.03** — Send metadata candidate and actual tab context only; never read input/textarea/select values, application answers or credentials.
4. **EXT-29.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_29_case_01` — Known synthetic JobPosting metadata produces the expected title/company candidate.
- `ext_29_case_02` — Multiple conflicting employers, malformed/oversized JSON-LD and missing company produce unknown without script execution.
- `ext_29_case_03` — Hostile markup renders as text; form-secret fixture values never appear in messages or logs.

```bash

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Load the synthetic job-pages fixture with a hidden fake form secret and compare outgoing metadata to an explicit allowlist.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Known synthetic JobPosting metadata produces the expected title/company candidate.
- [ ] Multiple conflicting employers, malformed/oversized JSON-LD and missing company produce unknown without script execution.
- [ ] Hostile markup renders as text; form-secret fixture values never appear in messages or logs.
- [ ] Every numbered EXT-29 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not fetch ATS APIs or inject history into the job page. An ambiguous employer remains Company unknown. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not fetch ATS APIs or inject history into the job page. An ambiguous employer remains Company unknown.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-29 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[29/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-29`; title: **Extract public editable job metadata without form access**; parent: one Chrome job/company memory main issue; band 6: Connection and metadata; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-30"></a>

#### EXT-30 — Enable site scripts only after host permission consent

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Permissions\
**Execution position:** 30/50; band 6/10 — Connection and metadata; group step 5/5.

##### Goal — what to complete

Register/unregister scripts per granted host and site opt-in.

##### Why this exists

Register/unregister scripts per granted host and site opt-in. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-27](#ext-27), [EXT-29](#ext-29) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/config.js` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.
- `extension/manifest.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/tests/bridge.test.mjs` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Request an optional supported-host grant only from a site-enable gesture; persist its opt-in separately from permission existence.
- Dynamically register the top-frame page script only for enabled granted hosts and unregister on disable/revoke.
- Keep install default off and keep unknown sites manual/current-tab only.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/manifest.json` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `extension/tests/bridge.test.mjs` | PROPOSED; supplied by EXT-03 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

MV3 required permissions storage/activeTab/scripting; optional hosts only boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co and exact selected JobGrid origin. No tabs/history/cookies/<all_urls>/externally_connectable. Grant via user gesture, then independent per-site opt-in; defaults off. Register content script dynamically in top frame only; revoke/disable unregisters and stops collection. Dev manifest `extension/manifest.dev.json` may allow localhost; release artifact must exclude it. Public exact origins only, no arbitrary API host input. Native ES modules, packaged scripts, no inline/eval/remote executable code.

Automatic job detail patterns: HTTPS boards.greenhouse.io or job-boards.greenhouse.io `/{board}/jobs/{job_id}`, and jobs.lever.co `/{board}/{posting_id}`. No listing/apply forms, suffix-spoof hosts, subframes or unknown routes. Classifier returns supported/manual eligibility, not employer identity. Metadata candidate: `{url:string,title:string|null,company:string|null}` plus sender-derived tab/document context; title/company <=500/320; conflicting/missing public metadata → null. No form values, credentials, resume data or app history in candidate messages. Worker re-reads accessible top-level URL before trusting candidate.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-30.01** — Request an optional supported-host grant only from a site-enable gesture; persist its opt-in separately from permission existence.
2. **EXT-30.02** — Dynamically register the top-frame page script only for enabled granted hosts and unregister on disable/revoke.
3. **EXT-30.03** — Keep install default off and keep unknown sites manual/current-tab only.
4. **EXT-30.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_30_case_01` — Denied permission results in no registration, collection or API write.
- `ext_30_case_02` — Granted-but-not-enabled site stays off; enabled+granted detail site registers exactly once.
- `ext_30_case_03` — Revoking access unregisters/stops subsequent navigation collection and clears associated badges.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/bridge.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Enable one supported site, deny another, then revoke the first in Chrome settings and navigate both.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Denied permission results in no registration, collection or API write.
- [ ] Granted-but-not-enabled site stays off; enabled+granted detail site registers exactly once.
- [ ] Revoking access unregisters/stops subsequent navigation collection and clears associated badges.
- [ ] Every numbered EXT-30 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Never request all hosts to fix a denied optional permission; make the missing permission visible. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Never request all hosts to fix a denied optional permission; make the missing permission visible.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-30 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[30/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-30`; title: **Enable site scripts only after host permission consent**; parent: one Chrome job/company memory main issue; band 6: Connection and metadata; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-31"></a>

#### EXT-31 — Check once for each qualifying top-level navigation

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Navigation worker\
**Execution position:** 31/50; band 7/10 — Navigation and visit transport; group step 1/5.

##### Goal — what to complete

Trigger one check on qualifying top-level navigation with 500 ms debounce.

##### Why this exists

Trigger one check on qualifying top-level navigation with 500 ms debounce. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-30](#ext-30) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED; supplied by EXT-28 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/tests/navigation.test.mjs` — PROPOSED NEW in EXT-31; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Use permitted tab/page notifications to identify top-level detail navigation and same-document SPA URL changes.
- Debounce by 500 ms and coalesce one in-flight check for a given tab/URL/document generation.
- Treat tab activation/reload/document change separately; ignore subframes, stale candidates and unsupported pages.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/navigation.test.mjs` | PROPOSED NEW in EXT-31 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

For opted-in/granted supported detail page: debounce500ms, one in-flight check per tab/URL/document generation → validate response/account → preserve pre-write facts → internal visit. Failed check = zero visit. Failed visit = retain known warning plus Visit not saved · Retry. Stale URL/document/account, paused tracking or permission revoke = cancel/ignore; no write queue. Job-page messages are candidates only. Unknown pages require popup activeTab gesture; manual check alone does not save a visit; explicit record-visit follows successful same-context check. 429 waits Retry-After and only deliberate Retry reattempts.

Automatic job detail patterns: HTTPS boards.greenhouse.io or job-boards.greenhouse.io `/{board}/jobs/{job_id}`, and jobs.lever.co `/{board}/{posting_id}`. No listing/apply forms, suffix-spoof hosts, subframes or unknown routes. Classifier returns supported/manual eligibility, not employer identity. Metadata candidate: `{url:string,title:string|null,company:string|null}` plus sender-derived tab/document context; title/company <=500/320; conflicting/missing public metadata → null. No form values, credentials, resume data or app history in candidate messages. Worker re-reads accessible top-level URL before trusting candidate.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-31.01** — Use permitted tab/page notifications to identify top-level detail navigation and same-document SPA URL changes.
2. **EXT-31.02** — Debounce by 500 ms and coalesce one in-flight check for a given tab/URL/document generation.
3. **EXT-31.03** — Treat tab activation/reload/document change separately; ignore subframes, stale candidates and unsupported pages.
4. **EXT-31.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_31_case_01` — Duplicate navigation events within 500 ms produce one check for the current job.
- `ext_31_case_02` — A SPA transition from job A to B invalidates A and checks B; repeated activation does not create writes.
- `ext_31_case_03` — Iframe/listing/unknown-route events produce no automatic check or visit.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/navigation.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Use the browser fixture to reload, switch tabs and pushState between two fixture jobs; inspect request counts and request generations.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Duplicate navigation events within 500 ms produce one check for the current job.
- [ ] A SPA transition from job A to B invalidates A and checks B; repeated activation does not create writes.
- [ ] Iframe/listing/unknown-route events produce no automatic check or visit.
- [ ] Every numbered EXT-31 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No navigation event alone is an application; do not introduce history permission or polling to capture more pages. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No navigation event alone is an application; do not introduce history permission or polling to capture more pages.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-31 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[31/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-31`; title: **Check once for each qualifying top-level navigation**; parent: one Chrome job/company memory main issue; band 7: Navigation and visit transport; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-32"></a>

#### EXT-32 — Record a visit after lookup without a false previous-visit warning

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Visit worker\
**Execution position:** 32/50; band 7/10 — Navigation and visit transport; group step 2/5.

##### Goal — what to complete

Save visit only after successful check and preserve the pre-write warning.

##### Why this exists

Save visit only after successful check and preserve the pre-write warning. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-31](#ext-31), [EXT-21](#ext-21) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED; supplied by EXT-28 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `backend/app/routers/browser_memory.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `extension/tests/navigation.test.mjs` — PROPOSED; supplied by EXT-31 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- On a valid opted-in detail navigation, complete the account-bound check before deriving an internal visit write.
- Keep the check snapshot for the displayed warning, then save visit under the same URL/document/account expectation.
- If check fails, do not write. If visit fails after a valid check, retain warnings and expose Visit not saved · Retry.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/navigation.test.mjs` | PROPOSED; supplied by EXT-31 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

For opted-in/granted supported detail page: debounce500ms, one in-flight check per tab/URL/document generation → validate response/account → preserve pre-write facts → internal visit. Failed check = zero visit. Failed visit = retain known warning plus Visit not saved · Retry. Stale URL/document/account, paused tracking or permission revoke = cancel/ignore; no write queue. Job-page messages are candidates only. Unknown pages require popup activeTab gesture; manual check alone does not save a visit; explicit record-visit follows successful same-context check. 429 waits Retry-After and only deliberate Retry reattempts.

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-32.01** — On a valid opted-in detail navigation, complete the account-bound check before deriving an internal visit write.
2. **EXT-32.02** — Keep the check snapshot for the displayed warning, then save visit under the same URL/document/account expectation.
3. **EXT-32.03** — If check fails, do not write. If visit fails after a valid check, retain warnings and expose Visit not saved · Retry.
4. **EXT-32.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_32_case_01` — First navigation displays no previous visit from its pre-write snapshot, then stores exactly one durable visit.
- `ext_32_case_02` — Revisit sees Visited before from server evidence and preserves first timestamp.
- `ext_32_case_03` — Failed lookup, changed account/document, paused tracking or revoked permission produces zero visit writes; failed save never fakes success.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/navigation.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Open a fresh fixture job, close/reopen it, then repeat with a forced check error and a forced visit error.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] First navigation displays no previous visit from its pre-write snapshot, then stores exactly one durable visit.
- [ ] Revisit sees Visited before from server evidence and preserves first timestamp.
- [ ] Failed lookup, changed account/document, paused tracking or revoked permission produces zero visit writes; failed save never fakes success.
- [ ] Every numbered EXT-32 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

The internal worker visit is authorized by validated opt-in/navigation state; content-script messages cannot supply an action flag to bypass that gate. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- The internal worker visit is authorized by validated opt-in/navigation state; content-script messages cannot supply an action flag to bypass that gate.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-32 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[32/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-32`; title: **Record a visit after lookup without a false previous-visit warning**; parent: one Chrome job/company memory main issue; band 7: Navigation and visit transport; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-33"></a>

#### EXT-33 — Check unsupported public pages only through a user gesture

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Manual fallback\
**Execution position:** 33/50; band 7/10 — Navigation and visit transport; group step 3/5.

##### Goal — what to complete

Implement current-tab gesture fallback for unsupported public pages.

##### Why this exists

Implement current-tab gesture fallback for unsupported public pages. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-28](#ext-28), [EXT-27](#ext-27) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED; supplied by EXT-28 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/tests/navigation.test.mjs` — PROPOSED; supplied by EXT-31 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- On popup invocation use activeTab to read only the current public page candidate; no permanent unknown-host monitor.
- Allow editable company/title and explicit check/record-visit actions; label the flow Manual check only.
- Validate URL and account again before every command; keep malformed/private/credential URL failures local and safe.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/site-rules.js` | PROPOSED; supplied by EXT-28 before use | Task-owned implementation/configuration boundary |
| `extension/tests/navigation.test.mjs` | PROPOSED; supplied by EXT-31 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

For opted-in/granted supported detail page: debounce500ms, one in-flight check per tab/URL/document generation → validate response/account → preserve pre-write facts → internal visit. Failed check = zero visit. Failed visit = retain known warning plus Visit not saved · Retry. Stale URL/document/account, paused tracking or permission revoke = cancel/ignore; no write queue. Job-page messages are candidates only. Unknown pages require popup activeTab gesture; manual check alone does not save a visit; explicit record-visit follows successful same-context check. 429 waits Retry-After and only deliberate Retry reattempts.

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-33.01** — On popup invocation use activeTab to read only the current public page candidate; no permanent unknown-host monitor.
2. **EXT-33.02** — Allow editable company/title and explicit check/record-visit actions; label the flow Manual check only.
3. **EXT-33.03** — Validate URL and account again before every command; keep malformed/private/credential URL failures local and safe.
4. **EXT-33.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_33_case_01` — Opening/navigating an unknown site without popup interaction sends zero check/visit messages.
- `ext_33_case_02` — A deliberate manual check sends the current validated URL with optional edited metadata, without auto-saving a visit.
- `ext_33_case_03` — An explicit record-visit can save only after successful same-context check; forbidden scheme/private/token URLs never reach server.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/navigation.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Open an unsupported synthetic job page, inspect zero background traffic, invoke popup and check, then explicitly record its visit.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Opening/navigating an unknown site without popup interaction sends zero check/visit messages.
- [ ] A deliberate manual check sends the current validated URL with optional edited metadata, without auto-saving a visit.
- [ ] An explicit record-visit can save only after successful same-context check; forbidden scheme/private/token URLs never reach server.
- [ ] Every numbered EXT-33 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Manual support is not a promise of LinkedIn/Indeed/Workday automatic detection or completed-submit recognition. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Manual support is not a promise of LinkedIn/Indeed/Workday automatic detection or completed-submit recognition.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-33 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[33/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-33`; title: **Check unsupported public pages only through a user gesture**; parent: one Chrome job/company memory main issue; band 7: Navigation and visit transport; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-34"></a>

#### EXT-34 — Bound temporary connection and unresolved apply state

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Session state\
**Execution position:** 34/50; band 7/10 — Navigation and visit transport; group step 4/5.

##### Goal — what to complete

Bound session-only pending apply state and clear it on account/disconnect changes.

##### Why this exists

Bound session-only pending apply state and clear it on account/disconnect changes. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-27](#ext-27) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED; supplied by EXT-28 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/tests/bridge.test.mjs` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Persist only site opt-ins/pause/public environment locally; store connection/request context in trusted-context-only chrome.storage.session.
- Keep at most one unresolved apply UUID+validated payload for <=24 hours, deleting it on success/disconnect/account change.
- After worker suspension require explicit reconnect and a new session/URL check; retained unknown-result context never auto-replays a mutation.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/bridge.test.mjs` | PROPOSED; supplied by EXT-03 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

##### API / event / cache / integration contracts

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-34.01** — Persist only site opt-ins/pause/public environment locally; store connection/request context in trusted-context-only chrome.storage.session.
2. **EXT-34.02** — Keep at most one unresolved apply UUID+validated payload for <=24 hours, deleting it on success/disconnect/account change.
3. **EXT-34.03** — After worker suspension require explicit reconnect and a new session/URL check; retained unknown-result context never auto-replays a mutation.
4. **EXT-34.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_34_case_01` — No account ID/job URL/company/title/request payload enters storage.local or storage.sync.
- `ext_34_case_02` — An unresolved apply survives worker suspension within the same browser session for deliberate same-key retry, then expires at 24h.
- `ext_34_case_03` — Browser restart/account change/disconnect clears connection/private results and causes no automatic apply replay.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/bridge.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Inspect extension storage after an ambiguous apply, suspend the worker and reconnect, then change account and verify private state is gone.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] No account ID/job URL/company/title/request payload enters storage.local or storage.sync.
- [ ] An unresolved apply survives worker suspension within the same browser session for deliberate same-key retry, then expires at 24h.
- [ ] Browser restart/account change/disconnect clears connection/private results and causes no automatic apply replay.
- [ ] Every numbered EXT-34 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not confuse MV3 worker suspension with browser restart; storage.session lifetime and explicit connection reset must be tested separately. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not confuse MV3 worker suspension with browser restart; storage.session lifetime and explicit connection reset must be tested separately.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-34 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[34/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-34`; title: **Bound temporary connection and unresolved apply state**; parent: one Chrome job/company memory main issue; band 7: Navigation and visit transport; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-35"></a>

#### EXT-35 — Pause tracking and invalidate tab badges safely

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Controls and lifecycle\
**Execution position:** 35/50; band 7/10 — Navigation and visit transport; group step 5/5.

##### Goal — what to complete

Add pause/disconnect lifecycle and per-tab badge invalidation.

##### Why this exists

Add pause/disconnect lifecycle and per-tab badge invalidation. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-32](#ext-32), [EXT-34](#ext-34) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/site-rules.js` — PROPOSED; supplied by EXT-28 before use; inspect current behavior/fixtures if present.
- `extension/jobgrid-bridge.js` — PROPOSED; supplied by EXT-03 before use; inspect current behavior/fixtures if present.
- `extension/tests/navigation.test.mjs` — PROPOSED; supplied by EXT-31 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Implement paused/disconnected state as a gate before every automatic check/visit.
- Clear or replace tab-specific badge/context on navigation, permission revocation and detected logout; use text/icon states in the popup.
- Disconnect clears connection/private session state; reconnection requires user choice and fresh session checks with no queued writes.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/navigation.test.mjs` | PROPOSED; supplied by EXT-31 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

##### API / event / cache / integration contracts

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

For opted-in/granted supported detail page: debounce500ms, one in-flight check per tab/URL/document generation → validate response/account → preserve pre-write facts → internal visit. Failed check = zero visit. Failed visit = retain known warning plus Visit not saved · Retry. Stale URL/document/account, paused tracking or permission revoke = cancel/ignore; no write queue. Job-page messages are candidates only. Unknown pages require popup activeTab gesture; manual check alone does not save a visit; explicit record-visit follows successful same-context check. 429 waits Retry-After and only deliberate Retry reattempts.

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-35.01** — Implement paused/disconnected state as a gate before every automatic check/visit.
2. **EXT-35.02** — Clear or replace tab-specific badge/context on navigation, permission revocation and detected logout; use text/icon states in the popup.
3. **EXT-35.03** — Disconnect clears connection/private session state; reconnection requires user choice and fresh session checks with no queued writes.
4. **EXT-35.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_35_case_01` — Paused navigation makes zero automatic API calls and a resume does not replay old navigations.
- `ext_35_case_02` — Job/account change clears the previous tab warning; detected logout at next session check shows sign-in.
- `ext_35_case_03` — Disconnect removes pending private state and never deletes server application history.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/navigation.test.mjs
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Pause while navigating two jobs, resume on a fresh job, then revoke access and disconnect; inspect request history and each tab badge.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Paused navigation makes zero automatic API calls and a resume does not replay old navigations.
- [ ] Job/account change clears the previous tab warning; detected logout at next session check shows sign-in.
- [ ] Disconnect removes pending private state and never deletes server application history.
- [ ] Every numbered EXT-35 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No push-logout detection promise or keepalive polling is added; server rejects stale account assertions on writes. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No push-logout detection promise or keepalive polling is added; server rejects stale account assertions on writes.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-35 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[35/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-35`; title: **Pause tracking and invalidate tab badges safely**; parent: one Chrome job/company memory main issue; band 7: Navigation and visit transport; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-36"></a>

#### EXT-36 — Render concise independent history facts in the popup

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Popup UI\
**Execution position:** 36/50; band 8/10 — Popup and controls; group step 1/5.

##### Goal — what to complete

Render check/loading/visited/applied/company/possible states with safe text.

##### Why this exists

Render check/loading/visited/applied/company/possible states with safe text. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-26](#ext-26), [EXT-33](#ext-33) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.js` — PROPOSED NEW in EXT-36; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/popup.css` — PROPOSED NEW in EXT-36; inspect current behavior/fixtures if present.
- `extension/tests/popup.test.mjs` — PROPOSED NEW in EXT-36; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Create safe popup markup/script/styles for checking, applied, possible, company, visit and successful no-record states.
- Use the frozen priority order, independent facts, locale display dates and UTC detail; display unknown employer honestly.
- Render server/page text using textContent and bound displayed matches to the server limit; use no innerHTML or remote scripts.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/popup.html` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `extension/popup.js` | PROPOSED NEW in EXT-36 | Task-owned implementation/configuration boundary |
| `extension/popup.css` | PROPOSED NEW in EXT-36 | Task-owned implementation/configuration boundary |
| `extension/tests/popup.test.mjs` | PROPOSED NEW in EXT-36 | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-36.01** — Create safe popup markup/script/styles for checking, applied, possible, company, visit and successful no-record states.
2. **EXT-36.02** — Use the frozen priority order, independent facts, locale display dates and UTC detail; display unknown employer honestly.
3. **EXT-36.03** — Render server/page text using textContent and bound displayed matches to the server limit; use no innerHTML or remote scripts.
4. **EXT-36.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_36_case_01` — Applied warning precedes possible/company/visit facts; multiple true facts remain visible.
- `ext_36_case_02` — No recorded application appears only for a successful complete lookup, never for null/failed data.
- `ext_36_case_03` — A malicious title/company is inert text, date/null formatting is stable, and history is visible only inside the extension.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/popup.test.mjs

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Open the popup against each fixed response fixture and compare exact short copy, order and UTC date details.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Applied warning precedes possible/company/visit facts; multiple true facts remain visible.
- [ ] No recorded application appears only for a successful complete lookup, never for null/failed data.
- [ ] A malicious title/company is inert text, date/null formatting is stable, and history is visible only inside the extension.
- [ ] Every numbered EXT-36 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not add an application dashboard or inject private history into job pages. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not add an application dashboard or inject private history into job pages.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-36 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[36/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-36`; title: **Render concise independent history facts in the popup**; parent: one Chrome job/company memory main issue; band 8: Popup and controls; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-37"></a>

#### EXT-37 — Render honest unavailable and partial lookup states

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Popup failure UX\
**Execution position:** 37/50; band 8/10 — Popup and controls; group step 2/5.

##### Goal — what to complete

Render partial/offline/401/403/429/timeout/unsupported states honestly.

##### Why this exists

Render partial/offline/401/403/429/timeout/unsupported states honestly. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-36](#ext-36), [EXT-32](#ext-32) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.js` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/tests/popup.test.mjs` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Distinguish partial lookup, offline, timeout, sign-in, unsupported/manual and quota/permission states.
- Keep definite existing matches on a partial lookup but never imply clearance; preserve successful warnings when only visit-save failed.
- Provide deliberate Retry and honor Retry-After without a background request loop.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/popup.js` | PROPOSED; supplied by EXT-36 before use | Task-owned implementation/configuration boundary |
| `extension/tests/popup.test.mjs` | PROPOSED; supplied by EXT-36 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-37.01** — Distinguish partial lookup, offline, timeout, sign-in, unsupported/manual and quota/permission states.
2. **EXT-37.02** — Keep definite existing matches on a partial lookup but never imply clearance; preserve successful warnings when only visit-save failed.
3. **EXT-37.03** — Provide deliberate Retry and honor Retry-After without a background request loop.
4. **EXT-37.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_37_case_01` — lookup_complete=false retains definite applied evidence and never shows No recorded application.
- `ext_37_case_02` — 401/403/timeout/offline produce the appropriate safe sign-in/unavailable state without stale private account history.
- `ext_37_case_03` — 429 disables early Retry until Retry-After; visit-write failure shows Visit not saved rather than Saved.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/popup.test.mjs

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Inject each transport/status response into the popup fixture and verify copy, enabled controls and request count after Retry.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] lookup_complete=false retains definite applied evidence and never shows No recorded application.
- [ ] 401/403/timeout/offline produce the appropriate safe sign-in/unavailable state without stale private account history.
- [ ] 429 disables early Retry until Retry-After; visit-write failure shows Visit not saved rather than Saved.
- [ ] Every numbered EXT-37 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No raw backend exception/provider response reaches the UI. Do not hide operational failure as an empty result. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No raw backend exception/provider response reaches the UI. Do not hide operational failure as an empty result.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-37 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[37/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-37`; title: **Render honest unavailable and partial lookup states**; parent: one Chrome job/company memory main issue; band 8: Popup and controls; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-38"></a>

#### EXT-38 — Require deliberate account and job confirmation before applying

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Popup confirmation\
**Execution position:** 38/50; band 8/10 — Popup and controls; group step 3/5.

##### Goal — what to complete

Add editable employer/title and one explicit account/URL confirmation before apply.

##### Why this exists

Add editable employer/title and one explicit account/URL confirmation before apply. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-36](#ext-36), [EXT-19](#ext-19) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.js` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `backend/app/browser_memory_schemas.py` — PROPOSED; supplied by EXT-07 before use; inspect current behavior/fixtures if present.
- `extension/tests/popup.test.mjs` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Add editable company/title fields with limits and display the exact URL/connected account before confirmation.
- Show duplicate/company context; exact/canonical applied evidence offers Open in JobGrid while a different role can still proceed.
- Dispatch apply only after literal explicit confirmation; keep applying separate from visit/check actions.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/popup.html` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `extension/popup.js` | PROPOSED; supplied by EXT-36 before use | Task-owned implementation/configuration boundary |
| `extension/tests/popup.test.mjs` | PROPOSED; supplied by EXT-36 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

Check request: `{url:string, company?:string|null, title?:string|null}`. Visit: `{url:string}`. Apply: `{url:string, company:string, title:string, confirmed:true}` plus UUID `Idempotency-Key`. Strict JSON/field allowlists; URL <=2048 characters; company <=320; title <=500; apply company/title must be nonblank and confirmation is literal boolean true. Public HTTP(S) only, no userinfo/private/loopback host; reject query keys token/access_token/auth/authorization/code/password/session/session_token case-insensitively. No server URL fetch or form input is allowed.

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-38.01** — Add editable company/title fields with limits and display the exact URL/connected account before confirmation.
2. **EXT-38.02** — Show duplicate/company context; exact/canonical applied evidence offers Open in JobGrid while a different role can still proceed.
3. **EXT-38.03** — Dispatch apply only after literal explicit confirmation; keep applying separate from visit/check actions.
4. **EXT-38.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_38_case_01` — Blank/overlong company/title prevents confirmation with an associated field error.
- `ext_38_case_02` — Check, page visit, extraction and Apply-button click on the job site produce no application command.
- `ext_38_case_03` — Possible/company warning can be explicitly acknowledged for a distinct role; known applied record is not silently resubmitted.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/popup.test.mjs

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Check a fresh job, edit employer/title, cancel once, then confirm; compare command counts and selected account/URL.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Blank/overlong company/title prevents confirmation with an associated field error.
- [ ] Check, page visit, extraction and Apply-button click on the job site produce no application command.
- [ ] Possible/company warning can be explicitly acknowledged for a distinct role; known applied record is not silently resubmitted.
- [ ] Every numbered EXT-38 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No prechecked confirmation, autofill submission or inference from a job-site success message. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No prechecked confirmation, autofill submission or inference from a job-site success message.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-38 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[38/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-38`; title: **Require deliberate account and job confirmation before applying**; parent: one Chrome job/company memory main issue; band 8: Popup and controls; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-39"></a>

#### EXT-39 — Keep popup apply retries bound to one confirmed payload

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Popup mutation state\
**Execution position:** 39/50; band 8/10 — Popup and controls; group step 4/5.

##### Goal — what to complete

Send apply once with stable session UUID/payload and recover ambiguous save result.

##### Why this exists

Send apply once with stable session UUID/payload and recover ambiguous save result. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-38](#ext-38), [EXT-34](#ext-34), [EXT-20](#ext-20) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.js` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/tests/popup.test.mjs` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Generate one UUID for the user-confirmed payload/account and disable overlapping submit gestures.
- Retain that key/payload when response is unknown; deliberate Retry uses the identical data/key after reconnection check.
- On changed fields/URL/account cancel the old intent; require fresh confirmation and never replay an old payload into another account.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/popup.js` | PROPOSED; supplied by EXT-36 before use | Task-owned implementation/configuration boundary |
| `extension/background.js` | PROPOSED; supplied by EXT-05 before use | Task-owned implementation/configuration boundary |
| `extension/tests/popup.test.mjs` | PROPOSED; supplied by EXT-36 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

Receipt key is cookie owner + apply UUID; digest uses normalized validated payload including literal confirmation. Replay returns stored response only if its owner application still exists. Prune expired receipts after 30 days inside write lock; max 10,000 active owner receipts, else 409 receipt_limit_reached. Expired receipt does not erase durable applied evidence. No independent commit, browser credential data or receipt restore. Lost response shows Save status unknown · Retry; keep same key/payload for deliberate retry only. Changed account invalidates the confirmation.

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-39.01** — Generate one UUID for the user-confirmed payload/account and disable overlapping submit gestures.
2. **EXT-39.02** — Retain that key/payload when response is unknown; deliberate Retry uses the identical data/key after reconnection check.
3. **EXT-39.03** — On changed fields/URL/account cancel the old intent; require fresh confirmation and never replay an old payload into another account.
4. **EXT-39.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_39_case_01` — Double-click produces one in-flight request; confirmed success clears pending state.
- `ext_39_case_02` — Lost response then deliberate same-key retry produces one durable application/first time and the Saved result.
- `ext_39_case_03` — Edited payload or account change cannot reuse the original key silently; ambiguous save displays status unknown until checked.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/popup.test.mjs

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Disconnect the response after server commit, reopen popup within the same session and Retry; inspect key and durable application count.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Double-click produces one in-flight request; confirmed success clears pending state.
- [ ] Lost response then deliberate same-key retry produces one durable application/first time and the Saved result.
- [ ] Edited payload or account change cannot reuse the original key silently; ambiguous save displays status unknown until checked.
- [ ] Every numbered EXT-39 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

No automatic retry queue; account_changed and application_deleted errors invalidate the old confirmation rather than creating a replacement application. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- No automatic retry queue; account_changed and application_deleted errors invalidate the old confirmation rather than creating a replacement application.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-39 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[39/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-39`; title: **Keep popup apply retries bound to one confirmed payload**; parent: one Chrome job/company memory main issue; band 8: Popup and controls; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-40"></a>

#### EXT-40 — Expose privacy controls and safe JobGrid navigation

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Popup controls\
**Execution position:** 40/50; band 8/10 — Popup and controls; group step 5/5.

##### Goal — what to complete

Add pause/disconnect/forget visit confirmation and safe Open in JobGrid link.

##### Why this exists

Add pause/disconnect/forget visit confirmation and safe Open in JobGrid link. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-35](#ext-35), [EXT-37](#ext-37), [EXT-10](#ext-10) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.js` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.
- `extension/background.js` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/tests/popup.test.mjs` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Add Pause, Disconnect and Forget visits with the frozen storage/server semantics.
- Require explicit current-account confirmation for DELETE /visits and explain that applications/row clicks/older backups may retain facts.
- Build Open in JobGrid links from the allowlisted app origin and server-validated IDs, never a supplied return URL.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `extension/popup.html` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `extension/popup.js` | PROPOSED; supplied by EXT-36 before use | Task-owned implementation/configuration boundary |
| `extension/tests/popup.test.mjs` | PROPOSED; supplied by EXT-36 before use | Task-owned regression/fixture |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No database schema change. Public metadata stays transient; server history is authoritative. Local storage contains settings only; private request state uses bounded trusted session storage.

##### API / event / cache / integration contracts

`DELETE /crm/browser-memory/visits`, no body, explicit popup confirmation → `200 {protocol_version:1,account_id:int,deleted:int}`. Only job_visits of the cookie owner are deleted; repeat returns zero. Retain JobTrack/application evidence, UrlHistory and CsvRow.clicked. Older user-selected backup may restore forgotten visits. `Open in JobGrid` uses only the selected exact trusted origin and validated returned application ID; never accept an arbitrary destination/return URL.

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-40.01** — Add Pause, Disconnect and Forget visits with the frozen storage/server semantics.
2. **EXT-40.02** — Require explicit current-account confirmation for DELETE /visits and explain that applications/row clicks/older backups may retain facts.
3. **EXT-40.03** — Build Open in JobGrid links from the allowlisted app origin and server-validated IDs, never a supplied return URL.
4. **EXT-40.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_40_case_01` — Forget cancellation makes no request; confirmed delete affects only the connected account job_visits.
- `ext_40_case_02` — Application history and source clicked state survive forget; 401/account_changed clears private UI.
- `ext_40_case_03` — Malformed or hostile app link cannot navigate outside selected trusted origin; pause/disconnect do not delete server applications.

```bash

# From repository root, after this ticket creates its named Node tests

node --test extension/tests/popup.test.mjs

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Cancel/confirm Forget, inspect remaining evidence, then Open in JobGrid and Disconnect; verify account and navigation destination.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Forget cancellation makes no request; confirmed delete affects only the connected account job_visits.
- [ ] Application history and source clicked state survive forget; 401/account_changed clears private UI.
- [ ] Malformed or hostile app link cannot navigate outside selected trusted origin; pause/disconnect do not delete server applications.
- [ ] Every numbered EXT-40 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not name this action Delete all history. Destructive application deletion stays in existing JobGrid workflows. Keep this capability disconnected until its dependent integration acceptance passes; disabling the extension/new caller retains product history.

##### Stop conditions

- Do not name this action Delete all history. Destructive application deletion stays in existing JobGrid workflows.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-40 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[40/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-40`; title: **Expose privacy controls and safe JobGrid navigation**; parent: one Chrome job/company memory main issue; band 8: Popup and controls; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-41"></a>

#### EXT-41 — Exercise the unpacked extension against the real local API

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** End-to-end acceptance\
**Execution position:** 41/50; band 9/10 — Integration acceptance; group step 1/5.

##### Goal — what to complete

Exercise unpacked extension → real local backend from a persistent Chromium profile.

##### Why this exists

Exercise unpacked extension → real local backend from a persistent Chromium profile. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-40](#ext-40), [EXT-25](#ext-25) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `frontend/playwright.config.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/fixtures.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_api.py` — PROPOSED; supplied by EXT-04 before use; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Launch the dev manifest using a disposable persistent Chromium profile, with actual local frontend/backend and two seeded accounts.
- Run first check/visit, explicit apply, canonical revisit and source-row deletion through extension commands.
- Record exact UI facts and fresh database counts; keep mocked transport tests separately labeled.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `frontend/tests/extension.spec.ts` | PROPOSED; supplied by EXT-05 before use | Task-owned regression/fixture |
| `extension/README.md` | PROPOSED; supplied by EXT-01 before use | Current-system documentation for this task only |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No production migration/write is authorized. Fixtures may create disposable A/B accounts and visits/tracks/receipts; compare persisted facts in fresh sessions and clean only disposable test state.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

`POST /crm/browser-memory/visit` consumes `{url}` → `200 {protocol_version:1,account_id:int,created:bool,first_visited_at:UTC}`. Revisit returns created false and the same first time. New remembered identity at 10,000 owner visits → `409 visit_limit_reached`; same hash/different canonical URL → `409 identity_conflict`. Write only the owner visit plus matching owned existing row clicked facts in one transaction: no new source row, JobTrack, application, synthetic open or session count. First navigation uses the pre-write check result so its just-created visit is not called previous.

`POST /crm/browser-memory/apply` consumes `{url,company,title,confirmed:true}` with UUID `Idempotency-Key` → `200 {protocol_version:1,account_id:int,application_id:int,created:bool,already_applied:bool,applied_at:UTC}`. A first explicit application creates/updates an exact never-applied track using the lifecycle writer; exact/canonical previously applied returns its ID/time/status unchanged. Possible/company-only match is never a merge target. Same key/payload replays; altered payload → 409 idempotency_conflict; deleted receipt target → 409 application_deleted. Track/event/receipt commit atomically. No CSV capture, click, synthetic open, note overwrite or advanced-status reset.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-41.01** — Launch the dev manifest using a disposable persistent Chromium profile, with actual local frontend/backend and two seeded accounts.
2. **EXT-41.02** — Run first check/visit, explicit apply, canonical revisit and source-row deletion through extension commands.
3. **EXT-41.03** — Record exact UI facts and fresh database counts; keep mocked transport tests separately labeled.
4. **EXT-41.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_41_case_01` — First visit is saved but not called previous; subsequent visit shows Visited before.
- `ext_41_case_02` — Explicit apply creates one track/event and revisit shows Already applied with unchanged time.
- `ext_41_case_03` — Deleting source row retains application/external visit; account B sees none of A private history.

```bash

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run the same walkthrough manually in Chrome with the unpacked package; record Chrome version and source revisions.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] First visit is saved but not called previous; subsequent visit shows Visited before.
- [ ] Explicit apply creates one track/event and revisit shows Already applied with unchanged time.
- [ ] Deleting source row retains application/external visit; account B sees none of A private history.
- [ ] Every numbered EXT-41 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

A standard Playwright web context without a loaded extension is not acceptance. Never use a personal browser profile or live database. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- A standard Playwright web context without a loaded extension is not acceptance. Never use a personal browser profile or live database.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-41 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[41/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-41`; title: **Exercise the unpacked extension against the real local API**; parent: one Chrome job/company memory main issue; band 9: Integration acceptance; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-42"></a>

#### EXT-42 — Prove cross-account and hostile-page boundaries

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Security acceptance\
**Execution position:** 42/50; band 9/10 — Integration acceptance; group step 2/5.

##### Goal — what to complete

Exercise two-account switch, forged messages and hostile site privacy negatives.

##### Why this exists

Exercise two-account switch, forged messages and hostile site privacy negatives. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-41](#ext-41) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `frontend/playwright.config.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/fixtures.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `backend/app/auth.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_security.py` — PROPOSED; supplied by EXT-21 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Use separate authenticated app tabs/accounts, a hostile job page and forged runtime message fixtures.
- Attempt writes through page/subframe/external sender paths and an account switch between session check and mutation.
- Inspect page DOM/messages/storage for application/company history leakage and server state for unintended writes.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `frontend/tests/extension.spec.ts` | PROPOSED; supplied by EXT-05 before use | Task-owned regression/fixture |
| `backend/tests/test_browser_memory_security.py` | PROPOSED; supplied by EXT-21 before use | Task-owned regression/fixture |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No production migration/write is authorized. Fixtures may create disposable A/B accounts and visits/tracks/receipts; compare persisted facts in fresh sessions and clean only disposable test state.

##### API / event / cache / integration contracts

Internal request `{version:1,request_id:UUID,kind:"session"|"check"|"visit"|"apply"|"forget_visits",account_id?:int,payload:object}` → `{version:1,request_id,ok:bool,data?:object,error?:{code,message,retry_after?:int}}`; max8192 UTF-8 bytes. Worker accepts apply/forget only from its own packaged popup sender. Automatic visit is worker-internal, derived from successful check + opted-in current top-frame detail navigation; page candidate may never request a write. Bridge validates own extension sender and maps only fixed routes/methods under same-origin `/api/crm/browser-memory`, credentials same-origin, fixed browser/expected-account headers on writes; no arbitrary URL/method/headers, external messaging or window relay. Response remains in worker/popup, never a job page. Version/shape/sender mismatch fails closed with a safe protocol error, no fetch. Timeout8s; response must match selected account/tab/document/URL/generation. Check account again before writing or displaying response.

New mutation requests require cookie auth, exact trusted frontend Origin, `X-JobGrid-Browser: 1`, and `X-JobGrid-Account-ID` equal to the cookie-resolved account before mutation/receipt lookup. That ID is an expectation, not owner authority. Wrong account → 409 account_changed; wrong/missing Origin/browser header → 403 origin_not_allowed; absent/invalid expected-account header → 422 invalid_browser_memory_payload. Other new errors: `{detail:{code,message,field?}}`; invalid input 422, quota/replay conflict 409, attempt limit 429 browser_memory_rate_limited with Retry-After, limiter/dependency failure 503 browser_memory_unavailable. Preserve existing session-auth 401 body. Per owner: check 120/min, visit 60/min, apply 20/min, forget 5/hour; rejected authenticated attempts count through shared persistent windows. No wildcard CORS, payload logging, token export or wrong-owner response. No success on partial failure.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-42.01** — Use separate authenticated app tabs/accounts, a hostile job page and forged runtime message fixtures.
2. **EXT-42.02** — Attempt writes through page/subframe/external sender paths and an account switch between session check and mutation.
3. **EXT-42.03** — Inspect page DOM/messages/storage for application/company history leakage and server state for unintended writes.
4. **EXT-42.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_42_case_01` — Account B receives no A matches/counts/IDs/receipt response even when guessed IDs/request keys are supplied.
- `ext_42_case_02` — A job-site script/subframe cannot trigger apply/forget, choose arbitrary fetch paths or receive private results.
- `ext_42_case_03` — Switch during apply yields account_changed and zero wrong-account writes; no cookie/form secret is exported.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_security.py -q

# PostgreSQL claims also require the isolated TEST_DATABASE_URL fixture in tests/conftest.py.

# Follow development.md section 5; do not point either database variable at live data. A skip is not a pass.

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Use the hostile fixture to attempt message injection while switching between A/B app tabs; inspect both accounts with fresh sessions.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Account B receives no A matches/counts/IDs/receipt response even when guessed IDs/request keys are supplied.
- [ ] A job-site script/subframe cannot trigger apply/forget, choose arbitrary fetch paths or receive private results.
- [ ] Switch during apply yields account_changed and zero wrong-account writes; no cookie/form secret is exported.
- [ ] Every numbered EXT-42 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Any cross-account disclosure blocks release immediately; do not weaken checks or merely hide the UI symptom. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- Any cross-account disclosure blocks release immediately; do not weaken checks or merely hide the UI symptom.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-42 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

None — regression assertions only; no runtime/setup behavior change. Record that reason in the main issue; a discovered runtime fix needs its own bounded scope.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[42/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-42`; title: **Prove cross-account and hostile-page boundaries**; parent: one Chrome job/company memory main issue; band 9: Integration acceptance; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-43"></a>

#### EXT-43 — Verify popup keyboard and accessible failure feedback

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Accessibility acceptance\
**Execution position:** 43/50; band 9/10 — Integration acceptance; group step 3/5.

##### Goal — what to complete

Exercise keyboard/screen-reader labels and every popup failure state.

##### Why this exists

Exercise keyboard/screen-reader labels and every popup failure state. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-41](#ext-41) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `frontend/playwright.config.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/fixtures.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/popup.html` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `extension/popup.css` — PROPOSED; supplied by EXT-36 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Test tab order, associated field labels, focus after confirmation/error and status live announcements.
- Exercise all loading/success/empty/error/paused/manual states without relying only on badge color.
- Verify popup at browser zoom/large text without lost controls or horizontal overflow; fix only owned markup/styles.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `frontend/tests/extension.spec.ts` | PROPOSED; supplied by EXT-05 before use | Task-owned regression/fixture |
| `extension/popup.html` | PROPOSED; supplied by EXT-02 before use | Task-owned implementation/configuration boundary |
| `extension/popup.css` | PROPOSED; supplied by EXT-36 before use | Task-owned implementation/configuration boundary |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No production migration/write is authorized. Fixtures may create disposable A/B accounts and visits/tracks/receipts; compare persisted facts in fresh sessions and clean only disposable test state.

##### API / event / cache / integration contracts

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-43.01** — Test tab order, associated field labels, focus after confirmation/error and status live announcements.
2. **EXT-43.02** — Exercise all loading/success/empty/error/paused/manual states without relying only on badge color.
3. **EXT-43.03** — Verify popup at browser zoom/large text without lost controls or horizontal overflow; fix only owned markup/styles.
4. **EXT-43.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_43_case_01` — Keyboard-only user can check, edit fields, cancel/confirm apply and access pause/disconnect/forget.
- `ext_43_case_02` — Validation identifies the field and moves/retains useful focus; asynchronous result is announced once.
- `ext_43_case_03` — 200% zoom retains readable text/action access and applied/possible/error meaning is available without color.

```bash

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium

# From frontend/, existing production build regression

npm run build
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Complete the synthetic popup workflow with keyboard and a screen reader; retain manual results separately from DOM assertions.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Keyboard-only user can check, edit fields, cancel/confirm apply and access pause/disconnect/forget.
- [ ] Validation identifies the field and moves/retains useful focus; asynchronous result is announced once.
- [ ] 200% zoom retains readable text/action access and applied/possible/error meaning is available without color.
- [ ] Every numbered EXT-43 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

Do not add an accessibility library or redesign unrelated app screens for this task. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- Do not add an accessibility library or redesign unrelated app screens for this task.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-43 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[43/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-43`; title: **Verify popup keyboard and accessible failure feedback**; parent: one Chrome job/company memory main issue; band 9: Integration acceptance; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-44"></a>

#### EXT-44 — Verify worker, offline and permission recovery

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P0\
**Type:** Lifecycle acceptance\
**Execution position:** 44/50; band 9/10 — Integration acceptance; group step 4/5.

##### Goal — what to complete

Verify worker suspension/restart, offline recovery, reload/SPA and permission revocation.

##### Why this exists

Verify worker suspension/restart, offline recovery, reload/SPA and permission revocation. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-41](#ext-41) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `frontend/playwright.config.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/fixtures.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `frontend/tests/extension.spec.ts` — PROPOSED; supplied by EXT-05 before use; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Priority: Already applied · {date}, Possible duplicate, Applied to this company · {count}, Visited before, then No recorded application only for successful complete lookup. Independent facts may coexist. Other states: Checking…, Company unknown, Sign in to JobGrid, Open JobGrid to connect, Tracking paused, Manual check only, Couldn’t check · Retry, Saving…, Saved, Visit limit reached, Visit not saved · Retry, Save status unknown · Retry. Loading disables overlapping actions; empty is a successful fact, not a network fallback. Render text only, locale display dates with UTC detail, labels/focus/live status and meaning beyond color. Never expose private facts to the job page.

##### Frozen source requirements / exact scope

- Terminate/suspend the worker, close/reopen the browser profile and simulate network loss at read/write boundaries.
- Exercise SPA changes, reload, tab closure and granted-host revocation while requests are in flight.
- Verify reconnection requires the correct account and no pending command is auto-replayed.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `frontend/tests/extension.spec.ts` | PROPOSED; supplied by EXT-05 before use | Task-owned regression/fixture |
| `extension/README.md` | PROPOSED; supplied by EXT-01 before use | Current-system documentation for this task only |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No production migration/write is authorized. Fixtures may create disposable A/B accounts and visits/tracks/receipts; compare persisted facts in fresh sessions and clean only disposable test state.

##### API / event / cache / integration contracts

storage.local: site opt-ins, pause, selected public environment only. storage.session restricted to trusted extension contexts: selected app tab/account, bounded request state and at most one unresolved apply key/payload for <=24h. No private storage.sync. Worker suspension clears active connection/results and requires deliberate reconnect + fresh session/URL verification; retained unresolved apply may be used only for deliberate same-key retry after validation. Full browser restart removes session state. Success/disconnect/account change deletes private pending state. No auto-replay, periodic polling, hidden keepalive or offline queue.

For opted-in/granted supported detail page: debounce500ms, one in-flight check per tab/URL/document generation → validate response/account → preserve pre-write facts → internal visit. Failed check = zero visit. Failed visit = retain known warning plus Visit not saved · Retry. Stale URL/document/account, paused tracking or permission revoke = cancel/ignore; no write queue. Job-page messages are candidates only. Unknown pages require popup activeTab gesture; manual check alone does not save a visit; explicit record-visit follows successful same-context check. 429 waits Retry-After and only deliberate Retry reattempts.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-44.01** — Terminate/suspend the worker, close/reopen the browser profile and simulate network loss at read/write boundaries.
2. **EXT-44.02** — Exercise SPA changes, reload, tab closure and granted-host revocation while requests are in flight.
3. **EXT-44.03** — Verify reconnection requires the correct account and no pending command is auto-replayed.
4. **EXT-44.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_44_case_01` — Worker suspension requires reconnect and fresh account/URL validation; unresolved apply can be deliberately retried without a duplicate.
- `ext_44_case_02` — Browser restart has no retained private result or auto-write; offline lookup never becomes no recorded application.
- `ext_44_case_03` — Revocation/navigation/tab closure cancels stale writes/results and clears stale badges on detection.

```bash

# From frontend/, real disposable local backend running; extension fixture must launch a persistent profile

npx playwright test tests/extension.spec.ts --project=chromium
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Use chrome://extensions service worker controls plus offline mode; reconnect deliberately and compare request log/counts.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Worker suspension requires reconnect and fresh account/URL validation; unresolved apply can be deliberately retried without a duplicate.
- [ ] Browser restart has no retained private result or auto-write; offline lookup never becomes no recorded application.
- [ ] Revocation/navigation/tab closure cancels stale writes/results and clears stale badges on detection.
- [ ] Every numbered EXT-44 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

If the installed Playwright build cannot simulate worker lifecycle faithfully, preserve a real Chrome manual gate rather than claiming a mocked pass. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- If the installed Playwright build cannot simulate worker lifecycle faithfully, preserve a real Chrome manual gate rather than claiming a mocked pass.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-44 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[44/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-44`; title: **Verify worker, offline and permission recovery**; parent: one Chrome job/company memory main issue; band 9: Integration acceptance; priority P0; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.

<a id="ext-45"></a>

#### EXT-45 — Measure bounded lookup performance and safe diagnostics

**Status:** PLANNED / not implemented; validation not run.\
**Priority:** P1\
**Type:** Performance acceptance\
**Execution position:** 45/50; band 9/10 — Integration acceptance; group step 5/5.

##### Goal — what to complete

Run timed matrix and verify bounded API/log behavior.

##### Why this exists

Run timed matrix and verify bounded API/log behavior. This ticket owns the bounded work below; later tasks retain their own delivery and release gates.

##### When to do it and dependencies

Start after [EXT-42](#ext-42), [EXT-43](#ext-43), [EXT-44](#ext-44) Accept prerequisite implementation and narrow tests on the work branch; a separate consuming branch requires merged dependencies. Local auth proof in EXT-05 gates auth-dependent work. Unavailable deployed credentials do not block independent local fixtures.

##### Estimated effort and execution size

Small–medium, one focused logical change (~2% planning weight). Run the checkpoints separately; no fixed day estimate is asserted. If a checkpoint introduces an unrelated schema, service or contract, split/revise it before widening scope.

##### Read before coding / files to inspect first

- `docs/repo_context.md` — baseline, source conventions and preserved boundaries.
- This packet’s frozen contracts below; compare with CCR-EXT-01 in section 9.4.
- `frontend/playwright.config.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `frontend/tests/fixtures.ts` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `backend/tests/conftest.py` — EXISTS at planning baseline; inspect current behavior/fixtures if present.
- `extension/manifest.dev.json` — PROPOSED; supplied by EXT-02 before use; inspect current behavior/fixtures if present.
- `backend/tests/test_browser_memory_matches.py` — PROPOSED; supplied by EXT-12 before use; inspect current behavior/fixtures if present.
- `extension/README.md` — PROPOSED; supplied by EXT-01 before use; inspect current behavior/fixtures if present.

Named Premium Product Builder rules: `frontend_rules.md, testing_rules.md, security_rules.md`. Use graph discovery/caller traces before shared-code edits. Attach current source contents, not just these paths, for a separate builder session.

##### User-facing behavior and UI states

Only the stated setup, session proof or release artifact/evidence is exposed; no unrelated application UI is added.

##### Frozen source requirements / exact scope

- Seed 10,000 visits plus the dense-company identity fixture in disposable databases and inspect indexed query plans.
- Measure 30 warm synthetic checks, calculate p95 and record Chrome/backend/environment versions; measure cold starts separately.
- Inspect actual server/extension diagnostics for forbidden cookies/payload URLs/company/title and record aggregate failures/timeouts.

Preserve: visited/imported/saved/applied are different facts; CsvRow and JobTrack IDs are different domains; private history belongs to the cookie-resolved owner.

##### Out of scope / do not change

- Other EXT tasks except the named prerequisite interfaces; unrelated backend files, source URLs, notes, historical migrations or accepted C/JG behavior.
- New auth providers/tokens, AI, paid hosting, dependencies, automated applications, broad browsing-history collection, or application-state inference.
- Issue/Linear creation, external messages, GitHub publication, provider changes, merge or store/production deployment as an automatic side effect of this local task.

##### Files to create or edit

| Exact repository-relative path | Planning snapshot state | Intended role |
|---|---|---|
| `backend/tests/test_browser_memory_matches.py` | PROPOSED; supplied by EXT-12 before use | Task-owned regression/fixture |
| `extension/README.md` | PROPOSED; supplied by EXT-01 before use | Current-system documentation for this task only |
| `docs/JOBGRID_BUILD_GUIDE.md` | EXISTS at planning baseline | Current-system documentation for this task only |

Paths are relative to `/Users/mac/Documents/Projects/CSV_Website`. A read-only inspection path is not an allowed edit. Evidence/checklist notes may update this ticket’s status/evidence lines in `development.md`; no other packet is silently changed. New runtime/test scaffolding not in this list requires an explicit packet correction before editing.

##### Data model

No production migration/write is authorized. Fixtures may create disposable A/B accounts and visits/tracks/receipts; compare persisted facts in fresh sessions and clean only disposable test state.

##### API / event / cache / integration contracts

`POST /crm/browser-memory/check` (bridge prefix `/api`) consumes `{url,company?,title?}` and returns `200 {protocol_version:1,checked_at:UTC,account_id:int,visit:{visited:bool,first_visited_at:UTC|null},matches:[{track_id:int,confidence:"exact"|"canonical"|"possible",reason:string,company:string|null,title:string|null,status:string,applied_at:UTC}],company_history_count:int,company_known:bool,lookup_complete:bool}`. UTC is RFC3339 ending in Z. Example: new synthetic URL → visit false/null, matches [], count 0; unknown employer → company_known false; no state is written. Only successful complete lookup may display No recorded application. Return <=20 matches, definite URL matches separately from the 500-candidate possible scan, ordered confidence then descending applied time/ID; cap hit means lookup_complete false. Counts include only own non-null applied_at, including archived/rejected history.

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

No additional public endpoint or event is authorized by this ticket. Referenced endpoints are consumed or asserted only within the exact scope above.

##### Validation rules and error handling

Validate the entire owned input before state changes. Apply the exact limits/error shapes in the copied contract; preserve null/false/zero distinctly. No partial success or fake Saved/No recorded application state. Roll back caller-owned writes and required events/receipts together; keep safe retry context, close owned resources and return a bounded error. For tests/docs-only tasks, assert these boundaries rather than creating unused validators.

##### Auth, permissions, security and privacy

Cookie-resolved account is authority. Expected account/header/Origin checks protect new writes; page metadata is untrusted and cannot select owner, transport destination or action. No cookies, form answers, private history or page payload URLs in logs/evidence; synthetic fixtures only. No `TEST_AUTH` production bypass. Test a second account whenever private data is read/written; permission denial must fail closed, not trigger broader grants.

##### Step-by-step implementation — how

1. **EXT-45.01** — Seed 10,000 visits plus the dense-company identity fixture in disposable databases and inspect indexed query plans.
2. **EXT-45.02** — Measure 30 warm synthetic checks, calculate p95 and record Chrome/backend/environment versions; measure cold starts separately.
3. **EXT-45.03** — Inspect actual server/extension diagnostics for forbidden cookies/payload URLs/company/title and record aggregate failures/timeouts.
4. **EXT-45.04** — Run the exact assertions below, review the scoped diff and update the owning guide/evidence. Do not start the successor until the acceptance criteria hold.

##### Required automated tests and commands

Scenario names below are **proposed assertion labels**, not a claim that matching test functions already exist. Create/extend only the named task test files; assert exact values and nonempty fixtures, never only a successful response.

- `ext_45_case_01` — Warm p95 <=2s for recorded fixture/environment; timeouts terminate at 8s and cold starts are not mixed into warm samples.
- `ext_45_case_02` — Known exact job is returned under dense company history with bounded result size/candidate scan.
- `ext_45_case_03` — Diagnostic capture contains action/outcome/duration only, with no real/synthetic payload sentinel or cookie text.

```bash

# From backend/, activated repository venv; disposable SQLite only

DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_matches.py -q
```

New file/command paths become runnable only after their owning task supplies them. Inspect existing fixtures before selecting tests. Real PostgreSQL concurrency, real Chrome and deployed OAuth acceptance remain distinct from mocked/unit/Chromium checks.

##### Manual QA

1. Run controlled warm and cold checks, publish sanitized aggregate timing and query-plan evidence, and induce one safe timeout.
2. Repeat the relevant invalid/foreign-account/permission case above; reload or open a fresh session before comparing durable state. Record expected versus observed, not just screenshots of the current UI.

##### Acceptance criteria

- [ ] Warm p95 <=2s for recorded fixture/environment; timeouts terminate at 8s and cold starts are not mixed into warm samples.
- [ ] Known exact job is returned under dense company history with bounded result size/candidate scan.
- [ ] Diagnostic capture contains action/outcome/duration only, with no real/synthetic payload sentinel or cookie text.
- [ ] Every numbered EXT-45 checkpoint is implemented or proven already satisfied with current evidence.
- [ ] Scoped regression and inherited caller behavior pass; unrun external checks remain pending.

##### Observability and operations

Existing logging/metrics only: safe action/outcome/error code, affected count and elapsed time; no cookie, URL query/body, title/company, form data or private label. New data and API are additive and remain disconnected until acceptance; disable extension grants/router to roll back while retaining both tables/history. No public/store/provider action is implicit in a local ticket. Use disposable profiles/databases and synthetic accounts only. Installed extension version and backend/frontend SHA are separate release records.

##### Release, rollout and rollback

If target misses, report measured results and fix the query/call path; do not raise the target silently or add paid infrastructure. This is test/evidence work: rollback the isolated test/config delta, retaining real product data.

##### Stop conditions

- If target misses, report measured results and fix the query/call path; do not raise the target silently or add paid infrastructure.
- A prerequisite lacks its stated evidence, current source contradicts the frozen contract, or the target is not demonstrably disposable.
- Ownership, transaction rollback, replay, history preservation, permission or compatibility assertions fail.
- The allowed files/contract cannot represent the behavior: report `Needs Architect Decision: EXT-45 — <boundary and evidence>`; continue only independent work.

##### Documentation impact and definition of done

Update the relevant current-system section of `docs/JOBGRID_BUILD_GUIDE.md` for what/why/how/where, usage, failure/retry, verification and limits. Do not turn the guide into a chronological task diary.

- [ ] Owned implementation/artifact and exact positive/failure assertions pass.
- [ ] Required caller regressions, diff/security review and relevant docs are complete.
- [ ] One focused micro-commit references main issue and `[45/50]`; no unrelated files or empty filler commits.
- [ ] Main issue checklist and applicable Linear state agree with evidence; this packet changes from planned only when its own exit criteria pass.
- [ ] No claim of a later task, store approval or production release is included.

##### Evidence record and suggested tracking metadata

Document ID: `EXT-45`; title: **Measure bounded lookup performance and safe diagnostics**; parent: one Chrome job/company memory main issue; band 9: Integration acceptance; priority P1; dependencies as above. Suggested labels: `jobgrid`, `chrome-extension`, plus the actual affected area. GitHub issue, Linear ID, implementation branch, commit and PR: **not assigned by this packet**; discover/reuse when implementation is authorized.

Evidence fields: baseline/implementation SHA; owner/reviewer; exact test command/runner/database/browser versions; fixture; expected/actual values; sanitized durable artifact or CI URL; docs delta; micro-commit/PR; local/CI/deployed/store/production status separately; unresolved blockers. All values currently **not recorded**.

**Ticket intake result:** WRITTEN / NOT DISPATCHED. Current-source and dependency acceptance must be rechecked; missing external proof remains scoped to its owning gate. This document adds executable detail, not implementation evidence.
