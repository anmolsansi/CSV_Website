"""Backfill JG-030 derived identity fields in bounded, resumable batches.

Examples:
    python scripts/backfill_job_identity.py --entity csv_rows --dry-run
    python scripts/backfill_job_identity.py --entity job_tracks --after-id 500
"""

from __future__ import annotations

import argparse
import json

from app.database import SessionLocal
from app.models import CsvRow, JobTrack
from app.services.job_identity import CANONICALIZATION_VERSION, backfill_identity_batch


MODELS = {
    "csv_rows": CsvRow,
    "job_tracks": JobTrack,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill conservative canonical job identity fields."
    )
    parser.add_argument(
        "--entity",
        choices=("csv_rows", "job_tracks", "all"),
        default="all",
        help="Record type to process. 'all' runs one bounded batch per table.",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Resume strictly after this integer primary key.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        choices=range(1, 501),
        metavar="1..500",
        help="Maximum records per table in this invocation (default: 500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute counts and collisions without writing derived fields.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = (
        MODELS.items()
        if args.entity == "all"
        else ((args.entity, MODELS[args.entity]),)
    )

    session = SessionLocal()
    try:
        reports = []
        for _, model in selected:
            report = backfill_identity_batch(
                session,
                model,
                after_id=args.after_id,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            reports.append(report.as_dict())

        if args.dry_run:
            session.rollback()
        else:
            session.commit()

        # Operational output is deliberately count/ID-only. Never print source
        # or canonical URLs from a real account.
        print(json.dumps({"identity_rule_version": CANONICALIZATION_VERSION, "reports": reports}, sort_keys=True))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
