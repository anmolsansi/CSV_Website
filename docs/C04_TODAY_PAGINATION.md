# C-04 Mixed-source Today pagination

Status: implementation/acceptance evidence for the C-04 completion package.

## Contract

The Today queue has one ordering tuple for every source:

`(due_is_null, due_at, -priority, type, id)`

This preserves the existing behavior: dated actions before undated actions, earlier due times first, higher priority first, deterministic source-type ordering, then stable source ID ordering.

Manual actions, follow-ups, deadlines, and interview preparation are normalized into the same item shape before cursor pagination. Pagination is applied once after the complete eligible population is merged and sorted. Counts describe the complete eligible population, not the current page.

The mixed-source cursor is signed and versioned as v2. It freezes `as_of` and binds the continuation to the authenticated user ID, account timezone, and `include_snoozed` setting. A tampered cursor is rejected. Reusing a valid cursor under another account or incompatible query context is rejected with a refresh instruction. Older cursor formats are intentionally rejected rather than silently interpreted under the new ordering contract.

`as_of` is frozen across continuation pages, but the queue is not a stored database snapshot. If mutable rows change between requests, pagination is best-effort and refresh is the recovery path. We do not claim immutable snapshot semantics.

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

Existing Playwright coverage in `frontend/tests/contacts-interviews.spec.ts` exercises Today interview cards, navigation from Today to application details, interview cancellation, API refresh, and disappearance of the cancelled Today card. Existing `frontend/tests/today.spec.ts` remains the browser regression suite for Today loading, retry, mutation, focus, and empty-state behavior.

## Performance scope

The repair removes the prior double-pagination wrapper and uses a fixed number of source queries independent of the number of continuation pages. The current implementation still materializes the eligible account-local Today population before sorting and taking `limit + 1`. That matches the pre-existing base Today implementation and fixes correctness, but it is not a claim that database row materialization is bounded by the page size. If account-scale measurements show this is material, candidate-window SQL pagination should be treated as a separate performance optimization rather than weakening cursor correctness.
