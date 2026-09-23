# JobGrid F9 Import and F10 Undo Foundation

This guide documents the implementation delivered by JG-059, JG-060, and JG-061. It complements `docs/JOBGRID_BUILD_GUIDE.md` with the new import workflow and the version/journal foundation that later F10 tickets will use.

## Deliberate import workflow

The dashboard importer now follows four explicit stages: choose a CSV/JSON file, map source columns by position, review the server preview, then commit. Choosing a file and generating a preview do not write destination rows.

`frontend/src/api/imports.js` reads only enough client-side structure to show source headers and calls the existing authenticated `/crm/imports` contract through the shared Axios client. `frontend/src/components/ImportPreview.jsx` owns positional mapping, preview counts, invalid-row recovery, update controls, conflict recovery, and commit pending state. `CsvUpload.jsx` refreshes the dashboard only after a confirmed commit, so the active search/filter/sort state remains in place.

The classic CSV importer remains available as an explicit fallback during rollout. It is not the default mapped workflow.

### Mapping rules

- A source column is identified by its zero-based position and displayed label. Duplicate labels remain distinguishable.
- Exactly one source column must map to `url`.
- One target field can be selected only once.
- Unmapped source columns are shown as ignored and are never claimed as preserved.
- Exact saved-mapping reuse requires the same SHA-256 header fingerprint. `backend/app/services/import_mapping.py` returns `saved_mapping_header_mismatch` instead of applying a positional mapping to reordered or renamed columns.

### Preview and commit safety

Preview creation is owner-scoped and stores a private plan for 24 hours. The existing F9 backend caps uploads at 10 MiB and 2,000 records, validates URL identity, retains a bounded 100-row sample, and fingerprints the destination state.

Commit defaults are deliberately conservative:

- mode: `insert_only`
- invalid rows: reject the entire commit
- possible duplicates: skip
- empty values: do not replace existing data

Updating existing exact-URL rows requires selecting `update_selected`, selecting the individual mapped fields, and separately enabling empty replacement if desired. Import never changes application status, application notes, applied dates, clicked state, or archive state.

The commit rechecks owner, preview expiry, preview version/checksum, and the destination fingerprint under the account-scoped database lock. A stale destination or preview requires a new preview. A lost network response is retried with the same idempotency key so the server returns the original committed result instead of creating duplicates.

Rejected-row CSV downloads are owner-only, `no-store`, limited to the preview lifetime, and spreadsheet-safe. The file contains the original rejected source values. The short on-screen error list is only a summary.

## JG-060 repeatability evidence

`backend/tests/test_jg060_import_acceptance.py` covers:

- UTF-8 BOM input
- quoted commas and quoted newlines
- duplicate headers by position
- blank values
- malformed JSON
- the exact 2,000-record boundary
- 2,001-record rejection before destination writes
- uploads over 10 MiB rejected before destination writes
- two independent database sessions attempting commits from the same original account destination state, with one commit succeeding and the stale plan rejected
- saved mapping backup/restore followed by exact fingerprint reuse and explicit mismatch rejection
- spreadsheet formula escaping in rejected-row downloads
- measured 2,000-row preview/commit count, SQL-statement count, and elapsed runtime printed as `JG060_MAX_FIXTURE ...` in test output

The measured test records evidence. It does not redefine the 2,000-row/10 MiB limits as a capacity claim. Raising either limit requires a separate design and production measurement.

## F10 optimistic version foundation

Migration `018_bulk_undo_foundation.py` is chained after the actual current migration head `017`. It adds positive integer `version` columns to `csv_rows` and `job_tracks`, both starting at 1.

Normal SQLAlchemy ORM mutations increment the version exactly once through the shared `before_update` hook registered in `backend/app/undo_models.py`. The repository writer inventory found two production mutation paths that bypass ORM update events:

1. `backend/app/routers/rows.py` uses bulk SQL for dashboard archive and relationship detachment before delete.
2. `backend/app/services/retention.py` uses bulk SQL for automatic archive.

Those statements increment `version` in the same SQL update. Existing import updates, row-click/lifecycle mutations, CRM/application edits, ApplyPilot/lifecycle service mutations, and restore code use ORM assignment and therefore use the shared hook. Deletes remove the entity and do not require a surviving version.

`backend/app/services/undo_foundation.py::compare_and_update` is the common owner-scoped compare-and-update primitive for later F10 mutation tickets. PostgreSQL locks the selected entity row before checking the expected version. A stale version returns the `version_conflict` domain error. JG-061 does not expose a bulk-mutation or Undo route.

## Bounded private journal

Migration 018 also adds:

- `bulk_actions`: owner, operation kind, request key, status, creation time, undo expiry, and aggregate result metadata
- `bulk_action_effects`: action, entity type/id, strict before-image, post-mutation version, and per-effect undo status

The journal contract is intentionally bounded:

- maximum 500 effects per action
- maximum 1 MiB canonical JSON before-image payload
- one `(user_id, request_key)` operation identity
- one effect per `(action_id, entity_type, entity_id)`
- before-images contain only fields that actually change and are present in the entity-specific allowlist
- owner checks happen before journal writes and do not reveal whether a missing ID belongs to another account
- no secrets, uploaded bytes, whole-row dumps, or unrelated private fields are accepted

`create_bulk_action_journal` validates target count and snapshot size before adding the journal. Replaying an identical request key returns the existing journal. Reusing the key for different journal input returns `request_key_conflict`.

## Expiry and backups

Private before-images are actionable for 10 minutes. `cleanup_bulk_action_journals` removes expired `before_json` values and changes still-active completed/partial actions to `expired`. Non-private operation metadata is retained for 30 days, then deleted in bounded batches.

Portable v2 backups may include F10 operation metadata through the existing `f10_bulk_action_metadata` extension. The extension never includes before-images and every exported record carries `undo_available: false`. Restored metadata is always written with `status=expired`, no effects, and `restored_non_actionable=true`. A backup restore can therefore preserve audit context without manufacturing a working Undo action in a different database state.

Transient F9 previews and rejected-row source payloads remain excluded from backups.

## Validation and failure behavior

The JG-061 regression suite verifies:

- version increments across ORM row updates, mapped-import updates, dashboard bulk archive, retention bulk archive, CRM JobTrack updates, and the compare-and-update helper
- stale optimistic versions conflict instead of overwriting newer state
- >1 MiB snapshots and >500-target journals fail with 413-class domain errors before journal writes
- duplicate operation keys create only one journal and conflicting reuse fails
- expired before-images are scrubbed while audit metadata remains
- foreign-account effect references return an owner-safe not-found error and create no journal
- snapshot generation records only changed allowlisted fields

## Deployment and rollback

Deploy database migration 018 before application code that expects row/track versions. The change is additive and existing rows receive server default version 1. Undo routes are not enabled by JG-061, so deploying this ticket does not expose destructive restore behavior.

Rollback is safe only while later F10 features are not relying on the version/journal columns. Revert the application changes first, then downgrade migration 018. Do not downgrade after later bulk-action tickets have begun persisting journals without reviewing their data-loss implications.
