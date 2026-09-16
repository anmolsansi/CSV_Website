# JobGrid Build Guide

This guide describes behavior implemented in the repository. It is not a copy of the future roadmap.

## Backup implementation status

JG-001 freezes and validates the portable backup **v2 record contract** in `backend/app/backup_schemas.py`.

JG-002 activates complete v2 export and adds the persistence contract that JG-003 will use for stable restore identity mapping:

- `GET /crm/backup/export` remains backward-compatible and returns v1 by default.
- `GET /crm/backup/export?version=2` returns the complete validated v2 document.
- `backend/app/services/backups.py` owns consistent-snapshot reads, backup-local references, relationship translation, counts, checksum, and final v2 validation.
- `backend/app/routers/backup.py` owns the live backup export transport while the legacy import handler remains in `routers/crm.py` until JG-003.
- `backend/app/models.py` contains `BackupImportMap`.
- Alembic revision `003` creates `backup_import_maps` and its replay-identity uniqueness index.

JG-002 does **not** activate v2 restore. `POST /crm/backup/import` remains the existing legacy implementation until JG-003 adds preflight, reference remapping, transactional restore, replay handling, and v1 incomplete-backup warnings.

## Why v2 exists

The original portable backup is lossy. A backup can contain an application record while the old restore path does not reconstruct the same application state. V2 makes all durable sections and persisted fields explicit before restore code constructs ORM objects.

Source database primary keys and `user_id` values are never portable authority. Export replaces source identities with opaque backup-local references. Restore will allocate destination IDs and bind all restored records to the authenticated destination user.

## V2 document shape

A v2 document contains exactly:

- `version`: `"2.0"`
- `backup_id`: UUID string
- `exported_at`: UTC ISO-8601 timestamp
- `schema_revision`: currently `"2.0.0"`
- `sections`: the nine exact v2 sections
- `counts`: exact record count for every section
- `checksum_sha256`: lowercase SHA-256 digest of canonical `sections` JSON

The nine sections are:

1. `csv_rows`
2. `url_history`
3. `job_tracks`
4. `saved_views`
5. `sessions`
6. `audit_events`
7. `applypilot_batches`
8. `column_preferences`
9. `user_goal`

Every record has a non-empty `backup_ref` unique within its section. Nullable fields are still present as keys, preserving the difference between null, empty text, `false`, and zero.

## Export identity and references

JG-002 generates a fresh `backup_id` for each export. Within that document, each record receives an opaque deterministic UUIDv5 reference derived from the backup ID, section, and source record identity. This makes repeated references inside one backup stable without exposing a source database ID as a reusable authorization identifier.

Relationships are translated as follows:

- `CsvRow.duplicate_of_id` -> `duplicate_of_ref`
- `JobTrack.csv_row_id` -> `csv_row_ref`
- `AuditEvent.session_id` -> `session_ref`
- known `AuditEvent.entity_id` targets -> typed `entity_ref`
- `ApplyPilotBatch.session_id` -> `session_ref`

`JobTrack.session_id` remains exported as scalar text because the ORM does not declare it as a `SearchSession` foreign key. JG-002 does not infer a `session_ref` from that text field.

If a declared active relationship points outside the authenticated snapshot, export fails with the safe `conflicting_reference_graph` contract rather than leaking another account's record or silently manufacturing a target.

Audit events are different because historical targets can legitimately disappear. A known target that is present gets `entity_ref`. An unknown or no-longer-present historical target stays detached with `legacy_entity_id`; that value is metadata only and is never active destination authority.

## Consistent export snapshot

The authenticated request session is not reused for the v2 data read. `export_backup_v2()` opens a dedicated connection and read transaction so a GET cannot commit unrelated request-session state.

Isolation is:

- PostgreSQL: `REPEATABLE READ`
- SQLite/local tests: `SERIALIZABLE`

All nine sections are read within that one transaction. The service fully builds and validates the document before the route serializes the response, so cursors/transaction resources are closed even if serialization fails.

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

### Saved views and sessions

Saved views export `name`, `view_type`, `filters`, `is_pinned`, and `created_at`. Search sessions export `name`, start/end timestamps, and notes.

### Audit events

Audit events export event type, entity type, metadata, timestamp, session relationship, and typed entity relationship where resolvable. Historical detached identifiers remain metadata only.

### ApplyPilot batches

Batches export name, payload, status, job count, timestamps, and a validated session reference when present.

### Column preferences and user goal

These user-owned singleton records export only portable preference/goal values. Ownership is reconstructed from the authenticated destination user during restore.

## Excluded data

Portable backups exclude `User` and `OAuthIdentity` records, account IDs/emails as authority, provider identities, JWTs, signing material, credentials, and server filesystem paths.

`BackupImportMap` is operational restore metadata and is also not exported. It maps a destination user's `(backup_id, section, backup_ref)` to a destination `target_id` and exists to make JG-003 retries stable.

## BackupImportMap persistence

Alembic revision `003_backup_import_maps.py` creates:

- `id` primary key
- `user_id` with `users.id` foreign key and cascade delete
- `backup_id`
- `section`
- `backup_ref`
- `target_id`
- `created_at`

The unique identity index covers `(user_id, backup_id, section, backup_ref)`. The map is additive and contains no source authorization. JG-002 creates the schema only; JG-003 owns transactional writes/upserts into it.

The downgrade is safe only when deliberately invoked in an environment where the map can be discarded. Production rollback of the v2 UI/route should normally retain this additive table and any restore history rather than deleting data.

## Limits and validation

The frozen JG-001 validation contract enforces:

| Limit | Value | Contract result |
|---|---:|---|
| Uncompressed UTF-8 JSON | 20 MiB | `413 backup_too_large` |
| Total records | 20,000 | `413 record_limit_exceeded` |
| `notes` | 20,000 characters | `413 field_too_large` |
| `jd_text` | 1 MiB UTF-8 | `413 field_too_large` |

Generated v2 exports are passed through `validate_backup_v2()` before they leave the service. This validates schema revision, counts, checksum, duplicate refs, field limits, and the active reference graph.

## Version compatibility

| Request/input | Current behavior |
|---|---|
| `GET /crm/backup/export` | Legacy v1 export, unchanged default |
| `GET /crm/backup/export?version=1` or `1.0` | Legacy v1 export |
| `GET /crm/backup/export?version=2` or `2.0` | Complete validated v2 export |
| v2 import | Not active yet; JG-003 owns it |
| v1 import | Existing legacy route remains until JG-003 compatibility wiring |

Do not remove the v1 default until all v2 consumers have passed their compatibility gates.

## Verification

Focused contract/export validation:

```sh
cd backend
python -m pytest tests/test_backup_contract.py tests/test_backup_export.py -q
```

The JG-002 focused suite proves:

- every one of the nine sections is nonempty in the complete fixture
- counts and checksum match the emitted sections
- v2 output validates against the frozen JG-001 contract
- foreign-account rows are absent
- CSV duplicate, job-track CSV, audit session/entity, and ApplyPilot session references resolve
- scalar `JobTrack.session_id` is preserved without a fabricated `session_ref`
- default and explicit v1 exports retain the legacy shape
- migration 003 creates its columns/unique index and can downgrade an empty schema safely

Run the wider affected backend suite and repository CI before merge.

## Rollback and recovery

JG-002 is additive.

For an application rollback:

1. Revert the route/service activation so the legacy v1 export is again the only live export behavior.
2. Keep `backup_import_maps` in place unless there is a separately reviewed reason to remove it.
3. Do not delete user records or restored records as part of a code rollback.
4. Database-level disaster recovery still uses `scripts/backup.sh` and `scripts/restore.sh`; production recovery proof belongs to JG-024.

JG-003 must preserve this rollback boundary when it activates restore.

## Change discipline

When a persisted model field is added, removed, or renamed, update the frozen backup field inventory and tests deliberately. Do not weaken the inventory check. Decide whether the field is exported, reconstructed, excluded with a reason, or blocked on a migration, then update schemas, export/restore adapters, examples, tests, and documentation together.
