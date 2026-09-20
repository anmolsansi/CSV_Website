from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import CsvRow, User


MAX_ARCHIVE_BATCH_SIZE = 500
MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 3650


@dataclass(frozen=True)
class CleanupResult:
    """Safe aggregate result for one bounded automatic-archive run."""

    scanned: int = 0
    archived: int = 0
    skipped: int = 0
    failed: int = 0
    duration_ms: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class RetentionJobError(RuntimeError):
    """A cleanup failure that carries a non-success aggregate result."""

    def __init__(self, message: str, result: CleanupResult):
        super().__init__(message)
        self.result = result


def _naive_utc(value: datetime | None) -> datetime:
    """Normalize an injected clock to the naive-UTC convention used by the ORM."""
    if value is None:
        return datetime.utcnow()
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _active_policy_groups(db: Session) -> dict[int, list[int]]:
    """Return valid enabled retention policies grouped by day count."""
    rows = (
        db.query(User.id, User.retention_days)
        .filter(
            User.retention_days.isnot(None),
            User.retention_days >= MIN_RETENTION_DAYS,
            User.retention_days <= MAX_RETENTION_DAYS,
        )
        .all()
    )
    groups: dict[int, list[int]] = {}
    for user_id, retention_days in rows:
        groups.setdefault(int(retention_days), []).append(int(user_id))
    return groups


def archive_eligible_rows(
    db: Session,
    *,
    now: datetime | None = None,
    batch_size: int = MAX_ARCHIVE_BATCH_SIZE,
) -> CleanupResult:
    """Archive one deterministic, bounded batch of policy-eligible rows.

    Eligibility requires an enabled per-account policy, a known clicked_at at
    or before that account's cutoff, and an unarchived row. This service never
    deletes data. One invocation owns one transaction and commits at most 500
    first-time archive transitions.
    """
    started = perf_counter()
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size < 1
        or batch_size > MAX_ARCHIVE_BATCH_SIZE
    ):
        result = CleanupResult(
            failed=1,
            duration_ms=int((perf_counter() - started) * 1000),
        )
        raise RetentionJobError(
            f"batch_size must be between 1 and {MAX_ARCHIVE_BATCH_SIZE}",
            result,
        )

    reference_now = _naive_utc(now)
    selected_ids: list[int] = []

    try:
        policy_groups = _active_policy_groups(db)
        if not policy_groups:
            return CleanupResult(
                duration_ms=int((perf_counter() - started) * 1000)
            )

        policy_clauses = [
            and_(
                CsvRow.user_id.in_(user_ids),
                CsvRow.clicked_at <= reference_now - timedelta(days=retention_days),
            )
            for retention_days, user_ids in sorted(policy_groups.items())
        ]

        candidate_query = (
            db.query(CsvRow.id)
            .filter(
                CsvRow.archived.is_(False),
                CsvRow.clicked_at.isnot(None),
                or_(*policy_clauses),
            )
            .order_by(CsvRow.id.asc())
            .limit(batch_size)
        )
        if db.get_bind().dialect.name == "postgresql":
            candidate_query = candidate_query.with_for_update(skip_locked=True)

        selected_ids = [row_id for (row_id,) in candidate_query.all()]
        if not selected_ids:
            return CleanupResult(
                duration_ms=int((perf_counter() - started) * 1000)
            )

        archived = (
            db.query(CsvRow)
            .filter(
                CsvRow.id.in_(selected_ids),
                CsvRow.archived.is_(False),
            )
            .update(
                {
                    CsvRow.archived: True,
                    CsvRow.archived_at: reference_now,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return CleanupResult(
            scanned=len(selected_ids),
            archived=int(archived),
            skipped=max(0, len(selected_ids) - int(archived)),
            duration_ms=int((perf_counter() - started) * 1000),
        )
    except RetentionJobError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        result = CleanupResult(
            scanned=len(selected_ids),
            failed=max(1, len(selected_ids)),
            duration_ms=int((perf_counter() - started) * 1000),
        )
        raise RetentionJobError("automatic archive batch failed", result) from exc
