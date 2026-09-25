# JG-001–JG-010 implementation checklist

Scope: finish and verify the first ten original tickets. Later feature extensions are changed only where needed for their complete recovery contract. No production deployment is part of this run.

Each item is complete only when its code review or named regression provides evidence. Backend groups depend on the transaction foundation; UI depends on complete backend dispatch; status updates depend on recorded results. Preserve existing implementation when acceptance already passes.

- [x] 01/40 — Map JG-001–010 acceptance criteria
- [x] 02/40 — Inspect current branch and preserve unrelated files
- [x] 03/40 — Locate backup transaction boundaries
- [x] 04/40 — Locate complete export dispatch
- [x] 05/40 — Locate bundle validation and file rollback
- [x] 06/40 — Locate UI preview and import routing
- [x] 07/40 — Reproduce late extension checksum failure
- [x] 08/40 — Reproduce ZIP extension omission
- [x] 09/40 — Add late database failure regression
- [x] 10/40 — Add verify-only no-write regression
- [x] 11/40 — Introduce shared restore transaction ownership
- [x] 12/40 — Reuse transaction in v1 and v2 restores
- [x] 13/40 — Join contact restore to outer transaction
- [x] 14/40 — Join mapping and audit metadata restore
- [x] 15/40 — Validate contact records before writes
- [x] 16/40 — Validate contact references and replay conflicts
- [x] 17/40 — Share one export snapshot across extensions
- [x] 18/40 — Export complete metadata inside ZIP
- [x] 19/40 — Validate ZIP extensions without weakening core schema
- [x] 20/40 — Restore ZIP extensions inside file transaction
- [x] 21/40 — Test failed bundle leaves no published files
- [x] 22/40 — Test metadata restore retry and conflicts
- [x] 23/40 — Test full graph and file round trip
- [x] 24/40 — Test extension verification counts
- [x] 25/40 — Add ZIP export API client
- [x] 26/40 — Route ZIP preview and restore correctly
- [x] 27/40 — Label metadata-only export accurately
- [x] 28/40 — Render consistent extension counts
- [x] 29/40 — Add real-API browser ZIP recovery test
- [x] 30/40 — Preserve invalid-file and retry UI behavior
- [x] 31/40 — Run backup contract/export/restore suites
- [x] 32/40 — Verify ownership and complete field inventory
- [x] 33/40 — Verify shared filter query semantics
- [x] 34/40 — Verify list/export/saved-view parity
- [x] 35/40 — Verify lifecycle replay and ownership
- [x] 36/40 — Verify writer event atomicity
- [x] 37/40 — Verify timezone DST and backfill contracts
- [x] 38/40 — Run PostgreSQL migration/concurrency checks
- [x] 39/40 — Run scoped browser and production build checks
- [x] 40/40 — Reconcile JG-001–010 status and evidence

## Completion evidence — 2026-09-24

JG-001–JG-010 are complete at the local verification level on branch `jg-001-010-completion`, based on `efcef42` plus this working-tree change. No hosted CI, staging acceptance, or deployment is claimed. The unrelated `backend/queries.md` and `backend/scraper.py` were preserved.

### Resulting behavior

- Complete ZIP export now includes document bytes and contact/interview/link, import-mapping, and supported audit metadata. Records-only JSON remains available and explicitly excludes files.
- Base, contact, and mapping restorers share one owned database transaction. A late validation or database failure leaves no partial records. Account row locking serializes concurrent restores; SQLite explicitly starts the outer transaction before savepoints.
- Export sections share one snapshot. Strict extension validation, references, replay conflicts, checksums, and aggregate limits are checked before writes. Verify-only previews do not persist records.
- ZIP restore preflights all sections and cleans files published by a failed attempt when database commit fails. This does not promise atomic filesystem/database recovery across process or machine crashes; existing reconciliation remains necessary.
- The browser routes ZIP and JSON correctly, distinguishes complete versus records-only backup, and renders extension counts consistently.
- Existing shared filtering, lifecycle event writers, timezone boundaries, and historical backfill passed acceptance. SQLite snooze assertions now compare canonical UTC instants and re-exported values without changing stored meaning.

### Ticket-to-test mapping

All backend paths below are relative to `backend/tests`; browser paths are relative to `frontend/tests`.

| Ticket | Acceptance evidence |
|---|---|
| JG-001 | `test_backup_contract.py`: field inventory, false/zero/null preservation, checksums, unknown fields and references; `test_complete_backup.py`: strict extension validation and total record limits |
| JG-002 | `test_backup_export.py`: complete sections, foreign-account exclusion, reference graph and migration; `test_complete_backup.py`: ZIP includes extensions |
| JG-003 | `test_backup_restore.py` and `test_complete_backup.py`: replay, conflicts, no-write preview, invalid checksum, late database failure and PostgreSQL concurrency; `test_document_backup.py`: commit failure removes attempt files and allows retry |
| JG-004 | `backup-restore.spec.ts`: real JSON and ZIP recovery, document bytes and contact recovery, invalid selection, legacy warning and retry |
| JG-005 | `test_filtered_exports.py`: shared account-scoped membership and deterministic sort semantics |
| JG-006 | `test_filtered_exports.py`: export parity, selected/foreign/empty IDs and formula-safe CSV |
| JG-007 | `filter-export-parity.spec.ts`: saved-view serialization, exact selected IDs, sorting, unsupported filters and errors; `release-workflows.spec.ts`: filtered top-five opening |
| JG-008 | `test_lifecycle_events.py`: idempotence, ownership, transaction rollback, metric definitions and migration |
| JG-009 | `test_lifecycle_mutations.py`: mutation writers, imports, bulk changes, replay and no-op status handling |
| JG-010 | `test_metric_timezones.py`: Kolkata midnight, 23/25-hour DST days, rolling windows, timezone validation, repeatable bounded backfill, unknown dates, dry-run and migration |

### Executed checks

| Check | Result | Local evidence |
|---|---|---|
| Full PostgreSQL backend suite | **598 passed**, zero skips | `/tmp/jg010-postgres.log`, `/tmp/jg010-postgres.xml` |
| Scoped SQLite backend suite | **110 passed, 1 skipped**; skipped PostgreSQL concurrency check passed above | `/tmp/jg010-sqlite.log`, `/tmp/jg010-sqlite.xml` |
| Chromium recovery/filter/release workflows | **13 passed**, including setup | `/tmp/jg010-browser.log` |
| Link-opening helper tests | **8 passed** | `/tmp/jg010-helpers.log` |
| Frontend production build | **Passed**; existing large-chunk warning remains | `/tmp/jg010-build.log` |

Temporary logs are local artifacts, not durable hosted CI links. Backend deprecation warnings remain. Full SQLite and every browser feature were not certified by this scoped run.

### Repeatable checks

Use the isolated test environment described in `development.md`, with separate disposable PostgreSQL unit/schema databases and a separate browser database. Backend fixtures recreate tables: never supply production URLs. Disable maintenance, reminders, URL checks, and SMTP. From `backend`, with the configured test virtual environment:

```sh
python -m pytest tests -q --tb=short
# With SQLite instead of PostgreSQL, run the scoped contract suite:
python -m pytest tests/test_complete_backup.py tests/test_backup_contract.py tests/test_backup_restore.py tests/test_backup_export.py tests/test_document_backup.py tests/test_contact_backup_contract.py tests/test_filtered_exports.py tests/test_lifecycle_events.py tests/test_lifecycle_mutations.py tests/test_metric_timezones.py -q --tb=short
```

With a test-only backend at localhost:8000, from `frontend`:

```sh
VITE_API_URL=http://localhost:8000 npx playwright test tests/backup-restore.spec.ts tests/filter-export-parity.spec.ts tests/release-workflows.spec.ts --project=chromium --reporter=line
node --test unit/open-jobs.test.mjs
npm run build
```

### Remaining project gates

JG-011–JG-064 are not closed by these results. Mixed-source Today pagination, broader SQLite/browser issues, real staging/provider checks, hosted CI for this change, and production release remain separate work. Broader C packages can overlap this implementation without being fully completed. No migration was added by this change.
