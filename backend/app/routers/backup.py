import io
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import ApplyPilotBatch, AuditEvent, CsvRow, JobTrack, SavedView, SearchSession, User
from ..services.backups import export_backup_v2

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/backup/export")
def export_backup(
    version: Literal["1", "1.0", "2", "2.0"] = Query("1.0"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export the legacy v1 document by default, or the complete v2 contract on request."""
    if version in {"2", "2.0"}:
        backup = export_backup_v2(db, user.id)
        content = json.dumps(backup, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="jobgrid_backup_v2_{ts}.json"'},
        )

    rows = db.query(CsvRow).filter(CsvRow.user_id == user.id).all()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id).all()
    views = db.query(SavedView).filter(SavedView.user_id == user.id).all()
    sessions = db.query(SearchSession).filter(SearchSession.user_id == user.id).all()
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.user_id == user.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(1000)
        .all()
    )
    batches = db.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user.id).all()
    backup = {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "csv_rows": [
            {
                "url": r.url,
                "company_guess": r.company_guess,
                "title": r.title,
                "ats_group": r.ats_group,
                "search_bucket": r.search_bucket,
                "resume_match_score": r.resume_match_score,
                "jd_text": r.jd_text,
                "sponsorship_status": r.sponsorship_status,
                "location_group": r.location_group,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ],
        "job_tracks": [
            {
                "url": t.url,
                "company": t.company,
                "title": t.title,
                "status": t.status,
                "applied_at": str(t.applied_at) if t.applied_at else None,
                "follow_up_at": str(t.follow_up_at) if t.follow_up_at else None,
                "notes": t.notes,
                "created_at": str(t.created_at) if t.created_at else None,
            }
            for t in tracks
        ],
        "saved_views": [
            {"name": v.name, "view_type": v.view_type, "filters": v.filters, "is_pinned": v.is_pinned}
            for v in views
        ],
        "sessions": [
            {
                "name": s.name,
                "started_at": str(s.started_at) if s.started_at else None,
                "ended_at": str(s.ended_at) if s.ended_at else None,
                "notes": s.notes,
            }
            for s in sessions
        ],
        "audit_events": [
            {
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "metadata_json": e.metadata_json,
                "created_at": str(e.created_at) if e.created_at else None,
            }
            for e in events
        ],
        "applypilot_batches": [
            {
                "name": b.name,
                "payload_json": b.payload_json,
                "status": b.status,
                "job_count": b.job_count,
                "created_at": str(b.created_at) if b.created_at else None,
            }
            for b in batches
        ],
    }
    content = json.dumps(backup, indent=2, default=str).encode("utf-8")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="jobgrid_backup_{ts}.json"'},
    )
