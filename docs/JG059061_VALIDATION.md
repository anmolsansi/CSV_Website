# JG-059 through JG-061 validation gates

This note records the repeatable repository gates for the mapped-import UI, F9 acceptance proof, and F10 version/journal foundation.

## Local acceptance status

JG-059, JG-060, and JG-061 are locally verified on branch `jg-059-061-import-ui-undo-foundation`.

The implementation gate passed in CI run #410 on commit `bb86f5f59db284e91334c0e226f78b9a53f375db`. That run completed successfully after correcting two stale backup-test expectations without weakening the production schema: generic backup fixtures now include the required optimistic `version`, and the availability backup regression expects schema revision `2.13.0`.

The canonical roadmap completion state is part of this branch’s final documentation gate. The temporary automation used to edit the large roadmap file is removed before merge.

This document records local implementation acceptance only. It does not claim staging acceptance or production release.

## Required CI

The branch is complete only when the repository CI workflow is green on the current implementation head. The gate includes backend compilation, the full backend pytest suite, frontend lint/build, Playwright end-to-end coverage, schema parity, migration replay/up/down checks, and repository audit jobs.

CI run #410 passed those repository gates on `bb86f5f59db284e91334c0e226f78b9a53f375db`.

## Targeted regressions

Backend:

```bash
cd backend
pytest -q tests/test_jg060_import_acceptance.py tests/test_jg061_undo_foundation.py tests/test_jg061_backup_versions.py tests/test_backup_contract.py tests/test_schema_parity.py
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npx playwright test tests/import-mapping.spec.ts tests/dashboard.spec.ts
```

The dashboard keeps the established accessible upload name `Upload CSV file`, while the control accepts both CSV and JSON. The dashboard upload regression exercises the deliberate map → review → commit path instead of treating file selection as an immediate write. Import-specific assertions read row values from the existing `row.data` API envelope, and the stale-preview recovery state exposes one unambiguous `Regenerate preview` action.

JG-059 coverage includes renamed-header preview/commit, preview-only zero writes, explicit title updates preserving user-managed fields, expired-preview regeneration, and lost-response replay without duplicate writes.

JG-060 coverage includes parser edge cases, bounded 2,000-row and 10 MiB limits, zero destination writes for over-limit input, same-account concurrency/replay behavior, saved-mapping header mismatch handling, and spreadsheet-formula-safe rejected-row reporting.

JG-061 coverage includes optimistic version defaults/constraints on the owned mutable records in scope, ActionJournal ownership and request identity, bounded seven-day journal retention, reverse-payload checksum handling, terminal journal pruning, backup compatibility, and migration/schema parity. Public undo execution remains owned by the later JG-062 ticket.

## Maximum import fixture

`test_maximum_fixture_records_actual_counts_queries_and_runtime` uses the frozen 2,000-record maximum. It records actual created-row count, SQL-statement count, and elapsed runtime in the test output. The evidence validates the current bounded contract only. It is not authorization to increase the 2,000-record or 10 MiB limits.

## Schema contract

Alembic head is `018`. Portable backup schema revision `2.13.0` carries `CsvRow.version` and `JobTrack.version`; older v2 backups default the additive version metadata to `1`. Private undo before-images are never portable backup content.

## Status boundary

- Local implementation: verified.
- CI: passed on implementation commit `bb86f5f59db284e91334c0e226f78b9a53f375db`, run #410.
- Staging acceptance: not claimed here.
- Production release: not claimed here.
