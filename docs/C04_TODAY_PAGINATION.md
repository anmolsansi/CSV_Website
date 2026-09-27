# C-04 Mixed-source Today pagination

Status: implementation/acceptance evidence for the C-04 completion package.

## Contract

The Today queue has one ordering tuple for every source:

`(due_is_null, due_at, -priority, type, id)`

This preserves the existing behavior: dated actions before undated actions, earlier due times first, higher priority first, deterministic source-type ordering, then stable source ID ordering.

Manual actions, follow-ups, deadlines, and interview preparation use the same ordering boundary. Each source query applies the decoded cursor before fetching a bounded candidate window. Those candidates are normalized into the same item shape, merged, sorted once, and paginated once. Counts describe the complete eligible population, not the current page.

The mixed-source cursor is signed and versioned as v2. It freezes `as_of` and binds the continuation to the authenticated user ID, account timezone, and `include_snoozed` setting. A tampered cursor is rejected. Reusing a valid cursor under another account or incompatible query context is rejected with a refresh instruction. Older cursor formats are intentionally rejected rather than silently interpreted under the new ordering contract.

`as_of` is frozen across continuation pages, but the queue is not a stored database snapshot. If mutable rows change between requests, pagination is best-effort and refresh is the recovery path. We do not claim immutable snapshot semantics.

Archive behavior is unchanged by C-04. Durable pending manual actions remain actionable according to their own state even if a discovery row later moves out of the active grid. Terminal application states and closed deadlines remain excluded by the established Today eligibility rules.

## Regression coverage

`backend/tests/test_interview_today.py` retains the original three-interview reproduction.

`backend/tests/test_today_mixed_pagination.py` covers:

- interview-only populations of 0, 1, exactly the limit, limit+1, and several pages;
- termination with no duplicate action keys or cursor loops;
- manual, follow-up, deadline, and interview items sharing identical due times;
- the stable mixed-source ordering tuple and undated-last behavior;
- counts remaining independent from page length;
- snoozed interview exclusion and `include_snoozed` behavior;
- signed cursor tampering;
- wrong-account cursor reuse;
- timezone and `include_snoozed` context mismatch;
- frozen account-local day boundaries across pages.

`backend/tests/test_today_mixed_cursor_contract.py` proves the old v1 cursor format is rejected with a refresh instruction and defines mutation-between-pages behavior. A cancelled item after page 1 disappears from page 2, the frozen `as_of` remains unchanged, counts reflect the current eligible population, and the continuation terminates without replaying earlier actions.

`backend/tests/test_today_mixed_boundedness.py` builds 250 eligible manual actions, requests a two-item page, records SQL SELECTs, verifies the returned total is still 250, verifies candidate object reads contain a SQL `LIMIT`, and asserts the measured SELECT count stays within a fixed ceiling independent of fixture row count.

`frontend/tests/today-mixed-pagination.spec.ts` keeps the production Today UI and real backend path, reduces only the requested page size to two, creates three scheduled interviews, verifies the first page contains two interview actions and the correct total, clicks the actual **Load more** control, verifies all three actions become reachable with no remaining continuation, and verifies application navigation still works.

Existing Playwright coverage in `frontend/tests/contacts-interviews.spec.ts` exercises Today interview cards, navigation from Today to application details, interview cancellation, API refresh, and disappearance of the cancelled Today card. Existing `frontend/tests/today.spec.ts` remains the browser regression suite for Today loading, retry, mutation, focus, and empty-state behavior.

## Boundedness and query scope

Candidate object reads are bounded per source to `limit + 1 + active_hidden_snooze_count`. The extra snooze allowance is bounded by the account's currently active hidden overrides and prevents snoozed candidates from starving the visible page. Aggregate count queries compute the complete eligible totals without materializing every row as ORM objects. When active hidden snoozes exist, only the referenced source IDs are batch-read to reconcile count categories.

The number of source/count queries is fixed by the four Today source types plus the set of nonempty hidden-snooze source kinds, not by the eligible account row count. The large-fixture regression records the current query ceiling rather than inventing a latency guarantee. Any future latency optimization must preserve the shared ordering/cursor contract and complete count semantics.
