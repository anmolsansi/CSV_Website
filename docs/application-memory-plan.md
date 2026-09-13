# Application memory and filtered batch opening

## PRD and architect decision
Users can mark selected jobs applied and find every remembered company and job
later, including after deleting CSV rows. They can open the first five unvisited
URLs across the entire current filtered, sorted result. Fewer matches opens fewer.
Opening never implies applying. Chrome is supported by running JobGrid in Chrome;
a website cannot choose a different installed browser. Allow site pop-ups.

Reuse database JobTrack snapshots (account-specific, existing backups) rather
than browser localStorage (device-specific and easily lost). No new service,
dependency or schema is needed. Exact URL remains job identity. Company directory
uses trimmed case-insensitive names; missing names appear as Unknown company.

## CCR-1: additive API contracts
- POST /crm/from-rows/bulk retains row_ids, adds optional status (known enum).
  Returns existing created/updated/skipped plus application_ids. A single
  transaction upserts by user/URL, sets status and first applied_at when applied.
  Existing clients can omit status. Reject missing/foreign IDs before writing.
- PATCH application status=applied sets a missing applied_at; retries preserve it.
- GET /crm/companies?q=&page=1&page_size=50 returns companies [{company,total,applied}],
  total_count/page/page_size/has_next. Only the current user's tracks are counted.
- GET /rows unopened_only now means clicked=false; opened_only means clicked=true.
  New openable_only excludes non-HTTP(S) URLs for batch selection. Both flags
  together give zero matches. Existing sorting/filtering remain authoritative.
- DELETE /rows detaches JobTrack references before deleting rows in one transaction.

## Staff assessment: ready for implementation
Main risks: popup blocking, incorrect ID space, deletion losing history, stale
filter results, partial tracking failures, and exposing another account's data.
Use blank tabs created synchronously during the click, sever opener before
navigation, fetch current server matches, close unused tabs, record only navigated
rows, surface failures, and disable repeat clicks until finished. No cross-tab
reservation: simultaneous clicks in different windows may open the same URL;
visit writes are idempotent. Never automatically submit applications.
Browser acknowledgement is not proof the external job page loaded successfully.

Deploy backend before frontend. No schema migration. Roll back code to prior
revision; existing application records remain readable. Monitor user-facing
errors and existing API metrics; do not add URLs or personal notes to logs.

## Microtasks and completion rule
Each item is one reviewable scope (~2.5%), in dependency order. Definition of
Done: implementation or evidence, narrow validation, diff review, documentation
impact assessed. Test-only changes have no runtime documentation impact. Runtime
contracts and usage live in README. No external tracker or commit is required
without separate publishing authorization; this checklist is the local record.

- [x] 01/40 — Audit stack and ownership — `docs/repo_context.md`. Validate against the stated contract; depends on preceding relevant items.
- [x] 02/40 — Trace visits versus applications — `backend/app/routers/rows.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 03/40 — Trace row IDs versus track IDs — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 04/40 — Approve retention and browser contracts — `docs/application-memory-plan.md`. Validate against the stated contract; depends on preceding relevant items.
- [x] 05/40 — Define optional bulk status validation — `backend/app/schemas.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 06/40 — Reject foreign or missing bulk rows — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 07/40 — Return real application IDs — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 08/40 — Persist applied status and first date atomically — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 09/40 — Preserve dates on status retries — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 10/40 — Correct opened predicate — `backend/app/routers/rows.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 11/40 — Correct unopened predicate — `backend/app/routers/rows.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 12/40 — Limit batch candidates to web URLs — `backend/app/routers/rows.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 13/40 — Detach history before CSV deletion — `backend/app/routers/rows.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 14/40 — Aggregate remembered companies — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 15/40 — Paginate and search companies — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 16/40 — Normalize company detail lookup — `backend/app/routers/crm.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 17/40 — Expose additive client contracts — `frontend/src/api/client.js`. Validate against the stated contract; depends on preceding relevant items.
- [x] 18/40 — Correct dashboard status ID mapping — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 19/40 — Correct follow-up ID mapping — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 20/40 — Create safe tab helper — `frontend/src/api/openJobs.js`. Validate against the stated contract; depends on preceding relevant items.
- [x] 21/40 — Reserve tabs during user gesture — `frontend/src/api/openJobs.js`. Validate against the stated contract; depends on preceding relevant items.
- [x] 22/40 — Fetch global filtered top five — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 23/40 — Record successful navigation only — `frontend/src/api/openJobs.js`. Validate against the stated contract; depends on preceding relevant items.
- [x] 24/40 — Surface blocked and failed visits — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 25/40 — Prevent repeat batches while busy — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 26/40 — Make visit filters mutually exclusive — `frontend/src/pages/Dashboard.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 27/40 — Render remembered company directory — `frontend/src/pages/CompanyHistory.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 28/40 — Add company directory pagination — `frontend/src/pages/CompanyHistory.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 29/40 — Fix company search stale state — `frontend/src/pages/CompanyHistory.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 30/40 — Show history errors and empty states — `frontend/src/pages/CompanyHistory.jsx`. Validate against the stated contract; depends on preceding relevant items.
- [x] 31/40 — Test visit and tracker independence — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 32/40 — Test filtered sorting beyond one page — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 33/40 — Test atomic applied persistence and retries — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 34/40 — Test account ownership and validation — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 35/40 — Test deletion retention — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 36/40 — Test company normalization and pagination — `backend/tests/test_application_memory.py`. Validate against the stated contract; depends on preceding relevant items.
- [x] 37/40 — Test popup success blocked and failure paths — `frontend/unit/open-jobs.test.mjs`. Validate against the stated contract; depends on preceding relevant items.
- [x] 38/40 — Verify dashboard and company browser flows — `frontend/tests/application-memory.spec.ts`. Validate against the stated contract; depends on preceding relevant items.
- [x] 39/40 — Run full applicable tests and build — `docs/application-memory-plan.md`. Validate against the stated contract; depends on preceding relevant items.
- [x] 40/40 — Review contracts and document usage and limitations — `README.md`. Validate against the stated contract; depends on preceding relevant items.

Additional verification scope: existing dashboard and company-history browser selectors updated for the new button and directory copy. Browser auth state is excluded from Git.

## Final verification — 2026-09-10

40/40 local implementation and verification items complete under the adapted
local Definition of Done. GitHub/Linear, micro-commits, PR, merge and deployment
were not performed. Work remains uncommitted on the original main checkout.

- Full backend suite: 113 passed (SQLite), including ownership, status/date retry,
  global filtered batches, retained records, company grouping, and slash names.
- Tab helper: 8 passed with Node's test runner, including blocked tabs, partial
  reservation failure, unsafe URLs, failed tracking, and closed/unused tabs.
- Affected-page Playwright regression run: 48 passed (setup plus Dashboard,
  Applications, Company History and the first new acceptance test).
- Final feature Playwright run: 5 passed (setup plus four acceptance scenarios:
  batches/history reload, blocked tabs, lookup failure cleanup, company retry).
- Vite production build passed; git diff --check passed. No standalone lint or
  typecheck command is configured in frontend/package.json.
- Isolated browser visual check: company directory and navigation rendered;
  browser errors absent. External job pages were fulfilled with test HTML.

No production deployment, PostgreSQL integration run, or real external application
submission was performed. Browser tests use Chromium. Actual Chrome settings must
allow site pop-ups. Concurrent batches in different windows can overlap. Existing
historical records with an incorrect applied status/date need user verification;
no dates were invented or backfilled. Existing cleanup job references a nonexistent
CsvRow.updated_at and can fail; it was outside this feature's scope and unchanged.

Contract note: company detail uses /companies/{company:path} so names containing
slashes can be selected from the directory. Existing ordinary names remain valid.

Staff final review: requested local acceptance scenarios pass; no destructive
migration or new service. Production acceptance remains separate from local tests.
