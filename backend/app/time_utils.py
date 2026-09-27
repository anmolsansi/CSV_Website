from __future__ import annotations

from datetime import datetime, timezone


def normalize_utc_instant(value: datetime) -> datetime:
    """Return a timezone-aware UTC instant for persisted UTC timestamps.

    SQLite drops timezone information when SQLAlchemy reloads DateTime(timezone=True)
    values. JobGrid writes UTC instants to those columns, so a naive value read back
    from persistence is interpreted as UTC, never as the host machine's timezone.
    Aware values are converted to UTC without changing the represented instant.

    This helper is for persistence/read boundaries. Request validators that require
    an explicit timezone offset must continue to reject naive user input before
    calling it.
    """

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def same_utc_instant(left: datetime, right: datetime) -> bool:
    """Compare persisted timestamps by instant across PostgreSQL and SQLite."""

    return normalize_utc_instant(left) == normalize_utc_instant(right)
