# JobGrid Backup and Recovery Strategy

Last verified against repository behavior: **2026-09-27**  
Portable backup schema: **v2.0 / revision 2.13.0**

JobGrid has two different recovery layers. They solve different problems and must not be treated as substitutes for one another.

1. **Portable account backup** is the authenticated, user-facing export/import contract implemented by FastAPI. It moves one account's supported JobGrid records between installations/accounts. The complete user-facing format is ZIP because documents are stored outside PostgreSQL.
2. **Operator disaster recovery** protects an environment as a whole. It requires a database backup plus the matching private document store. Repository scripts and provider backups support this layer, but a schedule or retention promise exists only after the operator actually configures and rehearses it.

## Portable backup formats

### Complete backup — records and files

Endpoint: `GET /crm/backup/export/bundle`

The ZIP bundle is the complete portable recovery path. It contains:

- one composed v2 metadata graph for the authenticated account;
- the durable contact/interview extension;
- saved import mappings;
- supported non-actionable bulk-action audit metadata;
- a manifest describing document members and hashes;
- immutable document bytes for portable ready document versions.

Restore/preflight endpoint: `POST /crm/backup/import/bundle?mode=verify_only|merge_missing`.

The bundle format is `jobgrid-document-bundle`, version 1. Current limits are 150 MiB uploaded bytes, 150 MiB expanded bytes, and 20,002 ZIP members. ZIP validation rejects duplicate members, unsafe paths, symlinks, unexpected members, missing required members, expansion beyond the configured limit, and byte/hash mismatches before the affected data is accepted.

### Records only — excludes document files

Endpoint: `GET /crm/backup/export?version=2.0`

The v2 JSON export contains portable records and document metadata, including document hashes, but `document_bytes_included` is false. It is useful for records-only recovery and verification. It must never be presented as a complete file backup.

Restore/preflight endpoint: `POST /crm/backup/import?mode=verify_only|merge_missing`.

Current JSON limits are 20 MiB uncompressed and 20,000 portable records across the composed backup. The parser rejects duplicate JSON object keys and non-finite numbers.

### Legacy v1

`GET /crm/backup/export` still defaults to the historical v1 JSON shape for compatibility. The restore adapter accepts versions `1` and `1.0`, records missing sections/fields instead of inventing historical facts, and reports incomplete legacy coverage. New recovery work should use v2 or the ZIP bundle.

## Portable data coverage

The code-level source of truth for base-model field coverage is `MODEL_FIELD_INVENTORY` in `backend/app/backup_schemas.py`. New persisted fields or models must update that inventory or tests must fail rather than silently losing data.

| Category | Portable behavior |
|---|---|
| CSV discovery rows and URL history | Exported. Destination IDs are reconstructed from backup-local references. Derived canonical identity fields are rebuilt rather than trusted as portable authorization data. |
| Durable application memory (`JobTrack`) | Exported, including company/role snapshot, status, notes, known dates, counters, and source-row relationship when present. Source database integer IDs are not portable. |
| Availability/deadline state | Exported. Transient URL-check request/lease/rate state is excluded. |
| Lifecycle events and application evidence | Exported with portable references. Recently soft-deleted evidence bodies are carried only by the bounded recovery section while eligible. Ordinary deleted evidence remains redacted. |
| Saved views, search sessions, goals, column preferences, account timezone/retention preference | Exported. Account ownership itself is reconstructed from the authenticated destination user. |
| Manual Today work and snooze overrides | Exported. Action keys that contain local IDs are reconstructed from remapped destination records. |
| Reminder preferences and durable delivery history | Exported. Preferences are restored disabled and retry/lease state is paused/cleared so restore cannot silently send or resend messages. Worker leases are not portable. |
| Company aliases | Exported. |
| Documents | Metadata and application selections are in v2 JSON. Immutable bytes are included only in the ZIP bundle. Environment-local storage keys are never portable. |
| Contacts, application-contact links, interviews | Exported in the checksummed `f8_private` extension and restored using backup-local application/contact references. |
| Saved external-import mappings | Exported in the checksummed `f9_import_mappings` extension. Uploaded import previews, rejected-row payloads, expiry state, and raw transient preview data are deliberately excluded. |
| Bulk action / undo history | Bounded audit metadata is exported in `f10_bulk_action_metadata`. Executable before-images/effects are deliberately excluded. Restored actions are forced to expired/non-actionable state and cannot execute an old Undo against new destination data. |
| Upload/capture/evidence idempotency receipts, request counters, job-check requests, maintenance state | Deliberately excluded as transient operational/replay state. |
| OAuth identities, session cookies, provider secrets, signing keys, SMTP credentials | Deliberately excluded. Authentication identity is not portable account data. |

## Snapshot and transaction contract

### Export

The composed v2 exporter and its extensions participate in one export snapshot through `backend/app/services/backup_sessions.py`. Section relationships therefore describe one account state instead of separate independent reads taken at unrelated times.

All private queries are scoped to the authenticated user. Backup-local references, not source database integer IDs, connect portable records.

### Preflight

`verify_only` validates without mutating durable records, publishing document bytes, sending reminders, or sending email. Validation covers schema/version handling, checksums, record/byte limits, duplicate identities, relationship references, extension checksums, replay conflicts, bundle members, and document hashes before restore is reported ready.

### Restore atomicity

The JSON, contact/interview, import-mapping, supported audit-metadata, and ZIP restore layers share one caller-owned database transaction. Child restore layers may flush to obtain destination IDs but must not independently commit or close the transaction.

A late validation, relationship, constraint, or commit failure must leave no partially committed portable database graph. Replay identity is stable: restoring the same backup content is idempotent, while changed content under the same replay identity is a conflict rather than a silent overwrite.

PostgreSQL restore serializes account-level destination changes where required. SQLite follows the supported application transaction path and is covered separately in the release matrix.

## Document-file transaction boundary

PostgreSQL and a filesystem are not one ACID transaction. ZIP restore therefore uses a staged-file protocol:

1. validate the full metadata graph and ZIP structure;
2. stage each document under attempt-owned private staging paths;
3. verify expected size and SHA-256 before publication;
4. execute metadata restore under the owned database transaction;
5. publish only the document files required by that attempt;
6. commit the database transaction;
7. on failure, roll back database state and remove attempt-owned staged/newly published files where possible.

A process can still die between filesystem publication and database commit. That crash window is an operational reconciliation case, not something the application should describe as cross-resource ACID. Existing document reconciliation and a retry of the same idempotent backup are the recovery path. Cleanup errors must be visible in logs/operation evidence and must never justify deleting a preexisting immutable file.

## Compatibility contract

- v1 / 1.0 is accepted through the legacy adapter with explicit incomplete-backup warnings.
- Early v2 backups remain accepted when additive base sections/fields were absent. Validators preserve the historical checksum shape for supported earlier revisions instead of fabricating keys into the signed payload.
- Current optional extensions may be absent. Their absence means that feature's portable records were not present in that older backup.
- Present extensions are validated in full, including their own schema revision and checksum, before their writes are accepted.
- Unknown or malformed required data is rejected before restore writes.
- JSON remains a supported metadata/records-only restore even when document bytes are intentionally absent.
- ZIP must not claim completeness when a required ready document member is missing or has a different hash.

Do not remove old readers merely because a newer writer exists. A future incompatible wire-format change requires a new explicit version plus previous-reader/previous-data tests.

## Failure and retry behavior

Expected operator/user behavior after a failed portable restore:

1. Keep the original backup file unchanged.
2. Read the structured error code rather than retrying by manually deleting destination records.
3. Correct destination conflicts or storage availability if the error is environmental.
4. Retry the same backup. The restore identity and mapping receipts are designed to return existing results instead of duplicating relationships.
5. If a process interruption may have occurred during ZIP publication, run document-storage reconciliation or inspect the private staging/trash areas before broad cleanup. Remove only files proven to belong to the failed attempt.
6. Never repair a partial-looking account by deleting the whole user. Investigate against a disposable copy first.

Restore does not authorize outbound side effects. It must not send reminder email, re-enable reminder preferences, run URL checks, or turn restored undo history into executable operations.

## Required recovery regression coverage

The release suite must keep these failures as permanent regressions:

- corrupt a late contact-extension checksum and prove zero destination rows remain after rejection;
- inject failures after base writes, contact writes, import mappings, supported audit metadata, and immediately before commit, then re-query through another session;
- verify `verify_only` has no durable side effects;
- round-trip a rich account containing application memory, Today state, contacts/interviews, import mappings, documents and selections, and supported undo/audit metadata;
- restore into empty and nonempty destinations, then repeat the restore without duplicates;
- reject wrong-account/broken portable references and changed-content replay;
- reject ZIP traversal, symlink, duplicate/unknown members, missing members, changed hashes, and size/member-limit violations;
- inject document publish/commit failures and prove database/file rollback or a documented retryable reconciliation state;
- run a real browser download → upload → preview → restore flow and download restored documents to verify bytes.

Current implementation evidence for JG-001–JG-010 is recorded in `docs/JG001_010_EXECUTION.md`. `development.md` owns the broader C-package release status.

## Operator disaster recovery

Portable account backups do not replace environment recovery. A production recovery plan must protect both:

- the PostgreSQL database; and
- the private document directory configured by `DOCUMENT_STORAGE_DIR`.

The repository contains `scripts/backup.sh`, `scripts/restore.sh`, `scripts/portable-backup.sh`, and `scripts/portable-restore.sh`. Treat them as operator tooling, not proof that a production schedule, remote destination, encryption policy, or retention policy is configured.

For a disaster-recovery rehearsal:

1. use a controlled write pause or another method that gives a database/document snapshot with a known consistency point;
2. capture PostgreSQL using the approved provider backup or compatible logical backup;
3. capture the matching private document tree and manifest/hashes;
4. store the recovery package outside the service/disk being protected with appropriate access controls;
5. restore to a separate disposable environment;
6. compare nonempty record counts, normalized relationships, schema revision, document inventory, and file hashes;
7. measure elapsed recovery time against the release's recorded RPO/RTO objectives;
8. verify the previous compatible application build can still read the migrated schema before claiming rollback readiness.

Do not run destructive restore commands against production merely to prove the runbook. Staging/disposable rehearsal evidence is the release gate; production restore is an incident action.

## Deployment requirements

A production document backup is only meaningful when document storage itself is durable. Ephemeral process/container filesystems do not satisfy JobGrid's document durability requirement. Before release, staging must prove that an uploaded document survives process restart and redeployment and remains included in a complete ZIP export.

Secrets belong in provider secret stores. Never commit database DSNs, OAuth credentials, SMTP credentials, signing secrets, session cookies, private keys, user backup payloads, or private document contents to this repository or CI artifacts.
