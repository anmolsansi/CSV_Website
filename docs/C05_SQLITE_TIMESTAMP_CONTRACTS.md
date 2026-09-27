# C-05 — SQLite Timestamp Contracts

Status: implementation complete pending hosted CI on the C-05 pull request.

Baseline: `4d2222e75ea1070977cff8710b9ae8c0770a7a59` (`main`, after C-04 / PR #162).

## Contract

JobGrid has three distinct time concepts and they must not be collapsed into one representation:

1. **UTC instants** — persisted events such as `WorkItemOverride.snoozed_until`, reminder scheduling/delivery timestamps, lifecycle timestamps, and similar event times represent one absolute instant. At Python service and wire boundaries these are normalized to timezone-aware UTC.
2. **Date-only values** — a calendar deadline/date remains a date when its owning contract defines it as a date. It must not acquire a host timezone merely because other timestamp fields use UTC instants.
3. **Account-local wall times** — reminder preference values such as `09:00`, quiet-start, and quiet-end are local scheduling rules interpreted with the account IANA timezone. They are not stored or compared as UTC instants until a specific occurrence is resolved.

For legacy/persisted UTC-instant columns, a naive datetime returned by SQLite means **naive UTC**, not local server time. `backend/app/time_utils.py::normalize_utc_instant()` is the explicit persistence-boundary normalization for that case. Aware values are converted to UTC without changing the represented instant.

This rule does **not** weaken request validation. User inputs that require an explicit offset remain invalid when naive.

## Why no migration is required

The target columns are already declared with `DateTime(timezone=True)`:

- `WorkItemOverride.snoozed_until`
- `ReminderDelivery.scheduled_at`
- `ReminderDelivery.lease_until`
- `ReminderDelivery.next_attempt_at`
- `ReminderDelivery.sent_at`
- `ReminderDelivery.read_at`

PostgreSQL reloads these as timezone-aware values. SQLite's SQLAlchemy datetime path reloads them without tzinfo. The observed failures were therefore representation differences at the Python boundary, not evidence that the database schema needed rewriting.

Production writers already resolve snoozes and reminder schedules to UTC before persistence. C-05 adds an explicit shared normalization boundary so reloaded SQLite values are interpreted consistently.

## WorkItemOverride.snoozed_until trace

1. `SnoozeRequest.until` requires an explicit timezone offset and converts the input to UTC.
2. `services.today.snooze_action()` persists that UTC instant in `WorkItemOverride.snoozed_until`.
3. PostgreSQL reloads an aware value. SQLite may reload the same stored UTC wall value as naive.
4. Today serialization uses the existing `canonical_utc_timestamp()` path, which treats persisted naive values as UTC and emits a canonical `Z` timestamp.
5. Portable backup export likewise canonicalizes persisted values to UTC `Z` strings.
6. Backup validation requires the frozen UTC timestamp contract, and restore writes that instant back into the target database.
7. The C-05 SQLite acceptance test expires/reopens the session, verifies microseconds, checks Today serialization, performs backup/restore, and verifies the re-exported instant.

## ReminderDelivery.sent_at trace

1. `apply_delivery_transition(..., new_status="sent", sent_at=...)` requires an explicit offset.
2. C-05 normalizes the accepted input to UTC before assigning `delivery.sent_at`.
3. After reload, SQLite may return naive UTC while PostgreSQL returns aware UTC.
4. Idempotent `sent -> sent` validation now compares canonical UTC instants rather than raw Python datetime tzinfo shape.
5. A genuinely different instant is still rejected as `sent_at_immutable`.
6. A naive caller-supplied `sent_at` remains rejected as `sent_at_timezone_required`, including the idempotent path.
7. Reminder API summaries normalize `scheduled_at`, `sent_at`, and `read_at` to aware UTC before FastAPI serialization, so SQLite and PostgreSQL represent the same instant on the wire.
8. Portable backup export emits UTC `Z`; restore preserves the accepted instant and does not resume sent deliveries.

## Acceptance coverage

`backend/tests/test_timestamp_contracts.py` adds explicit coverage for:

- UTC normalization with microseconds
- positive UTC offsets
- negative UTC offsets
- the 2026 `America/New_York` DST fall-back overlap, both folds
- legacy naive persisted values interpreted as UTC
- rejection of naive user timestamp input
- real SQLite persistence followed by session close/reopen
- null timestamp preservation
- Today snooze serialization
- reminder response serialization
- same-instant reminder idempotency after SQLite reload
- changed-instant immutability rejection
- portable backup export, restore, and re-export for both snooze and sent reminder timestamps
- subprocess execution of the two original C-05 regressions against an explicit SQLite database

The ordinary hosted backend test job continues to execute the same original tests against PostgreSQL. The explicit SQLite subprocess therefore makes the two originally failing regressions run against both supported database paths without waiting for the broader C-07 CI matrix work.

## No behavior changed outside the contract

C-05 does not:

- change any database column type
- add or rewrite an Alembic migration
- attach the host timezone to a naive persisted value
- reinterpret date-only deadlines
- reinterpret reminder local wall-clock preferences
- relax timezone-aware input requirements
- change reminder retry, delivery, or immutability state transitions
- introduce a second backup timestamp format

## Completion proof required before merge

The C-05 PR must show:

- the original backup snooze regression passing on PostgreSQL and SQLite
- the original reminder `sent_at` regression passing on PostgreSQL and SQLite
- focused C-05 timestamp tests passing
- related Today/reminder/backup tests passing
- backend compile/test CI green
- no migration or schema diff

After those checks are green, this document is the requirement-level evidence for C-05. `development.md` can be reconciled to checked/completed state during the normal completion-documentation pass without changing the technical contract recorded here.
