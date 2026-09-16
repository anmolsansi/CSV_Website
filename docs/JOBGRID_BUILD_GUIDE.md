# JobGrid Build Guide

This guide describes behavior that is implemented in the repository. It is not a copy of the future roadmap.

## Backup contract status

JG-001 freezes the portable backup **v2 record contract** in `backend/app/backup_schemas.py` and its regression suite in `backend/tests/test_backup_contract.py`.

JG-001 does **not** switch the live `/crm/backup/export` or `/crm/backup/import` routes to v2. Those route and restore changes belong to JG-002 and JG-003. Until those tickets are implemented, the existing route behavior remains the current user-facing behavior.

The frozen schema revision is `2.0.0` and the document version is `2.0`.

## Why the v2 contract exists

The original portable backup is lossy. A backup can contain an application record while the existing restore path does not reconstruct the same application state. The v2 contract prevents that class of silent loss by making every durable section and every persisted field explicit before restore code constructs ORM objects.

The contract also prevents ownership injection. Source database `id` and `user_id` values are not portable authority. Restore code must allocate destination IDs and bind records to the authenticated destination user.

## V2 document shape

A v2 document contains exactly these top-level fields:

- `version`: exactly `"2.0"`
- `backup_id`: UUID string
- `exported_at`: UTC ISO-8601 timestamp
- `schema_revision`: non-empty schema revision string
- `sections`: the nine exact v2 sections
- `counts`: exact record count for every section
- `checksum_sha256`: lowercase SHA-256 hex digest of canonical `sections` JSON

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

Every record has a non-empty `backup_ref`. A reference is unique within its own section. Source integer primary keys and `user_id` are not accepted v2 record fields.

All nullable fields are still required keys in v2. A producer must write `null` when the value is null. This preserves the difference between null, empty text, `false`, and numeric zero.

## Valid empty v2 example

This is a complete schema-valid empty backup. The checksum is the SHA-256 digest of the exact `sections` object shown below using the canonicalization rules in this guide.

```json
{
  "version": "2.0",
  "backup_id": "8ec0b836-ff0b-4a42-84b3-c757a91d1f48",
  "exported_at": "2026-09-16T09:30:00Z",
  "schema_revision": "2.0.0",
  "sections": {
    "csv_rows": [],
    "url_history": [],
    "job_tracks": [],
    "saved_views": [],
    "sessions": [],
    "audit_events": [],
    "applypilot_batches": [],
    "column_preferences": [],
    "user_goal": []
  },
  "counts": {
    "csv_rows": 0,
    "url_history": 0,
    "job_tracks": 0,
    "saved_views": 0,
    "sessions": 0,
    "audit_events": 0,
    "applypilot_batches": 0,
    "column_preferences": 0,
    "user_goal": 0
  },
  "checksum_sha256": "69f86f5cd7fd95a447d911f9503ca513360e8067fe50a3acbf711e9d8cae6312"
}
```

A non-empty `csv_rows` record must include the complete frozen CSV field allowlist from `CsvRowBackupV2`. Do not omit a nullable key simply because its value is null.

## Record contracts

### CSV rows

`CsvRowBackupV2` exports `upload_batch_id`, `created_at`, `clicked`, `clicked_at`, `archived`, `is_duplicate`, every frozen `CSV_COLUMNS` text field, and `duplicate_of_ref`.

The source `id` is represented by `backup_ref`. The source `user_id` is reconstructed from the authenticated destination user. `duplicate_of_id` is represented by `duplicate_of_ref` and must resolve to another `csv_rows` record.

The text-field allowlist is a frozen copy of the current ORM `CSV_COLUMNS`. `test_assert_complete_model_field_inventory` fails if the ORM changes without an explicit backup-contract decision.

### URL history

`UrlHistoryBackupV2` exports `url` and `first_seen_at`. Source `id` and `user_id` are reconstructed.

### Job tracks

`JobTrackBackupV2` exports every non-identity persisted field:

- `url`
- `company`
- `title`
- `ats_group`
- `search_bucket`
- `resume_match_score`
- `status`
- `opened_at`
- `applied_at`
- `follow_up_at`
- `notes`
- `session_id`
- `open_count`
- `last_opened_at`
- `created_at`
- `updated_at`

`csv_row_id` becomes `csv_row_ref`. `JobTrack.session_id` is preserved separately as scalar text because the current ORM column is not a declared `SearchSession` foreign key. `session_ref` exists only for an independently validated session relationship and must not be inferred from the scalar text value.

### Saved views

`SavedViewBackupV2` exports `name`, `view_type`, `filters`, `is_pinned`, and `created_at`. Source `id` and `user_id` are reconstructed.

### Search sessions

`SearchSessionBackupV2` exports `name`, `started_at`, `ended_at`, and `notes`. Source `id` and `user_id` are reconstructed.

### Audit events

`AuditEventBackupV2` exports `event_type`, `entity_type`, `metadata_json`, and `created_at`.

`session_id` becomes `session_ref`. `entity_id` becomes a typed `entity_ref` when its target is known. An opaque source integer may be retained only as `legacy_entity_id` historical metadata. It is never treated as a destination link.

Known active reference types currently validated by the contract include CSV rows, job tracks, sessions, saved views, ApplyPilot batches, and URL history. An unknown entity type may remain detached, but it cannot claim an unresolved active `entity_ref`.

### ApplyPilot batches

`ApplyPilotBatchBackupV2` exports `name`, `payload_json`, `status`, `job_count`, `created_at`, and `updated_at`. `session_id` becomes `session_ref`. Source `id` and `user_id` are reconstructed.

### Column preferences

`ColumnPreferenceBackupV2` exports `hidden_columns` and `column_order`. The destination authenticated user supplies ownership.

### User goal

`UserGoalBackupV2` exports `open_per_day`, `apply_per_day`, `followup_per_day`, and `applypilot_per_day`. The destination authenticated user supplies ownership.

## Explicitly excluded data

`User` and `OAuthIdentity` records are deliberately excluded from portable backups. That excludes account IDs, email identity, OAuth provider identity, JWT/signing material, and authentication authority.

The field inventory in `MODEL_FIELD_INVENTORY` classifies every current ORM column as one of:

- `exported`
- `reconstructed`
- `excluded`
- `migration_blocker`

JG-001 has no unresolved migration blocker against the current model snapshot. Any future ORM column causes the inventory regression to fail until its backup treatment and reason are deliberately added.

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

Then compute SHA-256 and store the lowercase hexadecimal digest in `checksum_sha256`.

`NaN`, positive infinity, and negative infinity are invalid. Duplicate JSON object keys are rejected during parsing before Pydantic validation. This avoids parser-dependent last-value-wins behavior.

## Reference validation

Validation runs on the full logical document before restore code may construct ORM objects.

The current reference rules are:

- `csv_rows[].duplicate_of_ref` targets `csv_rows` and cannot point to itself.
- `job_tracks[].csv_row_ref` targets `csv_rows`.
- `job_tracks[].session_ref`, when present, targets `sessions`.
- `audit_events[].session_ref`, when present, targets `sessions`.
- `audit_events[].entity_ref`, when present, targets the section selected by its known `entity_type`.
- `applypilot_batches[].session_ref`, when present, targets `sessions`.

A missing target or duplicate `backup_ref` is a reference-graph conflict. The contract exposes stable safe error codes without embedding job values, notes, or private content in the error detail.

## Limits

JG-001 enforces these frozen pre-restore limits:

| Limit | Value | Contract result |
|---|---:|---|
| Uncompressed UTF-8 JSON | 20 MiB | `413 backup_too_large` |
| Total records across all sections | 20,000 | `413 record_limit_exceeded` |
| `notes` | 20,000 characters | `413 field_too_large` |
| `jd_text` | 1 MiB UTF-8 | `413 field_too_large` |

`counts.<section>` must exactly equal the number of records in that section.

## Error contract available to route wiring

`BackupContractError` carries a stable `code`, proposed HTTP `status_code`, and optional safe `section`/`backup_ref` context.

Important mappings implemented by JG-001 include:

| Condition | Status | Code |
|---|---:|---|
| Invalid JSON or UTF-8 | 400 | `invalid_json` |
| Duplicate JSON key | 400 | `duplicate_json_key` |
| NaN/infinite number | 400 | `non_finite_number` |
| Frozen Pydantic schema mismatch or ownership field | 400 | `invalid_schema` |
| Invalid UUID | 400 | `invalid_backup_id` |
| Invalid/non-UTC timestamp | 400 | `invalid_timestamp` |
| Section count mismatch | 400 | `count_mismatch` |
| Checksum mismatch | 400 | `invalid_checksum` |
| Duplicate `backup_ref` | 409 | `duplicate_backup_ref` |
| Missing/conflicting reference target | 409 | `conflicting_reference_graph` |
| Byte, record, note, or JD limit | 413 | size-specific code |

JG-002/JG-003 own HTTP route integration. JG-001 only establishes and tests the reusable domain contract.

## V1 compatibility adapter

`adapt_v1_backup()` accepts version `1`/`1.0` dictionaries and returns an internal `LegacyV1Adaptation`.

The adapter deliberately does not fabricate data. For each legacy record it keeps the values actually present and records every absent v2 field in `missing_fields`. Missing v2 sections are recorded in `absent_sections`, and the adaptation carries the `incomplete_legacy_backup` warning.

The current v1 format omits durable categories such as URL history, column preferences, and user goals. Those absences remain explicit. If a v1 application record lacks `applied_at` or `opened_at`, the adapter does not derive or invent those dates.

`user_id` is rejected at both the legacy document and legacy record boundary so a source file cannot choose destination ownership.

## Version compatibility

| Input | JG-001 contract behavior | Live route status after JG-001 |
|---|---|---|
| v1 / `1.0` | Loss-aware adapter accepts known sections, records missing fields/sections, emits `incomplete_legacy_backup` | Existing route remains unchanged until later R1 tickets wire the adapter |
| v2 / `2.0`, schema revision `2.0.0` | Strict full-document validation, checksum, limits, field inventory, and reference graph are implemented | Contract exists but export/import route activation belongs to JG-002/JG-003 |
| Unknown version | Not accepted by the matching v1/v2 contract path | No new live behavior in JG-001 |

Future optional v2 sections must add explicit capability/section-version compatibility without silently ignoring required present data.

## How to use the contract in backend code

For v2 bytes received from a trusted request-size boundary:

```python
from app.backup_schemas import BackupContractError, validate_backup_v2

try:
    document = validate_backup_v2(raw_bytes)
except BackupContractError as exc:
    # JG-002/JG-003 route code maps exc.status_code and exc.as_detail().
    raise

# Only after this point may restore code resolve identities and construct ORM objects.
```

For a decoded v1 document:

```python
from app.backup_schemas import adapt_v1_backup

legacy = adapt_v1_backup(payload)
# Inspect legacy.missing_fields / absent_sections through the returned records.
# Do not fill missing historical timestamps with guessed values.
```

## Verification

Run the focused contract regression from an environment with backend dependencies installed:

```sh
cd backend
python -m pytest tests/test_backup_contract.py -q
```

The focused suite verifies:

- every current ORM field has an explicit backup disposition and reason
- the frozen CSV field snapshot matches `models.CSV_COLUMNS`
- all nine section record models reject extra keys
- null, empty string, `false`, and `0` survive validation and serialization distinctly
- unknown sections and `user_id` injection are rejected
- duplicate references and bad checksums produce safe 409/400 contract errors
- duplicate JSON keys and non-finite numbers are rejected
- reference targets and field limits are checked before restore
- v1 adaptation records loss instead of inferring application timestamps

After changing the contract, run the wider affected backend suite before merging.

## Rollback and recovery

JG-001 adds only a contract module, tests, and documentation. It does not modify the database, existing route behavior, or frontend.

Rollback is therefore code-only: revert the JG-001 commits if the contract itself must be withdrawn. No data rollback is required because JG-001 writes no application data and adds no migration.

When later R1 tickets activate v2, rollback must disable v2 export/import UI and route behavior without deleting restored data or any import identity mapping. Database-level disaster recovery remains the responsibility of `scripts/backup.sh` and `scripts/restore.sh`, and is verified separately by JG-024.

## Change discipline

When a model column is added, removed, or renamed, the backup field-inventory test should fail. Do not weaken the test. Decide explicitly whether the field is exported, reconstructed, excluded with a reason, or blocked on a migration, then update the record schema, compatibility rules, example/tests, and any later export/restore wiring together.
