# JobGrid F9 Import and F10 Undo, Archive, and Recovery

This guide documents the implementation delivered by JG-059 through JG-064. It complements `docs/JOBGRID_BUILD_GUIDE.md` with the deliberate import workflow, optimistic-version foundation, transactional Undo, Archive recovery workspace, and source-row deletion safety boundary.

## Deliberate import workflow

The dashboard importer follows four explicit stages: choose a CSV/JSON file, map source columns by position, review the server preview, then commit. Choosing a file and generating a preview do not write destination rows.

`frontend/src/api/imports.js` reads only enough client-side structure to show source headers and calls the existing authenticated `/crm/imports` contract through the shared Axios client. `frontend/src/components/ImportPreview.jsx` owns positional mapping, preview counts, invalid-row recovery, update controls, conflict recovery, and commit pending state. `CsvUpload.jsx` refreshes the dashboard only after a confirmed commit, so the active search/filter/sort state remains in place.

The classic CSV importer remains available as an explicit fallback during rollout. It is not the default mapped workflow.

### Mapping rules

- A source column is identified by its zero-based position and displayed label. Duplicate labels remain distinguishable.
- Exactly one source column must map to `url`.
- One target field can be selected only once.
- Unmapped source columns are shown as ignored and are never claimed as preserved.
- Exact saved-mapping reuse requires the same SHA-256 header fingerprint. `backend/app/services/import_mapping.py` returns `saved_mapping_header_mismatch` instead of applying a positional mapping to reordered or renamed columns.

### Preview and commit safety

Preview creation is owner-scoped and stores a private plan for 24 hours. The F9 backend caps uploads at 10 MiB and 2,000 records, validates URL identity, retains a bounded 100-row sample, and fingerprints the destination state.

Commit defaults are deliberately conservative:

- mode: `insert_only`
- invalid rows: reject the entire commit
- possible duplicates: skip
- empty values: do not replace existing data

Updating existing exact-URL rows requires selecting `update_selected`, selecting the individual mapped fields, and separately enabling empty replacement if desired. Import never changes application status, application notes, applied dates, clicked state, or archive state.

The commit rechecks owner, preview expiry, preview version/checksum, and the destination fingerprint under the account-scoped database lock. A stale destination or preview requires a new preview. A lost network response is retried with the same idempotency key so the server returns the original committed result instead of creating duplicates.

Rejected-row CSV downloads are owner-only, `no-store`, limited to the preview lifetime, and spreadsheet-safe. The file contains the original rejected source values. The short on-screen error list is only a summary.

## JG-060 repeatability evidence

`backend/tests/test_jg060_import_acceptance.py` covers UTF-8 BOM input, quoted fields, duplicate headers by position, blank values, malformed JSON, capacity boundaries, concurrent commit attempts, saved mapping reuse, spreadsheet escaping, and the measured 2,000-row fixture. Raising the current limits requires a separate design and production measurement.

## F10 optimistic version foundation

Migration `018_bulk_undo_foundation.py` adds positive integer `version` columns to `csv_rows` and `job_tracks`, both starting at 1.

Normal SQLAlchemy ORM mutations increment the version exactly once through the shared `before_update` hook registered in `backend/app/undo_models.py`. Raw bulk SQL writers that bypass ORM hooks must advance `version` in the same statement. Deletes remove the entity and do not require a surviving version.

`backend/app/services/undo_foundation.py::compare_and_update` is the common owner-scoped compare-and-update primitive. PostgreSQL locks the selected entity row before checking the expected version. A stale version returns `version_conflict` instead of overwriting newer state.

## Bounded private journal

Migration 018 also adds:

- `bulk_actions`: owner, operation kind, request key, status, creation time, undo expiry, and aggregate result metadata
- `bulk_action_effects`: action, entity type/id, strict before-image, post-mutation version, and per-effect undo status

The journal is bounded to 500 effects and 1 MiB of canonical JSON before-images per action. Before-images contain only changed allowlisted fields. Owner checks happen before writes and foreign IDs are not disclosed. Replaying the same request key returns the existing action, while conflicting reuse is rejected.

## Transactional bulk actions and Undo (JG-062)

`backend/app/services/bulk_actions.py` owns the F10 mutation/recovery service. `backend/app/routers/bulk_actions.py` exposes conflict-aware Undo and routes the existing Applications bulk-update URL through the journal without breaking its legacy `updated` and `failed` response fields.

Dashboard archive is also journaled. For each eligible entity the server records the narrow before-image, applies the mutation, flushes the optimistic version, and records the resulting version in the journal before the caller commits. Mutation and journal therefore succeed or roll back together.

Bulk responses add:

- `operation_id`
- `undo_expires_at`, generated by the server in UTC
- `undo_status`
- `replayed`

Existing response fields remain present.

### Undo contract

`POST /crm/bulk-actions/{operation_id}/undo` accepts:

```json
{"mode":"all_or_nothing"}
```

or the explicit recovery mode:

```json
{"mode":"restore_unchanged"}
```

The default is `all_or_nothing`. Before restoring anything, the service owner-checks the action, checks expiry, reloads every effect, and compares the entity's current version with the journal's post-mutation version.

If any entity changed or disappeared, default Undo returns 409 and restores zero records. The response includes aggregate conflict/missing counts. `restore_unchanged` is a separate deliberate request that restores only entities whose versions still match. Per-effect `restored`, `conflict`, and `missing` outcomes are persisted. Repeating a completed Undo is idempotent and does not mutate the records again.

Expired immediate Undo returns 410. A foreign-account action ID is owner-safe 404.

Application status, applied date, and follow-up restoration use the existing lifecycle writer instead of raw field rewrites. The recovery writes compensating lifecycle facts with deterministic operation IDs and resynchronizes reminders when status or follow-up state changes.

## Archive recovery workspace (JG-063)

`GET /rows` now accepts `archive_scope=active|archived|all`. The default remains `active`, so existing callers keep the previous behavior. The same server-side row filters, sorts, counts, and pagination logic are used for archived results. Row responses include optimistic `version`, `archived`, and `archived_at` metadata.

The `/archive` frontend route uses that shared query contract. It supports server-side search, ATS group, search bucket, location, decision, sponsorship, opened/error/JD-missing filters, sorting, and pagination. Legacy archived records without a timestamp display `Unknown` rather than a fabricated time.

`POST /rows/restore` requires selected owned row IDs plus their expected versions. Restore clears only `archived` and `archived_at`; it does not create visits, applications, or applied dates.

The cross-route `BulkActionStatus` panel stores only non-sensitive operation metadata in session storage. It shows the server-provided Undo deadline, remains available across route changes, renders 409 changed/missing counts, offers deliberate partial recovery only after a conflict, and explains that a 410 immediate-Undo expiry does not remove the Archive recovery path.

Archive listens for successful bulk-recovery events and reloads its query. Older Dashboard/Application views reload after successful Undo so stale state is not left visible.

## Permanent deletion and recovery boundary (JG-064)

Permanent deletion is not Undo. F10 ships no automatic source-row purge worker and reports `automatic_purge_enabled=false` from the preview contract.

The only permanent-delete path is for rows that are already archived:

1. The client selects archived rows in `/archive`.
2. `POST /rows/permanent-delete/preview` owner-checks the rows and optional expected versions.
3. The server returns the eligible count, warning, and an HMAC confirmation token bound to the owner, row IDs, and current versions.
4. The user explicitly confirms the warning.
5. `DELETE /rows` with `mode=delete` rechecks the rows and confirmation token before deleting the source rows.

Active rows cannot use this path. A stale version/token requires a fresh preview.

### Durable graph preservation

Repository foreign-key inventory shows the two source-row references that must be detached before source deletion:

- `CsvRow.duplicate_of_id`
- `JobTrack.csv_row_id`

The delete service clears those references before deleting selected archived `CsvRow` records. Applications remain. Durable application-owned lifecycle/evidence, documents, availability, aliases, contacts/interviews, work/reminder state, and other records that hang from `JobTrack` remain in place because the application record is not deleted.

Archived rows with unknown `archived_at` are never candidates for automatic purge because automatic purge is not implemented or enabled. Any future automatic purge is a separate feature and must remain opt-in, require a known age of at least 30 days, use bounded batches, preserve the same graph, expose a disable switch, and pass a production recovery rehearsal before activation.

### Backup recovery proof

JG-064 acceptance exports the portable v2 backup before an explicit source purge, deletes the archived source row, then restores the backup into another account. The restored row-to-application relationship, visit state, application status, notes, and open count must match the pre-purge history. This proves that the existing backup path can recover the tested durable history from a pre-purge backup. It does not claim that JSON backup contains private document bytes; byte-level document recovery remains the responsibility of the existing authenticated document bundle workflow.

## Validation

Focused backend acceptance:

```sh
cd backend
pytest tests/test_bulk_undo.py -q
```

The suite covers transaction rollback, zero-restore conflicts, explicit partial Undo, retry idempotency, 410/404 behavior, lifecycle correction after application Undo, Archive restore semantics, source-row graph preservation, unknown archive timestamps, default-disabled purge, newer-import conflict protection, and pre-purge backup recovery.

Focused browser acceptance:

```sh
cd frontend
npx playwright test tests/archive-undo.spec.ts --project=chromium
```

It covers archive/reload/restore, two-tab conflict protection, partial counts, expired immediate Undo with Archive recovery, and archived filtering.

Before merge, run the repository's complete backend, frontend, migration/schema, build, and Chromium checks. A ticket is not complete based only on focused tests.

## Observability

Bulk Undo logs operation ID, aggregate outcome, restored/conflict/missing counts, and elapsed milliseconds. Logs do not contain before-images. Permanent deletion returns only aggregate detachment/deletion counts. The owner is carried by authenticated database scope rather than written into browser-readable recovery state.

Operational release evidence must record:

- the deployment/PR identifier
- CI result
- automatic purge state, which must be disabled for this release
- recovery test result
- source rows deleted/restored in the rehearsal only as aggregate counts

## Deployment and rollback

Migration 018 must already be applied before JG-062 to JG-064 application code.

Recommended deployment order:

1. Deploy backend version/journal-aware mutation and Undo routes.
2. Verify focused backend acceptance and schema head.
3. Deploy Archive and global Undo UI.
4. Keep automatic purge disabled.
5. Verify Archive restore and two-tab conflict behavior in the deployed environment.

Rollback is application-first. Disable or revert the bulk mutation/Undo UI, keep Archive read/restore available when possible, and leave automatic purge disabled. Do not downgrade version/journal columns after actions have been recorded without a separate data migration/recovery review. Existing journal before-images may be allowed to expire normally or be scrubbed through the bounded cleanup service.

## Portable backup metadata

Private before-images are actionable for 10 minutes. `cleanup_bulk_action_journals` removes expired `before_json` values and changes still-active completed/partial actions to `expired`. Non-private operation metadata is retained for 30 days, then deleted in bounded batches.

Portable v2 backups may include F10 operation metadata through the existing `f10_bulk_action_metadata` extension. The extension never includes before-images and every exported record carries `undo_available: false`. Restored metadata is always written with `status=expired`, no effects, and `restored_non_actionable=true`. A backup restore can preserve audit context without manufacturing a working Undo action in a different database state.

Transient F9 previews and rejected-row source payloads remain excluded from backups.
