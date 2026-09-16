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
- JG-004 still owns the dedicated restore preview/interface. JG-003 does not claim that UI as shipped.

## Why v2 exists

The original portable backup is lossy. A backup can contain an application record while the old restore path does not reconstruct the same application state. V2 makes all durable sections and persisted fields explicit before restore code constructs ORM objects.

Source database primary keys and `user_id` values are never portable authority. Export replaces source identities with opaque backup-local references. Restore allocates destination IDs and binds every restored record to the authenticated destination user.

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

Every record has a non-empty `backup_ref` unique within its section. Nullable fields remain present as keys, preserving the difference between null, empty text, `false`, and zero.

## Export identity and references

JG-002 generates a fresh `backup_id` for each export. Within that document, each record receives an opaque deterministic UUIDv5 reference derived from the backup ID, section, and source record identity. This makes repeated references inside one backup stable without exposing a source database ID as a reusable authorization identifier.

Relationships are translated as follows:

- `CsvRow.duplicate_of_id` -> `duplicate_of_ref`
- `JobTrack.csv_row_id` -> `csv_row_ref`
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

All nine sections are read within one transaction. The service fully builds and validates the document before the route serializes the response, so transaction resources close even if serialization fails.

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

Every one of the nine sections is present in `counts` even when its values are all zero. Warnings contain safe codes plus optional `section` and `backup_ref`; they never contain notes, job descriptions, credentials, or another user's values.

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
8. job tracks after CSV references are resolvable
9. ApplyPilot batches after session references are resolvable
10. audit events last, after every supported target section has a destination identity

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
| `POST /crm/backup/import?mode=merge_missing` with v2 | Transactional nine-section restore |
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
- all nine v2 sections restore and CSV duplicate references remap to destination IDs
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
