# C-06 Browser Time Determinism — Completion Evidence

Date: 2026-09-27

Tracking issue: #165

Implementation PR: #167

Baseline: `3ac6239c6d7cd1935be0c2457c6fd13f6761b60a`

Validated source head before this evidence-only commit: `3d89942ac56e2c7963dc2f606bf151fa058daa15`

Validated pull-request merge ref: `69ffa44d1737f224105f6bc47afa3ec2cfcdee89`

## Scope

C-06 makes browser-time acceptance deterministic without changing JobGrid product-time semantics. The product already interprets `datetime-local` input as browser-local wall time and serializes it to a UTC instant. The defect was in the browser test fixtures: they created local-looking input text by stripping the timezone from a UTC ISO value and then compared that wall-clock text directly with the outgoing UTC payload.

The repair therefore stays in test/CI infrastructure. No product route, API contract, database schema, migration, or runtime behavior changes are part of C-06.

## Implemented contract

- `frontend/playwright.config.ts` keeps the established `chromium` project name for release-CI compatibility but gives it an explicit `UTC` timezone.
- `chromium-kolkata` repeats C-06 scenarios in `Asia/Kolkata`.
- `chromium-new-york` repeats C-06 scenarios in `America/New_York`.
- `frontend/tests/today.spec.ts` now creates browser-local wall-clock input independently from the expected outgoing UTC instant.
- `frontend/tests/c06-browser-time.spec.ts` freezes the browser clock and explicitly tests wall time, UTC payload/persistence, account timezone display/day boundaries, cancellation, validation, failed-request draft retention, keyboard focus restoration, reload persistence, and real-API snooze/reschedule behavior.
- `.github/workflows/c06-browser-timezones.yml` verifies that all three timezone projects collect C-06 tests, runs those tests against a migrated PostgreSQL-backed FastAPI instance, and uploads evidence artifacts.

## C-06 checkpoint mapping

| Checkpoint | Evidence |
| --- | --- |
| C-06.01 | Fixtures distinguish local wall-clock strings from fixed instants; no stripped UTC string is treated as local semantics. |
| C-06.02 | Tests derive the expected UTC instant separately with the browser timezone and assert it independently from the `datetime-local` value/display. |
| C-06.03 | Explicit Playwright coverage: `UTC`, `Asia/Kolkata`, `America/New_York`. |
| C-06.04 | Fixed browser clock plus `America/New_York` account timezone verifies account-day behavior independently from device timezone. |
| C-06.05 | Mock handlers explicitly fulfill deterministic responses while capturing/validating outgoing request payloads. |
| C-06.06 | Future snooze, invalid/empty input, past input, reschedule, reload persistence, cancellation, failed-request draft retention, and keyboard focus restoration are covered. |
| C-06.07 | A real migrated backend is used for one snooze and one follow-up reschedule; stored instants are read back and compared with browser-derived expected UTC instants. |
| C-06.08 | Dedicated multi-zone suite runs in all three zones; the complete Chromium suite also runs with an explicit UTC browser timezone. No host-timezone forcing is used as a substitute for coverage. |

## Validation evidence

### Dedicated C-06 Browser Timezones workflow

GitHub Actions run: `36324192952`

Result: **PASS**

- Collection guard confirmed `chromium`, `chromium-kolkata`, and `chromium-new-york` all contain C-06 scenarios.
- **16/16 tests passed**: one shared auth/setup test plus five C-06 scenarios in each of the three browser timezones.
- Real-API snooze and reschedule persistence passed in every declared timezone.
- Evidence artifact: `c06-browser-timezones-69ffa44d1737f224105f6bc47afa3ec2cfcdee89`, artifact ID `10933732073`.

### Full CI workflow

GitHub Actions run: `36324192979`

Result: **PASS**

- Alembic migrated to revision `018` before browser execution.
- Frontend production build passed.
- Backend compile check passed.
- PostgreSQL backend suite: **603/603 passed**.
- Tab-helper safety regressions: **8/8 passed**.
- Focused JG-023 browser release workflow: **2/2 passed**.
- Complete explicit-UTC Chromium collection: **186 tests in 31 files**.
- Complete explicit-UTC Chromium run: **186/186 passed**.

## Failures found while hardening the harness

Three test-harness issues were found and corrected before acceptance:

1. Renaming the established `chromium` project broke the existing JG-023 CI selector. The project name is now preserved while its timezone is made explicit.
2. The first real-API fixture used a 2030 snooze and correctly hit JobGrid's 365-day snooze limit. The deterministic future fixture was moved inside the product contract rather than weakening production validation.
3. The account-timezone check originally matched two visible copies of `America/New_York`. The assertion now targets the exact Today subtitle instead of relying on an ambiguous text locator.

None of these required a product-semantic change.

## Completion result

C-06 implementation and acceptance evidence are complete. The historical two timezone-sensitive Today failures are repaired at the fixture-contract level, explicit multi-zone coverage is enforced, real API persistence is verified, and the full browser/backend regression matrix is green.

C-07 remains responsible for the broader release-CI policy matrix, including SQLite release enforcement, branch protection/required checks, and final consolidation of release evidence. C-06 does not claim those C-07 responsibilities.
