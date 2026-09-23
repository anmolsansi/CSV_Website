# JG-059 through JG-061 validation gates

This note records the repeatable repository gates for the mapped-import UI, F9 acceptance proof, and F10 version/journal foundation.

## Required CI

The branch is complete only when the repository CI workflow is green on the current head. The gate includes backend compilation, the full backend pytest suite, frontend lint/build, Playwright end-to-end coverage, schema parity, migration replay/up/down checks, and repository audit jobs.

## Targeted regressions

Backend:

```bash
cd backend
pytest -q tests/test_jg060_import_acceptance.py tests/test_jg061_undo_foundation.py tests/test_backup_contract.py tests/test_schema_parity.py
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npx playwright test tests/import-mapping.spec.ts
```

## Maximum import fixture

`test_maximum_fixture_records_actual_counts_queries_and_runtime` uses the frozen 2,000-record maximum. It records actual created-row count, SQL-statement count, and elapsed runtime in the test output. The evidence validates the current bounded contract only. It is not authorization to increase the 2,000-record or 10 MiB limits.

## Schema contract

Alembic head is `018`. Portable backup schema revision `2.13.0` carries `CsvRow.version` and `JobTrack.version`; older v2 backups default the additive version metadata to `1`. Private undo before-images are never portable backup content.
