# JobGrid Build Guide

This guide describes behavior implemented in the repository. It is not a copy of the future roadmap.

## Backup implementation status

JG-001 freezes and validates the portable backup **v2 record contract** in `backend/app/backup_schemas.py`.

JG-002 activates complete v2 export and adds stable restore identity persistence:

- `GET /crm/backup/export` remains backward-compatible and returns v1 by default.
- `GET /crm/backup/export?version=2` returns the complete validated v2 document.
- `backend/app/services/backups.py` owns consistent-snapshot export, backup-local references, relationship translation, counts, checksum, validation, preflight, and restore domain behavior.
- `backend/app/models.py` contains `BackupImportMap`.
- Alembic revision `003` creates `backup_import_maps` and its replay-identity uniqueness index.

JG-003 activates the backend restore contract:

- `POST /crm/backup/import?mode=verify_only` validates and preflights without writing.
- `POST /crm/backup/import?mode=merge_missing` validates first, then restores in one destination transaction.
- `backend/app/routers/backup.py` owns the live backup export and import transport.
- The older backup handlers in `routers/crm.py` remain as compatibility source code but are removed from the live route table in `app/main.py`. There is one authoritative live handler for each backup method/path.
- JG-004 adds the dedicated restore preview/interface on the Dashboard, using this backend contract without changing restore semantics.

## JG-004 restore interface

`frontend/src/components/BackupRestore.jsx` owns the portable-backup UI and
`frontend/src/api/client.js` owns its transport calls. The Dashboard keeps ordinary data
export separate from backup actions.

The UI flow is deliberate:

1. **Export complete backup** requests `GET /crm/backup/export?version=2`.
2. Choosing a JSON file immediately calls `POST /crm/backup/import?mode=verify_only`.
3. Parse/schema/checksum errors are shown as failures and no Restore button is rendered.
4. A verified preview shows section `created`/`skipped`/`conflicts` counts, merge policy,
   and safe warning codes. Legacy warnings state that missing history cannot be recovered.
5. The separate **Restore backup** action calls `mode=merge_missing`; duplicate clicks are
   disabled while the request is active.
6. A failed import keeps the selected file and verified preview so **Retry restore** is
   possible. HTTP failure never renders a completed state.
7. Successful restore refreshes Dashboard rows and re-fetches Applications and Companies. If refresh fails, restore success remains
   truthful and the UI asks the user to reload rather than implying the transaction failed.
8. **Download restore summary** emits only `backup_id`, mode, verified flag, section counts,
   timestamp, and warning codes/sections. It never embeds restored records or private text.

The browser holds the selected `File` object only in component memory. Choosing a different
file clears stale preview/result state. Reloading or clearing the file discards it.

Focused interface verification:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/backup-restore.spec.ts --project=chromium
```

`backup-restore.spec.ts` covers invalid-file gating, explicit legacy limitations,
retry-after-import-failure with selection preserved, and a real v2 applied-job round trip
that verifies company/status/date after reload. The existing application-memory regression
remains part of the affected browser suite.

## Why v2 exists

The original portable backup is lossy. A backup can contain an application record while the old restore path does not reconstruct the same application state. V2 makes all durable sections and persisted fields explicit before restore code constructs ORM objects.

Source database primary keys and `user_id` values are never portable authority. Export replaces source identities with opaque backup-local references. Restore allocates destination IDs and binds every restored record to the authenticated destination user.

## V2 document shape

A v2 document contains exactly:

- `version`: `"2.0"`
- `backup_id`: UUID string
- `exported_at`: UTC ISO-8601 timestamp
- `schema_revision`: currently `"2.2.0"`
- `sections`: the eleven current v2 sections
- `counts`: exact record count for every section
- `checksum_sha256`: lowercase SHA-256 digest of canonical `sections` JSON

The eleven current sections are:

1. `csv_rows`
2. `url_history`
3. `job_tracks`
4. `lifecycle_events`
5. `saved_views`
6. `sessions`
7. `audit_events`
8. `applypilot_batches`
9. `column_preferences`
10. `user_goal`
11. `user_profile`

Every record has a non-empty `backup_ref` unique within its section. Nullable fields remain present as keys, preserving the difference between null, empty text, `false`, and zero.

## Export identity and references

JG-002 generates a fresh `backup_id` for each export. Within that document, each record receives an opaque deterministic UUIDv5 reference derived from the backup ID, section, and source record identity. This makes repeated references inside one backup stable without exposing a source database ID as a reusable authorization identifier.

Relationships are translated as follows:

- `CsvRow.duplicate_of_id` -> `duplicate_of_ref`
- `JobTrack.csv_row_id` -> `csv_row_ref`
- `JobLifecycleEvent.csv_row_id` -> `csv_row_ref`
- `JobLifecycleEvent.job_track_id` -> `job_track_ref`
- `AuditEvent.session_id` -> `session_ref`
- known `AuditEvent.entity_id` targets -> typed `entity_ref`
- `ApplyPilotBatch.session_id` -> `session_ref`

`JobTrack.session_id` remains exported and restored as scalar text because the ORM does not declare it as a `SearchSession` foreign key. Restore does not infer an active relationship from that text field.

If a declared active relationship points outside the authenticated snapshot, export or import fails with the safe `conflicting_reference_graph` contract rather than leaking another account's record or silently manufacturing a target.

Audit events are different because historical targets can legitimately disappear. A known target that is present gets `entity_ref`. A detached legacy identifier is stored only as namespaced historical metadata during restore and is not accepted as destination authority.

## Consistent export snapshot

The authenticated request session is not reused for the v2 data read. `export_backup_v2()` opens a dedicated connection and read transaction so a GET cannot commit unrelated request-session state.

Isolation is:

- PostgreSQL: `REPEATABLE READ`
- SQLite/local tests: `SERIALIZABLE`

All eleven current sections are read within one transaction. The service fully builds and validates the document before the route serializes the response, so transaction resources close even if serialization fails.

## Canonical checksum

The checksum covers `sections` only. It detects accidental corruption and is not an authenticity signature.

Canonical serialization is:

```python
json.dumps(
    sections,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
```

The SHA-256 lowercase hexadecimal digest is stored in `checksum_sha256`. `counts.<section>` must exactly equal the number of records in that section.

## Record contracts

### CSV rows

`CsvRowBackupV2` exports `upload_batch_id`, timestamps/state fields, every frozen `CSV_COLUMNS` text field, and `duplicate_of_ref`. The source `id` becomes `backup_ref`; source ownership is not exported.

### URL history

`UrlHistoryBackupV2` exports `url` and `first_seen_at`.

### Job tracks

`JobTrackBackupV2` exports every non-identity persisted field, including application status/timestamps, notes, `session_id`, open counts, and created/updated timestamps. `csv_row_id` becomes `csv_row_ref`.

### Lifecycle events

`JobLifecycleEventBackupV2` exports the durable event key, exact job URL, kind, occurrence/recording timestamps, source, allowlisted payload, and portable CSV-row/application references when those relationships still exist. Restore inserts these historical records directly. It never calls the live lifecycle writer or infers fresh visit/application facts from restored rows.

Older v2 documents created before JG-008 can omit `lifecycle_events` and its count. Validation treats that missing section as empty while checking the checksum against the original nine-section payload, so existing backups remain valid.

### Saved views and sessions

Saved views export `name`, `view_type`, `filters`, `is_pinned`, and `created_at`. Search sessions export `name`, start/end timestamps, and notes.

### Audit events

Audit events export event type, entity type, metadata, timestamp, session relationship, and typed entity relationship where resolvable. Historical detached identifiers remain metadata only.

### ApplyPilot batches

Batches export name, payload, status, job count, timestamps, and a validated session reference when present.

### Column preferences, user goal, and user profile

Column preferences and goals export only portable preference/goal values. The `user_profile` section exports exactly one portable account preference, the validated IANA timezone. It does not export account ID, email, authentication identities, or provider data.

On restore, profile timezone is applied to the authenticated destination account and the backup reference is persisted in `BackupImportMap`. Replaying the same backup is skipped, so a later manual timezone change is not overwritten by a retry.

## Excluded data

Portable backups exclude account IDs/emails as authority, all other `User` identity fields, `OAuthIdentity` records, provider identities, JWTs, signing material, credentials, and server filesystem paths.

`BackupImportMap` is operational restore metadata and is not exported. It maps a destination user's `(backup_id, section, backup_ref)` to a destination `target_id` and makes retries stable.

## BackupImportMap persistence

Alembic revision `003_backup_import_maps.py` creates:

- `id` primary key
- `user_id` with `users.id` foreign key and cascade delete
- `backup_id`
- `section`
- `backup_ref`
- `target_id`
- `created_at`

The unique identity index covers `(user_id, backup_id, section, backup_ref)`. The map contains no source authorization. JG-003 writes it in the same transaction as restored data and uses a nested savepoint for uniqueness races.

For merge restores, the destination user row is locked on PostgreSQL before writes. This serializes restores for one account while still allowing unrelated accounts to restore independently. Database uniqueness remains the final consistency boundary.

## Restore API

`POST /crm/backup/import` accepts multipart form data with a `file` part and one query mode:

- `mode=merge_missing` is the default and writes only after complete preflight validation.
- `mode=verify_only` returns the same section-level plan without creating records or import mappings.

A successful response has this shape:

```json
{
  "backup_id": "uuid",
  "mode": "merge_missing",
  "counts": {
    "csv_rows": {"created": 2, "skipped": 0, "conflicts": 0}
  },
  "warnings": [],
  "verified": true
}
```

Every one of the eleven current sections is present in new v2 exports and restore `counts`, even when its values are all zero. Revision 2.1.0 files may omit `user_profile`; revision 2.0.0 files may omit both `lifecycle_events` and `user_profile`. Missing additive sections are treated as empty only after their original checksum shape is preserved for validation. Warnings contain safe codes plus optional `section` and `backup_ref`; they never contain notes, job descriptions, credentials, or another user's values.

## Preflight and validation order

The application rejects a backup-import request whose declared multipart `Content-Length` exceeds 21 MiB before the multipart parser runs. This leaves up to 1 MiB for multipart framing while retaining the exact JSON-file boundary. The route independently reads at most 20 MiB plus one byte from the uploaded file, so a missing or inaccurate `Content-Length` cannot bypass the 20 MiB backup limit. Oversize input is rejected before JSON parsing. The domain service then:

1. Parses strict UTF-8 JSON and rejects duplicate keys/non-finite numbers.
2. Validates the full v2 schema.
3. Validates timestamps, section counts, field/record limits, and unique `backup_ref` values.
4. Validates the complete active reference graph.
5. Recomputes and validates the canonical checksum.
6. Classifies destination actions as `created`, `skipped`, or `conflicts`.
7. Writes only when `mode=merge_missing`.

`verify_only` stops after classification and commits no restore state.

## Transactional restore order

A v2 merge happens in one destination transaction. Records are created or mapped in dependency order:

1. search sessions
2. CSV rows without `duplicate_of_id`
3. CSV duplicate relationships after all row IDs are known
4. URL history
5. saved views
6. column preferences
7. user goal
8. user profile timezone
9. job tracks after CSV references are resolvable
10. lifecycle events after CSV-row and job-track references are resolvable
11. ApplyPilot batches after session references are resolvable
12. audit events last, after every supported target section has a destination identity

If any insert, mapping, or reference resolution fails, the dedicated restore session rolls back the entire operation, including `BackupImportMap` rows.

## Retry and merge behavior

A prior `BackupImportMap` is authoritative only inside the authenticated destination user's scope. A mapping whose target no longer exists produces `409 stale_restore_mapping`; it is not silently redirected to another account.

Natural-key merge rules are:

- CSV row: destination account + URL
- URL history: destination account + URL
- job track: destination account + URL
- saved view: destination account + `view_type` + `name`
- column preference: destination account singleton
- user goal: destination account singleton
- lifecycle event: destination account + `event_key`; equal replay is skipped and conflicting content preserves the destination record

When a natural key already exists, destination data wins. Equivalent values are counted as `skipped`; differing values are counted as `conflicts` and return `destination_record_preserved`. Restore never overwrites a destination status, note, timestamps, filters, preferences, or goal simply because an older backup contains another value.

Records without a stable natural key, including sessions, batches, and audit events, rely on `BackupImportMap`. Re-importing the same backup produces no duplicate destination entities.

## Legacy v1 compatibility

V1 input is still accepted. Its content is first passed through the JG-001 loss-aware adapter and receives `incomplete_legacy_backup` warnings. A deterministic compatibility backup ID/reference is derived from canonical v1 content so retries can be tracked without trusting source database IDs.

Known v1 CSV rows, applications, saved views, sessions, batches, and audit events are restored when their required legacy values are present. Relationship information that v1 never carried remains detached and is reported with warnings rather than fabricated. Legacy audit `entity_id` values are retained only as namespaced historical metadata, never as active links.

Missing v2-only sections produce explicit `legacy_section_absent` warnings. The importer does not invent omitted application dates or relationships.

## Limits and error behavior

The frozen JG-001/JG-003 contract enforces:

| Limit/error | Result |
|---|---|
| Declared multipart request body over 21 MiB | `413 backup_too_large` before multipart parsing |
| Uncompressed UTF-8 JSON over 20 MiB | `413 backup_too_large` |
| More than 20,000 total records | `413 record_limit_exceeded` |
| `notes` over 20,000 characters | `413 field_too_large` |
| `jd_text` over 1 MiB UTF-8 | `413 field_too_large` |
| Invalid JSON/schema/checksum | `400` with a bounded domain code |
| Broken active reference graph | `409 conflicting_reference_graph` |
| Stale/incompatible replay mapping | `409` with a bounded mapping code |
| Missing authentication | `401` from the existing auth dependency |
| Unexpected write failure | `500 restore_failed` after rollback |

The route logs a generated operation ID, safe outcome code, mode, created count, and elapsed time. It does not log backup records, notes, job descriptions, or credentials.

## Version compatibility

| Request/input | Current behavior |
|---|---|
| `GET /crm/backup/export` | Legacy v1 export, unchanged default |
| `GET /crm/backup/export?version=1` or `1.0` | Legacy v1 export |
| `GET /crm/backup/export?version=2` or `2.0` | Complete validated v2 export |
| `POST /crm/backup/import?mode=verify_only` with v2 | Full validation/preflight; no writes |
| `POST /crm/backup/import?mode=merge_missing` with v2 | Transactional restore of all sections present in the validated v2 document |
| v1 import | Compatibility restore with explicit incomplete-history warnings |

Do not remove the v1 export default until all v2 consumers have passed their compatibility gates.

## Verification

Focused backup validation:

```sh
cd backend
python -m pytest \
  tests/test_backup_contract.py \
  tests/test_backup_export.py \
  tests/test_backup_restore.py -q
```

The JG-003 restore suite proves:

- an applied application restores with company, notes, status, applied/follow-up dates after a fresh request
- all current v2 sections restore, including lifecycle records when present, and portable references remap to destination IDs
- `verify_only` writes neither user data nor import mappings
- the same backup retry is idempotent
- concurrent same-account retries serialize on PostgreSQL and create one destination entity/mapping per backup record
- an injected failure in the final audit-event section leaves zero partial restored records or mappings
- an existing destination application keeps its newer status/note/company values
- a malicious reference containing another account's database ID is rejected before writes
- v1 input returns explicit incomplete-history warnings while preserving known application memory
- the 20 MiB + one byte file boundary returns `413`; the application also rejects declared multipart requests above its 21 MiB transport guard

Run the wider backend suite, compile check, frontend build, and Playwright through repository CI before merge.

## Rollback and recovery

JG-003 uses the additive migration introduced by JG-002 and does not add another schema migration.

For an application rollback:

1. Revert the JG-003 route/service activation to stop v2 restore requests.
2. Keep `backup_import_maps` unless a separately reviewed migration explicitly removes it.
3. Keep restored user records. A code rollback must not delete user history.
4. Keep v1 export compatibility.
5. Database-level disaster recovery continues to use `scripts/backup.sh` and `scripts/restore.sh`; production recovery proof belongs to JG-024.
6. The dedicated restore UI remains gated by JG-004 acceptance, so rolling back JG-003 does not require migrating UI-owned state.

## Change discipline

When a persisted model field is added, removed, or renamed, update the frozen backup field inventory and tests deliberately. Do not weaken the inventory check. Decide whether the field is exported, reconstructed, excluded with a reason, or blocked on a migration, then update schemas, export/restore adapters, examples, tests, and documentation together.

## JG-005 account-scoped query contract

`backend/app/services/row_queries.py` owns immutable `RowQuery` and `ApplicationQuery` inputs plus the shared SQLAlchemy predicate and ordering builders. Authenticated routes supply `user.id`; query DTOs never accept account identity from client input.

`GET /rows` keeps its existing parameters, pagination envelope, filter options, stats, current numeric-sort adapter, and deterministic `CsvRow.id DESC` tie breaker. The applications list keeps its existing filter names, invalid-sort fallback, computed priority/triage handling, pagination envelope, and `JobTrack.id DESC` tie breaker.

The legacy `filtered_query` function remains as a compatibility wrapper for export callers until JG-006 migrates export scope. JG-005 deliberately does not change export behavior or repair the known SQLite numeric expression limitation reserved for JG-018.

Verification: `python -m compileall app`, `pytest tests/test_query_contracts.py -q`, and `pytest tests/ -q` from `backend`.


## JG-006 shared filtered export contract

JG-006 routes ordinary Dashboard and Applications exports through the same account-scoped query contracts used by the live tables. It does not change portable backup behavior, application-versus-visit semantics, or database schema.

`GET /crm/export/dashboard` now accepts the complete `RowQuery` filter/sort set using the same snake_case wire names as `GET /rows`: `sort_by`, `sort_dir`, `ats_group`, `location_group`, `search_bucket`, `decision`, `sponsorship_status`, `fit_category`, `seniority_level`, `work_model`, `role_family`, `salary_min`, `salary_max`, `q`, `opened_only`, `unopened_only`, `has_error`, `jd_missing`, and `openable_only`. Filtered export does not reuse table pagination. It applies the same primary sort, null-last behavior, and `CsvRow.id DESC` tie breaker as the table.

`GET /crm/export/applications` accepts every `ApplicationQuery` filter already supported by the applications table, including date/score/follow-up and row-derived filters, plus `sort_by` and `sort_dir`. Non-computed ordering uses the shared SQL query builder. `priority_score` and `triage` preserve the table's existing Python-computed ordering behavior, including the stable descending-ID tie order.

Both export endpoints accept additive `scope=all|filtered|selected`:

- omitted `scope` preserves legacy behavior: supplied filters apply, and valid `row_ids` intersect that result;
- `scope=all` exports the authenticated account's unarchived rows/applications without filter predicates;
- `scope=filtered` applies the shared filter contract with no offset or limit;
- `scope=selected` requires a non-empty comma-separated list of at most 500 positive IDs owned by the authenticated account. Missing, malformed, or foreign IDs reject the whole request instead of falling back to all data.

Dashboard `columns` is an ordered allowlist of persisted `CSV_COLUMNS`. Unknown or empty requested columns return HTTP 400. `clicked` and `clicked_at` remain appended compatibility fields.

CSV serialization is spreadsheet-safe by default. Text beginning with `=`, `+`, `-`, `@`, or control whitespace followed by one of those markers is prefixed with a single quote only in the downloaded CSV stream. Stored values and JSON exports remain lossless. Export rows are serialized incrementally in bounded iteration rather than duplicated into a second in-memory list. Empty CSV behavior remains an empty body and JSON remains `[]`.

Export audit events contain only the exported count, format, and a fixed map of boolean filter-presence flags. Filter values, URLs, notes, job descriptions, and other private text are not written into export event metadata.

Focused verification:

```sh
cd backend
python -m compileall app
pytest tests/test_filtered_exports.py -q
pytest tests/test_query_contracts.py -q
pytest tests/ -q
```

The JG-006 regression fixture proves 61 filtered Dashboard matches have the exact same order as all paginated `GET /rows` pages, selected scope never falls back to all rows, foreign selected IDs reject the complete request, CSV formula protection does not mutate JSON/storage, requested column order is preserved, and application export consumes row-derived shared filters and stable ordering.

Rollback is code-only: revert the JG-006 router/service changes together. There is no migration and no persisted export-format transformation to reverse. Local verification does not claim staging acceptance or production release.


## JG-007 shared browser and saved-view query serialization

`frontend/src/api/queryParams.js` is the frontend source of truth for Dashboard and Applications query serialization. It accepts the documented camelCase UI names and snake_case wire aliases, normalizes booleans and numbers explicitly, and emits the backend's snake_case query contract.

The same serializer is used for list loads, Dashboard top-five retrieval, filtered exports, and Saved View navigation. Export requests always send an explicit `scope` and sort, never copy `page`/`page_size`, and selected scope sends only selected IDs for the backend ownership check.

Saved Views serialize filter state into the destination URL. Dashboard and Applications hydrate their initial filter and sort state from that URL after reload. Unknown keys or invalid booleans/numbers render a recoverable error with a clear action instead of being ignored silently.

Dashboard and Applications record the last settled browse query. Export is disabled while a browse request is loading, snapshots the current query at click time, and refuses to export if that snapshot does not match the settled result. HTTP export failures show an error and never report a successful download.

Focused verification:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/filter-export-parity.spec.ts --project=chromium
```

JG-007 changes no database schema and does not change the JG-005/JG-006 backend filtering or ownership contracts.

## JG-008 durable lifecycle ledger

JG-008 added durable lifecycle storage. JG-009 wires the existing mutation paths into that storage. JG-010 adds account timezone and historical backfill primitives without activating the JG-011 analytics read-path cutover.

### Metric definitions

- **Saved** means a `JobTrack` exists. `count_saved()` uses `JobTrack.created_at` for an optional time window.
- **Visited** means one durable `first_visited` lifecycle fact. It is not inferred from a `JobTrack`.
- **Applied** means one durable `first_applied` lifecycle fact. It is not inferred from the current status value.
- Lifecycle time windows use `JobLifecycleEvent.occurred_at`, never the recording/update time.

These functions live in `backend/app/services/lifecycle.py`. Live visit/application writers now use the JG-009 transaction-owned mutation helpers described below.

### Storage contract

Alembic revision `004_job_lifecycle_events.py` adds `job_lifecycle_events` with:

- account ownership through `user_id`
- unique `(user_id, event_key)`
- `job_url` retained as private durable domain data
- nullable `csv_row_id` and `job_track_id` references with `ON DELETE SET NULL`
- `kind`, `occurred_at`, `recorded_at`, `source`, and JSON `payload`
- composite index `(user_id, occurred_at, kind)`

Supported kinds are `first_visited`, `first_applied`, `status_changed`, `applied_date_corrected`, and `followup_changed`. First-event keys are deterministic SHA-256-derived keys from account, exact URL, and kind. Transition events require a caller-provided UUID operation ID. Payload fields are allowlisted per kind and do not accept notes or resume content.

### Transaction and replay behavior

`write_event()` validates ownership of any linked CSV row/application and never commits. The caller owns the transaction, so a parent mutation and its lifecycle fact roll back together.

PostgreSQL and SQLite both use `ON CONFLICT DO NOTHING` against the owner/event-key identity. First-event replay returns the already-recorded fact and preserves its original occurrence. Reusing a transition operation UUID with different event input raises an `event_key_conflict` domain error.

### Backup behavior

Backup schema revision `2.1.0` adds `lifecycle_events`. Export translates row/application IDs to backup-local references. Restore resolves those references and inserts the historical event record directly, with a `BackupImportMap` entry for replay identity. Restore never calls `write_event()`, so a clicked row or applied JobTrack does not create a new first event during recovery.

Older schema-revision `2.0.0` v2 files without a lifecycle section remain valid. Their checksum is verified over the original section set, then the missing lifecycle section is treated as empty.

### Verification

Focused backend checks:

```sh
cd backend
python -m pytest tests/test_lifecycle_events.py tests/test_backup_contract.py -q
python -m pytest tests/test_backup_export.py tests/test_backup_restore.py tests/test_application_memory.py -q
python -m compileall app
```

The focused lifecycle suite covers deterministic replay, explicit SQLite conflict behavior, payload/kind validation, cross-account reference rejection, caller rollback, and distinct saved/visited/applied counts. Backup coverage verifies lifecycle occurrence/recording timestamps survive round trip and restore emits no derived `first_visited` or `first_applied` events.

### Rollback

Application code can be rolled back while leaving revision 004 and stored lifecycle history in place. Old readers ignore the additive table. Do not delete lifecycle history to make metrics match. A database downgrade that drops the table is destructive and is not the normal application rollback path.

## JG-009 lifecycle mutation wiring

JG-009 connects the existing mutation routes to the lifecycle ledger. It does not change the public analytics response definitions yet.

### Writer behavior

- `POST /rows/{row_id}/click` records `first_visited` only when the row changes from unvisited to visited. Repeating the click does not add another lifecycle fact.
- `POST /crm/from-row/{row_id}` and `POST /crm/from-rows/bulk` still create or reuse `JobTrack` records. A saved application is represented by the `JobTrack` itself and never implies a visit.
- Single and bulk application patches record `status_changed` only when status actually changes. Moving status backward does not erase the first known application date.
- The first transition from no `applied_at` to a real date records `first_applied` at that application date. Explicit edits to an existing application date record `applied_date_corrected`.
- Follow-up patches and presets record `followup_changed` only when the date actually changes.
- ApplyPilot result import records a first application from the declared `submitted_at`. If ApplyPilot explicitly reports `submitted=true` without a timestamp, the existing recording-time fallback is retained.
- External application import preserves declared `applied_at` and `follow_up_at` values. An imported status of `applied` without an application date does not invent one, so status and application evidence remain separate facts.
- Backup restore remains a historical replay path and inserts exported lifecycle records directly. It does not invoke live mutation helpers or manufacture fresh facts.

### Transactions, ownership, and replay

Lifecycle state and event writes share one SQLAlchemy transaction. `backend/app/services/lifecycle.py` owns the mutation rules while `rows.py` and `crm.py` own authentication, request validation, and HTTP error mapping.

Bulk application patch and row-to-application routes resolve the complete requested ID set for the authenticated account before changing any record. If any target is missing or belongs to another account, the request fails before mutation. A lifecycle failure rolls back both application state and lifecycle facts.

Transition-capable routes accept an optional `X-Operation-ID` request header containing a UUID. When omitted, JobGrid creates a request UUID. A stable request UUID is expanded into deterministic per-application/per-event child IDs so one bulk request can write several independent transition facts. Reusing an operation ID for conflicting transition input returns HTTP `409` and the transaction is rolled back.

The header is optional for existing clients. Clients that retry mutations after an uncertain network outcome should reuse the same UUID.

Lifecycle mutation logs contain only the action name, operation/request UUID, safe outcome code, affected count, and elapsed milliseconds. They do not log job URLs, notes, imported row values, or tokens.

Example:

```sh
curl -X PATCH http://localhost:8000/crm/applications/42 \
  -H "Content-Type: application/json" \
  -H "X-Operation-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"status":"applied"}'
```

### Verification

Focused checks:

```sh
cd backend
python -m pytest tests/test_lifecycle_mutations.py -q
python -m pytest tests/test_application_memory.py tests/test_rows.py -q
python -m compileall app
```

`test_lifecycle_mutations.py` covers all active writer paths, repeat-same-status behavior, bulk all-or-nothing ownership validation, ApplyPilot replay, operation-ID conflict rollback, declared external application dates, explicit date correction, and backward status changes.

Repository CI remains the integration gate for PostgreSQL backend tests, backend compilation, the frontend production build, and Playwright coverage.

### Rollback

JG-009 has no schema migration and adds no dependency. Application code can roll back independently while retaining lifecycle history already recorded. Do not delete lifecycle events during rollback. JG-010 is the additive timezone/backfill step described below; JG-011 remains the separate analytics read-path activation.



## JG-010 account timezone and historical lifecycle backfill

JG-010 adds the timezone and backfill foundation required before JG-011 switches analytics, goals, weekly reports, or digest reads. Those existing analytics endpoints are intentionally not changed by this ticket.

### Account timezone

Alembic revision `005_user_timezone.py` adds `users.timezone VARCHAR(64) NOT NULL`. Existing rows receive `UTC` during migration. The temporary database default is removed after the legacy copy, while the ORM keeps `default="UTC"` for newly created accounts.

The authenticated profile API is:

- `GET /crm/profile/timezone` -> `{"timezone":"Asia/Kolkata"}`
- `PATCH /crm/profile/timezone` with exactly `{"timezone":"Asia/Kolkata"}`

The PATCH route accepts only names that `zoneinfo.ZoneInfo` can load. Raw offsets such as `+05:30`, invented names, missing values, and ownership fields are rejected with HTTP 422. The route has no user-ID parameter, so it can update only the authenticated account.

`backend/app/services/lifecycle.py` provides:

- `local_day_utc_bounds()`, which converts local midnight to the next local midnight into stored UTC bounds.
- `rolling_week_utc_bounds()`, which moves back seven local calendar days at the same local wall-clock time and returns UTC bounds.

The local-day helper does not assume every day is 24 hours. For `America/New_York`, the 2026 spring-forward day maps to 23 hours and the 2026 fall-back day maps to 25 hours.

### Historical lifecycle backfill

The operational command is `scripts/backfill_lifecycle.py`. It requires an explicit mode:

```sh
# Inspect counts only. No lifecycle facts are written.
python scripts/backfill_lifecycle.py --dry-run

# Apply only source-backed historical facts.
python scripts/backfill_lifecycle.py --apply

# Resume after a fully completed account checkpoint.
python scripts/backfill_lifecycle.py --apply --after-id 42

# Smaller batches are allowed; 500 is the hard maximum.
python scripts/backfill_lifecycle.py --dry-run --batch-size 100
```

`--after-id` is a `User.id` checkpoint. Each account's CSV rows and applications use their own internal source cursor, and each transaction scans at most 500 source records. If execution stops inside one account, resume from the previous completed user checkpoint. Reprocessing that account is safe because first-event keys are deterministic.

The backfill rules are deliberately conservative:

- `first_visited` is created only when legacy `CsvRow.clicked_at` is non-null.
- `first_applied` is created only when legacy `JobTrack.applied_at` is non-null.
- Original occurrence timestamps are preserved exactly.
- Historical facts use `source="legacy_backfill"`.
- `clicked=true` without `clicked_at` is a warning, not a visit timestamp.
- `status="applied"` without `applied_at` is a warning, not an application timestamp.
- Duplicate legacy URLs are counted as conflicts and are not arbitrarily resolved.
- Dry-run follows the same candidate rules but writes nothing.

Command output contains aggregate counts and checkpoint IDs, not job URLs. It also prints private SQL review-query templates for operators who need to inspect missing-date or duplicate cases directly in the protected database.

### Backup contract

Backup schema revision `2.2.0` adds `user_profile` with one validated `timezone` field. Export uses the authenticated user only. Restore applies the timezone to that destination account and records a stable import mapping. A repeat restore is skipped, which prevents an old backup retry from overwriting a timezone the user changed after the first restore.

Compatibility remains additive:

- revision `2.1.0` without `user_profile` remains valid;
- revision `2.0.0` without `lifecycle_events` or `user_profile` remains valid;
- checksum validation uses the section shape that actually existed in the older document.

### Verification

Focused backend verification:

```sh
cd backend
python -m pytest tests/test_metric_timezones.py tests/test_backup_contract.py -q
python -m pytest tests/test_lifecycle_events.py tests/test_lifecycle_mutations.py tests/test_application_memory.py -q
python -m pytest tests/test_backup_export.py tests/test_backup_restore.py tests/test_schema_parity.py -q
python -m compileall app
```

The timezone regression covers Kolkata midnight, New York 23/25-hour DST days, profile validation, idempotent double backfill, dry-run no-write behavior, missing application dates, migration up/down, and timezone backup round trip.

### Rollback and activation

Revision 005 is additive. Normal application rollback leaves the timezone column and lifecycle history in place so older application code can continue operating. Do not delete lifecycle facts or fabricate replacement dates during rollback.

Run the backfill against a disposable database copy first. Compare dry-run counts with the apply result before any production execution. JG-010 implementation does not itself run a production backfill or activate JG-011 analytics reads.


## JG-011 shared analytics metric reads

JG-011 switches the user-facing progress read paths to the lifecycle definitions introduced by JG-008 and populated by JG-009/JG-010. It adds no database migration and does not execute the production historical backfill.

### Shared definitions and compatibility

`backend/app/services/lifecycle.py` owns the aggregate metric snapshot:

- **Visited** counts durable `first_visited` facts by `occurred_at`.
- **Saved** counts `JobTrack` records by `created_at`.
- **Applied** counts durable `first_applied` facts by `occurred_at`.
- `metric_counts()` groups the two lifecycle kinds in SQL and performs one saved-record count. It does not issue one count query per row.
- `count_visited_without_applied()` uses an owner-scoped SQL anti-existence check on exact job URL. It does not infer application state from the current status.

Existing response keys remain available where clients already depend on them:

- `GET /crm/analytics`: `total_opened` now means lifetime **visited**, `total_applied` means lifetime first-applied, and additive `total_saved` exposes saved jobs explicitly. `applied_today` uses the account-local calendar day and `applied_7d` uses the shared rolling seven-local-day interval.
- `GET /crm/stats`: `total_opened`, `opened_today`, and `last_24_hours` count visits; `total_applied` and `applied_today` count first applications. Additive `total_saved` exposes the saved definition.
- `GET /crm/analytics/funnel`: the compatibility stage named `Opened` is backed by visited facts, `Sent to Applications` is backed by saved records, and `Applied` is backed by first-application facts.
- `GET /crm/analytics/goals`: `today.opened` is retained as the wire key but now means visited jobs in the account's local day. `today.applied` uses the same local-day boundaries.
- `GET /crm/analytics/weekly`: `opened` is retained as the wire key but means visited jobs, additive `saved` reports saved jobs, and `applied` reports first applications in the same rolling seven-local-day interval.
- The weekly digest calls the same weekly and goal collectors, so it does not maintain a separate visit/application counting path.

The Analytics UI renders the compatibility values with the corrected labels **Visited jobs**, **Saved jobs**, and **Applied jobs**. The funnel renders the legacy `Opened` stage as **Visited** and `Sent to Applications` as **Saved** without changing the backend stage keys/shape.

### Timezone behavior

Analytics loads the existing authenticated `GET /crm/profile/timezone` value and saves changes through `PATCH /crm/profile/timezone`. The browser-detected IANA zone is a suggestion only; the server remains authoritative and validates the submitted zone.

Daily goals and `applied_today` use `local_day_utc_bounds()`. Weekly data and digest data use `rolling_week_utc_bounds()`. The same account timezone therefore controls every dated core metric read. Historical records whose occurrence timestamp is unknown are excluded from dated lifecycle totals instead of being assigned an invented time.

Changing the timezone refreshes analytics, goals, and weekly data after the server confirms the update. Invalid timezone input remains editable and shows a recoverable error.

### Lifecycle-backed analytics dimensions

The 30-day application series groups `first_applied.occurred_at` facts rather than current `JobTrack.applied_at`. Top applied companies join first-application facts to their application record. Top visited companies join first-visit facts to the source row while that source row still exists.

Deleting a source `CsvRow` does not delete the lifecycle fact, so lifetime visited totals remain durable. A deleted source row can no longer contribute its source-only company label to a dimensional company breakdown because that attribution was intentionally not duplicated into the lifecycle payload.

Current-status dimensions such as interview, rejection, and offer remain `JobTrack.status` reads because they describe current state, not first-occurrence history.

### Digest behavior

`backend/app/routers/email.py` collects digest data by calling the same weekly and goal functions used by the API. The digest subject uses **visited** terminology, and the template shows Uploaded, Visited, Saved, Applied, and Interviews as separate values. Automated JG-011 coverage replaces the SMTP sender and captures the structured digest input, so no real email is sent during tests.

### Verification

Focused backend checks:

```sh
cd backend
python -m pytest tests/test_metric_consistency.py tests/test_metric_timezones.py -q
python -m pytest tests/test_lifecycle_events.py tests/test_lifecycle_mutations.py tests/test_crm.py tests/test_email.py -q
python -m compileall app
```

Focused frontend checks:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/metric-consistency.spec.ts tests/analytics.spec.ts --project=chromium
```

`backend/tests/test_metric_consistency.py` covers cross-endpoint exact counts, account-local daily boundaries, retry idempotency, account scoping, durable visit history after source-row deletion, the existing stats/funnel readers, and digest parity with SMTP replaced. `frontend/tests/metric-consistency.spec.ts` creates one visit plus one saved/applied job through the public APIs, repeats the mutations, and verifies the same values and corrected labels on Analytics.

The TEST_AUTH-only reset deletes lifecycle facts before deleting tracks and rows. This is test isolation only; production lifecycle history is never cleared by the reset route because that route is unavailable when TEST_AUTH is disabled.

### Rollback

JG-011 is a code-only read-path/UI cutover. Roll back the application and frontend changes together if required, but retain migration 005, account timezone values, and all lifecycle events. Never delete or rewrite lifecycle history to make an older reader match. No dependency or schema downgrade is required.


## JG-012 explicit archive timestamps and disabled retention

JG-012 replaces the ambiguous archive-age contract with explicit persisted state. It does not implement the JG-013 cleanup worker or enable permanent purge.

### Storage and migration

Alembic revision `006` adds two nullable fields:

- `CsvRow.archived_at` records the UTC instant of the first explicit false-to-true archive transition.
- `User.retention_days` stores the account's future automatic-archive preference.

The migration performs no data backfill. Existing `archived=true` rows keep `archived_at=NULL` because their real archive time is unknown. Existing users keep `retention_days=NULL`, which means automatic archive is disabled. An index on `csv_rows.archived_at` supports the bounded maintenance reads owned by JG-013.

Do not infer an archive timestamp from `created_at`, `clicked_at`, deployment time, or migration time. Unknown age stays unknown.

### Manual archive behavior

`DELETE /rows` with `{"mode":"archive"}` remains account-scoped. The mutation now filters to `archived=false` rows and atomically sets:

- `archived=true`
- `archived_at=<current UTC time>`

Repeating the same archive request reports zero newly archived rows and does not move the timestamp. Archiving a source row does not detach or delete its `JobTrack` snapshot and does not rewrite `duplicate_of_id` links.

Legacy rows that were already archived before revision 006 remain archived with `archived_at=NULL`. Repeating archive on them does not invent a timestamp.

### Retention preference

`GET /preferences` now includes `retention_days` in addition to the existing column-preference fields.

Set retention with:

```http
PUT /preferences/retention
Content-Type: application/json

{"retention_days": 30}
```

Accepted values are:

- `null` or `0`: disabled
- any integer from `7` through `3650`

Negative values, `1..6`, values above `3650`, non-integer values, and unknown request fields are rejected. The authenticated user is the only account that can be changed by this route.

The existing `PUT /preferences` column-preference request remains compatible. Its response now also reports the account retention value.

### Runtime safety and legacy cleanup retirement

The new runtime controls are:

- `AUTO_ARCHIVE_AFTER_DAYS=0`
- `AUTO_PURGE_AFTER_DAYS=0`
- `RUN_MAINTENANCE_JOBS=false`

All default to disabled. `DELETE_AFTER_DAYS` is deprecated compatibility configuration and is **not** mapped into the new controls.

The old cleanup implementation mixed implicit archive with hard deletion and depended on a nonexistent row-update timestamp. JG-012 retired that unsafe behavior and made scheduler registration opt-in. JG-013 now supplies the bounded automatic archive worker described below. The worker uses the authenticated account's persisted retention policy and never maps `DELETE_AFTER_DAYS` or `AUTO_ARCHIVE_AFTER_DAYS` into an account policy.

Permanent purge remains disabled and is not implemented by JG-012 or JG-013.

### Backup contract

Backup schema revision `2.3.0` exports:

- `csv_rows[].archived_at`
- `user_profile[].retention_days`

Restore writes the exact archived state/timestamp and applies the retention preference to the authenticated destination profile. Both additions are nullable with defaults, so older valid v2 backups that do not contain these fields remain readable and restore them as `NULL`.

Retention values inside backups use the same `0` or `7..3650` validation rule.

### Verification

Focused backend checks:

```sh
cd backend
python -m pytest tests/test_archive_timestamps.py tests/test_backup_contract.py -q
python -m pytest tests/test_application_memory.py tests/test_rows.py tests/test_schema_parity.py -q
python -m compileall app
```

The JG-012 regressions prove first-archive timestamp stability, preservation of unknown legacy archive dates, visibility of unvisited rows after the additive schema change, authenticated retention validation/account isolation, preservation of application/duplicate relationships, disabled legacy cleanup, and backup/restore round-trip fidelity.

Run revision 006 against a disposable PostgreSQL database from revision 005 before production rollout. ORM `create_all` coverage does not replace migration-upgrade verification.

### Rollback

Disable maintenance registration first. JG-012 already defaults it off.

Application rollback can leave `archived_at` and `retention_days` in place safely. Do not downgrade revision 006 after users have meaningful retention values without exporting them first. Never convert `archived_at=NULL` legacy rows into purge candidates during rollback.

JG-013 may change maintenance execution, but it must preserve these storage and compatibility rules.


## JG-013 bounded observable automatic archive

JG-013 replaces the JG-012 compatibility shim with a bounded, observable archive worker. It is a service/maintenance change only. It adds no database migration, public API, settings UI, permanent-delete path, or production activation.

### Eligibility and transaction boundary

`backend/app/services/retention.py` owns the archive selection and mutation contract. One row is eligible only when all of these are true:

- the owning `User.retention_days` is an enabled value from 7 through 3650;
- `CsvRow.clicked_at` is known and is at or before `now - retention_days`;
- `CsvRow.archived` is still false.

An old `created_at` value is not visit evidence. Accounts with `retention_days=NULL`, `0`, or an invalid persisted value are treated as disabled. The deprecated `DELETE_AFTER_DAYS` value is never consulted. `AUTO_ARCHIVE_AFTER_DAYS=0` is also a global operator kill switch: the scheduled/manual worker returns disabled before opening a maintenance session. A positive value permits the worker to run but does not override or replace the account's persisted retention threshold.

Candidates are ordered by `CsvRow.id` and limited to 500 per invocation. PostgreSQL candidate reads use `FOR UPDATE SKIP LOCKED`. The write repeats the `archived=false` predicate before atomically setting `archived=true` and `archived_at=<run UTC time>`. This keeps retries safe if another transaction changed a selected row. One run commits one bounded batch. A second run resumes with the next eligible IDs. Re-running after the batch is exhausted reports zero new archives and never resets an existing archive timestamp.

The automatic worker contains no hard-delete code. Existing legacy archived rows with `archived_at=NULL` remain untouched, and permanent purge remains reserved for the later recoverable-archive work.

### Locking and scheduler behavior

`backend/app/jobs.py` retains the historical `cleanup_clicked_rows` function name for scheduler compatibility, but its behavior is now the JG-013 archive job.

Every invocation first attempts a non-blocking in-process lock. On PostgreSQL it then holds a dedicated session-level advisory lock for the complete service call. The advisory lock prevents two designated maintenance processes from running the archive batch at the same time, while `FOR UPDATE SKIP LOCKED` and the conditional archive update provide an additional row-level safety boundary. A contending invocation does not wait and does not report ordinary zero work. It returns a structured skipped result and logs `outcome=skipped reason=lock_contended`.

SQLite remains a local/test mode. It uses the in-process guard plus SQLite's serialized write behavior; multi-process maintenance deployment is not supported there. Production multi-process exclusion relies on PostgreSQL plus the designated-maintenance-process deployment rule.

The FastAPI lifespan still registers maintenance only when:

```text
RUN_MAINTENANCE_JOBS=true
```

The default remains `false`. Registration itself has an in-process guard, and the APScheduler job uses `coalesce=True` and `max_instances=1`. Even in a designated process, `AUTO_ARCHIVE_AFTER_DAYS=0` keeps automatic archive inert. Generic web workers therefore remain inactive unless a deployment explicitly designates one process to run maintenance.

### Result and failure contract

Every completed or skipped invocation returns exactly these aggregate fields:

```json
{
  "scanned": 0,
  "archived": 0,
  "skipped": 0,
  "failed": 0,
  "duration_ms": 0
}
```

For a normal batch, `scanned` is the selected candidate count, `archived` is the successful first-transition count, and `skipped` accounts for candidates that ceased to be eligible before the conditional update. For lock contention, `scanned=0` and `skipped=1` marks a skipped invocation so it is distinguishable from a healthy no-work run.

Database/query/update/commit failures roll back the active transaction. They raise `RetentionJobError` with a result whose `failed` value is non-zero. The scheduler therefore observes a failed invocation instead of a false zero-success result. Operational logs contain only the outcome and aggregate counts/timing. They do not include user IDs, job URLs, notes, or imported content.

### Operator controls and recovery

Do not enable maintenance only because JG-013 is deployed. The safe rollout sequence is:

1. deploy the code with `RUN_MAINTENANCE_JOBS=false`;
2. verify migrations remain at the existing JG-012 head and run the cleanup regression suite on a disposable PostgreSQL database;
3. configure retention only for accounts that explicitly opted in;
4. after archive execution is operationally approved, change `AUTO_ARCHIVE_AFTER_DAYS` from `0` to a positive value; this opens the global gate but does not replace account-specific `retention_days`;
5. designate one maintenance process and set `RUN_MAINTENANCE_JOBS=true` only for that process;
6. monitor aggregate cleanup outcomes and return `AUTO_ARCHIVE_AFTER_DAYS=0` or `RUN_MAINTENANCE_JOBS=false` immediately if failures or unexpected counts appear.

A deliberate operator can execute one bounded run from the backend environment with:

```sh
python -c "from app.jobs import cleanup_clicked_rows; print(cleanup_clicked_rows())"
```

That command can archive eligible rows and must only be run against the intended environment. It never purges data.

Rollback begins by setting `AUTO_ARCHIVE_AFTER_DAYS=0` and `RUN_MAINTENANCE_JOBS=false`, then stopping/restarting the designated process so no new job is registered. Application code can then roll back while retaining `archived_at` and `retention_days`; do not erase archive timestamps or reinterpret unknown legacy timestamps.

### Verification

Focused backend checks:

```sh
cd backend
python -m pytest tests/test_cleanup_job.py -q
python -m pytest tests/test_archive_timestamps.py tests/test_application_memory.py tests/test_rows.py -q
python -m compileall app
```

`test_cleanup_job.py` covers old unvisited rows, disabled policies, the exact retention boundary, 500-row batching/resume, repeat-run timestamp stability, rollback with a non-zero failure signal, overlapping worker suppression, lock release after failure, and PostgreSQL advisory-lock contention/recovery. Repository CI remains the integration gate for the complete PostgreSQL backend suite, backend compilation, frontend production build, and Playwright regressions.
