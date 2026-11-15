# AL-07–AL-12 Phase 2: CI Verification and Release Boundary

**Date:** November 15, 2026  
**Implementation:** [draft PR #207](https://github.com/anmolsansi/CSV_Website/pull/207), [issue #206](https://github.com/anmolsansi/CSV_Website/issues/206)  
**Verified implementation commit:** `935020f157f3c9d2601e0a8982e25eb50212442c`  
**Decision:** Phase 2 implementation and automated CI acceptance complete. **Hosted staging, production deployment and real-user account verification are NOT complete.**

## GitHub Actions on the verified implementation commit

| Required check | Evidence | Result |
| --- | --- | --- |
| Frontend production build | [CI run #43616929514](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929514) | Passed |
| PostgreSQL backend pytest | [CI run #43616929514](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929514) | Passed |
| Playwright Chromium E2E | [CI run #43616929514](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929514) | Passed |
| Extension Node contracts | [CI run #43616929514](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929514) | Passed |
| Backend compilation | [CI run #43616929514](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929514) | Passed |
| Three browser timezone contracts | [C-06 run #43616929628](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929628) | Passed |
| SQLite release contracts | [C-07 run #43616929568](https://github.com/anmolsansi/CSV_Website/actions/runs/43616929568) | Passed |

The implementation and browser test suites ran successfully with those checks. This document does not claim a manual staging smoke or runtime telemetry. Docs-only closeout commits after the verified implementation commit require their own final-head CI verification before merge.

## Item-by-item review

- **AL-07:** Three tabs with stable UI-only `tab` URL, owner-scoped backend filters, paging, search, unambiguous empty/error states. Browser tests cover switching, reload and scope.
- **AL-08:** Four independent account-wide cards read the existing analytics endpoint. Submitted is a first-applied event count, not current `status='applied'`. Current interview, offer and due counts are clearly labeled, not assumed to match filtered rows.
- **AL-09:** Company, role, stage, date, follow-up, and sortable updated timestamp remain in the table. Unknown metadata is not invented. Table actions remain accessible in the horizontally scrollable mobile layout.
- **AL-10:** Existing timeline, evidence, documents, due dates and reason-required date corrections remain in use. Details have `track_id` URL support. The application row links to the company-history page, where the existing people and interview workspace is available.
- **AL-11:** UI-only `tab` and `track_id` do not leak into server query serialization. Existing saved-view identity `view` survives URL rewrites. Filtered, selected and lifetime exports use the existing owner-safe server route rather than only the visible page.
- **AL-12:** Browser tests cover lifetime-vs-stage, overview count consistency, history panel and reload, filter/export request parity, list and metrics failures/retries, out-of-order responses, keyboard tabs and narrow layout. Full project CI and timezone suites passed.

## Boundaries and remaining work

1. No database schema or API changes, no cleanup of inconsistent historical data and no fabrication of applied dates or visits.
2. **No real-user application submission smoke or authenticated hosted staging check was performed.** Production may remain behind a deployment, account, rate-limit, or storage problem unrelated to this UI.
3. **Do not merge or deploy merely because CI passed.** In this repository merging main may trigger automatic Vercel/Render deployment. Obtain separate staging/deployment approval, verify authenticated read paths, loaded job applications, export and rollback before promotion.
4. Phase 3 (`AL-13–17`) will add explicit submissions for jobs not present in CSV; Phase 4 (`AL-18–22`) covers historical import and unknown-date architecture. Neither is delivered here.
5. Safe rollback is to revert the Phase 2 frontend and documentation changes. Never delete stored `JobTrack` data, first-applied evidence or CSV sources as a rollback mechanism.

**Exit disposition:** Phase 2 code and CI gate **PASS**. Hosted release acceptance **OPEN**.
