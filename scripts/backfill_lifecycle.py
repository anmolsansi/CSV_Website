#!/usr/bin/env python3
"""Backfill durable first lifecycle facts from known legacy timestamps.

Examples:
    python scripts/backfill_lifecycle.py --dry-run
    python scripts/backfill_lifecycle.py --apply --after-id 42

`--after-id` is a User.id checkpoint, not a CSV-row or JobTrack cursor. Each
source-table transaction scans at most 500 records. If a run stops while one
user is being processed, resume from the previous completed user checkpoint;
first-event keys make replay safe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.lifecycle import (  # noqa: E402
    LEGACY_BACKFILL_REVIEW_QUERIES,
    MAX_LEGACY_BACKFILL_BATCH_SIZE,
    backfill_legacy_applications,
    backfill_legacy_visits,
    legacy_backfill_warning_counts,
)


BackfillFunction = Callable[..., dict[str, int | bool]]


def _merge_counts(total: dict[str, int], batch: dict[str, int | bool]) -> None:
    for key in (
        "scanned",
        "eligible",
        "created",
        "already_present",
        "missing_dates",
        "duplicate_conflicts",
    ):
        total[key] = total.get(key, 0) + int(batch[key])


def _run_source(
    *,
    user_id: int,
    dry_run: bool,
    batch_size: int,
    function: BackfillFunction,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    source_cursor = 0
    while True:
        with SessionLocal() as session:
            with session.begin():
                batch = function(
                    session,
                    user_id=user_id,
                    after_id=source_cursor,
                    limit=batch_size,
                    dry_run=dry_run,
                )
        _merge_counts(totals, batch)
        if not bool(batch["has_more"]):
            break
        next_cursor = int(batch["last_id"])
        if next_cursor <= source_cursor:
            raise RuntimeError("Legacy backfill cursor did not advance.")
        source_cursor = next_cursor
    return totals


def _user_ids_after(after_id: int) -> list[int]:
    with SessionLocal() as session:
        return [
            int(user_id)
            for (user_id,) in (
                session.query(User.id)
                .filter(User.id > after_id)
                .order_by(User.id.asc())
                .all()
            )
        ]


def run_backfill(*, dry_run: bool, after_id: int, batch_size: int) -> dict:
    if after_id < 0:
        raise ValueError("--after-id must be zero or a positive User.id.")
    if batch_size < 1 or batch_size > MAX_LEGACY_BACKFILL_BATCH_SIZE:
        raise ValueError(
            f"--batch-size must be between 1 and {MAX_LEGACY_BACKFILL_BATCH_SIZE}."
        )

    aggregate = {
        "mode": "dry_run" if dry_run else "apply",
        "after_id": after_id,
        "batch_size": batch_size,
        "users_scanned": 0,
        "visits": {},
        "applications": {},
        "warnings": {
            "clicked_without_date": 0,
            "applied_without_date": 0,
            "duplicate_csv_urls": 0,
            "duplicate_track_urls": 0,
        },
        "last_completed_user_id": after_id,
        "review_queries": LEGACY_BACKFILL_REVIEW_QUERIES,
    }

    for user_id in _user_ids_after(after_id):
        with SessionLocal() as session:
            warnings = legacy_backfill_warning_counts(session, user_id=user_id)
        for key, value in warnings.items():
            aggregate["warnings"][key] += int(value)

        visit_counts = _run_source(
            user_id=user_id,
            dry_run=dry_run,
            batch_size=batch_size,
            function=backfill_legacy_visits,
        )
        application_counts = _run_source(
            user_id=user_id,
            dry_run=dry_run,
            batch_size=batch_size,
            function=backfill_legacy_applications,
        )
        _merge_counts(aggregate["visits"], visit_counts)
        _merge_counts(aggregate["applications"], application_counts)

        aggregate["users_scanned"] += 1
        aggregate["last_completed_user_id"] = user_id
        print(
            json.dumps(
                {
                    "checkpoint_after_user_id": user_id,
                    "mode": aggregate["mode"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely backfill JobGrid legacy lifecycle first events."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Report eligible facts and warnings without writing lifecycle events.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write only lifecycle facts backed by known legacy timestamps.",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Resume after this fully completed User.id checkpoint.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=MAX_LEGACY_BACKFILL_BATCH_SIZE,
        help=f"Source records per transaction (max {MAX_LEGACY_BACKFILL_BATCH_SIZE}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_backfill(
            dry_run=bool(args.dry_run),
            after_id=args.after_id,
            batch_size=args.batch_size,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
