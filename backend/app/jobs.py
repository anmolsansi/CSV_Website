from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Callable, Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, engine
from .services.retention import (
    CleanupResult,
    MAX_ARCHIVE_BATCH_SIZE,
    RetentionJobError,
    archive_eligible_rows,
)


logger = logging.getLogger(__name__)

# Session-level PostgreSQL advisory lock reserved for JobGrid's archive worker.
# The in-process lock protects duplicate scheduler/job invocation inside one
# Python process. PostgreSQL supplies the cross-process boundary in production.
POSTGRES_CLEANUP_LOCK_KEY = 0x4A47303133
_cleanup_process_lock = threading.Lock()


@contextmanager
def cleanup_job_lock() -> Iterator[bool]:
    """Acquire the non-blocking process and PostgreSQL cleanup locks."""
    if not _cleanup_process_lock.acquire(blocking=False):
        yield False
        return

    connection = None
    advisory_lock_acquired = False
    try:
        if engine.dialect.name == "postgresql":
            connection = engine.connect()
            advisory_lock_acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": POSTGRES_CLEANUP_LOCK_KEY},
                ).scalar()
            )
            if not advisory_lock_acquired:
                yield False
                return
        yield True
    finally:
        if connection is not None:
            if advisory_lock_acquired:
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": POSTGRES_CLEANUP_LOCK_KEY},
                    )
                except Exception:
                    # Closing the dedicated connection also releases a
                    # session-level advisory lock. Do not turn a completed,
                    # idempotent archive batch into a false data failure.
                    logger.warning(
                        "cleanup_archive_job outcome=unlock_warning",
                        exc_info=True,
                    )
            connection.close()
        _cleanup_process_lock.release()


def cleanup_clicked_rows(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    now: datetime | None = None,
    batch_size: int = MAX_ARCHIVE_BATCH_SIZE,
) -> dict[str, int]:
    """Run one bounded, observable automatic-archive batch.

    The historical function name is retained for scheduler compatibility.
    Unlike the retired implementation, this job never hard-deletes rows and
    never uses row creation time as visit evidence.
    """
    started = perf_counter()
    if settings.AUTO_ARCHIVE_AFTER_DAYS <= 0:
        result = CleanupResult(
            duration_ms=int((perf_counter() - started) * 1000),
        )
        logger.info(
            "cleanup_archive_job outcome=disabled reason=auto_archive_disabled "
            "scanned=0 archived=0 skipped=0 failed=0 duration_ms=%s",
            result.duration_ms,
        )
        return result.as_dict()

    try:
        with cleanup_job_lock() as acquired:
            if not acquired:
                result = CleanupResult(
                    skipped=1,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                logger.info(
                    "cleanup_archive_job outcome=skipped reason=lock_contended "
                    "scanned=%s archived=%s skipped=%s failed=%s duration_ms=%s",
                    result.scanned,
                    result.archived,
                    result.skipped,
                    result.failed,
                    result.duration_ms,
                )
                return result.as_dict()

            db = session_factory()
            try:
                result = archive_eligible_rows(
                    db,
                    now=now,
                    batch_size=batch_size,
                )
            finally:
                db.close()

            outcome = "success" if result.archived else "no_work"
            logger.info(
                "cleanup_archive_job outcome=%s scanned=%s archived=%s "
                "skipped=%s failed=%s duration_ms=%s",
                outcome,
                result.scanned,
                result.archived,
                result.skipped,
                result.failed,
                result.duration_ms,
            )
            return result.as_dict()
    except RetentionJobError as exc:
        result = exc.result
        logger.exception(
            "cleanup_archive_job outcome=failed scanned=%s archived=%s "
            "skipped=%s failed=%s duration_ms=%s",
            result.scanned,
            result.archived,
            result.skipped,
            result.failed,
            result.duration_ms,
        )
        raise
    except Exception as exc:
        result = CleanupResult(
            failed=1,
            duration_ms=int((perf_counter() - started) * 1000),
        )
        logger.exception(
            "cleanup_archive_job outcome=failed scanned=0 archived=0 "
            "skipped=0 failed=%s duration_ms=%s",
            result.failed,
            result.duration_ms,
        )
        raise RetentionJobError("automatic archive worker failed", result) from exc
