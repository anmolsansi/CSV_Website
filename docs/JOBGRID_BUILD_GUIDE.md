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

JG-025 extends backup v2 with durable manual Today work items and snooze overrides. Portable backups remap WorkItem track/row/view references and regenerate action keys from destination IDs so source database IDs never become restore authority.

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

## Today queue storage foundation

JG-025 adds the persistence and validation foundation for the Today queue without exposing a Today API or navigation yet.

### Manual work items

`WorkItem` stores manual actions only. Derived application follow-ups continue to come directly from `JobTrack.follow_up_at`; they are not copied into `work_items`.

A work item belongs to one user and contains:

- an optional application source (`track_id`), CSV-row source (`row_id`), and saved-view source (`source_view_id`);
- an optional per-owner `origin_key` used to deduplicate explicit source actions;
- a trimmed description from 1 through 500 characters;
- an optional timezone-aware due timestamp;
- priority `0..3`;
- state `pending` or `done`;
- a positive optimistic-lock `version`;
- created/updated timestamps and an optional completion timestamp.

Database constraints enforce the description, priority, state, positive version, and the rule that a `done` item must have `completed_at`. Source foreign keys use `ON DELETE SET NULL`, so deleting an application, CSV row, or saved view detaches the source without deleting the user's action or description.

Explicit saved-view actions use an owner-scoped origin key such as `view:{view_id}:row:{row_id}`. The unique `(user_id, origin_key)` contract makes repeated adds idempotent per account while allowing different accounts to use the same source-shaped key.

### Follow-up overrides and action keys

`WorkItemOverride` stores only per-user snooze state for a Today action. Its natural identity is `(user_id, action_key)`, with a timezone-aware `snoozed_until` and positive `version`.

Action keys are server-generated:

- manual action: `manual:{work_item_id}`
- derived follow-up: `followup:{track_id}:{UTC due timestamp}`

`backend/app/today_schemas.py` validates action ownership against the authenticated user's WorkItem or JobTrack. A follow-up key is accepted only while its timestamp still matches the track's current `follow_up_at`. Changing the follow-up date therefore creates a new action key and makes an old snooze irrelevant rather than silently applying it to a different due date. Optional work-item source IDs are also resolved through owner-scoped queries before future route code can persist them.

### Migration, backup, and rollback

Alembic revision `008` creates `work_items` and `work_item_overrides` after the existing revision `007_maintenance_status.py`. The roadmap's earlier reserved filename `007_today_queue.py` is not reused because Alembic must keep one linear revision ID.

Backup schema revision `2.4.0` adds optional `work_items` and `work_item_overrides` sections. Older v2 files can omit both sections and their counts without changing their original checksum contract. WorkItem track/row/view links are backup-local references. Saved-view origin keys are translated to backup-local references and rebuilt with destination IDs on restore. Override records never export raw `manual:{id}` or `followup:{track_id}:...` keys; restore regenerates them from remapped destination records.

Normal application rollback does not require dropping these tables. Leave the future Today routes/navigation disabled and retain both new tables plus existing `JobTrack.follow_up_at` history. A schema downgrade is appropriate only when the new Today data is intentionally disposable.

Focused backend verification:

```sh
cd backend
python -m pytest tests/test_today_models.py tests/test_backup_contract.py -q
```

## Today queue API and guarded mutations

JG-026 exposes the backend Today contract without adding a Today page or navigation item. The API is registered from `backend/app/routers/today.py`; queue composition and mutations live in `backend/app/services/today.py`.

### Queue membership and ordering

`GET /crm/today?limit=50&include_snoozed=false` returns `items`, `next_cursor`, `as_of`, the authenticated account `timezone`, and `counts`.

The service uses the validated account IANA timezone to calculate the local day's UTC start and next-midnight boundary. It includes:

- pending manual work items with no due date or a due date before the next local midnight;
- derived application follow-ups due before the next local midnight;
- no follow-up whose application status is `rejected`, `offer`, or `not_applying`;
- no actively snoozed action unless `include_snoozed=true`.

Items are ordered by due time ascending with undated items last, then priority descending, action type, and source ID. The maximum page size is 100. The opaque signed cursor carries the ordering tuple and the first page's `as_of` instant. Later pages therefore reuse the same day and snooze boundary, but the API does not claim an immutable database snapshot while records are edited.

`counts` is calculated from the same visible membership used for the queue and reports `total`, `overdue`, `due_today`, and `undated`.

### Manual work-item mutations

Create a manual action:

```http
POST /crm/work-items
Content-Type: application/json

{"description":"Review Acme role","priority":2,"due_at":"2026-09-21T18:00:00Z"}
```

The response is `201` and includes the server-generated `manual:{id}` action key, work-item `version`, and separate `snooze_version`.

Edit, complete, or explicitly reopen with optimistic locking:

```http
PATCH /crm/work-items/42
Content-Type: application/json

{"version":3,"state":"done"}
```

A successful write increments the work-item version. A stale version returns `409` with code `stale_version` and does not overwrite newer state. Completing writes `completed_at`; reopening clears it. Optional source IDs on create are resolved inside the authenticated account before the item is stored.

### Snooze and follow-up resolution

`POST /crm/today/snooze` accepts `action_key`, a timezone-aware future `until`, and the current `snooze_version`. Snoozes are limited to 365 days. The first snooze advances the override version from the queue's baseline 1 to 2, so a second stale tab cannot silently replace it.

Derived follow-ups remain `JobTrack.follow_up_at` facts. They are never copied into `work_items`.

Clear one:

```http
POST /crm/today/follow-up
X-Operation-ID: 9f0fa584-3ac8-4fac-b589-b79a4918c250
Content-Type: application/json

{"action_key":"followup:17:2026-09-21T12:00:00Z","resolution":"clear"}
```

For `resolution:"reschedule"`, include a timezone-aware `follow_up_at`. The route validates that the action key still matches the current follow-up, rejects inaccessible or terminal sources, and calls the existing lifecycle writer. That emits `followup_changed` without setting `applied_at` or recording `first_applied`.

### Add from a saved view

`POST /crm/today/from-view` accepts an owned `view_id`, `limit` from 1 through 20, and a request UUID. JG-026 supports the existing `job_links` saved-view type because its durable origin contract is row-based.

The service rebuilds the saved view through the shared R2 `RowQuery` filter and sort implementation. For the first matching rows it creates origin keys shaped as `view:{view_id}:row:{row_id}`. Existing pending actions are returned instead of duplicated. Completed actions stay completed and are reported in the `completed` count; this endpoint never reopens them implicitly.

### Errors, ownership, and rollback

Expected failures return bounded codes without record contents. Foreign work items, follow-ups, and saved views behave as not found. Invalid cursors and request shapes return validation errors. Stale work-item and snooze writes return `409`.

Today operations log only a request/operation ID, safe outcome code, affected count, and elapsed time. Descriptions, URLs, notes, and action payload text are not logged.

JG-026 backend rollback remains code-only: remove/disable the Today router registration while retaining the JG-025 tables and existing `JobTrack.follow_up_at` data. JG-027 separately owns the active frontend route/navigation and can be disabled without deleting persisted Today data.

Focused verification:

```sh
cd backend
python -m pytest tests/test_today_api.py -q
```

The repository CI remains the integration gate for PostgreSQL backend tests, backend compilation, frontend production build, and Chromium regressions.

## Today screen and accessible action controls

JG-027 activates the Today experience at `/today` and adds **Today** to the authenticated main navigation. The page consumes the JG-026 API contract instead of reimplementing queue membership in the browser. Server `as_of` and account `timezone` values are used to label the already-visible queue as **Overdue**, **Due today**, and **Undated**.

### User flow and UI states

The page has explicit initial loading, valid empty, loaded, recoverable network-error, per-item pending, and stale-conflict states. A failed mutation never removes an item optimistically. Successful mutations reload the persisted queue, and returning focus to the browser window refreshes the queue again.

Each action shows its description, company/role when available, origin label, and due time in the account timezone. The primary action is **Complete**. Manual completion patches the work item with its current optimistic version. Follow-up completion explicitly clears the underlying `JobTrack.follow_up_at`; it does not mark the application applied.

The current repository has a job-row `RowDrawer`, but it does not have a separate application-detail drawer. To preserve existing architecture, row-backed Today items navigate to the existing Job Links detail context and track-backed follow-ups navigate to the Applications surface. JG-027 does not introduce a second drawer or a parallel application editor.

### Manual actions, snooze, and reschedule

The inline manual-action form sends `POST /crm/work-items`. Description is required and limited to 500 characters. Due time is optional. The `datetime-local` input is interpreted in the browser/device timezone and converted to an explicit UTC timestamp before submission; queue membership and display grouping remain authoritative to the account timezone returned by the server.

Create, snooze, complete, and reschedule controls are disabled while their own request is in flight. Failed create/reschedule requests keep the user's draft. A `409` optimistic-lock conflict stays visible beside the affected action with an explicit refresh control.

Snooze and reschedule use native modal dialogs. Keyboard activation works with the normal button semantics, Escape/Cancel closes the dialog, and focus returns to the control that opened it.

### Deliberate Add to Today entry points

Saved Views exposes **Add to Today** only for `job_links` views. Before any mutation, the UI runs the saved view through the same dashboard query serializer and displays:

- the saved-view origin name;
- the exact matching row count;
- the exact number that will be submitted;
- the hard maximum of 20 actions.

Confirmation calls `POST /crm/today/from-view`; its response reports `created`, `existing`, and `completed`, so repeated entry remains visible rather than implying every row was newly created.

The existing Job Links row drawer and Applications table each expose a one-item **Add to Today** action. They create a manual work item with the owner-validated row/application source. These controls do not alter application status.

### Failure, accessibility, and rollback

Expected server validation text is surfaced without record contents. Stale writes retain the action and require refresh instead of overwriting newer state. The page never derives an application from opening a detail link or from completing a manual task.

To roll the UI back, remove/disable the `/today` route and Today navigation entry. Keep the JG-025 tables, JG-026 API, manual work items, snooze overrides, and existing follow-up dates intact. Original Applications follow-up editing remains available.

Focused frontend verification:

```sh
cd frontend
npm run test:e2e -- tests/today.spec.ts --project=chromium
npm run build
```

The Today browser fixture freezes the API `as_of` and account timezone instead of deriving day boundaries from the test runner's wall clock. Coverage includes overdue/undated rendering, keyboard snooze persistence after reload, failed-complete preservation, persisted follow-up rescheduling in the existing Applications surface, and the saved-view exact-count/20-item cap.


## F1 integrated Today acceptance

JG-028 is the integrated acceptance step for the F1 Today group. It adds no route, table, migration, or alternate queue implementation. The acceptance suite exercises the JG-025 storage/backup contract, JG-026 queue/mutation service, and JG-027 interface as one workflow.

### Deterministic 60-action fixture

`backend/tests/test_today_api.py::test_fixed_fixture_membership_and_count_parity` creates exactly 60 synthetic action sources across two accounts:

- 30 manual WorkItems: owned overdue, due-today, undated, tomorrow, and completed records plus five foreign-account records;
- 30 JobTrack follow-ups: owned overdue, due-today, tomorrow, and terminal records plus five foreign-account records;
- eight owned visible actions receive active snooze overrides.

At the fixed `2026-09-21T12:00:00Z` clock in UTC, the unsnoozed queue must contain exactly 25 actions: 12 overdue, 8 due today, and 5 undated. With `include_snoozed=true`, it must contain exactly 33: 16 overdue, 12 due today, and 5 undated. Tomorrow, completed, terminal, and foreign-account records must never leak into normal membership.

This fixture is intentionally larger than one page-sized work session and freezes expected membership rather than accepting approximate counts.

### Bounded queue SQL and PostgreSQL plans

Manual queue serialization reads optional application, CSV-row, and saved-view source metadata. Those relationships are eager-loaded in the main WorkItem query so serialization does not issue relationship SELECTs per item.

`test_no_n_plus_one_queue_queries` creates 12 manual actions with 12 distinct track/row/view source triples after expunging the ORM identity map. The complete queue build is required to use exactly three SELECT statements: one eager-loaded manual query, one follow-up query, and one override query. Increasing the number of sourced actions therefore does not increase query count.

Repository PostgreSQL CI also runs `test_today_postgres_query_plans_use_owner_due_indexes`. With sequential scans disabled only for the acceptance EXPLAIN, the real manual membership query must remain index-backed. PostgreSQL is allowed to choose the state, owner, due-time, or composite owner/due index according to fixture costs. A second owner-plus-due probe must expose `ix_work_items_user_due`, proving that the composite path is eligible. The follow-up membership plan must use either the owner or follow-up timestamp index. This records the planner's real cost-based choice instead of forcing one plan shape. It is not a latency benchmark and does not claim a production response-time target.

### Recovery, detachment, and timezone behavior

The F1 acceptance regressions verify these recovery boundaries:

- deleting a Saved View source detaches `source_view_id` through `ON DELETE SET NULL`, while the manual action and its description remain in Today;
- changing the authenticated account timezone recomputes next-local-midnight membership on the server. A cross-midnight action can be tomorrow in UTC and due today in Asia/Kolkata without changing the stored UTC instant;
- v2 export/restore moves all owned fixture WorkItems, JobTracks, and eight snooze overrides into a different destination owner, then reconstructs the same 25 visible / 33 including-snoozed queue counts;
- restored override keys are regenerated from destination IDs and remain destination-owner scoped.

### Saved-view complete-order acceptance

`test_saved_view_page_two_uses_full_filtered_order_and_no_duplicate_actions` creates 25 matching Greenhouse rows plus nonmatching rows, reads page 1 and page 2 of the shared sorted browse contract, and then adds 20 items from the Saved View. The created Today actions must match the first 20 rows from the complete filtered/sorted order, including the second browse page. Repeating the request creates zero duplicates and returns the same 20 pending actions.

This protects F1 from regressing back to visible-page-only selection.

### Five-action work session

The browser acceptance test `frontend/tests/today.spec.ts` performs a deterministic work session that:

1. opens an application-backed action in the existing Applications surface and returns to Today;
2. completes a manual action;
3. snoozes a second manual action;
4. reschedules an application follow-up;
5. attempts another completion, observes a synthetic server failure, and retries successfully.

The scripted session uses eight Today control activations because snooze and reschedule each require an explicit dialog confirmation and the failure case requires a retry. Four server mutations are confirmed. After a full reload, every confirmed removal remains removed, the failed-then-retried item is not lost, and the detail-only action remains available.

This is deterministic workflow evidence, not a human speed study. JG-028 does not claim that eight clicks are faster than a measured baseline. The acceptance claim is narrower: the tested work session can be completed from one queue with explicit controls, survives detail navigation/reload, and leaves no silently lost confirmed changes.

### Preserved release regressions

Full repository CI remains the group gate. In addition to the new F1 tests, it must keep the existing application-memory, complete filtered/sorted selection, and popup/tab-opening regressions green. In particular, `frontend/tests/release-workflows.spec.ts` continues to prove that the top-five workflow opens only successful eligible tabs, severs `window.opener`, and records no visits for blocked popups.

Focused commands:

```sh
cd backend
python -m pytest tests/test_today_api.py -q

cd ../frontend
npm run test:e2e -- tests/today.spec.ts --project=chromium
npm run build
```

Repository CI run **#204** provides the integrated evidence for this implementation revision: 367 backend tests passed on PostgreSQL, 141 Chromium Playwright tests passed, the frontend production build passed, and backend compilation passed. The earlier run #201 caught an over-specific planner assertion; the test was corrected to record PostgreSQL's cost-based index choice without changing the runtime query contract or schema.

No JG-028 migration exists. Roll back the queue-loading optimization by reverting its application-code commit if necessary. Persisted JG-025 Today records, snooze overrides, and `JobTrack.follow_up_at` remain compatible. The broader F1 UI rollback is still to disable the Today route/navigation without deleting user data.

## Why v2 exists

The original portable backup is lossy. A backup can contain an application record while the old restore path does not reconstruct the same application state. V2 makes all durable sections and persisted fields explicit before restore code constructs ORM objects.

Source database primary keys and `user_id` values are never portable authority. Export replaces source identities with opaque backup-local references. Restore allocates destination IDs and binds every restored record to the authenticated destination user.

## V2 document shape

A v2 document contains exactly:

- `version`: `"2.0"`
- `backup_id`: UUID string
- `exported_at`: UTC ISO-8601 timestamp
- `schema_revision`: currently `"2.6.0"`
- `identity_rule_version`: canonical-identity rule used for derived URL rebuilds, currently `"ccr-identity-1"`
- `sections`: the sixteen current v2 sections
- `counts`: exact record count for every section
- `checksum_sha256`: lowercase SHA-256 digest of canonical `sections` JSON

The sixteen current sections are:

1. `csv_rows`
2. `url_history`
3. `job_tracks`
4. `application_evidence`
5. `evidence_recovery`
6. `company_aliases`
7. `work_items`
8. `work_item_overrides`
9. `lifecycle_events`
10. `saved_views`
11. `sessions`
12. `audit_events`
13. `applypilot_batches`
14. `column_preferences`
15. `user_goal`
16. `user_profile`

Every record has a non-empty `backup_ref` unique within its section. Nullable fields remain present as keys, preserving the difference between null, empty text, `false`, and zero.

## Export identity and references

JG-002 generates a fresh `backup_id` for each export. Within that document, each record receives an opaque deterministic UUIDv5 reference derived from the backup ID, section, and source record identity. This makes repeated references inside one backup stable without exposing a source database ID as a reusable authorization identifier.

Relationships are translated as follows:

- `CsvRow.duplicate_of_id` -> `duplicate_of_ref`
- `JobTrack.csv_row_id` -> `csv_row_ref`
- `WorkItem.track_id` -> `track_ref`
- `WorkItem.row_id` -> `row_ref`
- `WorkItem.source_view_id` -> `source_view_ref`
- `WorkItemOverride.action_key` -> portable manual/follow-up target reference, then a destination action key on restore
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

All fourteen current sections are read within one transaction. The service fully builds and validates the document before the route serializes the response, so transaction resources close even if serialization fails.

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

### Company aliases

`CompanyAliasBackupV2` exports the normalized owner-local `alias_key`, preserved `display_name`, stable UUID `company_key`, and creation timestamp. Source IDs and source account ownership are reconstructed from `backup_ref` and the authenticated destination user. Two accounts may use the same alias key without sharing a company identity.

Backups created before JG-030 may omit `company_aliases` and its count. Their checksum is validated against the older section shape. New backups record `identity_rule_version`; restore rejects an unknown recorded rule before mutation.

Derived `canonical_url` and `canonical_url_hash` values are intentionally not authoritative backup fields. Restore preserves each original `url` and rebuilds the derived values with the recorded supported rule.

### Work items and Today overrides

`WorkItemBackupV2` exports durable manual action fields plus backup-local application, CSV-row, and saved-view references. The description is preserved even when one of those source records is later deleted. `WorkItemOverrideBackupV2` exports snooze/version state plus a portable manual-work-item or follow-up-track target. Restore regenerates the destination action key instead of trusting a source database ID.

Older v2 documents produced before JG-025 may omit both Today sections and counts. Validation treats them as empty and computes the checksum against the original document shape.

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


## JG-014 retention policy and maintenance health

JG-014 adds the account settings/API layer on top of the JG-012 policy fields and JG-013 bounded archive worker. It does **not** activate production maintenance, expose permanent purge, or add user-facing archived-row recovery.

### Durable maintenance health

Alembic revision `007` adds `maintenance_status`, keyed by `job_name`. The row stores only aggregate operational state:

- latest outcome;
- last attempted cleanup time;
- last successful cleanup time;
- last failed cleanup time;
- the existing aggregate cleanup result;
- update time.

The table has no user-owned data and is deliberately excluded from portable user backups. It exists because the designated maintenance process and API-serving workers may be different processes. Process-local timestamps would disappear on restart or be invisible to another worker, and `CsvRow.archived_at` cannot prove that a zero-work cleanup ran successfully.

The archive worker records `success` or `no_work` only after the bounded archive transaction completes. A later failure updates failure/attempt state but preserves the prior successful timestamp. Health persistence runs in a separate transaction, so a health-write problem cannot turn already committed archive work into a false archive failure. Missing health then degrades safely to unavailable.

### Retention profile API

Authenticated account settings are available at:

```http
GET /crm/profile/retention
```

The response contains:

```json
{
  "archive_after_days": 0,
  "eligible_row_count": 0,
  "maintenance": {
    "status": "disabled",
    "last_successful_cleanup_at": null,
    "last_attempted_cleanup_at": null,
    "last_outcome": "disabled"
  },
  "purge_available": false,
  "archived_rows_ui_available": false,
  "recovery_message": "Archived rows are preserved. Until JG-062 ships recovery requires the existing API/operator workflow."
}
```

`eligible_row_count` is a read-only preview for the authenticated account. It counts only rows that are still unarchived, have a known `clicked_at`, and are at or before the saved account cutoff. Reading the endpoint never calls the archive worker and never mutates rows.

Update the policy with:

```http
PATCH /crm/profile/retention
Content-Type: application/json

{"archive_after_days": 30}
```

The request body must contain exactly one field. Accepted values are `0` for disabled or an integer from `7` through `3650`. The route has no user-ID parameter, so it can change only the authenticated account. Existing `GET /preferences` and `PUT /preferences/retention` behavior remains compatible.

Saving a positive account policy does not turn on the operator worker. `AUTO_ARCHIVE_AFTER_DAYS=0` remains the global archive kill switch, `RUN_MAINTENANCE_JOBS=false` remains the generic-process default, and `AUTO_PURGE_AFTER_DAYS=0` remains the purge boundary.

### Health interpretation

The UI/API exposes only three health states:

- `disabled`: the global automatic-archive kill switch is off;
- `healthy`: the latest durable state has a successful cleanup within the freshness window and no later failure;
- `unavailable`: no successful state exists, a failure occurred after the last success, or the last success is stale.

The freshness window is the larger of two cleanup intervals or one cleanup interval plus five minutes. A failed or stale worker is never presented as a healthy zero-work run. The eligibility preview remains a separate database calculation.

### Dashboard behavior

`frontend/src/components/RetentionSettings.jsx` loads the profile when Dashboard opens. The control defaults to `0`, validates `0` or `7..3650`, and requires an explicit **Save**. Editing the input alone makes no request. While a save is pending the button is disabled, failed saves retain the draft, successful saves refresh the server result, and load failures expose a Retry action.

The panel shows the saved-policy eligibility preview, maintenance health, last successful cleanup time when known, and a permanent-purge unavailable message. Before JG-062 there is no archived-row recovery link. The panel explains that preserved archived rows require the existing API/operator recovery workflow.

### Operations, verification, and rollback

**Operational owner:** the deployment operator responsible for the single designated JobGrid maintenance process. No generic web worker should be enabled merely because this UI is deployed.

One bounded manual run remains:

```sh
cd backend
python -c "from app.jobs import cleanup_clicked_rows; print(cleanup_clicked_rows())"
```

That command can archive eligible rows when the global archive gate is enabled. It never purges rows.

Focused verification:

```sh
cd backend
python -m pytest tests/test_retention_profile.py tests/test_cleanup_job.py tests/test_archive_timestamps.py tests/test_backup_contract.py -q
python -m compileall app

cd ../frontend
npm run build
npm run test:e2e -- tests/retention-settings.spec.ts --project=chromium
```

Revision 007 must also be rehearsed up and down against a disposable database. Repository CI remains the final PostgreSQL/full-suite integration gate.

Rollback starts by keeping `AUTO_ARCHIVE_AFTER_DAYS=0` and `RUN_MAINTENANCE_JOBS=false`. The frontend/API changes can then be rolled back without changing user retention values. The `maintenance_status` table contains operational aggregates only; revision 007 can be downgraded by dropping that table after the worker is stopped. Do not remove `archived_at`, `retention_days`, or reinterpret legacy unknown archive timestamps. Permanent purge remains unavailable.\n## JG-015 reusable mutation validation contract

JG-015 introduces shared validation primitives for application mutation work without changing the existing database schema or activating stricter validation on public application writers. JG-016 owns route/service adoption, transaction behavior, and writer-wide enforcement. JG-017 owns frontend field-error rendering and import feedback.

### Status and omitted-field behavior

`backend/app/schemas.py` defines the reusable `JobTrackStatus` type with the existing persisted status values:

`opened`, `applied`, `follow_up`, `interview`, `rejected`, `offer`, and `not_applying`.

`backend/app/services/validation.py` exposes `STATUS_VALUES` from the ORM model's authoritative status list and `validate_status()` for service-level validation. A status may be omitted by a patch caller, but an explicitly supplied null or an unrecognized value is invalid.

`explicit_model_fields()` uses Pydantic's `model_fields_set` and `exclude_unset` behavior to distinguish an omitted field from an explicit clear. For example, a request that supplies only `company` does not manufacture timestamp changes, while `applied_at: null` and `follow_up_at: ""` remain visible to the service as explicit clears.

### Timestamp contract

`parse_timestamp()` returns the application's existing UTC-naive storage representation.

- `null` or an empty string clears a timestamp when the caller allows clearing.
- A date-only value such as `2026-01-02` requires the authenticated account's explicit IANA timezone.
- Date-only input is interpreted as local midnight and then converted to UTC. In `Asia/Kolkata`, `2026-01-02` becomes `2026-01-01 18:30:00` UTC.
- Full datetime values must include `Z` or a numeric UTC offset.
- Offset-less datetimes, impossible dates, invalid timezone names, and unrecognized strings are rejected before mutation.

The helper never uses the server's local timezone. JG-016 is responsible for passing `User.timezone` when a date-only request reaches an application writer.

### Text and URL boundaries

`validate_text_limits()` enforces the R5 limits before ORM construction:

- company: 300 characters;
- title: 300 characters;
- notes: 20,000 characters.

`validate_job_url()` accepts a non-empty HTTP(S) URL up to 2,048 characters, requires a host, rejects embedded username/password credentials and whitespace, and returns accepted text unchanged. It does not silently canonicalize or rewrite a user's source URL.

### Bulk ID normalization and ownership checks

`normalize_bulk_ids()` accepts 1 through 500 positive integer entries. It rejects booleans, zero, negative values, strings, empty lists, and oversized batches. Duplicate IDs are normalized in first-seen order while every original source index is retained.

`require_owned_bulk_ids()` compares the normalized IDs with IDs already resolved inside the authenticated account scope. If any requested ID is absent, it raises the shared safe `not_found` result with HTTP status 404 and points to the first source index. It does not distinguish a foreign record from a nonexistent record.

JG-016 must perform the account-scoped query before any write and pass the resulting owned IDs to this helper.

### Error compatibility

`ValidationContractError` carries a safe code, field, message, and intended HTTP status. Its normalized detail shape is:

```json
{
  "code": "validation_error",
  "fields": [
    {"field": "status", "message": "Invalid value"}
  ]
}
```

`format_error_detail()` converts legacy string details, legacy string-valued dictionaries, and the new field-list form into that shape. Unknown nested payloads are replaced with a generic message rather than stringified, which prevents request bodies or secrets from being reflected accidentally.

JG-015 does not globally replace FastAPI error handling. JG-016 and JG-017 adopt this formatter at the mutation/API and UI boundaries respectively so compatibility can be tested with each activation step.

### Verification

Focused backend validation:

```sh
cd backend
python -m pytest tests/test_mutation_validation.py -q
python -m compileall app
```

Affected regression coverage:

```sh
cd backend
python -m pytest tests/test_crm.py tests/test_application_memory.py tests/test_filtered_exports.py tests/test_query_contracts.py -q
```

`backend/tests/test_mutation_validation.py` covers every allowed and rejected status, omitted/null/empty timestamp semantics, Kolkata date-only conversion, offset handling, invalid dates, text/URL boundaries, duplicate and oversized bulk IDs, safe missing/foreign ownership behavior, and legacy/new error-detail normalization.

Repository CI remains the final integration gate for the PostgreSQL backend suite, backend compilation, frontend production build, and Playwright regressions.

### Rollback and activation boundary

JG-015 has no migration and writes no new persisted data. If rollback is required before JG-016 adopts these helpers, remove the validation service and schema alias together. Existing application writers remain behavior-compatible because JG-015 does not route them through the new contract.

Do not mark R5 fully released after JG-015 alone. JG-016 must apply the validators atomically to every application writer, and JG-017 must render the normalized failures and repair asynchronous import feedback before the R5 group acceptance fixture is complete.


## JG-016 atomic validation across application writers

JG-016 activates the reusable JG-015 validation contract at every active application-writing boundary. It is a code-only API/service change. There is no schema migration, no persisted-data rewrite, and no JG-017 frontend field-error work in this ticket.

### Active writer matrix

The following writers now validate the complete logical request before mutating ORM state:

- `POST /crm/from-row/{row_id}`: validates the source row URL plus company/title limits before upsert.
- `POST /crm/from-rows/bulk`: normalizes 1..500 strict positive row IDs, verifies account ownership for the full set, validates all source rows, then writes one transaction.
- `PATCH /crm/applications/{item_id}`: validates only explicitly supplied patch fields, including status, text limits, and account-timezone timestamp parsing.
- `PATCH /crm/applications/bulk`: normalizes IDs, preloads every owned application, validates the patch against every target record, then applies the batch atomically.
- `POST /crm/import/external`: validates every input record before constructing the first `JobTrack`. A later invalid record therefore causes zero imported records.
- `POST /crm/applypilot/import`: validates every result and preloads matching owned tracks before mutation. Missing tracks keep the historical skip behavior.

Bulk IDs are strict integers at the Pydantic transport boundary. Strings and booleans are not silently coerced into IDs. Duplicate IDs normalize in first-seen order.

### Status and timestamp rules

The central statuses remain:

`opened`, `applied`, `follow_up`, `interview`, `rejected`, `offer`, `not_applying`.

Status may be omitted. Explicit null is invalid when a writer supplies a status field.

Application patch timestamps use the authenticated user's stored IANA timezone. A date-only value is local midnight converted to the repository's naive-UTC storage convention. Full timestamps require `Z` or an explicit numeric offset. Invalid or impossible values fail before mutation.

Omitted timestamps remain unchanged. Explicit null or empty string clears a clearable timestamp, except `applied_at` cannot be explicitly cleared when the resulting status is still `applied`.

Ordinary ApplyPilot retries preserve the first stored `applied_at`. When a submitted result omits `submitted_at`, the lifecycle service only creates an application time if one does not already exist. An explicitly supplied different timestamp remains a deliberate correction and follows the existing lifecycle correction-event contract.

External import preserves its historical no-invention rule: `status="applied"` with an omitted `applied_at` can represent a legacy applied record whose exact application time is unknown. An explicitly supplied null/empty applied date combined with applied status is rejected.

### Atomicity, ownership, and errors

Every bulk writer verifies all referenced owned IDs before the first write. Missing and foreign IDs use the same not-found outcome so account existence is not disclosed.

Validation failures use the JG-015 field envelope:

```json
{
  "detail": {
    "code": "validation_error",
    "fields": [
      {"field": "applied_at", "message": "Applied date cannot be cleared while status remains applied."}
    ]
  }
}
```

Expected validation and ownership failures roll back the active transaction. Lifecycle conflicts remain bounded expected failures. Database uniqueness/integrity races roll back and return HTTP 409 with a safe retry message. Unexpected writer failures explicitly roll back, are logged with the operation/request ID, and return HTTP 500 with that request ID without reflecting request bodies, URLs, notes, or credentials.

### Backup JSON safety

The dedicated `backend/app/routers/backup.py` router remains authoritative for `/crm/backup/export` and `/crm/backup/import`. JG-016 removes the dead duplicate CRM backup implementation that called raw `json.loads`.

The live import route continues through `restore_backup_payload()`, which calls the JG-001 `parse_backup_json()` contract before restore routing. Invalid JSON, duplicate keys, non-UTF-8 data, non-finite numbers, and oversized payloads remain bounded parser errors rather than stack traces. JG-016 adds route-level regression coverage proving malformed JSON returns HTTP 400 with `code="invalid_json"`.

### Read-only legacy validation report

Authenticated users can inspect aggregate legacy warnings with:

```http
GET /crm/applications/validation-report
```

The response contains counts only:

```json
{
  "counts": {
    "total": 12,
    "invalid_status": 1,
    "applied_without_date": 2,
    "invalid_url": 1,
    "company_too_long": 0,
    "title_too_long": 0,
    "notes_too_long": 0
  },
  "repair_mode": "manual_only"
}
```

The report is owner-scoped and does not expose row IDs, URLs, companies, titles, notes, or foreign-account data. It never repairs records automatically. Corrections stay deliberate user mutations so lifecycle history remains auditable.

### Verification

Focused JG-016 checks:

```sh
cd backend
python -m pytest tests/test_all_application_writers.py tests/test_backup_contract.py -q
python -m pytest tests/test_lifecycle_mutations.py tests/test_application_memory.py tests/test_crm.py -q
python -m compileall app
```

Repository CI remains the integration gate for the complete PostgreSQL backend suite, backend compilation, frontend production build, and Playwright Chromium regressions.

The JG-016 regression fixture proves invalid status rejection across the endpoint matrix, zero-write rollback when a later external-import record is invalid, rejection of clearing an applied record's application date, safe duplicate from-row behavior, account-timezone date-only conversion, ApplyPilot retry preservation, foreign-ID preflight, invalid source URL rejection, text limits, account-scoped aggregate reporting, and strict malformed-backup JSON handling.

### Rollback and activation boundary

JG-016 has no migration. Rollback is an application-code rollback only and must not delete or rewrite already valid application data or lifecycle events.

If compatibility requires temporarily backing out writer enforcement, revert the JG-016 route/service adoption while retaining JG-015 validation helpers and all persisted lifecycle history. The strict JG-001 backup parser remains the authoritative restore boundary.

R5 is still not fully released after JG-016 alone. JG-017 owns visible frontend field-error rendering and asynchronous import feedback before the complete R5 group acceptance fixture is closed.

## JG-017 frontend validation feedback and external import lifecycle

JG-017 completes the R5 interface boundary. It does not add a database migration or change the JG-016 writer contract. The frontend now renders the validation information already returned by the backend, preserves unsaved user input after rejected mutations, and keeps import busy state aligned with the real asynchronous work.

### Shared frontend error contract

`frontend/src/api/client.js` exports `formatApiError()` and `apiFieldErrors()`. The formatter accepts the JG-016 normalized envelope:

```json
{
  "detail": {
    "code": "validation_error",
    "fields": [
      {"field": "applied_at", "message": "Applied date cannot be cleared while status remains applied."}
    ]
  }
}
```

It also accepts legacy string details and string-valued detail objects while the older callers remain in service. Unknown response shapes use a bounded generic message instead of reflecting request payloads or nested server data. Network failures use a retryable network message. Authentication redirects remain owned by the existing Axios response interceptor.

### Applications editing behavior

`frontend/src/pages/Applications.jsx` separates editable drafts from the last persisted server row for company, status, application date, follow-up date, and notes.

- Company, application date, and follow-up date submit on blur or Enter.
- Notes submit on blur so Enter remains available for multiline text.
- Status keeps the existing immediate-selection behavior.
- A row has at most one application mutation in flight. Its editing controls and Mark applied action are disabled until that request settles.
- Bulk Mark applied also has an explicit pending guard.
- Failed validation keeps the draft visible, renders the backend field message beside the matching control, and returns focus to the first invalid field.
- A successful mutation first uses the returned server record and then refreshes the application query so the screen is reconciled with persisted values.
- Application and follow-up dates are not written merely because the table rendered. A request is sent only after the user explicitly changes the date or uses a quick action.

The backend remains authoritative for invariants such as refusing to clear `applied_at` while the resulting status is still `applied`.

### External JSON import behavior

`frontend/src/pages/ImportExternal.jsx` no longer nests asynchronous work inside `FileReader.onload`. Selecting a file now performs one guarded `await file.text()` parse flow. Importing performs exactly one awaited `POST /crm/import/external` call inside its own `try/catch/finally`.

Changing the selected file immediately clears the prior preview, parsed records, success result, and error state. A stale slower file read cannot overwrite a newer selection. Invalid JSON or an unsupported top-level shape leaves Import disabled.

A valid file keeps the complete parsed record array separately from the visible preview. The screen therefore reports, for example, `Preview (10 of 25 rows)` while displaying only ten rows. A valid empty file is shown as an empty result and cannot be submitted.

During an import request the button displays `Importing...` and remains disabled through the API response. Validation or network failure preserves the selected file and valid preview so the user can correct or retry without reselecting the file. Only a confirmed server response displays the imported `created` count.

### Verification

Focused frontend checks:

```sh
cd frontend
npm run build
npm run test:e2e -- tests/application-validation.spec.ts --project=chromium
```

`frontend/tests/application-validation.spec.ts` verifies:

- clearing an applied application's date with Enter shows the `applied_at` field error, preserves the draft, focuses the invalid control, and leaves the persisted date unchanged after reload;
- file-read and network failures are recoverable and do not create an unhandled page error;
- the Import button stays disabled while the request is pending;
- a 25-row file reports a 10-of-25 preview, and replacing it with invalid JSON clears the stale preview and disables Import;
- a company draft can submit with Enter and remains persisted after the server refresh and page reload.

Repository CI remains the integration gate for the PostgreSQL backend suite, backend compilation, production frontend build, and complete Playwright Chromium regression set.

### Rollback and R5 completion boundary

JG-017 changes frontend application code and tests only. No migration, data rewrite, or new durable state is introduced. Rollback can revert the JG-017 frontend/error-formatting commits while retaining JG-015 validation helpers, JG-016 writer enforcement, and all existing application/lifecycle data.

After the JG-017 focused fixture and repository CI pass, the R5 implementation group is locally complete. JG-018 is the next ordered roadmap item. External production release proof remains separate from local implementation status.



## JG-018 shared numeric parsing and dialect adapters

JG-018 replaces database-specific numeric parsing scattered across the row and application routes with one read-only contract for text-backed numeric fields. It does not change the database schema, rewrite imported CSV text, or claim SQLite Alembic support. PostgreSQL remains the deployment and migration acceptance database, while SQLite keeps functional query support for local development and focused tests.

### Accepted numeric text

`backend/app/services/numeric_values.py` owns the contract. `parse_numeric_text()` first applies the 128-character cap to the original value, removes only percent signs, dollar signs, commas, and whitespace, then accepts one finite decimal number with an optional leading sign and decimal point.

Representative results:

| Source text | Parsed value |
|---|---:|
| `2` | `2` |
| ` 10 ` | `10` |
| `85%` | `85` |
| `1,000` | `1000` |
| `$99.50` | `99.50` |
| `-3` | `-3` |
| `+.5` | `0.5` |
| blank, malformed, exponent notation, NaN/Infinity-like text, or more than 128 characters | null |

Invalid input is never converted to zero. Numeric reads do not write normalized values back to `CsvRow` or `JobTrack`.

### Dialect behavior

`numeric_text_expression()` is a SQLAlchemy expression with one contract and two supported compilers.

- SQLite compiles to `jobgrid_numeric(column)`. `backend/app/database.py` installs a SQLAlchemy connection listener before the primary engine is created. Every SQLite DBAPI connection, including connections from test-created engines after application import, receives the deterministic scalar function.
- PostgreSQL compiles to a bounded `CASE` expression. Values longer than 128 characters become null before casting. Accepted separator characters are removed with `regexp_replace`, the normalized value must match the numeric regex, and only then is it cast to `NUMERIC`.
- No unsupported value is cast speculatively, and no invalid value is treated as zero.

### Query behavior

`backend/app/services/row_queries.py` is the shared read-path owner.

The following text-backed Dashboard sort fields use the numeric adapter:

- `page_number`
- `posted_age_days`
- `jd_text_length`
- `resume_match_score`

Salary filters use the same contract for `salary_min_extracted` and `salary_max_extracted`. Application score filters/order and row-derived posted-age filters also use the same expression through the existing shared application query builder.

Both ascending and descending numeric sorts keep invalid/empty values last. Equal numeric values retain the existing deterministic `id DESC` tie breaker. Account scoping, archive filtering, pagination, export query reuse, and application-versus-visit semantics are unchanged.

The legacy private helpers `rows._safe_sort_column()` and `crm.num_expr()` remain as thin compatibility wrappers for existing internal callers/tests, but they no longer contain their own PostgreSQL-specific parsing logic.

### Verification

Focused backend verification:

```sh
cd backend
python -m pytest tests/test_numeric_sort.py -q
python -m pytest tests/test_query_contracts.py tests/test_filtered_exports.py tests/test_application_memory.py tests/test_crm.py -q
python -m compileall app
```

`backend/tests/test_numeric_sort.py` covers the accepted/rejected parsing table, the 128-character and non-finite boundaries, SQLite connection registration, numeric rather than lexical ordering, null-last ordering in both directions, descending-ID ties, all four numeric CSV sort fields, separator-aware salary filters, application score/posted-age behavior, PostgreSQL/SQLite SQL compilation, and preservation of stored source text.

Repository CI remains the integration gate for PostgreSQL backend tests, backend compilation, the frontend production build, and Playwright Chromium regressions.

### Rollback and R6 boundary

JG-018 is a code-only read-path change. Rollback removes the shared expression and restores the previous query helpers. There is no migration to downgrade and no numeric source data to restore.

Do not describe R6 as complete after JG-018 alone. JG-019 still owns fresh-PostgreSQL migration/schema parity proof and JG-020 owns the integrated R6 acceptance boundary.

## JG-019 database engine configuration and schema acceptance

JG-019 makes the database test boundary explicit. It does not add or change a
database migration and it does not rewrite persisted data.

### Shared engine configuration

`backend/app/database.py` exposes `create_jobgrid_engine()`. The application
engine and test-created engines use this helper so connection-level behavior is
not limited to the first application connection.

For SQLite connections the helper:

- keeps the JG-018 deterministic `jobgrid_numeric(value)` registration active
  on every SQLAlchemy engine connection;
- enables `PRAGMA foreign_keys=ON` so local constraint behavior does not
  silently ignore relationships that PostgreSQL enforces.

The normal `SessionLocal` used by request handlers, cleanup jobs, and the
lifecycle backfill remains bound to the configured application engine. There is
no separate background database engine to configure.

### Disposable SQLite acceptance fixtures

The ordinary local test default no longer relies on a repository-level
`test.db` file. Pytest creates a temporary suite database when no explicit
database URL is supplied.

JG-019's SQLite acceptance fixture creates a separate test-named database under
Pytest's temporary directory for each test. The fixture is used to prove that a
fresh connection can call `jobgrid_numeric` and that an invalid foreign-key
write raises an integrity error. Temporary files are disposed with the test and
are never production data.

### Fresh PostgreSQL schema acceptance

PostgreSQL migration acceptance uses `TEST_DATABASE_URL`, not the ordinary
`DATABASE_URL`. The two URLs must identify different databases. The target
database name must clearly be a disposable test database.

The PostgreSQL-marked fixture:

1. connects to the same server's administrative `postgres` database;
2. drops and recreates only the database named by `TEST_DATABASE_URL`;
3. runs `alembic upgrade head` against that empty database;
4. uses SQLAlchemy inspection to compare migrated tables, column nullability,
   indexes, unique constraints, foreign keys, and declared delete behavior with
   `Base.metadata`;
5. runs `alembic upgrade head` again and verifies the schema fingerprint and
   Alembic revision do not change;
6. disposes connections and removes the disposable database after the module.

A local run without `TEST_DATABASE_URL` skips the PostgreSQL-only tests and the
skip is **not** schema-acceptance evidence. In CI, a missing
`TEST_DATABASE_URL` is a hard test failure. The backend GitHub Actions job
supplies a dedicated `jobgrid_schema_test` database URL while regular backend
tests continue using `jobgrid_test`.

### Verification

Focused checks:

```sh
cd backend
python -m pytest tests/test_database_dialects.py -q

TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/jobgrid_schema_test \
  python -m pytest tests/test_schema_parity.py -q

python -m compileall app
```

The PostgreSQL account used by the schema test must be allowed to create and
drop the named disposable test database. Do not point
`TEST_DATABASE_URL` at production, staging, or the regular test database.

Repository CI remains the integration gate for the complete PostgreSQL backend
suite, backend compilation, the frontend production build, and Playwright
Chromium regressions.

### Rollback and R6 boundary

JG-019 is configuration-and-verification work only. Rollback reverts the shared
engine helper, test fixtures, schema checks, and CI test URL. There is no
migration to downgrade and no application data to restore.

SQLite remains a supported functional local runtime, but historical
PostgreSQL-specific Alembic migrations are not redefined as SQLite-portable.
Fresh migration/schema acceptance is PostgreSQL-only. JG-020 supplies the
integrated runtime and browser acceptance described below.

## JG-020 integrated SQLite and PostgreSQL runtime acceptance

JG-020 closes the R6 verification boundary without adding a migration, changing
stored numeric text, or introducing a third database abstraction. It verifies
the JG-018 numeric contract and the JG-019 engine/schema contract through the
same public rows API and through the Dashboard.

### Runtime evidence matrix

| Runtime | What it proves | What it does not prove |
|---|---|---|
| SQLite | Numeric API behavior, connection-level `jobgrid_numeric`, foreign-key enforcement, and fresh-process startup/restart behavior | Alembic portability or production migration readiness |
| PostgreSQL 16 | Numeric API behavior on the deployment dialect plus the approved release database major version | Production data safety by itself |
| Isolated PostgreSQL schema DB | Fresh `alembic upgrade head`, ORM/schema parity, and migration replay no-op | Authorization to touch staging or production |
| Playwright + PostgreSQL backend | Exact Resume Score order in the real Dashboard, reload stability, and successful rows API response | External deployment or provider acceptance |

PostgreSQL 16 is the approved deployment and migration acceptance runtime for
R6. The repository does not claim that another PostgreSQL major version has
passed this ticket unless an actual run records that result.

### Frozen numeric fixture and exact order

Both backend API acceptance and the browser fixture use these source values:

```text
2
10
85%
1,000
$99.50
-3
<blank>
invalid
```

Ascending order is:

```text
-3, 2, 10, 85%, $99.50, 1,000, invalid, <blank>
```

Descending order is:

```text
1,000, $99.50, 85%, 10, 2, -3, invalid, <blank>
```

The last two values both parse to null. They remain last in either direction and
use the existing descending-record-ID tie breaker, so the later-created
`invalid` fixture precedes the blank fixture.

### Backend acceptance

`backend/tests/test_database_dialects.py` now includes three R6 integration
regressions in addition to the JG-019 connection/foreign-key checks:

- `test_both_dialect_api_responses_are_200` seeds the same eight rows in a
  disposable SQLite database and in the ordinary PostgreSQL test runtime, calls
  `GET /rows` through the FastAPI application, and requires HTTP 200 plus the
  exact ascending and descending score sequences on both dialects. Response
  bodies are included in assertion failures so server errors are visible.
- `test_startup_and_new_connection_smoke` starts the application in two fresh
  Python interpreters against the same disposable SQLite file. Each interpreter
  opens a database connection, verifies `PRAGMA foreign_keys=ON`, calls
  `jobgrid_numeric`, and confirms `GET /health` returns
  `{"status":"ok"}`. This proves registration is not accidentally limited to
  the first process or first pooled connection.
- `test_release_requires_real_postgres_result` requires the ordinary backend
  test engine to be PostgreSQL, requires the isolated schema URL to remain a
  different PostgreSQL database, and reads `SHOW server_version_num` to prove
  the release run actually used PostgreSQL 16.

A developer running only SQLite can exercise the SQLite tests, but the
dual-dialect/release assertions may skip because PostgreSQL is absent. That
local skip is deliberately not counted as release evidence. In mandatory CI the
ordinary backend database is PostgreSQL 16, so a non-PostgreSQL result is a
failure rather than a silent substitute.

Focused local SQLite verification:

```sh
cd backend
DATABASE_URL=sqlite:////tmp/jobgrid-r6.sqlite3 \
TEST_AUTH=true \
SECRET_KEY=jg020-local-test-secret \
FRONTEND_URL=http://localhost:5173 \
python -m pytest tests/test_numeric_sort.py tests/test_database_dialects.py -q
```

Release-capable PostgreSQL verification:

```sh
cd backend
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/jobgrid_test \
TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/jobgrid_schema_test \
TEST_AUTH=true \
SECRET_KEY=jg020-postgres-test-secret \
FRONTEND_URL=http://localhost:5173 \
ENVIRONMENT=test \
python -m pytest \
  tests/test_numeric_sort.py \
  tests/test_database_dialects.py \
  tests/test_schema_parity.py -q
```

The schema-test account must be allowed to create/drop only the explicitly named
disposable test database. Never use production, staging, or the ordinary test
database as `TEST_DATABASE_URL`.

### Browser acceptance

`frontend/tests/numeric-sort.spec.ts` uploads the same eight-value fixture
through the authenticated API. It opens the Dashboard with a URL-backed
`resume_match_score` ascending sort, asserts the exact rendered score order,
reloads and asserts the same order again, then clicks the Resume Score table
header and requires the resulting `GET /rows` response to be HTTP 200 before
asserting the exact descending order. The test also fails on browser page
errors.

Run it with the authenticated backend already running against PostgreSQL 16:

```sh
cd frontend
npm run test:e2e -- tests/numeric-sort.spec.ts --project=chromium
```

The full GitHub Actions Playwright job remains the integration source of truth
because it starts the backend on PostgreSQL 16 before running the browser suite.

### Release evidence and failure handling

For R6, the following are separate facts and must stay separate in release
notes:

1. A SQLite focused run proves local functional compatibility.
2. A PostgreSQL 16 backend run proves the deployment-dialect numeric path.
3. The isolated schema test proves a fresh PostgreSQL migration reaches the
   current Alembic head and matches ORM metadata.
4. The Playwright run proves the Dashboard requests and renders the exact
   numeric order through the PostgreSQL-backed API.
5. Full repository CI proves the R6 changes did not regress the preserved
   application-memory, filtering/export, and top-five tab-opening contracts.

If either dialect API call fails, the backend regression reports the HTTP status
and response body. If the fresh-process startup probe fails, its captured stdout
and stderr are included. Do not convert either failure into a skip.

### Rollback and migration limitations

JG-020 itself changes tests and documentation only. It has no migration and
performs no persisted-data rewrite.

R6 functional sorting can be rolled back at the application-code layer while
preserving stored source text and existing user data. Historical Alembic
revisions contain PostgreSQL-specific types such as JSONB, so SQLite migration
acceptance is intentionally unsupported. Do not rewrite historical migrations
to make SQLite pass, and never downgrade a production database merely to satisfy
this verification gate.

An external production deployment remains separate evidence. A passing local or
CI run does not claim that production was deployed or manually smoke-tested.



## JG-021 CI startup and PostgreSQL release-gate composition

JG-021 hardens the repository CI release gate without changing application schema, persisted data, or public API behavior. The workflow remains split into frontend build, Playwright browser acceptance, backend compile, and backend pytest jobs.

### Backend startup and migration order

The Playwright job runs the backend from `${{ github.workspace }}/backend`. The historical repository-root `cd ../backend` path is not used.

Before Uvicorn starts, CI runs:

```sh
python -m alembic upgrade head
```

Migration output is captured instead of echoing connection configuration. After a successful upgrade, the workflow prints only the applied Alembic revision. The E2E API then starts against the disposable PostgreSQL 16 service.

Readiness is not a fixed sleep. CI polls `GET /health` once per second for at most 60 seconds and stops early if the backend process exits. If readiness never succeeds, the step fails. The raw temporary server log is filtered before it is printed or retained so PostgreSQL credentials and named secret environment variables are replaced with bounded redacted values.

### Isolated PostgreSQL test configuration

Both PostgreSQL-backed CI jobs use explicit synthetic credentials declared in the workflow. They do not read repository production secrets.

The backend pytest job uses separate database targets:

- `DATABASE_URL` for the ordinary PostgreSQL test runtime.
- `TEST_DATABASE_URL` for fresh schema/migration acceptance.

The existing fixture continues to reject a `TEST_DATABASE_URL` that is non-PostgreSQL, does not look explicitly disposable, or resolves to the same database as `DATABASE_URL`.

The Playwright job also receives explicit test-only settings, including `TEST_AUTH=true`, `ENVIRONMENT=test`, and disabled maintenance jobs. These values are scoped to CI and are not production deployment configuration.

### Nonempty collection gates

A green job must prove that tests were actually collected.

Before backend execution, CI runs:

```sh
pytest tests/ --collect-only -q
```

Pytest collection is executed with shell pipe failure propagation, so an empty collection or failed collection cannot be hidden by `tee`.

Before browser execution, CI runs:

```sh
npx playwright test --list --project=chromium
```

The workflow records the collection output and requires a nonzero Playwright total before running the full Chromium project. The existing `frontend/playwright.config.ts` contract remains unchanged: the `chromium` project depends on the `setup` project, so authentication setup failure fails the browser run instead of being treated as success.

### Failure evidence and retention

Failure evidence is intentionally synthetic and short-lived.

Backend CI writes pytest collection output and JUnit XML to `backend/ci-artifacts/`. The browser job retains its collection output, Playwright report/test-results, and a sanitized backend server log when a failure occurs. Artifact uploads run only on failure and use a 7-day retention period.

Server and migration logs must never be uploaded in raw form when they can contain connection information. The workflow redacts PostgreSQL URL credentials and the values of `DATABASE_URL`, `TEST_DATABASE_URL`, and `SECRET_KEY` before printing or retaining diagnostic output.

### Verification

The focused JG-021 contract regressions live in `backend/tests/test_database_dialects.py`:

- `test_workflow_command_resolves_backend_directory`
- `test_health_timeout_fails_job`
- `test_postgres_suite_and_browser_suite_run`
- `test_zero_tests_or_failed_setup_is_not_success`

They verify the workflow text, bounded health failure behavior, explicit PostgreSQL/browser suite composition, nonempty test collection, synthetic-secret boundary, and preservation of Playwright setup dependency.

Repository CI remains the integrated proof because it executes the actual PostgreSQL 16 backend suite, backend compilation, frontend production build, and Chromium browser suite.

### Rollback and release boundary

JG-021 has no migration file and performs no persisted-data rewrite. If the release gate itself regresses, revert the JG-021 workflow/test/documentation commits. Do not downgrade or rewrite a user database to roll back this ticket.

A locally passing JG-021 CI run is not the complete R7 production release. Later R7 tickets still own production configuration rejection, provider/staging acceptance, backup/restore release evidence, and the final production release gate.


## JG-022 fail-fast production configuration

JG-022 adds a production-only startup safety gate without changing database schema, stored user data, or application/visit semantics. Validation runs while `app.config` is imported, before `app.main` can initialize the database, run migrations, register routes, or start the maintenance scheduler.

### Production startup requirements

When `ENVIRONMENT=production`, startup rejects the configuration before the API serves traffic if any of these conditions are true:

- `TEST_AUTH=true`.
- `SECRET_KEY` is empty, shorter than 32 UTF-8 bytes, or matches a known development/test placeholder pattern.
- `FRONTEND_URL` is not a public HTTPS URL.
- `OAUTH_REDIRECT_BASE` is not a public HTTPS URL.
- `CORS_ORIGINS` was not explicitly configured.
- Any configured CORS origin is not a public HTTPS origin.

Localhost, loopback addresses, embedded URL credentials, and plain HTTP public origins are rejected in production. Development and test retain the existing localhost defaults and may continue using local HTTP origins.

Production configuration errors name the unsafe setting or rule but never include the configured signing-secret value.

A minimal production inventory is:

```text
ENVIRONMENT=production
TEST_AUTH=false
SECRET_KEY=<deployment-managed random value of at least 32 bytes>
FRONTEND_URL=https://app.example.com
OAUTH_REDIRECT_BASE=https://api.example.com
CORS_ORIGINS=https://app.example.com
```

Generate signing material outside the repository, for example:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
# or
openssl rand -hex 32
```

Put the generated value in the deployment platform's secret manager or equivalent protected configuration. Do not paste the real value into `.env.example`, documentation, logs, CI artifacts, commits, or issue/PR text.

### Development/test authentication boundary

`POST /auth/dev-login` is registered only when the runtime environment is not production. In development/test, the existing `TEST_AUTH=true` gate still controls whether the handler succeeds. In production the route is absent, so every request payload receives route-level 404 behavior instead of reaching request-body or login logic.

The separate `/test/seed` and `/test/reset` helpers remain controlled by the existing `TEST_AUTH` startup condition. Production cannot reach that state because the configuration validator rejects `TEST_AUTH=true` before the application is created.

### Cookie policy

Cookie security remains server-controlled.

- Production OAuth/session cookies use `Secure` and `SameSite=None` so HTTPS cross-site OAuth callback behavior works without weakening transport protection.
- Development/test cookies remain non-Secure with `SameSite=Lax` for localhost compatibility.
- The Starlette `SessionMiddleware`, OAuth callback session token, logout deletion, and dev-login cookie use the same environment-derived policy.

### Verification

Focused JG-022 regression coverage lives in `backend/tests/test_production_config.py`:

```sh
cd backend
python -m pytest tests/test_production_config.py -q
```

The suite proves unsafe production `TEST_AUTH` fails during import before serving, placeholder/short signing keys fail without leaking the key, HTTPS/CORS validation is enforced, development/test dev-login remains available, production dev-login is not registered, and production cookie attributes are Secure with `SameSite=None`.

Repository CI remains the broader integration gate for PostgreSQL backend tests, backend compilation, the frontend production build, and Playwright Chromium coverage.

### Rollback and release boundary

JG-022 has no migration and does not rewrite persisted data. If the startup/configuration or cookie behavior regresses, revert the JG-022 application/configuration commits. Do not downgrade the database.

A passing JG-022 local or CI result establishes this configuration gate only. Real provider OAuth, SMTP sandbox delivery, staging restore comparison, and production release evidence remain later R7 work and must not be inferred from this ticket.

## JG-023 release regression gate

JG-023 promotes the September 12 audit failures into a named release gate. It does not change application runtime behavior, database schema, persisted data, or public API contracts. The gate makes the repaired contracts hard to drop silently during later work.

### Enforced backend contracts

`backend/tests/test_release_contracts.py` is the release manifest and adds direct regressions for boundaries that are easiest to lose during integration. Repository CI executes it together with the existing deep regressions for:

- complete v2 backup round trip with retained application/company/date/note data;
- filtered export parity with the complete multi-filter, multi-page browse result;
- shared visited/saved/applied metric reconciliation;
- invalid application status/date and malformed backup rejection before mutation;
- cleanup failure being reported as failure rather than successful zero work;
- numeric ordering on the primary CI database plus separate SQLite numeric functional coverage;
- cross-account mutation/visit/export denial; and
- durable company/application history after source-row deletion, including company names containing a slash.

The release manifest must be nonempty. CI also parses the focused JUnit result and rejects zero tests, failures, errors, or skips. A skipped release contract is not a passing release contract.

Focused backend verification:

```sh
cd backend
python -m pytest \
  tests/test_release_contracts.py \
  tests/test_backup_restore.py::test_restore_applied_company_notes_and_dates \
  tests/test_filtered_exports.py::test_filtered_export_equals_all_list_pages \
  tests/test_metric_consistency.py::test_shared_metrics_agree_across_analytics_goals_and_weekly \
  tests/test_cleanup_job.py::test_cleanup_failure_not_zero_success \
  tests/test_numeric_sort.py::test_numeric_order_not_lexical \
  -q
```

In CI, the backend release gate runs with PostgreSQL configuration after `alembic upgrade head` has succeeded and the applied revision has been recorded. The full backend suite still runs afterward. The explicit SQLite numeric regression remains useful local/dialect coverage, but it is not migration or production-database acceptance.

### Enforced browser contract

`frontend/tests/release-workflows.spec.ts` creates a nonempty synthetic job set and verifies the complete top-five workflow. It checks that the browser uses the server's complete filtered/sorted candidate query, opens exactly five eligible HTTPS jobs, severs `window.opener`, persists exactly those successful visits, and records no additional visits when popups are blocked.

The existing `frontend/unit/open-jobs.test.mjs` suite is also part of the JG-023 CI gate. It preserves unsafe-URL rejection and the lower-level blocked/failed popup behavior.

Focused browser verification:

```sh
cd frontend
node --test unit/open-jobs.test.mjs
npm run test:e2e -- tests/release-workflows.spec.ts --project=chromium
```

CI fails if Playwright cannot collect at least one focused release test. The full Chromium suite runs after the focused workflow.

### Release evidence

Each CI run writes synthetic evidence next to the test results.

Backend evidence records:

- Git commit SHA;
- applied Alembic revision;
- Python and pip versions;
- FastAPI, SQLAlchemy, Alembic, pytest, and PostgreSQL driver package versions;
- `backend/requirements.txt` SHA-256; and
- focused release test count with zero failures, errors, and skips.

Browser evidence records:

- Git commit SHA;
- Node and npm versions;
- Playwright and Chromium versions;
- `frontend/package-lock.json` SHA-256;
- focused Playwright collection output; and
- focused workflow output.

GitHub Actions uploads these files as seven-day `jg023-backend-release-evidence-<sha>` and `jg023-browser-release-evidence-<sha>` artifacts. These artifacts contain synthetic test/runtime metadata only. They must not contain database URLs, signing secrets, OAuth credentials, SMTP credentials, imported private text, or production data.

### Release-state vocabulary

JG-023 keeps three states separate:

- **local-ready** means the implementation and required synthetic release regressions are green for the recorded commit, including mandatory repository CI. It does not claim external provider or deployment acceptance.
- **staging-accepted** means the authorized staging gates for the same release candidate have passed, including the external checks owned by JG-024 such as real OAuth/SMTP and restore rehearsal where configured.
- **released** means that an accepted release candidate was actually deployed to the intended production environment and its required post-deploy smoke/recovery evidence was recorded.

A ticket can be marked completed in the implementation roadmap when its own definition of done is satisfied without calling that state `released`. Do not use a generic `Done` label to imply staging or production acceptance.

### Rollback

JG-023 is tests, CI configuration, and documentation only. If the release gate itself is incorrect, revert the JG-023 test/workflow/documentation commits together. No database downgrade, data rewrite, queue drain, or user-data recovery operation belongs to this rollback. Real OAuth, SMTP, staging restore, deployment, and production-release proof remain JG-024 responsibilities.



## JG-024 release acceptance

JG-024 adds operational acceptance tooling only. It does not change the database schema, public API contract, application-versus-visit semantics, or persisted user data.

### Backup and restore rehearsal

scripts/backup.sh supports explicit compose/service/database overrides plus a deterministic JOBGRID_BACKUP_FILE. It rejects empty backups, runs gzip integrity verification, records byte size and SHA-256, and writes a .sha256 sidecar. Set JOBGRID_BACKUP_SKIP_PRUNE=true during a disposable rehearsal so validation cannot remove unrelated backup history.

scripts/restore.sh accepts --yes only for already-authorized noninteractive rehearsals, validates gzip and the expected/sidecar SHA-256 before writes, restores with psql -v ON_ERROR_STOP=1, and exits nonzero if the backend does not return healthy. Service/database names and health polling are environment-overridable for isolated staging compose projects.

### Release-evidence validation

scripts/smoke_jobgrid.py --self-test-release-acceptance runs deterministic regressions for:

- staging_restore_content_comparison
- oauth_real_provider_not_dev_login
- smtp_received_not_merely_queued
- rollback_preserves_user_history
- deployment_smoke_and_rollback

scripts/smoke_jobgrid.py --release-evidence FILE validates an operator-supplied JSON evidence file. Gates are PASS, FAIL, or BLOCKED. A blocked gate must name its owner, environment, command, expected/actual result, and exact missing dependency. Blocked gates never become staging acceptance.

A restore PASS requires nonempty equal source/restored counts and matching SHA-256 content hashes. A real OAuth PASS rejects dev-login evidence and requires /auth/me success plus production cookie/logout assertions. SMTP PASS rejects status=logged and requires controlled-sandbox receipt evidence. Rollback PASS requires identical nonempty user-history count/hash before and after the old-code rehearsal. Staging acceptance also requires backend/frontend smoke plus an explicit rollback trigger.

### Operational runbook

See docs/RELEASE_ACCEPTANCE.md for the disposable PostgreSQL comparison flow, additive-migration/old-code rehearsal, real OAuth test, authorized SMTP sandbox receipt, deployment smoke, rollback triggers, evidence schema, and security rules.

JG-024 keeps three states distinct:

- **local-ready**: scripts/docs/regressions and repository CI are green for the candidate SHA.
- **staging-accepted**: every acceptance gate is PASS for that staging candidate.
- **released**: the accepted candidate was deployed to production and post-deploy evidence exists.

The repository-connected JG-024 implementation does not have staging OAuth/SMTP/deployment credentials or sending authorization. Those external gates remain BLOCKED until an authorized operator executes the runbook. This is not represented as staging-accepted or released.

Rollback of JG-024 itself is code/documentation-only: revert these script and documentation changes. Do not downgrade the database or delete restored/user history to roll back acceptance tooling.


## JG-029 conservative job identity

JG-029 adds pure identity helpers in `backend/app/services/job_identity.py`. It does not add database columns, aliases, routes, badges, or automatic merges. Original `CsvRow.url` and `JobTrack.url` values remain authoritative and unchanged.

### Canonical URL contract

The active rule version is `ccr-identity-1`.

`canonicalize_job_url(url)`:

- accepts only nonempty HTTP(S) URLs up to 2048 characters;
- rejects embedded credentials, missing hosts, invalid ports, and surrounding whitespace;
- lowercases scheme and host while applying Python's IDNA host conversion consistently;
- removes only default ports 80/443;
- removes fragments;
- removes query keys beginning with `utm_` plus `gclid` and `fbclid`;
- preserves path casing, trailing-slash distinction, every other query key, duplicate values, and their order; and
- returns the unchanged original URL, derived canonical URL, SHA-256 canonical hash, and rule version.

Examples:

| Original | Canonical |
|---|---|
| `HTTPS://Example.COM:443/Jobs/42?req=abc&utm_source=x#apply` | `https://example.com/Jobs/42?req=abc` |
| `https://example.com/Jobs/Role/?id=2&id=1` | `https://example.com/Jobs/Role/?id=2&id=1` |
| `https://bücher.example:443/Jobs` | `https://xn--bcher-kva.example/Jobs` |

A different requisition value, path case, trailing slash, or order of nontracking duplicate query values remains a different canonical identity.

### Company identity and confidence

`normalize_company_alias_key` trims, collapses whitespace, and case-folds a company name. It derives only an owner-local lookup key and does not fuzzy-merge companies.

`classify_identity_match` returns a confidence and reason:

- `exact / same_original_url` when original URLs are identical;
- `canonical / same_canonical_url` when conservative canonical hashes match;
- `possible / company_title_only` when normalized company and title text match but job URLs remain distinct; or
- `None / no_identity_match` when there is no safe identity signal.

A `possible` result is a warning signal only. It must never silently merge, hide, or block a legitimate job/application.

### Changing canonical rules

Do not expand the tracking-key list or add provider-specific equivalence rules ad hoc. A rule change requires:

1. a new explicit rule version;
2. fixtures proving the provider-specific equivalence and non-equivalence cases;
3. a dry-run collision report against existing derived identities;
4. review of collisions without changing original URLs, application status, notes, or history; and
5. a separate backfill/rebuild plan before activation.

JG-030 owns persistence and backfill. JG-029 itself is rollback-safe by removing callers of the pure helper. No data migration or destructive recovery action is needed.

### Verification

Focused verification:

```sh
cd backend
python -m pytest tests/test_job_identity.py -q
```

Repository CI remains the full PostgreSQL/backend/frontend/Chromium integration gate.


## JG-030 persisted identity, aliases, and safe backfill

JG-030 adds the storage and operational layer for the conservative identity rules introduced by JG-029. It does not activate application-match APIs, alias-management routes, duplicate warning UI, or automatic merges.

### Storage contract

Alembic revision `009_job_identity.py` follows the existing `008_today_queue.py` revision. It adds nullable `canonical_url` and `canonical_url_hash` columns to both `csv_rows` and `job_tracks`.

Each table has a non-unique `(user_id, canonical_url_hash)` index. Non-unique is intentional. Two original URLs that reduce to the same conservative canonical URL remain two separate records with their original URL, application status, notes, timestamps, and history unchanged.

`company_aliases` stores explicit owner-local company groupings:

- `id`
- `user_id`
- normalized `alias_key`
- preserved `display_name`
- stable UUID `company_key`
- `created_at`

`(user_id, alias_key)` is unique. `(user_id, company_key)` is indexed for grouping. No cross-account company directory, alias chains, or fuzzy auto-merge exists in JG-030.

### Writer behavior

`backend/app/services/job_identity.py` owns `apply_persisted_job_identity()`. CSV upload and application creation/edit paths call that shared helper.

The original `url` column is never rewritten. A URL that is valid under `ccr-identity-1` gets derived canonical URL/hash values. A malformed legacy/import URL keeps its original value and nullable derived fields instead of being deleted or silently rewritten.

### Backfill

Run from `backend/`:

```sh
# Inspect one bounded batch from both tables without writes.
python scripts/backfill_job_identity.py --dry-run

# Backfill one table, at most 500 records.
python scripts/backfill_job_identity.py --entity csv_rows

# Resume strictly after an already completed primary-key checkpoint.
python scripts/backfill_job_identity.py --entity job_tracks --after-id 500

# Smaller bounded batches are allowed.
python scripts/backfill_job_identity.py --entity job_tracks --after-id 500 --limit 100
```

The hard batch maximum is 500 records per table. The service is idempotent, so replaying an already processed range reports unchanged records rather than changing the original URL or creating a duplicate. Dry-run computes the same derivation without assigning canonical fields.

Operational output contains entity names, counts, collision counts, and checkpoint IDs only. It never prints source or canonical job URLs.

A canonical collision is evidence for later matching, not permission to merge. The backfill does not change `status`, `notes`, original URLs, lifecycle events, duplicate flags, or application ownership.

### Backup and restore

Backup schema revision `2.5.0` adds optional `company_aliases` plus top-level `identity_rule_version`.

New exports:

- preserve original CSV/application URLs;
- export explicit owner-scoped aliases and stable company grouping keys;
- do not export derived canonical URL/hash fields as authoritative data; and
- record `ccr-identity-1` so restore can rebuild derived identity deterministically.

Restore validates the recorded rule before mutation. Supported backups rebuild derived identity from the preserved original URL. Older v2 backups without aliases or a rule version remain compatible and rebuild with the current rule because they predate persisted derived identity.

### Verification

Focused checks:

```sh
cd backend
python -m pytest tests/test_job_identity.py tests/test_identity_backfill.py tests/test_backup_contract.py tests/test_backup_export.py -q
python -m compileall app scripts
```

The required JG-030 regressions prove idempotent retry, collision preservation, account-scoped aliases, backup alias grouping, and dry-run no-write behavior. Repository CI remains the full PostgreSQL migration/backend/frontend/Chromium gate.

### Rollback

Revision 009 is additive. Normal application rollback can leave the nullable canonical columns and `company_aliases` table in place while older code ignores them.

Stop any backfill before rolling application code back. Do not resolve rollback by deleting canonical-collision records, original URLs, aliases, application status/notes, or lifecycle history. A schema downgrade is appropriate only when the new alias/derived data is intentionally disposable and the deployment has confirmed no newer code is using it.


## JG-031 applied-before matching and explicit company aliases

JG-031 exposes the persisted identity foundation from JG-029/JG-030 without changing schema or automatically merging jobs. The feature is advisory. A prior application can warn the user, but it does not block a legitimate reapplication.

### Application-match API

Authenticated callers can check a saved CSV row:

```http
GET /crm/application-matches?row_id=123
```

Unsaved capture flows can provide the same evidence directly:

```http
POST /crm/application-matches
Content-Type: application/json

{
  "url": "https://jobs.example.com/role/42?utm_source=linkedin",
  "company": "Acme Corp",
  "title": "Backend Engineer"
}
```

The response is bounded to 20 matches:

```json
{
  "matches": [
    {
      "track_id": 77,
      "confidence": "canonical",
      "reason": "same_canonical_url",
      "company": "Acme Corp",
      "title": "Backend Engineer",
      "status": "applied",
      "applied_at": "2026-09-18T09:45:00"
    }
  ],
  "company_history_count": 3
}
```

Only `JobTrack` rows with a known `applied_at` participate. A visited/opened-only job is not an applied-before warning. Evidence remains separate:

- `exact`: unchanged original URL.
- `canonical`: the conservative `ccr-identity-1` canonical hash matches.
- `possible`: the company or an explicit owner-local alias group matches and the normalized title matches.

The candidate scan is capped at 100 owner-scoped applied records and the returned list is capped at 20. Alias lookup, candidate retrieval, and history counting use a constant number of SQL queries rather than one query per match.

`GET /crm/application-matches` returns 404 when the requested CSV row does not belong to the authenticated account. Invalid URL/input returns 422. No match response includes another account's rows, aliases, or applications.

`POST /crm/from-row/{row_id}` keeps its existing application response and now adds `warning_candidates`. This is additive and does not change the existing unique `(user_id, url)` application contract.

### RowDrawer behavior

Opening a Dashboard row checks applied-before context. The drawer shows loading, empty, loaded-warning, and recoverable-error states. Exact, canonical, and possible evidence are labeled separately and include the prior status/date.

The **Mark applied** action uses the existing bulk row-to-application writer. If applied history exists, the user must explicitly confirm before continuing. Confirmation does not modify the old application or the current CSV row. The action is locked while the request is pending, and the drawer refreshes its match context after server success.

Each warning includes a **View prior application** link. It opens Company History with encoded `company` and `track_id` query parameters and focuses the matching role card.

### Company-alias API

Aliases are explicit, owner-local grouping metadata:

```http
GET /crm/company-aliases?company=Acme%20Corp
POST /crm/company-aliases
DELETE /crm/company-aliases/{alias_id}
```

Create payload:

```json
{
  "company": "Acme Corp",
  "alias": "Acme Incorporated"
}
```

When a company has no alias group yet, creation stores the selected company name and proposed alias under one stable owner-local UUID `company_key`. If the selected company already belongs to a group, the new label joins that group. Repeating an alias already in the same group is idempotent.

If a proposed alias already belongs to a different group, the server returns 409 with code `alias_conflict` and echoes `proposed_label` in the error detail. The UI keeps the draft text so the user can refresh and retry.

Delete is owner-scoped. A foreign alias ID returns 404. Removing an alias deletes only that `CompanyAlias` row. It never deletes or edits `JobTrack`, application status, dates, notes, or source CSV data.

Alias responses include per-label history counts and a group history count so the UI can explain the impact before confirmation. Company History resolves explicit alias groups when loading roles, while the underlying application records remain separate.

### Slash-containing company names

The backend company-history route remains `/crm/companies/{company:path}`. The frontend always sends the company using `encodeURIComponent`, so names such as `Research/AI Labs` remain navigable. Prior-application links use encoded query parameters and a track-specific fragment.

### Verification

Focused backend coverage:

```sh
cd backend
python -m pytest tests/test_application_matches.py -q
```

The file includes the required JG-031 regressions:

- `visited_only_has_no_applied_warning`
- `exact_match_returns_prior_application_date`
- `canonical_warning_does_not_block_reapply`
- `slash_company_navigation_works`
- `foreign_alias_cannot_be_deleted`

It also checks 409 alias conflicts and proves alias grouping/removal preserves application rows.

Focused browser coverage:

```sh
cd frontend
npm run test:e2e -- tests/applied-before.spec.ts --project=chromium
npm run build
```

Repository CI remains the integration gate for the PostgreSQL backend suite, migration application, backend compile, frontend production build, and Chromium Playwright suite.

### Rollback

JG-031 adds no migration. To disable the feature, remove/hide the applied-before warning and alias controls and stop registering the alias route. Keep the JG-030 canonical fields, alias table, original URLs, JobTracks, lifecycle history, statuses, dates, and notes. No destructive data rewrite or database downgrade is required.

## JG-032 false-positive acceptance for applied-before warnings

JG-032 is the F2 acceptance gate. It adds no schema, route, writer, matching rule, or automatic merge behavior. It verifies the JG-029–JG-031 implementation with labeled synthetic data and keeps the existing conservative confidence levels unchanged.

### Labeled acceptance matrix

The backend acceptance fixture uses isolated companies and requisitions so each expected classification is explicit:

| Case | Candidate change | Expected result |
|---|---|---|
| Exact prior role | Original URL unchanged | `exact / same_original_url` |
| Tracking variant | Same path and nontracking query, only `utm_*` values change | `canonical / same_canonical_url` |
| Same company, new role | New requisition URL and different title | No match |
| Unrelated company, similar title | Different URL and company with a similar title | No match |

A separate new-requisition regression keeps the title the same while changing the requisition path. That case is allowed to return only `possible / company_title_only`; it must never be promoted to `exact` or `canonical`. This is the intentional false-positive boundary: company/title evidence can prompt review, but it is not duplicate identity.

Every matrix lookup is read-only. The fixture compares JobTrack IDs/counts before and after matching to prove the matcher does not merge, delete, or rewrite applications.

### Source deletion and URL-change behavior

The URL-change acceptance case is a re-imported tracking-parameter variant. JG-032 does not add a JobTrack URL-edit path because F2 deliberately preserves original persisted URLs.

The source-deletion regression creates an application through the existing row-to-application writer, marks it applied through the existing application mutation route, then hard-deletes the source CSV row through `DELETE /rows`. The JobTrack must remain applied with `csv_row_id = null`, and an unsaved application-match request for the preserved original URL must still return `exact / same_original_url`.

### Alias grouping boundary

The alias regression creates two distinct applied JobTracks under two company labels, groups them with the public alias API, verifies cross-label `possible` evidence, removes the alias, and verifies the grouping changes while both JobTracks, URLs, statuses, and applied dates remain unchanged. Alias removal is therefore a grouping change only, never an application-history mutation.

### Bounded matching evidence

The large-fixture regression creates `APPLICATION_MATCH_SCAN_LIMIT + 40` applied records for one company. It instruments SQL with the repository's existing `before_cursor_execute` pattern and asserts:

- the scan limit remains 100;
- the response limit remains 20;
- the candidate JobTrack query contains a SQL `LIMIT`;
- matching performs exactly one bounded candidate select plus one company-history count over JobTrack; and
- the complete request uses a constant small number of SELECT statements rather than one query per candidate.

### Synthetic precision metric

For JG-032, “duplicate-grade” means only `exact` or `canonical`. The four-case labeled matrix has two positive duplicate-grade cases and two negative cases. A passing fixture therefore records duplicate-grade precision as **2 correct duplicate-grade warnings / 2 duplicate-grade warnings = 100% on this synthetic matrix**, with **0 exact/canonical warnings across the two negative matrix cases**.

This number is an acceptance-fixture measurement only. It is not a claim about real-world matching accuracy or production precision. Real-world accuracy requires reviewed production-like labeled data before any such claim can be made.

### Verification

Focused backend acceptance:

```sh
cd backend
python -m pytest tests/test_application_matches.py -q
```

JG-032 adds or strengthens these required regressions:

- `test_jg032_labeled_false_positive_matrix`
- `test_new_requisition_not_exact_duplicate`
- `test_source_delete_retains_warning`
- `test_alias_remove_changes_grouping_only`
- `test_matching_query_bounded_for_large_fixture`

Focused browser acceptance:

```sh
cd frontend
npm run test:e2e -- tests/applied-before.spec.ts --project=chromium
npm run build
```

The browser case `tracking_variant_warning_and_continue` uploads a tracking variant, opens RowDrawer, verifies the canonical warning, explicitly continues through the existing Mark applied writer, and then proves the prior application and the new reapplication both remain present.

Repository CI remains the final integration gate for PostgreSQL-backed backend tests, migration application, backend compile, frontend production build, and the full Chromium Playwright suite.

### Rollback and release state

JG-032 is test/documentation-only and adds no migration. Reverting JG-032 itself removes only acceptance coverage/documentation. Runtime rollback of the underlying F2 feature remains the JG-031 procedure: hide warning/alias controls while retaining canonical fields, aliases, original URLs, JobTracks, lifecycle history, statuses, dates, and notes.

A green local/CI acceptance result is recorded separately from staging acceptance or production release.



## Application evidence storage and immutable lifecycle payloads

JG-033 provides the F3 persistence contract. JG-034 activates the authenticated evidence mutation, correction, and merged timeline API on those existing tables. JG-035 still owns the user interface.

### Evidence records

`application_evidence` stores evidence attached to one owned `JobTrack`. The parent relationship uses `ON DELETE RESTRICT`, so application history cannot disappear while evidence still depends on it. Each row stores:

- `kind`: `confirmation_url`, `confirmation_text`, or `note`;
- `body`: private evidence content. Active evidence requires a body. A soft-deleted row may keep the body only during the recovery window;
- optional `occurred_at`, plus `created_at` and `updated_at`;
- optimistic `version`, starting at 1;
- explicit `is_deleted`.

Confirmation URLs are user assertions. They must be credential-free HTTP(S), are limited to 2,048 characters, and are never fetched automatically. Text and note evidence are limited to 20,000 characters. `backend/app/services/evidence.py::require_owned_track` resolves a parent only inside the authenticated account.

Migration `010_application_evidence.py` is additive and follows the already-applied JG-030 revision `009`. It also creates `evidence_create_receipts`, keyed uniquely by account and UUID request key. Receipts store only the payload hash, evidence ID, and creation time. They are replay state, not portable account content.

### Lifecycle payload rules

The existing `JobLifecycleEvent` remains the only lifecycle ledger. JG-033 adds `evidence_added`, `evidence_edited`, and `evidence_deleted`. Their payloads may contain only evidence identifiers, evidence kind, and the version needed for edited/deleted markers. Full evidence bodies are rejected from lifecycle payloads.

Correction metadata is additive. `applied_date_corrected` may carry the previous value, new value, and a trimmed reason of 1 to 500 characters. A compensating `status_changed` correction may additionally carry `correction_of`, which identifies the original event. Existing lifecycle rows are never rewritten to represent a correction. JG-034 requires a reason on the dedicated applied-date and status-correction routes while preserving compatibility for older application writers.

### Evidence mutation API

JG-034 exposes the F3 service under the existing authenticated CRM boundary:

- `POST /crm/tracks/{track_id}/evidence` requires an `Idempotency-Key` UUID. A new matching request returns HTTP 201. Replaying the same key and payload returns HTTP 200 with the same evidence row and does not emit another lifecycle event. Reusing the key with different input returns 409.
- `PATCH /crm/tracks/{track_id}/evidence/{evidence_id}` requires the current positive `version`. It can update `body` and/or `occurred_at`. A stale version returns 409. A successful edit increments the version and appends one `evidence_edited` marker.
- `DELETE /crm/tracks/{track_id}/evidence/{evidence_id}` is a soft delete. The first delete appends one `evidence_deleted` marker and increments the version. Repeating the delete as the same owner returns 204 without creating a duplicate event.
- `PATCH`, `DELETE`, and correction routes accept the same optional `X-Operation-ID` UUID used by existing CRM mutation endpoints. If omitted, the server creates an operation ID for that request.

All parent and evidence lookups are account-scoped. A missing or foreign track/evidence returns 404. Validation failures return 422 before mutation, optimistic/concurrency conflicts return 409, and the route rolls back the caller transaction on service or lifecycle failure. Operational logs include only the action, request ID, outcome, affected count, and elapsed time. Evidence bodies are never written to those logs.

Ordinary evidence serialization includes the private `body` only while evidence is active. A deleted row keeps its historical metadata and recovery storage policy, but its ordinary API representation omits the body entirely.

### Merged timeline API

`GET /crm/tracks/{track_id}/timeline?before=&limit=50` merges the immutable lifecycle ledger with current evidence records. The response shape is:

```json
{
  "items": [
    {
      "type": "lifecycle",
      "id": 41,
      "timestamp": "2026-09-20T12:00:00Z",
      "kind": "first_applied",
      "source": "user",
      "payload": {}
    },
    {
      "type": "evidence",
      "id": 9,
      "timestamp": "2026-09-20T12:05:00Z",
      "kind": "confirmation_url",
      "source": "user",
      "track_id": 17,
      "version": 1,
      "is_deleted": false,
      "body": "https://example.com/confirmation"
    }
  ],
  "next_before": null
}
```

Pages are capped at 100. The server selects the newest bounded page and returns that page in chronological order. `next_before` is an opaque URL-safe cursor over timestamp, record type, and record ID. Equal timestamps therefore paginate without duplicate or missing records. Clients must not parse or construct the cursor themselves.

Lifecycle sources are normalized to the public labels `user`, `import`, `system`, or `legacy`. Deleted evidence remains visible as a redacted evidence marker with `is_deleted=true`; its private body is absent. Lifecycle evidence-added/edited/deleted markers remain append-only audit facts.

### Corrections

`POST /crm/tracks/{track_id}/applied-date-corrections` accepts a replacement `applied_at` plus a trimmed 1–500 character `reason`. The service takes an application-row lock, routes the change through the shared lifecycle writer, and appends `applied_date_corrected` with the old date, new date, and reason. The original `first_applied` event remains unchanged, so historical applied metrics are not rewritten.

`POST /crm/tracks/{track_id}/status-corrections` accepts `expected_event_id`, `restore_status`, and `reason`. Under an application-row lock, the expected event must still be the latest `status_changed` event, the track's current status must match that event's recorded `to` value, and `restore_status` must equal its prior valid `from` value. Any intervening status change returns 409. Success updates current status and appends a compensating `status_changed` event containing `correction_of` and the reason. The original event is never edited or deleted.

### Soft-delete recovery and maintenance

A soft delete hides the body from ordinary serializers immediately. The private body can remain in storage for at most 30 days, measured from the evidence row's deletion `updated_at`. `purge_expired_evidence_recovery_state()` processes at most 500 rows per call, blanks expired private bodies without deleting evidence markers, and removes create receipts older than 30 days. JG-033 does not register a scheduler. The caller owns the transaction and later maintenance wiring.

The ordinary `application_evidence` backup section always redacts the body when `is_deleted=true`. If that body is still inside the recovery window, export places it only in the explicitly labeled `evidence_recovery` section with an absolute `body_purge_at`. Restore remaps the evidence to the destination application and restores the private recovery body only while that original deadline is still active. Restoring a backup never extends the recovery period.

Evidence lifecycle events use `evidence_ref` in portable backups. The runtime database ID is removed from the exported payload and rebuilt from the destination evidence mapping during restore. Status corrections use the same rule: runtime `correction_of` IDs become `correction_of_ref` in backup records and are remapped to the destination original event during restore. Correction references must point to an earlier lifecycle record, which prevents restore from preserving a source-database primary key by accident. Older v2 backups that lack the evidence sections and the new portable lifecycle reference fields keep their original checksum shape and remain valid.

### Validation

Focused backend checks are:

```sh
cd backend
pytest tests/test_evidence_models.py tests/test_evidence_api.py tests/test_backup_contract.py tests/test_schema_parity.py -q
```

Repository CI remains the release gate for PostgreSQL migration parity, the complete backend suite, backend compilation, the production frontend build, and Chromium regressions.

Rollback is data-preserving. Disable future evidence consumers first. Do not remove evidence rows, lifecycle events, or application history to roll back application code. Older code can ignore the additive evidence tables and optional v2 evidence sections.


### Application timeline and evidence interface

JG-035 exposes the existing F3 evidence and lifecycle contracts from the Applications screen. Expand **History & evidence** on an application, or follow a RowDrawer **History & evidence** link, to load the owner-scoped merged timeline from `GET /crm/tracks/{track_id}/timeline`.

The interface keeps occurrence time and recording time separate. Evidence without `occurred_at` displays **Unknown** rather than treating `created_at` as the submission date. Imported lifecycle entries are labeled as imports and explicitly state that their recorded/import time is not assumed to be an application date. The **Recorded** hint exposes the immutable ledger/evidence recording timestamp in its tooltip.

Evidence entry supports confirmation URLs, confirmation text, and notes. User-provided text is rendered as React text only, never injected as HTML. Confirmation URLs must be credential-free HTTP(S). Create requests use an idempotency UUID. Edits send the evidence version and preserve the local draft when the server returns 409 for a stale version. Deletes are soft deletes. Their body disappears from ordinary reads immediately and recovery data may retain it for at most 30 days.

An existing applied date is read-only in the applications table. Corrections happen in the timeline interface, require a reason, preview the old and new metric dates, and append an `applied_date_corrected` lifecycle event. The latest status can be compensated only when the displayed `status_changed` event is still latest. A 409 is shown as a newer-change conflict and does not discard the correction reason.

Timeline pagination uses the server `next_before` cursor. Loading older pages prepends older records while preserving chronological display. Network failures keep evidence/correction drafts and expose retry/reload actions. Successful mutations refresh the persisted timeline and application snapshot.

**Rollback:** remove or disable the JG-035 interface controls only. Do not delete application evidence, evidence receipts, or lifecycle events. Existing application status, notes, and the JG-034 APIs remain compatible.


### F3 lifecycle and recovery acceptance proof

JG-036 verifies that application history remains trustworthy across source deletion, backup/restore, and transactional failure. It adds no new storage model or public API.

A source CSV row is disposable after its application snapshot exists. Deleting the CSV row clears `JobTrack.csv_row_id` and database `SET NULL` references on lifecycle rows, but the application, evidence, and lifecycle timeline remain available with the same user-visible content. Evidence continues to be owned by the durable application track, not the CSV source row.

Portable v2 backup preserves active evidence, deleted-evidence recovery data, lifecycle events, evidence references, and status-correction references. Restore remaps database IDs into the destination account. The acceptance fixture compares the source and destination timelines after normalizing only those database-local reference IDs. Event kind, source, occurrence/recording timestamps, evidence body/deletion state, status transitions, correction reasons, and ordering must remain semantically equivalent.

Evidence creation is one transaction with its lifecycle marker and idempotency receipt. The JG-036 failure-injection regression raises a lifecycle-event error after the evidence row has been flushed. The request must fail and the transaction rollback must leave zero evidence rows, zero create receipts, and zero partial lifecycle markers.

Soft deletion immediately removes the private evidence body from ordinary evidence/timeline serialization while retaining only the historical deletion marker. A recently deleted body may exist only in the explicitly labeled recovery backup section for the bounded 30-day recovery window. It is never restored into the ordinary timeline body field.

Status correction remains compensating history, not mutation of prior events. The original status event stays unchanged. A correction appends a new `status_changed` event with `correction_of` and a bounded reason. Reusing an older expected event after a newer status event exists returns a conflict instead of overwriting newer history.

Legacy/import uncertainty is preserved deliberately. Imported record timestamps are not treated as verified submission timestamps, and evidence is a user-recorded assertion rather than proof that an application was actually submitted. Missing occurrence dates remain unknown.

**Verification commands:**

```sh
cd backend
python -m pytest tests/test_evidence_api.py tests/test_backup_restore.py -q

cd ../frontend
npm run test:e2e -- tests/application-timeline.spec.ts --project=chromium
npm run build
```

**Rollback:** JG-036 changes only verification coverage and documentation. Removing those tests/docs does not authorize deleting evidence, lifecycle events, correction history, or recovery data.
