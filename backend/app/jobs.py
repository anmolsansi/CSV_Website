import logging
from datetime import datetime, timedelta, timezone

from .config import settings
from .database import SessionLocal
from .models import CsvRow

logger = logging.getLogger(__name__)


def cleanup_clicked_rows() -> int:
    """Archive old rows and delete very old ones.

    - Rows older than DELETE_AFTER_DAYS are soft-archived (hidden from default queries).
    - Rows archived for 7+ days are hard-deleted.

    Returns the number of rows affected.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        archive_cutoff = now - timedelta(days=settings.DELETE_AFTER_DAYS)
        delete_cutoff = now - timedelta(days=settings.DELETE_AFTER_DAYS + 7)

        # Hard-delete rows that have been archived for 7+ days
        deleted = (
            db.query(CsvRow)
            .filter(
                CsvRow.archived.is_(True),
                CsvRow.updated_at < delete_cutoff,
            )
            .delete(synchronize_session=False)
        )

        # Soft-archive rows older than DELETE_AFTER_DAYS (not yet archived)
        archived = (
            db.query(CsvRow)
            .filter(
                CsvRow.archived.is_(False),
                CsvRow.created_at < archive_cutoff,
            )
            .update(
                {CsvRow.archived: True},
                synchronize_session=False,
            )
        )

        db.commit()
        total = deleted + archived
        if total > 0:
            logger.info("Cleanup: archived=%d, deleted=%d", archived, deleted)
        return total
    except Exception:
        db.rollback()
        logger.exception("Cleanup job failed")
        return 0
    finally:
        db.close()
