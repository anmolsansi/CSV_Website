# JobGrid Build Guide Addendum — JG-056 through JG-058

This addendum records the repository-local implementation and verification boundary for JG-056, JG-057, and JG-058. It does not claim a staging or production deployment.

## JG-056 — F8 privacy, scheduling, and recovery acceptance

F8 contacts and interviews remain authenticated-account private. Contact search is owner-scoped, soft-deleted contacts are omitted from normal contact search, and application-linked deleted contacts serialize only a tombstone without email or notes. Interview cancellation preserves the application record, application notes, applied date, and interview history while cancelling unsent interview reminder deliveries.

Calendar export is authenticated and emits one RFC 5545 `VEVENT`. User text is escaped and folded so it cannot inject calendar properties or additional events. Private contact notes, interview notes, and preparation notes are not written into the calendar file. Interview times are stored as UTC instants with an explicit IANA display timezone. Ambiguous DST wall-clock input without an offset is rejected; explicit instants on either side of DST gaps/overlaps remain distinct.

Contact and interview creation do not send recruiter/interviewer email or invitations. The calendar endpoint is a download only. Portable backup/restore includes owner-scoped contacts, application-contact relationships, interviews, private notes, display timezone, and relationship remapping. Restore keeps the relationship graph intact under the destination account.

Focused acceptance coverage lives in `backend/tests/test_jg056_acceptance.py` together with the existing F8 contact, calendar, Today, reminder, and backup suites.

## JG-057 — Private import preview and mapping persistence

Alembic revision `017` adds:

- `import_previews`, an owner-scoped transient preview/reconciliation record.
- `import_mappings`, an owner-scoped reusable source-column-index mapping.

Import previews store source metadata, exact positional headers, header fingerprint, mapping, normalized plan, rejected original rows, summary, destination fingerprint, version, expiry, commit replay identity, and final result. Preview status is constrained to `ready`, `committing`, `committed`, or `failed`.

Saved mapping names are unique per account. A saved mapping uses the exact header fingerprint generated from the normalized header sequence. Duplicate source labels remain distinguishable because mapping keys are zero-based source positions, not header text.

Transient previews expire after 24 hours. Committed replay results are retained for 30 days while normalized/raw valid rows are removed after commit. The bounded cleanup helper removes expired previews and scrubs expired raw-row blobs. Portable backup includes saved mappings only. Uploaded previews, normalized rows, rejected raw rows, commit locks, and other transient preview state are excluded.

The import update allowlist is limited to source-derived `CSV_COLUMNS` fields other than URL identity. Application/lifecycle state such as JobTrack status, notes, applied/follow-up timestamps, and CsvRow clicked/archive state is not writable through this import path.

Focused model/contract coverage is in `backend/tests/test_import_preview_models.py`.

## JG-058 — Preview parsing and transactional reconciliation

### Limits and accepted input

`POST /crm/imports/preview` accepts a multipart file plus JSON `mapping` and optional JSON `options` form fields.

- Maximum upload: 10 MiB.
- Maximum records: 2,000.
- Preview sample: at most 100 rows.
- CSV: UTF-8 or UTF-8-BOM. Delimiter detection is bounded to comma, tab, or semicolon. Headers are preserved by position, including duplicate labels.
- JSON: UTF-8 array of objects only. Scalar values may be string, number, boolean, or null. Spreadsheet formulas are never executed.
- URL is required and validated through the shared JobGrid URL validation contract.
- One source position maps to one known JobGrid CSV field, and one target can have only one source in the initial release.

Preview performs no row mutation. It returns the preview ID, expiry/version, positional columns, a bounded sample, exact create/exact-duplicate/possible-duplicate/invalid counts, and bounded row/column error codes.

Duplicate planning is conservative. Exact original-URL matches are the only records eligible for `update_selected`. Canonical URL matches and company/title-only matches are possible duplicates and are never silently merged.

### Commit

`POST /crm/imports/{preview_id}/commit` accepts:

- `version`
- UUID `idempotency_key`
- `mode`: `insert_only` or `update_selected`
- explicit `update_fields`
- `invalid_policy`: `reject` or `skip`
- `replace_empty` for deliberate empty replacement

Defaults are insert-only and reject-invalid. Before mutation, commit rechecks owner, expiry, preview version, payload replay identity, and destination fingerprint. PostgreSQL uses an account-scoped advisory transaction lock. Non-PostgreSQL local/test execution relies on that database engine's transaction semantics; no process-local mutex is claimed.

If the destination changed since preview, commit returns `409 destination_changed`; it does not silently re-plan. Reusing the same idempotency key with the same payload returns the recorded final result. Reusing it with different content returns a conflict.

The commit is one database transaction. Inserted rows receive canonical identity and URL-history entries. Exact matches may update only explicitly selected allowlisted source fields. `replace_empty=false` preserves existing values when the incoming selected value is null/empty. Import never changes application status, notes, applied/follow-up timestamps, clicked state, clicked timestamp, archive state, or archive timestamp. Any commit failure rolls back the logical import and replay state together.

### Rejected rows

`GET /crm/imports/{preview_id}/rejected.csv` is authenticated and owner-scoped. It preserves original source header order and invalid source values, adds source row number and error code, uses spreadsheet-safe serialization, and sends `Cache-Control: no-store`. The endpoint returns `410` after the 24-hour preview expiry.

### Rollback and compatibility

The original `/upload` importer remains available. The new preview/commit API does not automatically fall back to the old importer after a preview failure. Rolling back application code can disable the new routes while retaining migration `017` tables and any already committed job rows. No reverse mutation is performed automatically.

JG-059 owns the new mapping/review UI. JG-058 exposes backend/service behavior only and does not mark that later interface ticket complete.

## Verification

Focused backend command:

```sh
cd backend
python -m pytest \
  tests/test_jg056_acceptance.py \
  tests/test_import_preview_models.py \
  tests/test_import_preview.py \
  tests/test_import_commit.py -q
```

The required JG-058 regressions are named:

- `invalid_reject_zero_writes`
- `skip_invalid_counts_exact`
- `update_title_preserves_notes_clicked_applied`
- `destination_changed_after_preview409`
- `replayed_commit_identical_result`
- `last_row_failure_rolls_back_all`

Repository completion requires migration `017`, the full PostgreSQL backend suite, backend compile check, frontend production build, and full Chromium Playwright suite to pass on the final PR head. External staging/release remains a separate gate.