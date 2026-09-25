# JobGrid — Development, Verification, and Deployment Guide

> **2026-09-24 update:** JG-001–JG-010 are completed and verified locally. See [implementation and acceptance evidence](docs/JG001_010_EXECUTION.md). Earlier audit findings below are historical unless updated in those ticket entries. JG-011–JG-064 and the broader C packages retain their separate acceptance gates. This update is not hosted CI or deployment evidence.

Prepared: **2026-09-24**\
Audited baseline: **`31d51d3e2d61626a13c1b02bc6c4126d3710e542` on main**\
Overall status: **Not completed — implementation exists across the roadmap, but recovery defects, queue pagination, test failures, and external acceptance remain.**

This is the primary execution guide for finishing the existing JobGrid scope. It consolidates the requirements and completion work from [jg.md](jg.md), which remains a historical planning reference. It explains what remains, why it matters, when to start, where to work, how to implement and verify the change, and what evidence closes it. It does not expand the product into another speculative feature roadmap.

Documentation checkout inspected: **`80983814ea64cb27868cfa2b9ca3333997297c41`**. The application audit below remains the September 23 audit at `31d51d3`; application tests were not rerun while writing this file. Refresh remote main and recheck changed code before starting implementation.

The original [64-ticket specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md) remains the detailed source for individual feature contracts. This guide supplies the current completion order and audit corrections. Its current findings take precedence over stale completion summaries in that specification. The Serviq document supplied earlier is a format reference only; none of its product requirements apply here.

## Navigation

- [Scope and completion](#completion-definition)
- [Audit evidence](#audit-evidence)
- [Status rules](#status-rules)
- [Ordered work packages C-01–C-12](#work-order)
- [Repeatable local test commands](#test-commands)
- [All 64 original tickets and their development steps](#original-tickets)
- [GitHub, staging, and production deployment runbook](#deployment-runbook)
- [Final handover](#final-handover)

<a id="completion-definition"></a>
## 1. What “complete” means

JobGrid is complete for this scope when the two original workflows and all 17 roadmap groups satisfy their acceptance contracts, the defects below have regression coverage, the supported database/browser combinations pass, and the same release candidate passes staging and production smoke checks.

- Remember applied jobs and companies durably per account. Application history survives reload, sign-in, and deletion of source CSV rows.
- Open at most five eligible unopened HTTP(S) links from the **entire active filtered and sorted result**, including jobs outside the visible page. Opening a link does not mean applying to a job.
- Deliver reliable backup/restore, filtering, analytics, retention, validation, numeric sorting, release gates, Today, identity matching, evidence, reminders, documents, capture, availability, contacts/interviews, imports, and undo/archive.
- Preserve ownership, reference integrity, deterministic ordering, retry behavior, and existing data through failures and releases.
- Record external acceptance separately. A merged PR, green CI, or local dev login is not proof of a production release.

**Boundary:** the browser opens tabs in the browser running the application. A website cannot force the user's separate Google Chrome installation to open. Test the requested workflow in Chrome and document popup permissions/manual fallback.

**Excluded from required scope:** new AI features, automated applications, a browser extension, new cloud services, enabling automatic purge by default, and large architectural rewrites. Add them only through a separate product decision. No actual code fixes, staging actions, or deployment are performed by writing this guide.

<a id="audit-evidence"></a>
## 2. Evidence baseline and its limits

These results were obtained in the preceding audit on the exact SHA above, using synthetic users and disposable databases. They are not results from executing this guide's future tasks.

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

Every C-01–C-12 completion package starts **Not completed**. The original JG tickets use a separate status vocabulary so implemented features are not presented as absent:

| Original-ticket status | Meaning | Next action |
|---|---|---|
| Verified complete | Every requirement has current code and acceptance evidence | Preserve as regression coverage |
| Implemented—verification pending | Implementation is present, but full requirement-level proof is missing | Verify existing behavior; repair only demonstrated gaps |
| Needs repair | The audit demonstrated a failure affecting the ticket's acceptance | Reproduce, fix, and add regression coverage |
| Externally blocked | Local tooling exists, but real staging/provider proof is missing | Complete the specified external gate |

JG-001–JG-010 are now **Verified complete** locally; remaining ticket assessments refer to the earlier audited baseline. The prior roadmap label is retained separately. An integration defect can require repair without invalidating every part of an otherwise implemented ticket.

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
| 1 | Not completed | [C-01 — Preserve reproductions and freeze recovery contracts](#c-01) | None | JG-001–004, JG-023 |
| 2 | Not completed | [C-02 — Make every restore atomic](#c-02) | C-01 | JG-003, JG-056, JG-058, JG-064 |
| 3 | Not completed | [C-03 — Deliver one complete recoverable backup](#c-03) | C-02 | JG-002, JG-004, JG-044, JG-056–058, JG-064 |
| 4 | Not completed | [C-04 — Fix mixed-source Today pagination](#c-04) | C-01 | JG-026–028, JG-051, JG-055–056 |
| 5 | Not completed | [C-05 — Normalize SQLite timestamp contracts](#c-05) | C-02 | JG-010, JG-019–020, JG-025, JG-037 |
| 6 | Not completed | [C-06 — Make browser time tests deterministic](#c-06) | C-04, C-05 | JG-010, JG-023, JG-027–028, JG-038–040 |
| 7 | Not completed | [C-07 — Enforce the corrected release test matrix](#c-07) | C-02–06 | JG-019–023 |
| 8 | Not completed | [C-08 — Close every product acceptance contract](#c-08) | C-07 | All 64 original tickets |
| 9 | Not completed | [C-09 — Prepare staging and prove durable operations](#c-09) | C-08 | JG-012–014, JG-022, JG-024, JG-040, JG-044, JG-064 |
| 10 | Not completed | [C-10 — Execute real staging acceptance](#c-10) | C-09 | JG-024, JG-040, JG-048 |
| 11 | Not completed | [C-11 — Reconcile documentation and ticket evidence](#c-11) | C-08–10 | All 64 original tickets |
| 12 | Not completed | [C-12 — Release, observe, and close the project](#c-12) | C-11 | Final release |

Test-harness preparation may happen while a feature is repaired, but dependent acceptance cannot close early. C-08 defects become bounded follow-ups linked to their original ticket; rerun affected gates before advancing. Do not silently add them to a future wishlist.

<a id="c-01"></a>
## C-01 — Preserve reproductions and freeze recovery contracts

**Priority:** P1 prerequisite. **When:** before restore changes. **Owner:** backend implementer plus reviewer. **Status:** Not completed.

**What and why:** turn the independent failures into durable regression inputs and define exactly which data “complete backup” preserves. Otherwise the next repair can pass tests while losing a later feature's records.

**Where:** `backend/app/services/backups.py`, `contact_backups.py`, `import_backups.py`, `backend/app/routers/backup.py`, `backend/tests/test_backup_contract.py`, `docs/BACKUP_STRATEGY.md`, and the existing feature-specific recovery tests discovered through the graph. New test function names below are proposed assertions, not claims of existing tests.

**Implementation checkpoints:**

- [ ] C-01.01 Record baseline SHA, migration head, runtime versions, working-tree scope, and test database names in the evidence record.
- [ ] C-01.02 Recreate a synthetic source account with an applied track, notes/dates, contact, association, interview, saved import mapping, manual task/snooze, document/version/selection, and undo audit metadata. Include two accounts to detect ownership leaks.
- [ ] C-01.03 Export v2 JSON, alter only the contacts-extension checksum, then import into an empty destination. Assert HTTP rejection **and zero new rows in every affected table**. Baseline behavior: rejection still leaves one application committed.
- [ ] C-01.04 Export both JSON and ZIP. Inventory section names, backup-local references, file members, checksums, and declared exclusions. Baseline behavior: JSON has contact/mapping extensions but no document bytes; ZIP has document bytes but omits those extensions.
- [ ] C-01.05 Create three future interviews on the same account-local day and request Today with limit two. Assert all three are reachable through cursors. Baseline behavior: two items, total three, null next cursor.
- [ ] C-01.06 Create a persisted-data coverage table from current ORM models: exported, reconstructed, or deliberately excluded with reason. Include data introduced after the base backup schema; do not infer coverage from table counts alone.
- [ ] C-01.07 Preserve deliberate exclusions: authentication secrets, transient upload previews, and executable undo before-images must not be made portable by accident. Restored undo metadata remains non-actionable. Document whether pending deliveries are disabled/replanned so restore never silently resends messages.
- [ ] C-01.08 Specify compatibility for v1, early v2, current extensions, missing optional sections, unknown required sections, and metadata-only restores. Reject unsupported required data before writes.
- [ ] C-01.09 Keep regression fixtures small, deterministic, and synthetic; promote the reproductions into versioned tests. Record both the expected failure and the later passing result.

**Failure/retry:** fixtures must use fresh destinations or rolled-back test transactions. A prior failed restore may have polluted the destination; do not reuse it unknowingly. Never point tests at production.

**Completion proof:** three independent baseline failures are reproduced, and the data-coverage/compatibility contract is reviewed. Capture deliberately failing regressions on the repair branch, then make them pass with C-02–C-06 before merging. Never merge a knowingly failing required CI check as a standalone foundation change. C-01 evidence can be ready before its dependent fixes; final publication requires the combined repair to be green.

<a id="c-02"></a>
## C-02 — Make every restore atomic

**Priority:** P1 data integrity. **When:** immediately after C-01. **Owner:** backend implementer. **Status:** Not completed.

**Observed defect:** `restore_backup_payload_with_contacts` calls the base restore before validating the contacts extension. The base can commit using its own session. Later wrappers add further independent commit boundaries. An outer `rollback()` on the request session cannot undo an already committed inner session.

**Where:** `backend/app/services/backups.py` (`restore_backup_payload`, `restore_backup_v2`, transaction helpers, bundle restore), `contact_backups.py`, `import_backups.py`, and `backend/app/routers/backup.py`. Verify how `backend/app/main.py` wires wrapped functions before changing dispatch.

**Required behavior:** preflight validates the complete document without writes. An actual restore either installs all intended database records or installs none. Repeating a successful restore is idempotent. Conflicts never become silent overwrites.

**Implementation checkpoints:**

- [ ] C-02.01 Trace the JSON, legacy, and ZIP entry points to all session creation, flush, commit, rollback, receipt, and filesystem operations. Record a compact call/transaction map.
- [ ] C-02.02 Parse/version-route once; validate checksums, sizes, identifiers, duplicate references, all present extensions, ownership, and cross-section references before applying records.
- [ ] C-02.03 Separate pure validation and destination conflict classification from mutation. Use a typed validated restore plan or an existing equivalent; do not introduce a general workflow engine.
- [ ] C-02.04 Give one restore orchestrator ownership of the transaction/session. Child writers accept that same session and flush when IDs are needed; they do not independently commit or close it.
- [ ] C-02.05 Account for SQLAlchemy autobegin from earlier reads. Do not blindly wrap an already active request transaction in `begin()`; choose an explicit dedicated restore session or the established caller-owned transaction pattern consistently.
- [ ] C-02.06 Move contact, interview, association, import-mapping, and allowed undo-metadata writes into that transaction. Apply parent references before children and remap using backup references rather than source integer IDs.
- [ ] C-02.07 Lock/revalidate destination conflicts inside the write transaction. Preflight is advisory if another request changes the account before commit.
- [ ] C-02.08 Commit imported data, required lifecycle/history entries, and restore identity receipts together. No successful receipt or event survives a rolled-back restore.
- [ ] C-02.09 Make verification mode side-effect free: no rows, receipt increments, document publication, reminders, or external messages.
- [ ] C-02.10 On validation/constraint/commit errors, roll back all database state and return the existing structured safe error. Do not expose raw SQL or call the result successful with a warning.
- [ ] C-02.11 Preserve replay rules: same backup identity and content is a no-op/reported replay; changed content under the same identity conflicts. Concurrent identical restores must not duplicate relationships.
- [ ] C-02.12 Inject failures after base writes, after contacts, after mappings, after undo metadata, and immediately before commit. Re-query through a separate session to prove durable state is unchanged.
- [ ] C-02.13 Test nonempty destinations, missing optional legacy sections, broken references, wrong-owner references, changed payload replay, and two concurrent PostgreSQL attempts.

**Files and database are not one ACID transaction:** C-03 must coordinate immutable document staging/publication with database commit. Preserve existing files; remove only newly staged/published files owned by the failed attempt, or leave a documented recoverable state with a reconciler. A cleanup failure must be visible and retryable.

**Completion proof:** original checksum reproduction leaves zero imported records; every injected late failure preserves before/after counts and normalized content; successful full restores and retries pass on PostgreSQL and the supported SQLite path. Existing legacy restore tests remain green.

**Rollback:** keep format compatibility and revert the application change if needed; never repair partial imports by deleting a user's account. Record an explicit reconciliation approach for any already-affected data before running it on real accounts.

<a id="c-03"></a>
## C-03 — Deliver one complete recoverable backup

**Priority:** P1 recovery. **When:** after C-02 establishes transaction ownership. **Owner:** backend and frontend implementer. **Status:** Not completed.

**Observed defect:** `export_backup_bundle` calls the base exporter, bypassing later extensions. The UI calls JSON export and labels it complete even though document bytes are excluded.

**Where:** `backend/app/services/backups.py`, `contact_backups.py`, `import_backups.py`, `backend/app/routers/backup.py`, `frontend/src/components/BackupRestore.jsx`, its existing API client, and backup/document recovery tests.

**Implementation checkpoints:**

- [ ] C-03.01 Create one explicitly composed metadata export path covering all portable current sections. Reuse it for JSON and ZIP; avoid circular imports or behavior that relies on changing an imported function indirectly.
- [ ] C-03.02 Produce metadata from one consistent database snapshot. All section references must describe the same account state; sequential independent snapshots can invent broken relationships during concurrent edits.
- [ ] C-03.03 Add a capability/manifest declaration that accurately identifies included metadata and files. Retain compatibility with existing versioned validators and checksums.
- [ ] C-03.04 Verify each included immutable document's ownership, storage key, byte count, and checksum. Handle missing/quarantined/deleted files according to an explicit contract; never silently call a missing-file package complete.
- [ ] C-03.05 Enforce compressed and expanded byte limits, member count, duplicate member rejection, path traversal/symlink rejection, and per-file hash validation before writes. Do not extract untrusted paths directly under the live document root.
- [ ] C-03.06 Route ZIP restore through the same complete metadata validator/transaction orchestrator as JSON. Merely fixing ZIP export without import dispatch still loses data.
- [ ] C-03.07 Stage new files privately using attempt-owned names. Verify all bytes before metadata becomes ready. Preserve preexisting immutable files during retry/rollback; reconcile interruption between file publication and DB commit.
- [ ] C-03.08 Expose “Complete backup — records and files” for ZIP and “Records only — excludes document files” for JSON. Update explanatory text, download names, busy state, errors, and success notifications together.
- [ ] C-03.09 Accept supported JSON/ZIP inputs in the restore UI and show preflight counts, format, capabilities, file exclusions, conflicts, and failures before applying. Keep a selected file/draft after a recoverable failure.
- [ ] C-03.10 Use one busy guard against double-submit. Do not report complete until the API has committed. If the response is lost after commit, an idempotent retry must report the existing result.
- [ ] C-03.11 Round-trip the C-01 rich fixture into an empty account and compare normalized content, references, timestamps, relationships, and file hashes. Source/destination integer IDs need not match.
- [ ] C-03.12 Round-trip into a nonempty account and repeat the import; assert deterministic conflict/replay behavior and zero duplicate contacts, mappings, document versions, or events.
- [ ] C-03.13 Simulate missing file, changed hash, disk full/write failure, process interruption, and cleanup failure. Verify a safe retry/reconciliation path and an accurate user message.
- [ ] C-03.14 Perform a real browser download → upload → preview → restore flow against the local backend, not only mocked responses. Download restored documents and verify bytes.
- [ ] C-03.15 Update backup documentation with data categories, intentional exclusions, restore compatibility, limits, and operator recovery steps. Use the same definitions in UI and docs.

**Completion proof:** a single supported user-facing backup path restores all portable metadata **and** document bytes. Metadata-only export is clearly labeled. Failure/retry and legacy-format tests pass. Restored undo records cannot execute old destructive operations; restoring data does not send email.

**Rollback:** preserve old readers until new packages are versioned and compatibility-tested. Retain a known-good recovery package before deploying; reverting code must not delete newly uploaded files.

<a id="c-04"></a>
## C-04 — Fix mixed-source Today pagination

**Priority:** P2 unreachable work. **When:** after reproductions are durable; before Today acceptance. **Owner:** backend implementer. **Status:** Not completed.

**Observed defect:** the interview wrapper merges interviews into only the first already-paginated base page, truncates to `limit`, and keeps the base cursor. With three interviews and limit two it returns two with no cursor. Mixed queues can also displace base items behind an incorrect cursor.

**Where:** `backend/app/services/today.py`, `backend/app/services/today_f8.py`, existing Today schemas/routes, and Today/interview tests. Preserve the current public response shape unless a justified versioned change is required.

**Implementation checkpoints:**

- [ ] C-04.01 Define one ordering tuple across manual actions, follow-ups, deadlines, and interview preparation. Preserve due-time/null ordering, priority, source type, and stable source ID tie-breakers.
- [ ] C-04.02 Use the same frozen `as_of`, account timezone, snooze policy, archive policy, and visibility filters across every source and continuation page.
- [ ] C-04.03 Normalize source candidates before pagination. Remove the special case that skips interviews when a cursor is present.
- [ ] C-04.04 Apply the decoded cursor's ordering boundary to every source. Fetch only the bounded candidates required to produce `limit + 1` merged results; do not scan an unbounded account graph just to fetch one page.
- [ ] C-04.05 Merge and sort once. Emit at most `limit` items. Build the next cursor from the final **emitted mixed-source item** only when another item exists.
- [ ] C-04.06 Validate and sign cursor contents. Bind account and relevant query context, including timezone/include-snoozed behavior, or explicitly reject incompatible reuse. Do not permit a cursor to widen ownership.
- [ ] C-04.07 Version incompatible cursor formats. Document controlled rejection/reload of old cursors rather than silently returning the wrong page.
- [ ] C-04.08 Calculate counts from the same eligible population; separate total from page length. Verify count semantics when snoozed/archived/terminal records are hidden.
- [ ] C-04.09 Define mutation-between-pages behavior. Freezing `as_of` does not freeze mutable database rows; either document best-effort pagination with refresh or implement a justified stronger snapshot policy. Do not claim an immutable snapshot without storing one.
- [ ] C-04.10 Test interview-only queues of size 0, 1, exactly limit, limit+1, and several pages. Test all source types mixed, identical due times, null due times, snoozes, cancellations, archive changes, and account-local midnight.
- [ ] C-04.11 Traverse all pages of an unchanged fixture and compare the emitted ordered keys to the expected complete set: no missing items, no duplicates, no infinite cursor loop.
- [ ] C-04.12 Test tampered/wrong-account/context-mismatched cursors. Inspect query counts and boundedness with a larger fixture; record measured results instead of inventing a latency guarantee.
- [ ] C-04.13 Exercise actual Today Load more/navigation and an interview mutation in the browser. Verify refreshed cards, counts, focus, and empty states.

**Completion proof:** the three-interview reproduction returns a valid second page; mixed-source traversal is complete and stable for unchanged data; all old Today behavior remains covered.

**Failure/retry:** invalid or stale cursor yields a clear refresh path without losing the user's draft. A failed page load retains previously loaded cards and enables retry.

<a id="c-05"></a>
## C-05 — Normalize SQLite timestamp contracts

**Priority:** P2 supported-runtime correctness. **When:** after restore repair, before the matrix is enforced. **Owner:** backend implementer. **Status:** Not completed.

**Observed failures:** `test_backup_round_trip_retains_snooze_and_manual_action` in `backend/tests/test_backup_contract.py` and `test_illegal_state_transition_rejected` in `backend/tests/test_reminder_models.py` compare naive SQLite values with timezone-aware UTC values. PostgreSQL passed. This is not evidence of lost timestamps by itself.

**Implementation checkpoints:**

- [ ] C-05.01 State the intended contract at three boundaries: stored legacy columns, internal Python values, and wire/export timestamps. Distinguish UTC instants from date-only deadlines and local scheduled wall times.
- [ ] C-05.02 Trace `WorkItemOverride.snoozed_until` and `ReminderDelivery.sent_at` from input through persistence, reload, comparison, export, restore, and response serialization.
- [ ] C-05.03 If stored naive values mean UTC, normalize explicitly to UTC at the chosen boundary. Never attach the host timezone to a legacy naive UTC value.
- [ ] C-05.04 Reuse an existing appropriate helper; add a small shared helper only if production consumers require it. If production behavior already honors the contract and only assertions are wrong, fix assertions to compare canonical instants without changing schema.
- [ ] C-05.05 Test persistence after session expiration/new session, not only the in-memory object. Preserve actual instant, microseconds, and null behavior.
- [ ] C-05.06 Add UTC, positive-offset, negative-offset, DST-boundary, legacy-naive, and backup round-trip examples. Reject ambiguous inputs according to the existing API contract.
- [ ] C-05.07 Run both failing tests, then related reminder/Today/backup tests on both databases. Do not remove timezone checks or add blanket skips to get a green result.
- [ ] C-05.08 Change a database column only if demonstrated necessary. Any migration requires explicit conversion semantics and previous-data verification on a disposable clone.

**Completion proof:** both original tests pass for a documented reason on SQLite and PostgreSQL, and wire/export values represent the same instant after reload and restore.

**Rollback:** prefer boundary normalization over data rewrites. If a migration is required, retain a backup and demonstrate old-code compatibility or a documented recovery route before rollout.

<a id="c-06"></a>
## C-06 — Make browser time tests deterministic

**Priority:** P2 release confidence. **When:** after C-04/C-05. **Owner:** frontend implementer. **Status:** Not completed.

**Observed failures:** `keyboard_snooze_persists_after_reload` and `followup_reschedule_updates_application_drawer` in `frontend/tests/today.spec.ts`. A helper derives a `datetime-local` input using UTC `toISOString()`, and the assertion compares that wall-clock text directly with the outgoing UTC timestamp. Asia/Kolkata exposes the mismatch; UTC masks it.

**Implementation checkpoints:**

- [ ] C-06.01 Decide whether each fixture represents a local wall time or a fixed instant. Construct it accordingly using local calendar fields or an explicit conversion, never a UTC string with its timezone suffix removed by accident.
- [ ] C-06.02 Compute the expected outgoing instant from the intended local input and configured browser timezone. Assert instant equality, then separately assert the displayed local value.
- [ ] C-06.03 Configure browser-context timezone explicitly in Playwright for UTC, Asia/Kolkata, and a DST-observing zone such as America/New_York. Host `TZ` diagnostics alone are not a portable browser-timezone configuration.
- [ ] C-06.04 Test account timezone differing from browser timezone, with expected day boundaries specified. Freeze a clock where midnight or “tomorrow” would make the test flaky.
- [ ] C-06.05 Ensure mock handlers return responses and capture payloads for test assertions; do not hide a handler assertion as a dialog timeout.
- [ ] C-06.06 Add coverage for valid future snooze, invalid/past input, reschedule, reload persistence, cancellation, failed request draft retention, and keyboard focus restoration.
- [ ] C-06.07 Exercise at least one snooze and reschedule against the real API to separate serialization behavior from mock expectations.
- [ ] C-06.08 Rerun the targeted failures in each configured timezone, then the complete required browser matrix. Do not enforce UTC-only execution as the fix.

**Completion proof:** payload instant, persisted instant, and local display match the contract in all declared zones; no host-specific test failures remain.

**Rollback:** test changes should not alter product semantics. If this work exposes a real product-time conversion bug, add a separate failing product regression and repair that conversion explicitly.

<a id="c-07"></a>
## C-07 — Enforce the corrected release test matrix

**Priority:** release gate. **When:** after C-02–06. **Owner:** test/CI implementer. **Status:** Not completed.

**Where:** `.github/workflows/ci.yml`, `frontend/playwright.config.ts`, existing test fixtures, `docs/RELEASE_ACCEPTANCE.md`.

**Implementation checkpoints:**

- [ ] C-07.01 Preserve a PostgreSQL job with real migrations and separate explicitly disposable databases for regular tests and migration/concurrency tests.
- [ ] C-07.02 Add/retain a SQLite job with clear expected PostgreSQL-only skips. A supported SQLite runtime must not silently disappear from release coverage.
- [ ] C-07.03 Enforce the new restore/backup/queue regression cases and multi-zone browser checks. Collect tests before running; an empty selection must fail.
- [ ] C-07.04 Build with the intended API configuration. Start local E2E services with explicit frontend origin/CORS, disabled external workers, and isolated document storage; do not inherit hosted `.env` values accidentally.
- [ ] C-07.05 Preserve unit/helper tests, production build, actual backend routes, and focused real-API browser workflows. Mark mocked tests clearly so they cannot substitute for integration acceptance.
- [ ] C-07.06 Fail the job on test errors, failed migrations, failed readiness, unexpected skips, or missing required evidence. Retries must remain visible; repeated flaky retries are an issue, not proof of correctness.
- [ ] C-07.07 Attach JUnit/browser reports, traces on failure, sanitized service logs, runtime/dependency versions, source SHA, and migration revision. Do not publish private backup contents or credentials.
- [ ] C-07.08 Ensure required status checks match the actual job names and protect the target branch using authorized repository settings. A workflow file alone does not establish branch protection.
- [ ] C-07.09 Run the full matrix once for the final candidate. Repeat affected coverage after any subsequent change, then require green CI on the exact deployable SHA.

**Completion proof:** no failures in supported local paths, all required CI checks green on the candidate, and new independent regressions are enforced rather than residing only in `/tmp`.

**Failure/retry:** preserve the first failure's artifacts, fix the cause, and rerun. Environment failures must be labeled separately from application defects, as the earlier local CORS mismatch was.

<a id="c-08"></a>
## C-08 — Close every product acceptance contract

**Priority:** required project acceptance. **When:** after corrected CI. **Owner:** feature implementer with reviewer. **Status:** Not completed.

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
- [ ] C-10.03 **SMTP:** after explicit authorization to send to the controlled inbox, trigger the supported delivery flow, confirm actual inbox receipt, record provider/message identifier without secrets, and check content/timezone. `logged` or queued is not delivered.
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

Review every skip. Only database-specific exclusions are expected; do not blanket-ignore skipped feature acceptance. The two recorded failures must be fixed before closing this path.

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

The index contains 64 original tickets: 10 are locally verified complete, 10 need repair, 2 are externally blocked, and 42 are implemented with requirement-level verification pending. Remaining assessments retain the earlier audit disposition; these counts are not percentage of code written.

### Ticket index

| Ticket | Scope | Closeout status |
|---|---|---|
| [JG-001](#jg-001-closeout) | Freeze and validate the complete backup v2 record schema | Verified complete |
| [JG-002](#jg-002-closeout) | Add import identity mapping and complete v2 export | Verified complete |
| [JG-003](#jg-003-closeout) | Implement preflight and transactional full restore | Verified complete |
| [JG-004](#jg-004-closeout) | Build restore preview and prove recoverability in the UI | Verified complete |
| [JG-005](#jg-005-closeout) | Extract one account-scoped query builder without changing list behavior | Verified complete |
| [JG-006](#jg-006-closeout) | Route every export through the shared filter contract | Verified complete |
| [JG-007](#jg-007-closeout) | Unify browser and saved-view query serialization | Verified complete |
| [JG-008](#jg-008-closeout) | Define metric semantics and add durable lifecycle event storage | Verified complete |
| [JG-009](#jg-009-closeout) | Wire every mutation into the lifecycle ledger | Verified complete |
| [JG-010](#jg-010-closeout) | Add user timezone and safely backfill known historical facts | Verified complete |
| [JG-011](#jg-011-closeout) | Switch analytics goals weekly reports and digest to shared definitions | Implemented—verification pending |
| [JG-012](#jg-012-closeout) | Introduce explicit archive timestamps and disabled-by-default retention | Implemented—verification pending |
| [JG-013](#jg-013-closeout) | Replace broken cleanup with a bounded observable archive job | Implemented—verification pending |
| [JG-014](#jg-014-closeout) | Expose retention policy and maintenance health safely | Implemented—verification pending |
| [JG-015](#jg-015-closeout) | Create reusable status timestamp URL and bulk validators | Implemented—verification pending |
| [JG-016](#jg-016-closeout) | Apply validation atomically to every application writer | Implemented—verification pending |
| [JG-017](#jg-017-closeout) | Render field errors and fix asynchronous import feedback | Implemented—verification pending |
| [JG-018](#jg-018-closeout) | Define one numeric parsing contract and dialect adapters | Implemented—verification pending |
| [JG-019](#jg-019-closeout) | Register SQLite functions in app and test engines and add real schema checks | Needs repair |
| [JG-020](#jg-020-closeout) | Document and verify both runtime paths | Needs repair |
| [JG-021](#jg-021-closeout) | Correct CI paths readiness and PostgreSQL test composition | Implemented—verification pending |
| [JG-022](#jg-022-closeout) | Add fail-fast production configuration checks | Implemented—verification pending |
| [JG-023](#jg-023-closeout) | Promote audit reproductions into enforced release regressions | Needs repair |
| [JG-024](#jg-024-closeout) | Run staging login delivery restore and rollback acceptance | Externally blocked |
| [JG-025](#jg-025-closeout) | Model manual actions and follow-up overrides | Implemented—verification pending |
| [JG-026](#jg-026-closeout) | Build the stable daily queue and guarded mutations | Needs repair |
| [JG-027](#jg-027-closeout) | Build the Today screen and accessible action controls | Needs repair |
| [JG-028](#jg-028-closeout) | Prove the daily queue improves a real work session | Needs repair |
| [JG-029](#jg-029-closeout) | Implement conservative URL and company identity rules | Implemented—verification pending |
| [JG-030](#jg-030-closeout) | Persist aliases and backfill derived identity safely | Implemented—verification pending |
| [JG-031](#jg-031-closeout) | Expose matching and show applied-before context | Implemented—verification pending |
| [JG-032](#jg-032-closeout) | Validate duplicate warnings against false positives | Implemented—verification pending |
| [JG-033](#jg-033-closeout) | Add evidence records and immutable event payload rules | Implemented—verification pending |
| [JG-034](#jg-034-closeout) | Build evidence mutations and merged timeline API | Implemented—verification pending |
| [JG-035](#jg-035-closeout) | Build timeline and evidence entry in application detail | Implemented—verification pending |
| [JG-036](#jg-036-closeout) | Prove history survives lifecycle and recovery operations | Implemented—verification pending |
| [JG-037](#jg-037-closeout) | Model reminder preferences and delivery state machine | Implemented—verification pending |
| [JG-038](#jg-038-closeout) | Implement clock-safe planning claiming and delivery | Implemented—verification pending |
| [JG-039](#jg-039-closeout) | Expose opt-in preferences and delivery history | Implemented—verification pending |
| [JG-040](#jg-040-closeout) | Verify reminder recovery and controlled real delivery | Externally blocked |
| [JG-041](#jg-041-closeout) | Model immutable document versions and private storage boundaries | Implemented—verification pending |
| [JG-042](#jg-042-closeout) | Implement bounded upload download and storage reconciliation | Implemented—verification pending |
| [JG-043](#jg-043-closeout) | Add document library and per-application version selection | Implemented—verification pending |
| [JG-044](#jg-044-closeout) | Extend recoverable backups to document bytes | Needs repair |
| [JG-045](#jg-045-closeout) | Add manual capture schema and replay identity | Implemented—verification pending |
| [JG-046](#jg-046-closeout) | Implement capture API with identity warnings | Implemented—verification pending |
| [JG-047](#jg-047-closeout) | Build quick-add page and user-invoked bookmarklet | Implemented—verification pending |
| [JG-048](#jg-048-closeout) | Validate capture across browsers and lifecycle transitions | Implemented—verification pending |
| [JG-049](#jg-049-closeout) | Model explicit deadlines and availability evidence | Implemented—verification pending |
| [JG-050](#jg-050-closeout) | Implement manual freshness and a disabled-by-default safe check adapter | Implemented—verification pending |
| [JG-051](#jg-051-closeout) | Show deadlines freshness labels and Today actions | Implemented—verification pending |
| [JG-052](#jg-052-closeout) | Validate freshness limits and false-closure resistance | Implemented—verification pending |
| [JG-053](#jg-053-closeout) | Model contacts associations and scheduled interviews | Implemented—verification pending |
| [JG-054](#jg-054-closeout) | Build private workspace APIs and safe calendar downloads | Implemented—verification pending |
| [JG-055](#jg-055-closeout) | Build application people and interview panels | Needs repair |
| [JG-056](#jg-056-closeout) | Verify contact privacy scheduling and recovery | Needs repair |
| [JG-057](#jg-057-closeout) | Model private import previews and reusable column mappings | Implemented—verification pending |
| [JG-058](#jg-058-closeout) | Implement preview parsing and transactional reconciliation | Implemented—verification pending |
| [JG-059](#jg-059-closeout) | Build column mapping and deliberate commit preview | Implemented—verification pending |
| [JG-060](#jg-060-closeout) | Validate reimport repeatability and bounded resource use | Implemented—verification pending |
| [JG-061](#jg-061-closeout) | Add optimistic versions and bounded undo journals | Implemented—verification pending |
| [JG-062](#jg-062-closeout) | Implement transactional bulk changes and conflict-aware undo | Implemented—verification pending |
| [JG-063](#jg-063-closeout) | Build Archive and explicit Undo conflict handling | Implemented—verification pending |
| [JG-064](#jg-064-closeout) | Prove recovery and decide whether automatic purge is safe | Needs repair |

<a id="jg-001-closeout"></a>
### JG-001 — Freeze and validate the complete backup v2 record schema

**Source entry points (present in inspected checkout):** [backups.py](backend/app/services/backups.py), [contact_backups.py](backend/app/services/contact_backups.py), [import_backups.py](backend/app/services/import_backups.py), [BackupRestore.jsx](frontend/src/components/BackupRestore.jsx). Trace callers/tests before editing shared behavior.

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-001 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-001).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-002 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-002).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-003 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-003).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-004 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-004).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-005 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-005).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-006 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-006).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #45; CI run #70 passed\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-007 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-007).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #47; CI run #74 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-008 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-008).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #49; CI run #80 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-009 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-009).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Verified complete.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #52; CI run #97 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-010 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-010).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #55; CI run #103 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-011 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-011).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-012 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-012).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-013 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-013).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-014 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-014).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-015 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-015).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-016 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-016).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-017 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-017).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-018 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-018).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-019 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-019).

**Current finding:** SQLite run has two timezone assertion failures. Close C-05; the PostgreSQL pass does not close SQLite acceptance.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-020 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-020).

**Current finding:** Both runtime paths are not yet green. Close C-05/C-07 and retain separate migration evidence.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-021 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-021).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-022 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-022).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-023 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-023).

**Current finding:** The current release suite missed the independent restore and pagination reproductions. C-07 must enforce them.

**What to verify or finish, in order:**

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

**Current assessment:** Externally blocked.\
**Prior roadmap label:** COMPLETED / checked — local acceptance tooling merged and CI-verified; external staging gates remain BLOCKED, so no staging-accepted or released claim is made\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-024 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-024).

**Current finding:** Local acceptance tooling exists; external staging gates remain unverified. C-09/C-10 must close them before release.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked — schema/contract foundation merged and CI-verified; Today API/navigation remains owned by JG-026–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-025 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-025).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked — backend Today API/service merged and CI-verified; Today UI/navigation remains owned by JG-027–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-026 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-026).

**Current finding:** Confirmed integration defect: the interview wrapper can truncate the queue with no continuation cursor. Close C-04.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-027 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-027).

**Current finding:** Today UI exists despite the stale proposed status. Close C-06 timezone assertions and C-08 keyboard/real-API acceptance.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-028 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-028).

**Current finding:** A successful small queue does not prove mixed-source pagination. Include C-04 and the full daily-workflow acceptance.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-029 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-029).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-030 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-030).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-031 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-031).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-032 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-032).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-033 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-033).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #122\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-034 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-034).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #124\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-035 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-035).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #127\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-036 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-036).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #132\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-037 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-037).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-038 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-038).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-039 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-039).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Externally blocked.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134; controlled external email remains disabled pending explicit staging authorization/credentials\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-040 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-040).

**Current finding:** Local delivery tests are not inbox receipt. Controlled real delivery remains an external C-10 gate.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-041 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-041).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-042 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-042).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-043 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-043).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-044 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-044).

**Current finding:** The document ZIP omits later metadata extensions. C-03 must compose export and import paths, not only add files.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-045 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-045).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-046 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-046).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-047 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-047).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-048 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-048).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-049 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-049).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-050 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-050).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-051 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-051).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-052 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-052).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-053 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-053).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-054 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-054).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-055 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-055).

**Current finding:** People panels exist; associated Today interview actions can be unreachable. C-04 is required integration acceptance.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-056 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-056).

**Current finding:** Confirmed gaps in restore atomicity and interview pagination. C-02/C-03/C-04 are required before full acceptance.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-057 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-057).

**Current finding:** Mappings exist despite the stale proposed heading. Complete ZIP recovery must include reusable mappings through C-03.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-058 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-058).

**Current finding:** Preview/reconciliation code exists despite the stale heading. Verify current behavior and close cross-feature restore composition.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-059 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-059).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-060 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-060).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-061 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-061).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-062 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-062).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Implemented—verification pending.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-063 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-063).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

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

**Current assessment:** Needs repair.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-064 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-064).

**Current finding:** Recovery cannot be certified while complete backup and transaction defects remain. Keep purge disabled by default.

**What to verify or finish, in order:**

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

Keep the filesystem document adapter, but attach a Render persistent disk mounted at `/var/data`; set `DOCUMENT_STORAGE_DIR=/var/data/jobgrid-documents`. Current `render.yaml` declares `plan: free` and no disk. That manifest is not sufficient for the planned durable document feature. Render's current documentation requires a paid service for persistent disks, limits a disk to one service instance, and does not provide zero-downtime deployment with a disk. Disk access is runtime-only, so file verification/backup cannot run in a pre-deploy job that lacks the disk. Confirm current cost and capacity before provisioning; do not silently substitute ephemeral storage if provisioning is unavailable. [Render persistent disk documentation](https://render.com/docs/disks).

Use a single Uvicorn process/instance initially, matching the disk constraint. Run disk-dependent reconciliation and authorized scheduled work in that instance through the existing implementation. Retain database leases/claims; single-instance deployment is not a substitute for retry safety. Expansion to multiple instances or remote object storage is a later architectural change.

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
| Private disk | Staging disk | Production disk | Mounted path survives restart/redeploy |
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
| `DOCUMENT_STORAGE_DIR` | Render | `/var/data/jobgrid-documents` | `/var/data/jobgrid-documents` on production disk |
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
5. Confirm that staging has no production database, disk, signing key, provider callback, or unrestricted production mail sender.
6. Retain manual production promotion for the release described here. Re-enabling automatic deployment is a later explicit operating-policy change after equivalent gates can be enforced automatically.

**Exit:** merging a repair PR cannot unexpectedly deploy an unaccepted candidate to production.

### 7.6 Provision and deploy staging

1. Create the dedicated Supabase staging project and copy its connection URI into the staging Render secret store. Disable the unused Supabase Data API for this backend-only design, or otherwise prove that anonymous/authenticated Data API roles cannot access JobGrid tables. Do not assume FastAPI owner checks protect a separately exposed database API.
2. Provision the staging Render service using Python 3.12 and the current pinned backend requirements. Use the existing `backend` root and Uvicorn start command; select an approved paid instance and disk size based on the fixture and measured capacity needs.
3. Attach the disk at `/var/data`; configure the settings in 7.3. Test write/read permissions at runtime. Document uploads must not write into the source checkout or a publicly served directory.
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
2. Capture the database with the approved provider backup or a PostgreSQL-compatible logical backup, and capture the corresponding private document directory. Record timestamps, schema revision, file manifest/hashes, and encryption/access controls.
3. Store the package outside the instance and outside the only disk being protected. Confirm that the operator can retrieve/decrypt it. Provider disk snapshots alone do not establish consistency with an independently hosted database.
4. Restore to a separate disposable destination. Compare nonempty counts, normalized record graph, file hashes, and reference integrity. Measure restoration time against the agreed objective.
5. Deploy the previous application build against the staging migrated schema without removing new columns. Verify startup, login, history, and document access; return to the candidate and compare data again.
6. For a real failed application deployment, stop promotion and restore the known-good frontend/backend versions first. Preserve schema and data. A destructive schema downgrade or backup restore needs an explicit incident decision because it can discard newer user writes.
7. If the previous build cannot read the migrated schema, the candidate fails rollback acceptance. Implement compatible additive migration/application behavior before release; do not waive the gate silently.

**Exit:** both application rollback and full recovery have exercised evidence. No production restore is implied by this rehearsal.

### 7.8 Promote the accepted release

1. Confirm all C-01–C-11 gates and original-ticket acceptance dispositions. Resolve P1/P2 defects. Record explicitly approved scope changes instead of marking omitted functionality complete.
2. Record the exact accepted main SHA, successful CI run, staging deployment IDs, operator, reviewer, current backup, rollback artifacts, and observation window.
3. Ensure production settings match the accepted configuration with production-specific credentials/origins. Confirm disk durability and migrations are compatible with the previous application revision.
4. Create the GitHub release/tag for the accepted SHA using the repository's established naming convention; inspect existing tags before selecting a name. Publication itself does not deploy the application.
5. Manually deploy that SHA to the production Render service, watch migration/startup/readiness, and verify the recorded schema revision. Expect a controlled interruption with the chosen disk-based deployment; record a maintenance window rather than promising zero downtime.
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
| Provider credentials or durable disk unavailable | Continue independent local work; record exact dependency | Staging and release |
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
