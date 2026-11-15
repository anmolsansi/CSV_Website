# Application Ledger Phase 2: UI and Reporting Architecture

**Status:** Implementation scoped to AL-07–AL-12. **Baseline:** merged Phase 1 PR #205. **No hosted release claimed.**

## Decision: reuse the existing application read APIs

- List and filtered counts use authenticated `GET /crm/applications`, which is owner-scoped, paginated and supports `applied_only` and `follow_up_due`. A page of results is never a lifetime total.
- Four top-level account-wide cards use the already authenticated `GET /crm/analytics` response: `total_applied` (first-applied lifecycle facts), `interviews` (current interview-stage tracks), `offers` (current offer-stage tracks), and `follow_ups_due` (currently due tracks). These are **not** filter-dependent; they may not equal the number of records visible on a filtered page, especially for legacy inconsistent records. Document that explicitly.
- Use existing PATCH and reason-required correction APIs and existing `ApplicationTimeline`, `ApplicationDocuments` and `JobAvailability`. Do not alter status or first-applied semantics.
- No database changes, new routes, dependencies, background tasks, feature-flag changes, or browser extension activation. Rollback is code-only. Retain all data.

## URL and saved view contract

- A UI-only `tab` query key identifies `applied`, `all`, or `followups`. It must not be sent to the backend's application query serializer.
- The existing `view` key remains reserved for saved view identity. `track_id` is an optional numeric deep link, also not sent to backend queries.
- Keep legacy bare `/applications` in All Tracked mode, so existing callers and regression tests do not lose rows. The main navigation destination uses `/applications?tab=applied` and labels it **My Applications**.
- Explicit `tab` overrides conflicting saved filter flags. Without explicit tab, infer from `applied_only` or `follow_up_due` before falling back to all tracked. Tab switching preserves search/company/stage/date filters but resets conflicting lifetime/due flags and page to 1.
- The view's sort and page state use existing serialized application query keys; `view` and `track_id` are retained through in-page navigation. The UI must not fabricate data to satisfy a deep link absent from the current filtered page.

## Failure and data-integrity safeguards

- Sequence-gate applications requests so stale responses cannot clobber the latest filters. Show an explicit error and a Retry control rather than silently showing stale results as current.
- Analytics is independent and can fail with a card-level retry while the list stays operational. No optimistic lifetime metric increases.
- Use stable id pagination already provided by `order_application_query`. Show current page row range, not a guessed total.
- Existing exact URL duplicate identity and account ownership are unchanged. Dates are display-only unless the user follows the existing date-correction workflow requiring a reason.
- Preserve existing filtered/selected/full/lifetime exports, and avoid introducing page-level export as though it covered all matching rows.

## Testing and acceptance

- Navigation, saved views, deep links, filter preservation, tab modes, list/export query parity, stale responses, empty/error states, current-stage/ever-applied separation, keyboard and narrow-screen behavior require Playwright coverage.
- Run frontend production build, applicable browser suites and existing backend tests in GitHub Actions. Production authentication, deployment, and real-account history are separate acceptance gates.
