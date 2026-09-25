# JobGrid — Project Completion Guide

> **2026-09-24 update:** JG-001–JG-010 are completed and verified locally. See [implementation and acceptance evidence](docs/JG001_010_EXECUTION.md). Earlier audit findings below are historical unless updated in those ticket entries. JG-011–JG-064 and the broader C packages retain their separate acceptance gates. This update is not hosted CI or deployment evidence.

Prepared: **2026-09-23**\
Audited baseline: **`31d51d3e2d61626a13c1b02bc6c4126d3710e542` on main**\
Overall status: **Not completed — implementation exists across the roadmap, but recovery defects, queue pagination, test failures, and external acceptance remain.**

This is the execution guide for finishing the existing JobGrid scope. It explains what remains, why it matters, when to start, where to work, how to implement and verify the change, and what evidence closes it. It does not expand the product into another speculative feature roadmap.

The original [64-ticket specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md) remains the detailed source for individual feature contracts. This guide supplies the current completion order and audit corrections. Its current findings take precedence over stale completion summaries in that specification. The Serviq document supplied earlier is a format reference only; none of its product requirements apply here.

## 1. What “complete” means

JobGrid is complete for this scope when the two original workflows and all 17 roadmap groups satisfy their acceptance contracts, the defects below have regression coverage, the supported database/browser combinations pass, and the same release candidate passes staging and production smoke checks.

- Remember applied jobs and companies durably per account. Application history survives reload, sign-in, and deletion of source CSV rows.
- Open at most five eligible unopened HTTP(S) links from the **entire active filtered and sorted result**, including jobs outside the visible page. Opening a link does not mean applying to a job.
- Deliver reliable backup/restore, filtering, analytics, retention, validation, numeric sorting, release gates, Today, identity matching, evidence, reminders, documents, capture, availability, contacts/interviews, imports, and undo/archive.
- Preserve ownership, reference integrity, deterministic ordering, retry behavior, and existing data through failures and releases.
- Record external acceptance separately. A merged PR, green CI, or local dev login is not proof of a production release.

**Boundary:** the browser opens tabs in the browser running the application. A website cannot force the user's separate Google Chrome installation to open. Test the requested workflow in Chrome and document popup permissions/manual fallback.

**Excluded from required scope:** new AI features, automated applications, a browser extension, new cloud services, enabling automatic purge by default, and large architectural rewrites. Add them only through a separate product decision. No actual code fixes, staging actions, or deployment are performed by writing this guide.

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

## 3. Status, ownership, and execution rules

Every completion task starts **Not completed**. This describes its remaining acceptance work, not an assertion that all existing code is absent. An original ticket can have implementation present while acceptance or a later integration repair remains open.

Use these evidence states in records: `not-started`, `in-progress`, `local-ready`, `staging-accepted`, `released`, `blocked`. Use **Completed** in the checklist only when the task's stated exit criteria are satisfied at a recorded SHA. Never count a blocked external gate as passed.

1. Before work, inspect branch, diff, current main, applicable instructions, and migration head. Preserve unrelated changes; the audit left `backend/queries.md` and `backend/scraper.py` untouched.
2. Prefer the code knowledge graph for discovery. File paths below are source anchors, not permission to rewrite entire modules.
3. Assign an implementer and reviewer to each task. The release operator owns staging, secrets, deployment, and recovery evidence. Record actual names when work starts; no owner is assigned by this document.
4. Use a small independent change per coherent outcome. Capture a failing reproduction before fixing a confirmed defect, then run the relevant existing suite. Do not create new abstractions merely to match a checklist.
5. Keep backups backward compatible. If a schema/format change is unavoidable, specify version negotiation, missing-section behavior, upgrade tests, and rollback before changing writers.
6. Freeze contracts in the owning task before touching dependent features. Do not change lifecycle semantics, backup identifiers, or timestamp interpretation silently.
7. This is a documentation request. Publication, messages to others, and deployment are separate actions; apply the user's authorization at execution time rather than inventing blanket approval requirements for ordinary local work.

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

**Completion proof:** three independent baseline failures are reproduced, and the data-coverage/compatibility contract is reviewed. This task can complete with deliberately failing new tests on its working branch; C-07 requires every enforced regression green before release.

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

## 6. All 64 original tickets — completion mapping

The entries below retain each ticket's original implementation scope and add its current closeout route. The scope bullets are **requirements to verify**, not a claim that they all need rebuilding. “Not completed — acceptance closeout” means this guide has not certified every original checklist item; much of that ticket's implementation may already be merged and locally supported.

For every entry, execute C-08's requirement-to-evidence procedure, follow its acceptance pack above, and record proof using the evidence template. Dependencies mentioning C-09/C-10 apply to the final external closeout, not to the start of local verification in C-08. Use the linked original specification for its full contracts, file scope, and historical microtasks; revalidate historical proposed names against current code before acting.

<!-- Original ticket completion entries are generated below from the audited inventory. -->

### Ticket index

| Ticket | Scope | Closeout status |
|---|---|---|
| [JG-001](#jg-001-closeout) | Freeze and validate the complete backup v2 record schema | Completed — locally verified |
| [JG-002](#jg-002-closeout) | Add import identity mapping and complete v2 export | Completed — locally verified |
| [JG-003](#jg-003-closeout) | Implement preflight and transactional full restore | Completed — locally verified |
| [JG-004](#jg-004-closeout) | Build restore preview and prove recoverability in the UI | Completed — locally verified |
| [JG-005](#jg-005-closeout) | Extract one account-scoped query builder without changing list behavior | Completed — locally verified |
| [JG-006](#jg-006-closeout) | Route every export through the shared filter contract | Completed — locally verified |
| [JG-007](#jg-007-closeout) | Unify browser and saved-view query serialization | Completed — locally verified |
| [JG-008](#jg-008-closeout) | Define metric semantics and add durable lifecycle event storage | Completed — locally verified |
| [JG-009](#jg-009-closeout) | Wire every mutation into the lifecycle ledger | Completed — locally verified |
| [JG-010](#jg-010-closeout) | Add user timezone and safely backfill known historical facts | Completed — locally verified |
| [JG-011](#jg-011-closeout) | Switch analytics goals weekly reports and digest to shared definitions | Not completed — acceptance closeout |
| [JG-012](#jg-012-closeout) | Introduce explicit archive timestamps and disabled-by-default retention | Not completed — acceptance closeout |
| [JG-013](#jg-013-closeout) | Replace broken cleanup with a bounded observable archive job | Not completed — acceptance closeout |
| [JG-014](#jg-014-closeout) | Expose retention policy and maintenance health safely | Not completed — acceptance closeout |
| [JG-015](#jg-015-closeout) | Create reusable status timestamp URL and bulk validators | Not completed — acceptance closeout |
| [JG-016](#jg-016-closeout) | Apply validation atomically to every application writer | Not completed — acceptance closeout |
| [JG-017](#jg-017-closeout) | Render field errors and fix asynchronous import feedback | Not completed — acceptance closeout |
| [JG-018](#jg-018-closeout) | Define one numeric parsing contract and dialect adapters | Not completed — acceptance closeout |
| [JG-019](#jg-019-closeout) | Register SQLite functions in app and test engines and add real schema checks | Not completed — acceptance closeout |
| [JG-020](#jg-020-closeout) | Document and verify both runtime paths | Not completed — acceptance closeout |
| [JG-021](#jg-021-closeout) | Correct CI paths readiness and PostgreSQL test composition | Not completed — acceptance closeout |
| [JG-022](#jg-022-closeout) | Add fail-fast production configuration checks | Not completed — acceptance closeout |
| [JG-023](#jg-023-closeout) | Promote audit reproductions into enforced release regressions | Not completed — acceptance closeout |
| [JG-024](#jg-024-closeout) | Run staging login delivery restore and rollback acceptance | Not completed — acceptance closeout |
| [JG-025](#jg-025-closeout) | Model manual actions and follow-up overrides | Not completed — acceptance closeout |
| [JG-026](#jg-026-closeout) | Build the stable daily queue and guarded mutations | Not completed — acceptance closeout |
| [JG-027](#jg-027-closeout) | Build the Today screen and accessible action controls | Not completed — acceptance closeout |
| [JG-028](#jg-028-closeout) | Prove the daily queue improves a real work session | Not completed — acceptance closeout |
| [JG-029](#jg-029-closeout) | Implement conservative URL and company identity rules | Not completed — acceptance closeout |
| [JG-030](#jg-030-closeout) | Persist aliases and backfill derived identity safely | Not completed — acceptance closeout |
| [JG-031](#jg-031-closeout) | Expose matching and show applied-before context | Not completed — acceptance closeout |
| [JG-032](#jg-032-closeout) | Validate duplicate warnings against false positives | Not completed — acceptance closeout |
| [JG-033](#jg-033-closeout) | Add evidence records and immutable event payload rules | Not completed — acceptance closeout |
| [JG-034](#jg-034-closeout) | Build evidence mutations and merged timeline API | Not completed — acceptance closeout |
| [JG-035](#jg-035-closeout) | Build timeline and evidence entry in application detail | Not completed — acceptance closeout |
| [JG-036](#jg-036-closeout) | Prove history survives lifecycle and recovery operations | Not completed — acceptance closeout |
| [JG-037](#jg-037-closeout) | Model reminder preferences and delivery state machine | Not completed — acceptance closeout |
| [JG-038](#jg-038-closeout) | Implement clock-safe planning claiming and delivery | Not completed — acceptance closeout |
| [JG-039](#jg-039-closeout) | Expose opt-in preferences and delivery history | Not completed — acceptance closeout |
| [JG-040](#jg-040-closeout) | Verify reminder recovery and controlled real delivery | Not completed — acceptance closeout |
| [JG-041](#jg-041-closeout) | Model immutable document versions and private storage boundaries | Not completed — acceptance closeout |
| [JG-042](#jg-042-closeout) | Implement bounded upload download and storage reconciliation | Not completed — acceptance closeout |
| [JG-043](#jg-043-closeout) | Add document library and per-application version selection | Not completed — acceptance closeout |
| [JG-044](#jg-044-closeout) | Extend recoverable backups to document bytes | Not completed — acceptance closeout |
| [JG-045](#jg-045-closeout) | Add manual capture schema and replay identity | Not completed — acceptance closeout |
| [JG-046](#jg-046-closeout) | Implement capture API with identity warnings | Not completed — acceptance closeout |
| [JG-047](#jg-047-closeout) | Build quick-add page and user-invoked bookmarklet | Not completed — acceptance closeout |
| [JG-048](#jg-048-closeout) | Validate capture across browsers and lifecycle transitions | Not completed — acceptance closeout |
| [JG-049](#jg-049-closeout) | Model explicit deadlines and availability evidence | Not completed — acceptance closeout |
| [JG-050](#jg-050-closeout) | Implement manual freshness and a disabled-by-default safe check adapter | Not completed — acceptance closeout |
| [JG-051](#jg-051-closeout) | Show deadlines freshness labels and Today actions | Not completed — acceptance closeout |
| [JG-052](#jg-052-closeout) | Validate freshness limits and false-closure resistance | Not completed — acceptance closeout |
| [JG-053](#jg-053-closeout) | Model contacts associations and scheduled interviews | Not completed — acceptance closeout |
| [JG-054](#jg-054-closeout) | Build private workspace APIs and safe calendar downloads | Not completed — acceptance closeout |
| [JG-055](#jg-055-closeout) | Build application people and interview panels | Not completed — acceptance closeout |
| [JG-056](#jg-056-closeout) | Verify contact privacy scheduling and recovery | Not completed — acceptance closeout |
| [JG-057](#jg-057-closeout) | Model private import previews and reusable column mappings | Not completed — acceptance closeout |
| [JG-058](#jg-058-closeout) | Implement preview parsing and transactional reconciliation | Not completed — acceptance closeout |
| [JG-059](#jg-059-closeout) | Build column mapping and deliberate commit preview | Not completed — acceptance closeout |
| [JG-060](#jg-060-closeout) | Validate reimport repeatability and bounded resource use | Not completed — acceptance closeout |
| [JG-061](#jg-061-closeout) | Add optimistic versions and bounded undo journals | Not completed — acceptance closeout |
| [JG-062](#jg-062-closeout) | Implement transactional bulk changes and conflict-aware undo | Not completed — acceptance closeout |
| [JG-063](#jg-063-closeout) | Build Archive and explicit Undo conflict handling | Not completed — acceptance closeout |
| [JG-064](#jg-064-closeout) | Prove recovery and decide whether automatic purge is safe | Not completed — acceptance closeout |

<a id="jg-001-closeout"></a>
### JG-001 — Freeze and validate the complete backup v2 record schema

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-001 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-001).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Create strict Pydantic v2 backup models with extra=forbid and an explicit section field allowlist
- [x] List every current model column as exported, reconstructed, deliberately excluded with reason, or an unresolved migration blocker; include UrlHistory and preference/goal rows
- [x] Define backup-local references and canonical checksum serialization; use allow_nan=False and reject duplicate JSON object keys
- [x] Validate lengths, total-record limits, section uniqueness and reference targets before constructing ORM objects
- [x] Implement a v1-to-internal-format adapter that records which fields were absent; never infer first application dates
- [x] Write the v2 example and version compatibility table in the build guide

**Required assertion scenarios from the original ticket:** `assert_complete_model_field_inventory`, `test_null_empty_false_zero_round_trip`, `test_unknown_section_or_ownership_field`, `test_duplicate_refs_and_bad_checksum`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-002-closeout"></a>
### JG-002 — Add import identity mapping and complete v2 export

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-002 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-002).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Add BackupImportMap with account foreign key, backup UUID, section and source reference; unique index prevents duplicate replay identities
- [x] Generate deterministic per-record backup_ref values within the export without exposing them as reusable authorization identifiers
- [x] Read all sections within one consistent database snapshot; use PostgreSQL repeatable-read for export and an equivalent read transaction in SQLite
- [x] Serialize exact CSV and track fields using JG-001 schema; translate every supported FK to a backup-local reference
- [x] Add version=2 branch to GET export while retaining old v1 output for compatibility
- [x] Include declared section counts and checksum; close cursors and transaction on serialization failure; never commit unrelated state from GET

**Required assertion scenarios from the original ticket:** `test_export_every_section`, `test_foreign_user_absent`, `test_export_reference_graph`, `test_migration_up_down_empty`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-003-closeout"></a>
### JG-003 — Implement preflight and transactional full restore

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-003 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-003).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Read at most 20 MiB plus one byte; use application body limits as a second guard and do not call unbounded file.read
- [x] Parse and validate the entire record graph and checksum before beginning destination writes
- [x] Build a preflight plan of creates, natural-key skips, conflicts and remapped references; verify_only returns that plan
- [x] Insert sessions and rows before dependent tracks, batches and events; resolve duplicate_of after all source rows have mapped IDs
- [x] Insert restored rows, preferences, goals and import identity mapping in one transaction; use savepoints or an upsert for concurrent map uniqueness
- [x] On retry return stable mapping results without repeating mutations; on any insert/reference failure roll back every section
- [x] Preserve destination-owned records on merge conflicts and report exact counts; v1 omissions produce explicit incomplete warnings

**Required assertion scenarios from the original ticket:** `test_restore_applied_company_notes_and_dates`, `test_retry_and_concurrent_retry`, `test_failure_on_last_section_rolls_back_all`, `test_merge_preserves_newer_destination`, `test_wrong_account_and_reference_injection`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-004-closeout"></a>
### JG-004 — Build restore preview and prove recoverability in the UI

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Recovery must preserve the complete private record graph and document bytes.\
**When:** after C-02, C-03; close under C-08 / A01. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-004 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-004).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Add export-v2 and restore entry points next to existing backup export; keep the ordinary data export separate
- [x] Present section counts, legacy limitations and merge policy after verify_only; require a deliberate Restore click to write
- [x] Retain selected file in memory only; disable duplicate submissions, reset result when a different file is chosen
- [x] Render uploading, validating, ready, importing, completed-with-warnings and error states with retry guidance; never show success on HTTP failure
- [x] After completion refresh Applications and Companies from the server and offer a summary download without embedded private records
- [x] Exercise the group manual QA with two disposable accounts; save expected/actual evidence and update backup limitations in README and build guide

**Required assertion scenarios from the original ticket:** `backup-restore.spec.ts`, `test_invalid_file_has_no_restore_button`, `test_legacy_backup_warning`, `test_import_failure_does_not_clear_selection`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A01 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-005-closeout"></a>
### JG-005 — Extract one account-scoped query builder without changing list behavior

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-005 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-005).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Capture all existing query arguments and expected defaults from active routes and client mapping
- [x] Create RowQuery and ApplicationQuery models separate from output serializers; bind user_id from get_current_user only
- [x] Move predicates and stable ordering into pure query-building functions returning SQLAlchemy queries; keep serializers at route boundary
- [x] Replace list_rows and application list use incrementally while preserving count, page_size and has_next behavior
- [x] Keep numeric sort expression delegated to the current adapter; do not conceal the SQLite failure scheduled for JG-018
- [x] Prove generated row IDs are unchanged for supported existing filters before enabling export reuse

**Required assertion scenarios from the original ticket:** `test_each_filter_and_pair`, `test_two_users_same_url`, `test_null_and_empty_columns`, `test_page_boundaries_and_ties`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-006-closeout"></a>
### JG-006 — Route every export through the shared filter contract

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-006 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-006).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Add all shared filter parameters to dashboard and applications exports with documented aliases
- [x] Apply scope and ownership checks before querying; selected scope rejects absent, malformed or foreign IDs
- [x] Use the same order expression as the table, omit offset/limit for filtered export, and stream bounded chunks instead of reading every record into an additional large list
- [x] Validate requested columns against CSV_COLUMNS and preserve explicit column order
- [x] Add spreadsheet-safe CSV escaping only at serialization; keep JSON lossless and document the distinction
- [x] Return no export body on validation errors; event metadata records only count, format and bounded filter-presence flags

**Required assertion scenarios from the original ticket:** `test_filtered_export_equals_all_list_pages`, `test_selected_empty_never_exports_all`, `test_selected_foreign_id`, `test_formula_cells_escaped_in_csv_only`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-007-closeout"></a>
### JG-007 — Unify browser and saved-view query serialization

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #45; CI run #70 passed\
**Why:** A filter must select the same account-owned population in every consumer.\
**When:** after C-07; close under C-08 / A02. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-007 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-007).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Create one serializer for each shared query model with known camelCase aliases and explicit false/null handling
- [x] Use it for list loads, filtered export, top-five fetches and saved-view application
- [x] Make export scope and sort explicit, and ensure export from page 2 does not inherit page parameters
- [x] Read saved-view filters from the actual navigation URL/state on initial load, validate them and show a recoverable error for unsupported keys
- [x] Capture the exact query at click time; disable export until the matching request state has settled and surface network errors
- [x] Exercise the group manual QA and add an ID-based assertion rather than checking only that a file downloaded

**Required assertion scenarios from the original ticket:** `filter-export-parity.spec.ts`, `test_selected_scope_exact_ids`, `test_sort_changes_export_order`, `test_error_response_not_downloaded_as_csv`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A02 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-008-closeout"></a>
### JG-008 — Define metric semantics and add durable lifecycle event storage

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #47; CI run #74 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-008 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-008).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Add the table, uniqueness constraints and user/time/kind composite index from CCR-LIFECYCLE-1
- [x] Implement write_event within a caller-owned transaction; never commit inside the helper
- [x] Define pure event-key generation and per-kind payload validation; reject unknown kinds
- [x] Implement first-visit and first-application insert-on-conflict semantics for PostgreSQL and SQLite
- [x] Expose saved,visited,applied definitions as named service functions; avoid reusing count(JobTrack) for visits
- [x] Extend backup v2 schema/export/import maps for lifecycle events in the same ticket and assert no restore emits new first events

**Required assertion scenarios from the original ticket:** `first_event_replay`, `event_owner`, `transaction_rollback`, `backup_lifecycle_roundtrip`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-009-closeout"></a>
### JG-009 — Wire every mutation into the lifecycle ledger

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #49; CI run #80 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-009 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-009).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] List active writers: click, from-row, from-rows bulk, application patch, bulk patch, follow-up presets, external import and ApplyPilot result import
- [x] Route state changes through common service methods receiving a transaction, authenticated user and stable operation ID
- [x] Record first_visited once at actual visit write; record first_applied once when missing applied_at becomes known
- [x] Record status_changed only if the value actually changes, with from/to and source; date correction uses an explicit correction kind
- [x] Validate every bulk target belongs to the user before any mutation, then commit state and events once
- [x] Ensure imports preserve declared dates and do not treat restore/replay as a fresh application; surface uniqueness conflicts as retryable 409 rather than blind re-execution

**Required assertion scenarios from the original ticket:** `all_writer_paths_emit_same_facts`, `repeat_patch_same_status`, `bulk_partial_failure`, `applypilot_replay`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-010-closeout"></a>
### JG-010 — Add user timezone and safely backfill known historical facts

**Closeout status:** Completed — locally verified.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #52; CI run #97 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-010 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-010).

**Current finding:** Local acceptance passed on 2026-09-24; recovery gaps are repaired. See [ticket-specific evidence](docs/JG001_010_EXECUTION.md).

**What to verify or finish, in order:**

- [x] Add timezone default UTC for existing users and validate new selections with zoneinfo; accept neither an arbitrary offset nor an invalid zone name
- [x] Implement profile read/update routes and common UTC-boundary calculation for daily and rolling-week metrics
- [x] Write a resumable backfill command with --dry-run and --after-id; process at most 500 rows per transaction
- [x] Create historical first events only from nonnull clicked_at/applied_at; record source=legacy_backfill and preserve original dates
- [x] Detect conflicting URL duplicates and missing dates; produce aggregate warning counts and a private review query, not a public list of user records
- [x] Extend backup of profile timezone and compare dry-run counts before applying to a disposable copy

**Required assertion scenarios from the original ticket:** `kolkata_midnight`, `dst_23_and_25_hour_days`, `backfill_twice`, `missing_applied_date`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-011-closeout"></a>
### JG-011 — Switch analytics goals weekly reports and digest to shared definitions

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified — merged in PR #55; CI run #103 passed\
**Why:** Events and local-day definitions must produce consistent metrics without inventing historical facts.\
**When:** after C-05, C-06, C-07; close under C-08 / A03. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-011 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-011).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Replace independent event/track/csv counting with shared metric service calls while preserving response field compatibility
- [ ] Show distinct labels Visited jobs, Saved jobs and Applied jobs; do not silently rename a response key without documenting its corrected meaning
- [ ] Add timezone selection and an explanation that historical records with unknown dates are excluded from dated totals
- [ ] Use the same boundaries in goals, weekly report and digest data collection; do not send a real email during automated tests
- [ ] Avoid per-row counting queries; group in SQL with bounded dimensions and account scoping
- [ ] Run the group QA and verify exact numeric assertions across pages after retries and a source-row deletion

**Required assertion scenarios from the original ticket:** `metric-consistency.spec.ts`, `daily_boundary_api`, `historical_delete`, `digest_preview_matches_weekly`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A03 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-012-closeout"></a>
### JG-012 — Introduce explicit archive timestamps and disabled-by-default retention

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-012 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-012).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add archived_at and nullable user retention preference with documented migration defaults
- [ ] Keep legacy archived flags but leave unknown archived_at null; do not backdate them
- [ ] Change manual archive to update only rows transitioning false to true; preserve application snapshots and duplicate links
- [ ] Add non-destructive retention configuration with allowed days 0 or 7..3650; reject invalid negative/too-small values
- [ ] Extend backup v2 for archive metadata and retention preferences
- [ ] Document the retirement of implicit two-day cleanup and keep all purge activation off

**Required assertion scenarios from the original ticket:** `archive_twice_preserves_timestamp`, `existing_archived_unknown_date_is_not_purgeable`, `migration_does_not_hide_unvisited_rows`, `backup_preserves_archive_state`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-013-closeout"></a>
### JG-013 — Replace broken cleanup with a bounded observable archive job

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-013 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-013).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Remove the nonexistent updated_at access and the current hard-delete branch
- [ ] Select only policy-eligible visited nonarchived rows using clicked_at and account policy; old created_at alone is insufficient
- [ ] Page deterministically in batches of 500; update state/timestamp in a single transaction per batch
- [ ] Add process job registration guard and database lease/lock where more than one scheduler instance is possible; log lease contention as skipped
- [ ] Return or record the structured result and propagate a bounded failure state to logging/metrics; do not catch and pretend success
- [ ] Exercise eligibility, clock boundaries, repeated runs, lock expiry and mid-batch rollback

**Required assertion scenarios from the original ticket:** `old_unvisited_is_preserved`, `500_row_batch_limit_and_resume`, `cleanup_failure_not_zero_success`, `two_workers_do_not_double_count`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-014-closeout"></a>
### JG-014 — Expose retention policy and maintenance health safely

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Background retention must be opt-in, bounded, observable, and recoverable.\
**When:** after C-07, C-09; close under C-08 / A04. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-014 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-014).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add GET/PATCH /crm/profile/retention with {archive_after_days:0
- [ ] 7..3650}; document that purge is unavailable until the final archive tranche
- [ ] Show disabled-by-default control, eligible-row count preview and last successful cleanup time
- [ ] Require an explicit Save for policy changes; do not run cleanup merely by opening settings
- [ ] Display failed/stale maintenance state as unavailable rather than reporting zero eligible jobs
- [ ] Add a link to preserved archived rows only once JG-062 exists; until then explain archive recovery is an API/operator action and do not enable auto archive in production
- [ ] Run policy UI validation and record the operational owner/run command in the guide

**Required assertion scenarios from the original ticket:** `retention-settings.spec.ts`, `cross_account_policy_write_is_denied`, `preview_has_no_side_effect`, `failed_health_does_not_look_healthy`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A04 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-015-closeout"></a>
### JG-015 — Create reusable status timestamp URL and bulk validators

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-015 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-015).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Create reusable enums and validators without changing domain data storage types
- [ ] Separate omitted fields from explicit clear using model_fields_set/exclude_unset semantics
- [ ] Parse date-only values only with an explicit user timezone supplied by the service; do not use server local time
- [ ] Validate URL scheme/host/credential limits and lengths before constructing a JobTrack
- [ ] Normalize bulk IDs while retaining source indices for error reporting
- [ ] Add a compatibility error formatter that accepts legacy string/dict and new field lists

**Required assertion scenarios from the original ticket:** `parameterized_status_allowed_and_rejected`, `omitted_null_empty_date_semantics`, `date_only_kolkata_conversion`, `bulk_duplicate_missing_foreign_and_max_count`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-016-closeout"></a>
### JG-016 — Apply validation atomically to every application writer

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-016 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-016).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Inventory and update single patch, bulk patch, from-row, from-rows, external import and ApplyPilot result paths
- [ ] Preload ownership of all referenced rows/tracks; validate the whole batch before mutations
- [ ] Preserve first applied_at on ordinary retries; use explicit correction commands for date edits
- [ ] Catch only expected parse/constraint errors and map to 400/409/422; unexpected failures stay 500 with a request ID and rollback
- [ ] Reject invalid JSON backup bodies using the JG-001 parser instead of exposing a stack trace
- [ ] Add a read-only legacy-invalid-data report; keep repair as deliberate user correction

**Required assertion scenarios from the original ticket:** `endpoint_matrix_invalid_status_never_200`, `second_invalid_record_rolls_back_batch`, `date_clear_with_applied_status_rejected`, `concurrent_duplicate_returns_safe_conflict_or_existing_record`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-017-closeout"></a>
### JG-017 — Render field errors and fix asynchronous import feedback

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Invalid input must fail consistently without partial writes or lost user drafts.\
**When:** after C-07; close under C-08 / A05. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-017 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-017).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Use await file.text() and one awaited API call inside a single try/catch/finally for external import
- [ ] Clear stale preview/result when file changes or parsing fails; disable Import until a valid parse exists
- [ ] Display full file row count and preview count separately instead of saying 10 of 10 for larger files
- [ ] Use the shared error formatter for application fields and import errors; keep user input on failure
- [ ] Prevent duplicate form submission and confirm displayed state from server response, then refresh persisted values
- [ ] Test keyboard submission and focus return to the first invalid field; preserve read-only dates until the user explicitly edits

**Required assertion scenarios from the original ticket:** `application-validation.spec.ts`, `file_reader_and_network_failure`, `pending_request_button_disabled`, `preview_10_of_25_and_invalid_replacement_file`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A05 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-018-closeout"></a>
### JG-018 — Define one numeric parsing contract and dialect adapters

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-018 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-018).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Write a table of accepted and rejected numeric strings and expected Decimal/null values
- [ ] Implement the deterministic parser with a length cap of 128 characters and finite-number check
- [ ] Select a PostgreSQL numeric expression or SQLite jobgrid_numeric expression by bound dialect
- [ ] Apply consistent nulls-last and deterministic ID tie-breakers
- [ ] Cover each numeric CSV field and salary filters without modifying stored text

**Required assertion scenarios from the original ticket:** `numeric_order_not_lexical`, `invalid_values_last_both_directions`, `negative_decimal_percentage_currency`, `long_or_nonfinite_value_is_null`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-019-closeout"></a>
### JG-019 — Register SQLite functions in app and test engines and add real schema checks

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-019 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-019).

**Current finding:** SQLite run has two timezone assertion failures. Close C-05; the PostgreSQL pass does not close SQLite acceptance.

**What to verify or finish, in order:**

- [ ] Create an engine-configuration helper or engine connect listener that registers SQLite functions on every connection
- [ ] Call the same setup from fixture-created engines and background session factories
- [ ] Use per-test disposable DB naming and foreign_keys=ON in SQLite acceptance fixtures
- [ ] Add a PostgreSQL-only test marker that requires a supplied isolated TEST_DATABASE_URL and fails visibly when mandatory CI cannot supply it
- [ ] Use SQLAlchemy inspector to compare actual tables, nullability, indexes and critical uniqueness/FK constraints after alembic upgrade head
- [ ] Do not count a skipped PostgreSQL check as schema acceptance

**Required assertion scenarios from the original ticket:** `new_connection_has_function`, `foreign_key_fixture_enforced`, `fresh_postgres_matches_metadata`, `migration_replay_is_noop`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-020-closeout"></a>
### JG-020 — Document and verify both runtime paths

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Both supported database paths must honor the same numeric and timestamp contracts.\
**When:** after C-05, C-07; close under C-08 / A06. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-020 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-020).

**Current finding:** Both runtime paths are not yet green. Close C-05/C-07 and retain separate migration evidence.

**What to verify or finish, in order:**

- [ ] Document SQLite quick start separately from PostgreSQL migration and release acceptance
- [ ] Add a browser test clicking Resume Score and asserting exact row order rather than only a header arrow
- [ ] Run the numeric test suite on SQLite and PostgreSQL; capture server errors if either fails
- [ ] Verify a new DB connection and application restart do not lose function registration
- [ ] State migration rollback limitations and the approved production DB version without claiming unrun evidence

**Required assertion scenarios from the original ticket:** `numeric-sort.spec.ts`, `both_dialect_api_responses_are_200`, `startup_and_new_connection_smoke`, `release_requires_real_postgres_result`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A06 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-021-closeout"></a>
### JG-021 — Correct CI paths readiness and PostgreSQL test composition

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-021 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-021).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Change the backend start step to the real backend working directory; remove cd ../backend
- [ ] Run alembic upgrade head before starting the API and print only the revision, not the DSN credentials
- [ ] Replace fixed sleep with bounded health polling and capture sanitized server logs on failure
- [ ] Start PostgreSQL tests with explicit isolated environment variables; never use production secrets in PR jobs
- [ ] Keep browser auth setup as a dependency and verify test collection is nonempty
- [ ] Attach test and trace artifacts on failure with retention appropriate for synthetic data

**Required assertion scenarios from the original ticket:** `workflow_command_resolves_backend_directory`, `health_timeout_fails_job`, `postgres_suite_and_browser_suite_run`, `zero_tests_or_failed_setup_is_not_success`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-022-closeout"></a>
### JG-022 — Add fail-fast production configuration checks

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-022 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-022).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add a pure configuration validator invoked before route-serving startup
- [ ] Reject TEST_AUTH in production and empty/default signing secrets; keep real secret value out of exceptions
- [ ] Require valid HTTPS public origins in production and explicit CORS allowlist; preserve localhost only for development/test
- [ ] Test cookie Secure and expected SameSite options for production OAuth login/logout
- [ ] Make dev-login return 404 under production regardless of the request payload
- [ ] Document required deployment environment checks and how to generate/store a signing secret outside the repo

**Required assertion scenarios from the original ticket:** `production_test_auth_rejected_before_serving`, `default_or_empty_key_rejected`, `https_and_cors_validation`, `test_environment_dev_login_preserved`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-023-closeout"></a>
### JG-023 — Promote audit reproductions into enforced release regressions

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-023 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-023).

**Current finding:** The current release suite missed the independent restore and pagination reproductions. C-07 must enforce them.

**What to verify or finish, in order:**

- [ ] Turn each audit failure into an unconditional assertion with a nonempty synthetic fixture
- [ ] Include backup round trip, multi-filter export, metric reconciliation, invalid inputs, cleanup failure and numeric sort
- [ ] Replace conditional if-data assertions within touched tests; fail setup when expected fixtures are missing
- [ ] Require all tests on the migrated PostgreSQL runtime and keep SQLite functional coverage separately
- [ ] Record application/library/browser versions and current SHA beside test evidence
- [ ] Define the local-ready, staging-accepted and released status vocabulary; never collapse them into Done

**Required assertion scenarios from the original ticket:** `break_each_contract_then_test_fails`, `cross_user_scenarios_remain_denied`, `test_count_nonzero`, `no_manual_skip_counts_as_pass`, `original_company_history_survives_source_delete_and_slash_name`, `top5_complete_filters_sort_safe_url_popup_blocking_and_click_recording`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-024-closeout"></a>
### JG-024 — Run staging login delivery restore and rollback acceptance

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked — local acceptance tooling merged and CI-verified; external staging gates remain BLOCKED, so no staging-accepted or released claim is made\
**Why:** Local checks, external staging acceptance, and release are different claims.\
**When:** after C-07, C-09, C-10; close under C-08 / A07. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-024 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-024).

**Current finding:** Local acceptance tooling exists; external staging gates remain unverified. C-09/C-10 must close them before release.

**What to verify or finish, in order:**

- [ ] Create an evidence checklist with owner, environment, command, expected and actual result for each gate
- [ ] Use a disposable PostgreSQL DB to prove backup restore retains rows, tracks, notes, dates and references; compare row counts plus content hashes
- [ ] Test additive migration followed by old-code startup while retaining new columns, then restore current code
- [ ] Exercise configured OAuth login/logout with a staging test account; verify account linkage and cookie behavior
- [ ] With explicit sending authorization, deliver one SMTP message to a controlled sandbox and inspect received content; do not treat status=logged as delivered
- [ ] Run smoke requests after backend/frontend deployment and document rollback trigger; leave external gates blocked if credentials/environment are unavailable

**Required assertion scenarios from the original ticket:** `staging_restore_content_comparison`, `oauth_real_provider_not_dev_login`, `smtp_received_not_merely_queued`, `rollback_preserves_user_history`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A07 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-025-closeout"></a>
### JG-025 — Model manual actions and follow-up overrides

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked — schema/contract foundation merged and CI-verified; Today API/navigation remains owned by JG-026–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-025 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-025).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add WorkItem and WorkItemOverride with owner indexes, timezone-aware timestamps and positive version constraints
- [ ] Keep derived follow-ups out of WorkItem; define and validate source action keys against owned source records
- [ ] Constrain description to1..500 trimmed characters, priority0..3 and the two states; done requires completed_at
- [ ] Write an additive migration and test foreign-key detachment without deleting work items
- [ ] Extend backup v2 with work_items and work_item_overrides, including remapped track refs; old v2 files omit these sections safely
- [ ] Add nullable row/source-view references and origin_key uniqueness for explicit shortlist actions; preserve description after source deletion

**Required assertion scenarios from the original ticket:** `owned_action_key_rejects_foreign_track`, `migration_preserves_existing_followups`, `done_timestamp_constraint`, `backup_round_trip_retains_snooze_and_manual_action`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-026-closeout"></a>
### JG-026 — Build the stable daily queue and guarded mutations

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked — backend Today API/service merged and CI-verified; Today UI/navigation remains owned by JG-027–JG-028\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-026 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-026).

**Current finding:** Confirmed integration defect: the interview wrapper can truncate the queue with no continuation cursor. Close C-04.

**What to verify or finish, in order:**

- [ ] Compute local-day UTC bounds using the validated account timezone from JG-010
- [ ] Build owned manual and derived-follow-up queries with snooze exclusion and the frozen deterministic order
- [ ] Implement cursor decoding and limits; include counts with exactly the same membership filters
- [ ] Implement create/edit/snooze using version compare-and-update in one transaction; return409 without overwriting newer state
- [ ] Resolve follow-ups through the existing validated follow-up writer and lifecycle ledger; reject terminal or disappeared sources
- [ ] Register the router and document response examples for empty, overdue and conflict states
- [ ] Implement bounded from-view creation using the R2 server query, preserving sort and deduplicating pending origin keys

**Required assertion scenarios from the original ticket:** `queue_local_midnight_and_dst`, `pagination_no_duplicates_for_fixed_fixture`, `stale_version_returns409_without_write`, `followup_completion_does_not_increment_applied`, `foreign_action_returns404`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-027-closeout"></a>
### JG-027 — Build the Today screen and accessible action controls

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-027 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-027).

**Current finding:** Today UI exists despite the stale proposed status. Close C-06 timezone assertions and C-08 keyboard/real-API acceptance.

**What to verify or finish, in order:**

- [ ] Add a Today route and navigation item with overdue, due today and undated group labels
- [ ] Display company, role, source, due time and one primary action; link to the existing application drawer
- [ ] Add manual action creation and explicit complete, snooze and reschedule dialogs with keyboard focus return
- [ ] Show initial loading, empty success, network retry, per-item pending and stale-version conflict states
- [ ] Refresh after server success and on window focus; preserve form drafts on failures and never optimistically mark application status
- [ ] Use a fake account timezone/clock fixture to exercise day boundaries rather than depending on wall-clock today
- [ ] Add Add to Today in saved views and application/row detail; display origin and exact count before creating at most20 actions

**Required assertion scenarios from the original ticket:** `today.spec.ts`, `keyboard_snooze_persists_after_reload`, `failed_complete_preserves_item`, `followup_reschedule_updates_application_drawer`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-028-closeout"></a>
### JG-028 — Prove the daily queue improves a real work session

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Every eligible daily action must be reachable and safe to mutate in the correct timezone.\
**When:** after C-04, C-05, C-06, C-07; close under C-08 / A08. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-028 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-028).

**Current finding:** A successful small queue does not prove mixed-source pagination. Include C-04 and the full daily-workflow acceptance.

**What to verify or finish, in order:**

- [ ] Create an acceptance fixture with60 mixed due/manual/snoozed/terminal actions and record exact expected membership
- [ ] Check query plans on PostgreSQL for owner/due indexes and confirm no per-item ORM query loop
- [ ] Rehearse five actions from Today through application detail and back; count clicks and unresolved decisions
- [ ] Verify deletion/detachment, timezone changes, tab conflicts and backup restore using the same fixture
- [ ] Record baseline and new session results without inventing a speed improvement; keep feature acceptance conditional on understandable actions

**Required assertion scenarios from the original ticket:** `fixed_fixture_membership_and_count_parity`, `no_n_plus_one_queue_queries`, `restore_reconstructs_today_items`, `five_action_workflow_no_lost_changes`, `saved_view_page_two_uses_full_filtered_order_and_no_duplicate_actions`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A08 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-029-closeout"></a>
### JG-029 — Implement conservative URL and company identity rules

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-029 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-029).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement a pure canonicalizer with explicit version and unchanged original URL output
- [ ] Write examples for tracking parameters, multiple query values, case-sensitive paths, fragments, ports and international domains
- [ ] Implement company alias key normalization independently from job identity
- [ ] Return confidence plus reason codes; never turn fuzzy company/title similarity into equality
- [ ] Document how provider rules are added with fixtures and a collision report before deployment

**Required assertion scenarios from the original ticket:** `utm_variants_same_canonical_key`, `different_requisition_query_values_remain_distinct`, `path_case_and_duplicate_query_order_preserved`, `credentialed_or_invalid_url_rejected`, `company_similarity_is_possible_only`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-030-closeout"></a>
### JG-030 — Persist aliases and backfill derived identity safely

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-030 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-030).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add nullable canonical columns and nonunique account/hash indexes plus CompanyAlias table
- [ ] Create a resumable500-record backfill with --dry-run and --after-id; emit counts not full URLs
- [ ] Report canonical collisions without merging or changing status, notes or original URLs
- [ ] Write identity fields on new and edited records through the common service
- [ ] Extend backup with aliases and preserve original URLs; rebuild derived canonical keys using the recorded rule version after restore

**Required assertion scenarios from the original ticket:** `backfill_retry_is_idempotent`, `canonical_collision_retains_two_tracks`, `aliases_are_account_scoped`, `backup_restores_alias_grouping`, `dry_run_writes_nothing`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-031-closeout"></a>
### JG-031 — Expose matching and show applied-before context

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-031 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-031).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement scoped match and alias routes with bounded results and constant-count queries
- [ ] Filter matches to actual applied history; label canonical and possible results separately with dates and statuses
- [ ] Show drawer warning before Mark applied and link to the prior application without overwriting the current row
- [ ] Add explicit company alias create/remove controls and show affected history counts before confirmation
- [ ] Use encoded route params for slash-containing company names and return404 for foreign records
- [ ] Handle stale alias conflicts with409 and preserve the users proposed label for retry

**Required assertion scenarios from the original ticket:** `visited_only_has_no_applied_warning`, `exact_match_returns_prior_application_date`, `canonical_warning_does_not_block_reapply`, `slash_company_navigation_works`, `foreign_alias_cannot_be_deleted`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-032-closeout"></a>
### JG-032 — Validate duplicate warnings against false positives

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / locally verified\
**Why:** Remembered applications require conservative identity matching and protection against false merges.\
**When:** after C-07; close under C-08 / A09. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-032 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-032).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Build a labeled synthetic matrix with exact, canonical, same-company-new-role and unrelated matches
- [ ] Assert zero automatic merges and exact expected confidence/reason for every case
- [ ] Exercise upload, row drawer, company aliases and mark-applied paths without duplicating writers
- [ ] Verify changing a URL or deleting a source CSV leaves prior applied history discoverable
- [ ] Document observed precision on the fixture and make no claim about real-world matching accuracy until reviewed data exists

**Required assertion scenarios from the original ticket:** `applied-before.spec.ts`, `new_requisition_not_exact_duplicate`, `source_delete_retains_warning`, `alias_remove_changes_grouping_only`, `matching_query_bounded_for_large_fixture`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A09 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-033-closeout"></a>
### JG-033 — Add evidence records and immutable event payload rules

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-033 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-033).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add evidence table with owner/track indexes, version and explicit soft-delete state
- [ ] Extend lifecycle kind validation with evidence_added, evidence_edited and evidence_deleted payload allowlists
- [ ] Define correction events with old/new timestamps and a bounded reason; avoid placing full private evidence in log payloads
- [ ] Specify retained audit metadata versus removable evidence body in the build guide
- [ ] Extend backup schemas and reference mapping for evidence and new event kinds
- [ ] Add EvidenceCreateReceipt and30-day soft-delete body retention/purge semantics; document recovery-export treatment

**Required assertion scenarios from the original ticket:** `evidence_track_owner_checked`, `unknown_event_payload_field_rejected`, `original_event_immutable_after_correction`, `backup_preserves_evidence_event_references`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-034-closeout"></a>
### JG-034 — Build evidence mutations and merged timeline API

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #122\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-034 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-034).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Create evidence and ledger events in one transaction using a unique account/operation idempotency key
- [ ] Merge lifecycle and evidence history with stable timestamp/type/ID pagination; bound pages at100
- [ ] Implement version-guarded edit and idempotent soft-delete with redacted read serialization
- [ ] Route applied-date correction through the common lifecycle writer and require a reason
- [ ] Return404 for foreign/missing tracks,409 for stale edits and422 for invalid evidence without partial events
- [ ] Implement latest-status correction with expected event ID and row lock; reject intervening status edits and append compensation

**Required assertion scenarios from the original ticket:** `create_retry_one_evidence_one_event`, `pagination_same_timestamp_stable`, `soft_deleted_body_absent`, `foreign_timeline_returns404`, `correction_preserves_original_event_and_metrics`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-035-closeout"></a>
### JG-035 — Build timeline and evidence entry in application detail

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #124\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-035 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-035).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add a timeline section showing source label, event date and separate recorded-at tooltip
- [ ] Show Unknown for missing occurrence dates and avoid assuming imported timestamps are application dates
- [ ] Add plain-text/confirmation-URL evidence form with field errors and pending controls
- [ ] Require a correction reason when editing applied date and preview how daily metrics will move
- [ ] Implement load more, empty, error/retry and stale edit states; preserve drafts and return focus after dialogs
- [ ] Offer Correct latest status with a reason and preview; show409 as a newer-change conflict, not generic failure

**Required assertion scenarios from the original ticket:** `application-timeline.spec.ts`, `unknown_import_date_label`, `script_like_text_rendered_literally`, `stale_edit_draft_preserved`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-036-closeout"></a>
### JG-036 — Prove history survives lifecycle and recovery operations

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #127\
**Why:** History must remain trustworthy through edits, deletion, retries, and recovery.\
**When:** after C-02, C-03, C-07; close under C-08 / A10. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-036 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-036).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Create a complete timeline fixture with imported history, application, status changes, evidence and correction
- [ ] Delete only the source CSV and compare the remaining application timeline content
- [ ] Export and restore into a different empty account, checking remapped evidence and event references
- [ ] Inject a failure between evidence insertion and event insertion and require complete rollback
- [ ] Document known uncertainty for legacy dates and the distinction between user-recorded evidence and verified submission

**Required assertion scenarios from the original ticket:** `source_row_delete_retains_evidence`, `restored_timeline_semantic_equivalence`, `event_insert_failure_rolls_back_evidence`, `deleted_evidence_body_not_in_normal_read`, `individual_status_correction_preserves_original_and_rejects_stale_event`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A10 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-037-closeout"></a>
### JG-037 — Model reminder preferences and delivery state machine

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #132\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-037 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-037).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add preference/delivery tables with unique occurrence/channel constraint and owner/schedule indexes
- [ ] Define legal status transitions and immutable sent_at after acceptance
- [ ] Keep preferences disabled by default for existing and new accounts
- [ ] Add backup sections for preferences and delivery history; restored pending records stay paused until explicit re-enable
- [ ] Validate local times, channel, timezone availability and quiet-hour behavior including equal start/end meaning no quiet period

**Required assertion scenarios from the original ticket:** `duplicate_occurrence_unique_constraint`, `illegal_state_transition_rejected`, `default_opt_out`, `restore_does_not_replay_sent_or_pending_email`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-038-closeout"></a>
### JG-038 — Implement clock-safe planning claiming and delivery

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-038 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-038).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement a pure due-occurrence planner accepting injected UTC clock and account timezone
- [ ] Upsert deterministic occurrence keys and cancel ineligible unsent rows after source edits
- [ ] Claim bounded batches with leases and atomic owner checks; test actual PostgreSQL concurrent transactions
- [ ] Wrap the existing email transport behind an outcome adapter distinguishing accepted, known-rejected and unknown
- [ ] Apply bounded backoff only to known retryable failures and quarantine ambiguous outcomes
- [ ] Expose processed/sent/failed/unknown/lease counts with safe error codes and stop gracefully on shutdown

**Required assertion scenarios from the original ticket:** `dst_gap_and_overlap_one_daily_occurrence`, `two_workers_one_claim`, `crash_after_acceptance_becomes_unknown`, `known_transient_failure_bounded_retry`, `rescheduled_followup_cancels_old_delivery`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-039-closeout"></a>
### JG-039 — Expose opt-in preferences and delivery history

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-039 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-039).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement owner-scoped preference and paginated history APIs with version guards
- [ ] Add explicit reminder opt-in UI explaining channel, local delivery time and quiet hours
- [ ] Display in-app unread reminders and truthful pending, sent, failed and uncertain labels
- [ ] Add deliberate retry for unknown delivery with duplicate warning, new operation ID and audit event
- [ ] Keep email unavailable with a clear configuration reason if verified destination or transport is absent
- [ ] Disable pending occurrences when the user opts out and retain historical delivery results

**Required assertion scenarios from the original ticket:** `opt_out_cancels_unsent_only`, `unverified_destination_cannot_enable_email`, `unknown_retry_requires_explicit_action`, `foreign_delivery_hidden`, `ui_does_not_label_queued_as_sent`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-040-closeout"></a>
### JG-040 — Verify reminder recovery and controlled real delivery

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #134; controlled external email remains disabled pending explicit staging authorization/credentials\
**Why:** Reminder timing and delivery state must survive retries without misleading receipt claims.\
**When:** after C-05, C-06, C-07, C-10; close under C-08 / A11. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-040 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-040).

**Current finding:** Local delivery tests are not inbox receipt. Controlled real delivery remains an external C-10 gate.

**What to verify or finish, in order:**

- [ ] Run fake-clock integration coverage across due-date edits, timezone edits and quiet hours
- [ ] Stop a worker after claim, restart after lease expiry and check safe recovery states
- [ ] Exercise the UI through opt-in, due notification, opt-out and page reload
- [ ] With explicit sending authorization and staging credentials send one controlled test email and record received evidence
- [ ] Document on-call steps for failed/unknown queues and a disable-worker rollback drill; do not bulk retry unknown records

**Required assertion scenarios from the original ticket:** `reminders.spec.ts`, `restart_does_not_duplicate_accepted_delivery`, `timezone_change_replans_unsent`, `controlled_inbox_receipt_or_explicit_blocked_gate`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A11 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-041-closeout"></a>
### JG-041 — Model immutable document versions and private storage boundaries

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-041 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-041).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add version/link tables and constraints with UUID identifiers and explicit owner references
- [ ] Define immutable content fields and ready-only attachment rule; preserve original display filename separately from storage key
- [ ] Add private durable storage directory configuration and readiness check; no default inside a served directory
- [ ] Reserve quota under an account-level lock so concurrent uploads cannot exceed100 MiB
- [ ] Extend backup metadata with document checksums and application refs while explicitly marking byte coverage incomplete
- [ ] Add family-scoped version allocation, used/reference association semantics and DocumentCreateReceipt with one-used-version-per-kind constraint

**Required assertion scenarios from the original ticket:** `referenced_version_cannot_be_overwritten`, `cross_user_link_rejected`, `quota_concurrency_one_reservation_wins`, `ephemeral_or_public_path_configuration_rejected`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-042-closeout"></a>
### JG-042 — Implement bounded upload download and storage reconciliation

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-042 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-042).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Stream multipart upload with byte quota and actual PDF/UTF-8 checks; reject unsupported formats before ready state
- [ ] Generate random internal keys, hash and persist through staging/atomic rename with explicit pending/failed states
- [ ] Implement authenticated downloads with attachment headers, no-store and no public file URLs
- [ ] Implement link/detach and guarded deletion; never delete a file still linked to an application
- [ ] Add bounded reconciliation for old staging files, pending rows and missing ready bytes; report safe IDs/error codes
- [ ] Use idempotency keys to return an existing upload result after a retry without duplicating quota or versions

**Required assertion scenarios from the original ticket:** `oversize_stream_stops_without_ready_file`, `crash_before_and_after_rename_reconciles`, `foreign_uuid_download404`, `download_headers_and_hash_match`, `retry_upload_single_version`, `filename_path_traversal_cannot_escape_storage`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-043-closeout"></a>
### JG-043 — Add document library and per-application version selection

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #138\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-043 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-043).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add a document library with kind, label, version, uploaded time and size; hide internal storage keys
- [ ] Add upload progress, cancel-before-completion behavior, validation messages and quota feedback
- [ ] Add application attachment picker showing immutable version and download action
- [ ] Explain detach versus delete and show referencing applications when server returns409
- [ ] Show missing-file recovery state without substituting the latest document version
- [ ] Ensure keyboard upload/selection works and preserve application context when opening the library
- [ ] Show applications and existing outcome statuses for each version; distinguish Used from Reference and require deliberate correction when replacing the recorded used version

**Required assertion scenarios from the original ticket:** `document_versions.spec.ts`, `failed_upload_never_appears_ready`, `referenced_delete_conflict_explained`, `download_requires_current_session`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-044-closeout"></a>
### JG-044 — Extend recoverable backups to document bytes

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Private immutable documents must remain retrievable after redeployment and restore.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A12. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-044 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-044).

**Current finding:** The document ZIP omits later metadata extensions. C-03 must compose export and import paths, not only add files.

**What to verify or finish, in order:**

- [ ] Add explicit bundle format with manifest metadata and per-file size/hash; keep JSON-only export labeled metadata-only for documents
- [ ] Validate ZIP member names, type, count, duplicate entries and expanded byte total before extraction
- [ ] Restore file bytes into isolated staging then finalize with DB mapping; reconcile failure paths without publishing half-ready files
- [ ] Require exact hash comparison on restore and reject missing/corrupt required bytes
- [ ] Exercise v1/v2 JSON compatibility and complete bundle round-trip; update recovery runbook and scripts integration before calling the feature recoverable

**Required assertion scenarios from the original ticket:** `bundle_restores_bytes_and_links`, `zip_slip_symlink_and_zip_bomb_rejected`, `missing_member_fails_before_ready`, `json_only_reports_document_bytes_excluded`, `failed_restore_reclaims_staging`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A12 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-045-closeout"></a>
### JG-045 — Add manual capture schema and replay identity

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-045 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-045).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add source/captured_at/capture_notes fields with nullable defaults for legacy rows
- [ ] Add CaptureRequest unique owner/key mapping and payload hash, detaching row ref if later removed
- [ ] Define strict manual input models using shared URL/text validators
- [ ] Document exact defaults for every required CsvRow column and prove schema parity
- [ ] Extend backups to preserve capture provenance and notes; omit expired replay keys or document their safe reconstruction
- [ ] Create RequestWindowCounter with fixed hourly policy and48-hour cleanup; isolate counter commit from capture rollback

**Required assertion scenarios from the original ticket:** `legacy_rows_unchanged_after_migration`, `capture_required_column_defaults_valid`, `request_key_conflicting_payload_rejected`, `capture_notes_round_trip`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-046-closeout"></a>
### JG-046 — Implement capture API with identity warnings

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — merged to `main` via PR #143\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-046 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-046).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Validate payload and authenticate before duplicate/match lookup
- [ ] Use F2 identity service for exact/canonical/possible matches and preserve original URL
- [ ] Create row plus request mapping in one transaction; concurrent exact-URL captures resolve using a documented account-level lock
- [ ] Return existing exact row for repeat capture and never mutate its clicked/applied state
- [ ] Wire deliberate capture-notes transfer into later save/apply writer only when target notes are empty or user selects append
- [ ] Rate-limit bounded capture requests per account using shared server enforcement; avoid process-local-only guarantees

**Required assertion scenarios from the original ticket:** `capture_not_visited_or_applied`, `concurrent_repeat_creates_one_row`, `same_key_different_payload409`, `foreign_existing_url_not_disclosed`, `existing_notes_not_overwritten`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-047-closeout"></a>
### JG-047 — Build quick-add page and user-invoked bookmarklet

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-047 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-047).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add short URL/title/company/notes form and immediate server-side match context before final save
- [ ] Provide a generated bookmarklet for the configured app origin with properly encoded fragment JSON
- [ ] Read and validate fragment size/schema, strip it from history and preserve an expiring login draft in sessionStorage
- [ ] Restrict login return route to same-origin /capture; discard malformed or expired drafts
- [ ] Show saved/existing-row result and links to row/application history; preserve edits on network errors
- [ ] Explain browser behavior and manual-copy fallback without promising forced Chrome tabs

**Required assertion scenarios from the original ticket:** `capture.spec.ts`, `expired_or_malformed_draft_discarded`, `login_preserves_valid_draft`, `external_return_url_rejected`, `repeat_submit_one_row`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-048-closeout"></a>
### JG-048 — Validate capture across browsers and lifecycle transitions

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Capture must safely save a job without claiming that it was visited or applied to.\
**When:** after C-07, C-10; close under C-08 / A13. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-048 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-048).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Test manual form in the supported browser and bookmarklet via a synthetic source page with hostile title text
- [ ] Exercise logged-out return, popup-blocked fallback and two rapid clicks
- [ ] Capture then visit then apply; verify exactly one distinct lifecycle event for each real action
- [ ] Delete source CSV rows and confirm any created application history persists
- [ ] Measure a five-job capture walkthrough against the under-one-minute-per-job acceptance goal and record actual timings only

**Required assertion scenarios from the original ticket:** `capture_visit_apply_counts_separate`, `title_markup_rendered_as_text`, `popup_blocked_copy_fallback`, `duplicate_warning_survives_capture_flow`, `backup_restores_capture_provenance`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A13 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-049-closeout"></a>
### JG-049 — Model explicit deadlines and availability evidence

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED — validated in PR #145 and CI run #335\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-049 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-049).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add independent URL-scoped availability records, version guards and source fields
- [ ] Define user-confirmed closed precedence and nonauthoritative checker status mapping
- [ ] Reuse timezone validators and require explicit date-only deadline conversion
- [ ] Add backup section and URL mapping that survives source row deletion
- [ ] Document exact Today eligibility for deadlines and interaction with terminal application states
- [ ] Add JobCheckRequest with indexed durable rate/lease state and7-day metadata cleanup; exclude transient checks from portable backup

**Required assertion scenarios from the original ticket:** `user_closed_not_overwritten_by_reachable`, `date_only_conversion_visible_and_dst_safe`, `source_delete_preserves_availability`, `backup_keeps_deadline_source`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-050-closeout"></a>
### JG-050 — Implement manual freshness and a disabled-by-default safe check adapter

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-050 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-050).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement manual availability routes with owner/version checks independently of outbound networking
- [ ] Implement injectable DNS/transport interfaces with strict public-address validation and pinned connection semantics
- [ ] Enforce redirect count, total time, byte budget and no credential forwarding for every hop
- [ ] Map response outcomes conservatively and preserve user-confirmed closed state
- [ ] Persist/claim bounded check requests and per-account limits; keep JOB_URL_CHECKS_ENABLED=false until safety tests pass
- [ ] Document a manual-only release path if safe transport or destination-policy evidence is unavailable

**Required assertion scenarios from the original ticket:** `ipv4_ipv6_private_and_mixed_dns_answers_blocked`, `dns_rebinding_cannot_change_pinned_destination`, `redirect_private_target_blocked`, `timeout_and403_unknown`, `404_unavailable_not_closed`, `body_limit_stops_read`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-051-closeout"></a>
### JG-051 — Show deadlines freshness labels and Today actions

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-051 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-051).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add deadline editor with explicit timezone and closed/reopen confirmation controls
- [ ] Display last checked timestamp, source and cautious reachable/unavailable/unknown labels
- [ ] Expose Check link only when server capability is enabled and show pending/rate-limit/failure states
- [ ] Add derived deadline actions using stable keys and owner-safe snooze handling
- [ ] Recompute unsent reminders on deadline changes without changing already-sent delivery history
- [ ] Do not hide all manual tasks merely because a related job is closed; show source state and allow explicit resolution

**Required assertion scenarios from the original ticket:** `closed_job_deadline_excluded_but_manual_task_retained`, `deadline_edit_updates_today_and_unsent_reminder`, `disabled_check_capability_has_manual_fallback`, `timezone_label_visible`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-052-closeout"></a>
### JG-052 — Validate freshness limits and false-closure resistance

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** Deadline/freshness information must be explicit and conservative; remote checks must remain bounded.\
**When:** after C-04, C-07; close under C-08 / A14. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-052 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-052).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Build a local mock transport matrix for statuses, redirects, DNS changes, byte limits and timeouts
- [ ] Assert unknown outcomes never set confirmed_closed_at or remove unrelated application history
- [ ] Test repeated checks across two processes against durable rate/claim state
- [ ] Exercise manual deadline, snooze, close, reopen and restore through UI
- [ ] Record network-check enablement evidence separately from manual freshness acceptance; no real-site crawling is required for automated tests

**Required assertion scenarios from the original ticket:** `job-freshness.spec.ts`, `ambiguous_network_response_never_closes`, `concurrent_rate_limit_enforced`, `restore_preserves_user_confirmation`, `unsafe_request_count_zero`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A14 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-053-closeout"></a>
### JG-053 — Model contacts associations and scheduled interviews

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-053 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-053).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add Contact, ApplicationContact and Interview with owned indexes, bounded fields and versions
- [ ] Enforce matching owners for every association before insert and make duplicate role links idempotent
- [ ] Define soft-delete behavior for contacts and source-less applications without cascading private history
- [ ] Validate meeting/profile URLs and timezone-aware time ranges through shared validators
- [ ] Extend backup schema/reference mapping for contact links and interviews; preserve UTC instant and display timezone
- [ ] Add MutationReceipt replay storage and explicit interview round/preparation plus referral-source fields; include only durable user data in backups

**Required assertion scenarios from the original ticket:** `cross_user_association_rejected`, `duplicate_role_link_single_row`, `end_before_start422`, `contact_delete_preserves_interview_marker`, `backup_maps_all_relationships`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-054-closeout"></a>
### JG-054 — Build private workspace APIs and safe calendar downloads

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-054 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-054).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Implement owner-scoped paginated contact search and version-guarded edits with explicit association routes
- [ ] Implement idempotent interview create/edit/cancel and nonblocking overlap warnings
- [ ] Generate ICS with stable UID, incrementing sequence, UTC instants, line folding and escaped CRLF/commas/semicolons
- [ ] Exclude notes/emails from calendar descriptions by default and use authenticated attachment download
- [ ] Emit safe lifecycle events for interview scheduling and cancel unsent reminder occurrences after edits

**Required assertion scenarios from the original ticket:** `foreign_contact_and_ics404`, `ics_injection_cannot_add_second_event`, `ics_dst_instant_correct`, `stale_interview_edit409`, `cancel_suppresses_unsent_reminder`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-055-closeout"></a>
### JG-055 — Build application people and interview panels

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-055 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-055).

**Current finding:** People panels exist; associated Today interview actions can be unreachable. C-04 is required integration acceptance.

**What to verify or finish, in order:**

- [ ] Add linked people list with role, optional contact fields and private notes disclosure
- [ ] Support selecting existing contacts or creating a new one without duplicating by default
- [ ] Add interview editor showing chosen timezone plus account-local preview and overlap warning
- [ ] Provide Download calendar event with wording that no invitation is sent
- [ ] Add preparation action to Today using stable interview source keys and existing snooze rules
- [ ] Show empty/loading/error/conflict states and retain unsaved interview notes on failed requests
- [ ] Expose interview round, preparation notes and referral source beside the linked application; never put private preparation notes in default ICS

**Required assertion scenarios from the original ticket:** `contacts-interviews.spec.ts`, `interview_timezone_preview_matches_server`, `calendar_download_not_sent_message`, `cancel_removes_today_interview_action`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-056-closeout"></a>
### JG-056 — Verify contact privacy scheduling and recovery

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** People and interview data must remain private, schedulable, pageable, and recoverable.\
**When:** after C-02, C-03, C-04, C-07; close under C-08 / A15. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-056 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-056).

**Current finding:** Confirmed gaps in restore atomicity and interview pagination. C-02/C-03/C-04 are required before full acceptance.

**What to verify or finish, in order:**

- [ ] Use two accounts with similar names to prove search/results/links never cross ownership boundaries
- [ ] Test DST overlap/gap inputs, explicit offsets and ICS round-trip using an independent parser
- [ ] Exercise contact soft-delete and interview cancel without losing application history
- [ ] Restore backup into an empty account and compare contact associations, notes and UTC times
- [ ] Review default export/calendar payloads for unnecessary private fields and document exact retention behavior

**Required assertion scenarios from the original ticket:** `foreign_search_zero_results`, `ics_parser_reads_exactly_one_correct_event`, `restored_interview_links_and_notes_match`, `deleted_contact_notes_absent_from_normal_read`, `no_outbound_message_side_effect`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A15 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-057-closeout"></a>
### JG-057 — Model private import previews and reusable column mappings

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-057 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-057).

**Current finding:** Mappings exist despite the stale proposed heading. Complete ZIP recovery must include reusable mappings through C-03.

**What to verify or finish, in order:**

- [ ] Add preview and mapping tables with owner/expiry/status indexes and version constraints
- [ ] Define bounded stored normalized row shape and checksum/fingerprint algorithms
- [ ] Define allowed update fields excluding all user lifecycle and application-memory fields
- [ ] Add24h preview and30-day committed-result cleanup rules; remove raw rows after commit
- [ ] Extend backup with saved mappings only and document transient preview exclusions
- [ ] Store bounded original rejected rows with24-hour download expiry; remove valid raw rows after commit and exclude both from portable backups

**Required assertion scenarios from the original ticket:** `preview_expiry_and_owner_constraints`, `duplicate_headers_preserved_by_index`, `forbidden_update_fields_rejected`, `committed_payload_raw_rows_removed`, `backup_includes_mapping_not_uploaded_preview`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-058-closeout"></a>
### JG-058 — Implement preview parsing and transactional reconciliation

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** PROPOSED / unchecked\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-058 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-058).

**Current finding:** Preview/reconciliation code exists despite the stale heading. Verify current behavior and close cross-feature restore composition.

**What to verify or finish, in order:**

- [ ] Bound incoming bytes/records before loading normalized payload and reject unsupported encoding/shape
- [ ] Parse headers by position, apply explicit mapping and shared field/identity validation
- [ ] Compute exact/possible duplicate plan with per-row reasons and a bounded preview sample
- [ ] On commit recheck owner, expiry, version and destination conflict fingerprint under the account lock
- [ ] Apply create/update-selected with explicit empty replacement policy and no lifecycle field writes in one transaction
- [ ] Persist final counts and replay result atomically; on conflict409 require regenerated preview rather than silent replan
- [ ] Add authenticated rejected.csv download preserving original invalid values and header order with spreadsheet-safe output; return410 after expiry

**Required assertion scenarios from the original ticket:** `invalid_reject_zero_writes`, `skip_invalid_counts_exact`, `update_title_preserves_notes_clicked_applied`, `destination_changed_after_preview409`, `replayed_commit_identical_result`, `last_row_failure_rolls_back_all`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-059-closeout"></a>
### JG-059 — Build column mapping and deliberate commit preview

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-059 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-059).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add upload then map then review then commit stages without writing during preview
- [ ] Show source columns by label and position, required URL target and unmapped-column warning
- [ ] Show create/update/skip/invalid counts with downloadable safe row-number error report
- [ ] Default to insert-only/reject-invalid and make field update plus empty replacement deliberate controls
- [ ] Handle expired preview, changed destination conflict and lost response using server replay identity
- [ ] Refresh rows and aggregate counts after completed commit while preserving active filters
- [ ] Offer Download rejected rows with exact expiry and source values, separately from the compact error summary

**Required assertion scenarios from the original ticket:** `import-mapping.spec.ts`, `preview_only_no_rows_written`, `explicit_title_update_preserves_user_fields`, `expired_preview_requires_regenerate`, `lost_response_retry_no_duplicates`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-060-closeout"></a>
### JG-060 — Validate reimport repeatability and bounded resource use

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Imports must preview clearly, reconcile transactionally, and remain repeatable.\
**When:** after C-02, C-03, C-07; close under C-08 / A16. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-060 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-060).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Run fixtures for BOM, quoted commas/newlines, duplicate headers, blank values and malformed JSON
- [ ] Exercise maximum2000 rows and reject2001/over10 MiB before destination writes
- [ ] Run two commits for the same account concurrently and verify conflict/replay behavior
- [ ] Round-trip saved mappings through backup and test incompatible header fingerprint warning
- [ ] Record actual counts/query counts/runtime for the maximum fixture and document limit escalation as a future separate design

**Required assertion scenarios from the original ticket:** `parser_fixture_matrix_expected_values`, `over_limit_zero_destination_writes`, `concurrent_commit_no_lost_updates`, `saved_mapping_header_mismatch_not_silent`, `spreadsheet_error_report_formula_safe`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A16 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-061-closeout"></a>
### JG-061 — Add optimistic versions and bounded undo journals

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-061 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-061).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add row/track versions and bulk action/effect models with uniqueness, expiry and snapshot limits
- [ ] Inventory every CsvRow/JobTrack writer including bulk SQL, imports, backup merge and background cleanup
- [ ] Create a shared compare-and-update helper and define fields that require version increments
- [ ] Store only changed allowlisted fields in before-images; avoid copying unrelated private data
- [ ] Document expiry cleanup and backup behavior; require the writer inventory complete before exposing Undo

**Required assertion scenarios from the original ticket:** `version_changes_on_each_mutation_path`, `snapshot_over_limit_rejected_before_write`, `duplicate_operation_key_single_journal`, `expired_before_images_removed`, `foreign_effect_reference_rejected`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-062-closeout"></a>
### JG-062 — Implement transactional bulk changes and conflict-aware undo

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-062 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-062).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Route archive/update bulk operations through shared versioning and journal creation in one transaction
- [ ] Integrate version increments into every inventoried writer before enabling undo endpoints
- [ ] Implement preflight version/owner/expiry checks for all_or_nothing and deliberate restore_unchanged modes
- [ ] Restore fields through domain writers, emitting compensating lifecycle events for application corrections
- [ ] Persist per-effect outcomes so retries never reapply undo and report restored/conflict/missing counts
- [ ] Expose operation ID and server undo expiry in bulk response; preserve legacy response fields additively

**Required assertion scenarios from the original ticket:** `bulk_failure_rolls_back_changes_and_journal`, `one_conflict_default_zero_restore`, `partial_mode_restores_only_unchanged`, `retry_undo_no_second_mutation`, `expired410_foreign404`, `metric_correction_matches_undo`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-063-closeout"></a>
### JG-063 — Build Archive and explicit Undo conflict handling

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-063 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-063).

**Current finding:** Implementation is present and the preceding audit found no additional ticket-specific defect. This is local support, not exhaustive proof of every acceptance checkpoint.

**What to verify or finish, in order:**

- [ ] Add paginated Archive screen using the same complete filter/sort contract as active rows
- [ ] Show archived time or Unknown and allow selected owned rows to restore without changing application status
- [ ] Display bulk result counts, operation link and server-based undo deadline; preserve result across route changes
- [ ] On409 show changed/missing counts and offer deliberate restore-unchanged with clear partial result
- [ ] After410 keep Archive recovery available and explain that only immediate undo expired
- [ ] Ensure keyboard access, per-operation pending state and refresh after success across active/archive/application views

**Required assertion scenarios from the original ticket:** `archive-undo.spec.ts`, `two_tab_conflict_no_silent_overwrite`, `partial_undo_counts_visible`, `expired_undo_archive_still_recoverable`, `filters_work_over_all_archived_pages`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

<a id="jg-064-closeout"></a>
### JG-064 — Prove recovery and decide whether automatic purge is safe

**Closeout status:** Not completed — acceptance closeout.\
**Prior roadmap label:** COMPLETED / checked (locally verified)\
**Why:** Undo must respect concurrent changes and archive must preserve a reliable recovery path.\
**When:** after C-02, C-03, C-07, C-09; close under C-08 / A17. Documentation reconciliation follows in C-11.\
**Detailed original contract:** [JG-064 specification](docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md#jg-064).

**Current finding:** Recovery cannot be certified while complete backup and transaction defects remain. Keep purge disabled by default.

**What to verify or finish, in order:**

- [ ] Run archive/undo/restore with applied tracks, evidence, documents, availability, aliases, contacts and reminders present
- [ ] Verify every source-row FK detaches safely and no durable application/company memory cascades away
- [ ] Rehearse database and document-bundle recovery on disposable storage before any purge decision
- [ ] Implement selected-row permanent-delete preview/confirmation only after the preceding assertions pass; keep application/document deletion out of scope
- [ ] If automatic purge is requested later require explicit per-account opt-in, archived_at older than30 days, known timestamp and bounded batches; otherwise keep it disabled
- [ ] Record operational owner, disable switch, counts and recovery evidence; stop rollout on any missing-history or stale-version failure

**Required assertion scenarios from the original ticket:** `purge_source_preserves_complete_application_graph`, `unknown_archive_timestamp_never_purged`, `default_automatic_purge_disabled`, `undo_cannot_overwrite_newer_import`, `restored_backup_matches_pre_purge_history`. These are scenario names; locate equivalent existing tests before adding or running a selector.

**How to close:** map the bullets to current code and exact assertions; run acceptance pack A17 and affected cross-feature regressions, including the dependency tasks above. Record nonempty fixture values, expected/actual output, SHA, and evidence location. Use the original specification for field-level constraints and failure cases.

**Failure/retry:** preserve existing correct code and user data. For any unmet requirement, capture a failing case and make a bounded fix; do not mark the whole ticket absent or suppress the failing assertion. Recheck account isolation and replay/rollback where the task changes state.

**Completion proof:** reviewer accepts the scope-to-evidence mapping and all required assertions pass. Any external gate is either actually passed or the ticket remains explicitly blocked; C-11 updates the old roadmap label only after this proof.

## 7. Final handover checklist

- [ ] C-01–C-12 have evidence-backed final status.
- [ ] All JG-001–JG-064 entries have requirement-level acceptance or a documented approved scope decision.
- [ ] Restore rollback, complete record/file recovery, and mixed-source pagination reproductions remain in the enforced suite.
- [ ] SQLite, PostgreSQL, helper, browser timezone, build, and migration checks pass on the release SHA.
- [ ] Real OAuth, controlled SMTP receipt, deployed smoke, durable files, and old-code rollback have actual evidence.
- [ ] Production release identifiers and observation results are recorded separately from the Git commit.
- [ ] Backup/recovery objectives, schedule, operator, alerts, and rollback procedure are handed over.
- [ ] Remaining low-risk limitations are explicit; no failed or blocked mandatory gate is described as complete.

**Stopping rule:** finish this scope when these checks are satisfied. New feature ideas do not automatically extend the project.
