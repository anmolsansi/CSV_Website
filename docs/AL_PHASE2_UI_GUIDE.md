# Application Ledger 2.0 Phase 2: My Applications UI

**Implementation branch:** `al-phase2-my-applications`. **Scope:** AL-07–AL-12. **Release state:** code review and CI only until separate staging/production approval. **No migrations or new APIs.**

## How to use

1. Select **Applications** from the main navigation. It opens `/applications?tab=applied`, the **Ever Applied** tab by default. This view includes dated submissions whose current stage is applied, interview, rejected, offer, or any other stage.
2. Switch to **All Tracked** for saved and opened entries that were not confirmed submitted. For older bookmarks, bare `/applications` retains All Tracked as a compatibility default.
3. Use **Follow-ups Due** for tracked entries whose follow-up timestamp is at or before now. This is a due-only view, not a queue of all scheduled future reminders.
4. Search and refine current stage, employer, ATS, sponsorship, score, opened-time and applied-time dates using the existing filter controls. The current tab controls its default lifetime/due predicate. Clear filters keeps the current tab.
5. Use **Export** to choose all account records, matching filtered records, page-selected records, Ever Applied matching filters, or all due follow-ups. CSV and JSON queries run against the backend's complete matching result, not just the current page.
6. Each row shows employer, role, current stage, last updated timestamp, opened time, first applied date (when recorded), follow-up and notes. Sort with headers. Unknown metadata is displayed as unknown, not fabricated.
7. Choose **History, evidence & documents** to open existing job availability, linked documents, people/interview workspace and the authenticated application timeline. The URL gains `track_id`. Date corrections with an already recorded first date require a reason in this panel. Use **Company history** to open the company directory focused on that role.
8. The four account-wide summary cards report **lifetime first-applied events**, **current interview-stage tracks**, **current offer-stage tracks**, and **currently due follow-ups** from `GET /crm/analytics`. The cards do not change with table filters or pagination. `Total matching` represents the active tab and current filter query, not the analytics total.
9. If the list or overview fails, use their separate Retry controls. The list never silently treats a failed fetch as an empty successful result.

## URL, API and saved-view contracts

- UI-only `tab=applied|all|followups` is understood by the application page and is **not** sent to the CRM API. `view` retains existing saved-view identity. `track_id` is a detail deep link, not an authorization bypass.
- `GET /crm/applications` owns filtering, page sizes, sort, stage and per-owner counts. `GET /crm/analytics` owns historical first_applied and current-stage metrics. `GET /crm/export/applications` handles owner-scoped full-result export. Existing `PATCH /crm/applications/{id}` and application timeline/correction routes handle updates.
- Tabs preserve ordinary facet filters, clear contradictory ever-applied/due-only predicates and reset to page 1. A URL with an explicit tab takes precedence over legacy filter flags. Existing URL sort and pagination remain supported.
- A deep-linked track must be on the requested filtered page to show inline. Use All Tracked, clear filters or navigate pages if the shared bookmark points outside the current result. No hidden cross-account or unrestricted lookup was added.
- The difference between lifetime first_applied event counts and dated-tracks filtering is **intentional** for inconsistent legacy history, and must not be "fixed" with synthetic dates.

## Implementation files and checks

- `frontend/src/pages/Applications.jsx`: tab, filters, URL, pagination, list/errors, expanded details, overview orchestration.
- `frontend/src/utils/applicationLedgerViews.js`: pure tab selection and clear empty-state semantics.
- `frontend/src/components/ApplicationLedgerTabs.jsx`: accessible tab strip, arrow keys, Home/End.
- `frontend/src/components/ApplicationSummary.jsx`: owner-account metrics with scoped labels and error retry.
- `frontend/src/styles.css`: responsive tab and table rules. `frontend/src/components/Navigation.jsx`: Ever Applied launch URL.
- `frontend/src/api/queryParams.js`: accepts UI-only metadata in saved-view navigation without serializing it into backend queries.
- `frontend/tests/application-ledger-tabs.spec.ts`, `frontend/tests/application-ledger-phase2.spec.ts`: helper and browser acceptance tests.

Use `cd frontend && npm ci && npm run build` and `npx playwright test tests/application-ledger-tabs.spec.ts tests/application-ledger-phase2.spec.ts --project=chromium` with the dev API and `TEST_AUTH=true` test configuration. Run the repository's full CI suites before merge.

## Rollback

Revert this frontend-only feature PR. No migrations, account-owned data, first-applied facts, evidence, exports, browser extension, or backend contract changes must be removed. Production smoke requires separate authorization.
