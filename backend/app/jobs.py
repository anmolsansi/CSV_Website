from datetime import datetime, timedelta

from .config import settings
from .database import SessionLocal
from .models import CsvRow


def cleanup_clicked_rows() -> int:
    """Hard-delete rows that were clicked more than DELETE_AFTER_DAYS ago."""
    cutoff = datetime.utcnow() - timedelta(days=settings.DELETE_AFTER_DAYS)
    db = SessionLocal()
    try:
        deleted = (
            db.query(CsvRow)
            .filter(CsvRow.clicked_at.isnot(None), CsvRow.clicked_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted
    finally:
        db.close()
