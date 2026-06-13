import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import Float, asc, case, cast, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, JOB_TRACK_STATUS_VALUES, CsvRow, JobTrack, SavedView, SearchSession, User
from ..schemas import BulkFromRowsIn, BulkUpdateIn, JobTrackUpdateIn, SavedViewIn, SessionIn, SessionUpdateIn

router = APIRouter(prefix="/crm", tags=["crm"])
SORT_FIELDS = {"company", "title", "ats_group", "search_bucket", "resume_match_score", "status", "opened_at", "applied_at", "follow_up_at", "created_at", "updated_at"}


def parse_dt(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def num_expr(col):
    cleaned = func.nullif(func.regexp_replace(col, r"[%,$,\s]", "", "g"), "")
    return case((cleaned.op("~")(r"^-?\d+(\.\d+)?$"), cast(cleaned, Float)), else_=None)


def to_out(item):
    return {"id": item.id, "csv_row_id": item.csv_row_id, "url": item.url, "company": item.company, "title": item.title, "ats_group": item.ats_group, "search_bucket": item.search_bucket, "resume_match_score": item.resume_match_score, "status": item.status, "opened_at": item.opened_at, "applied_at": item.applied_at, "follow_up_at": item.follow_up_at, "notes": item.notes, "session_id": item.session_id, "open_count": item.open_count, "last_opened_at": item.last_opened_at, "created_at": item.created_at, "updated_at": item.updated_at}


def upsert_from_row(db, user_id, row, now):
    item = db.query(JobTrack).filter_by(user_id=user_id, url=row.url).first()
    if item:
        item.csv_row_id = row.id
        item.open_count = (item.open_count or 0) + 1
        item.last_opened_at = now
        item.updated_at = now
        item.company = item.company or row.company_guess
        item.title = item.title or row.title
        item.ats_group = item.ats_group or row.ats_group
        item.search_bucket = item.search_bucket or row.search_bucket
        item.resume_match_score = item.resume_match_score or row.resume_match_score
        return item
    item = JobTrack(user_id=user_id, csv_row_id=row.id, url=row.url, company=row.company_guess, title=row.title, ats_group=row.ats_group, search_bucket=row.search_bucket, resume_match_score=row.resume_match_score, status="opened", opened_at=now, last_opened_at=now, open_count=1)
    db.add(item)
    return item


def filtered_query(db, user_id, status=None, company=None, ats_group=None, search_bucket=None, quick_range=None, date_from=None, date_to=None, min_score=None, max_score=None, follow_up_due=False, opened_not_applied=False, q=None):
    query = db.query(JobTrack).filter(JobTrack.user_id == user_id)
    if status:
        query = query.filter(JobTrack.status == status)
    if company:
        query = query.filter(func.lower(JobTrack.company).contains(company.lower()))
    if ats_group:
        query = query.filter(func.lower(JobTrack.ats_group) == ats_group.lower())
    if search_bucket:
        query = query.filter(func.lower(JobTrack.search_bucket) == search_bucket.lower())
    if q:
        needle = q.lower()
        query = query.filter(or_(func.lower(JobTrack.company).contains(needle), func.lower(JobTrack.title).contains(needle), func.lower(JobTrack.url).contains(needle), func.lower(JobTrack.notes).contains(needle)))
    now = datetime.utcnow()
    start = parse_dt(date_from)
    end = parse_dt(date_to)
    if quick_range == "last_24_hours":
        start, end = now - timedelta(hours=24), now
    elif quick_range == "last_7_days":
        start, end = now - timedelta(days=7), now
    elif quick_range == "last_30_days":
        start, end = now - timedelta(days=30), now
    if start:
        query = query.filter(JobTrack.opened_at >= start)
    if end:
        query = query.filter(JobTrack.opened_at < end)
    score = num_expr(JobTrack.resume_match_score)
    if min_score is not None:
        query = query.filter(score >= min_score)
    if max_score is not None:
        query = query.filter(score <= max_score)
    if follow_up_due:
        query = query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now)
    if opened_not_applied:
        query = query.filter(JobTrack.applied_at.is_(None), JobTrack.status == "opened")
    return query


@router.post("/from-row/{row_id}")
def create_from_row(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    now = datetime.utcnow()
    item = upsert_from_row(db, user.id, row, now)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.get("/applications")
def list_apps(status: str | None = Query(None), company: str | None = Query(None), ats_group: str | None = Query(None), search_bucket: str | None = Query(None), quick_range: str | None = Query(None), date_from: str | None = Query(None), date_to: str | None = Query(None), min_score: float | None = Query(None), max_score: float | None = Query(None), follow_up_due: bool = Query(False), opened_not_applied: bool = Query(False), q: str | None = Query(None), sort_by: str = Query("opened_at"), sort_dir: Literal["asc", "desc"] = Query("desc"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = filtered_query(db, user.id, status, company, ats_group, search_bucket, quick_range, date_from, date_to, min_score, max_score, follow_up_due, opened_not_applied, q)
    if sort_by not in SORT_FIELDS:
        sort_by = "opened_at"
    order = asc if sort_dir == "asc" else desc
    sort_col = num_expr(JobTrack.resume_match_score) if sort_by == "resume_match_score" else getattr(JobTrack, sort_by)
    rows = query.order_by(order(sort_col).nullslast(), JobTrack.id.desc()).all()
    options = db.query(JobTrack.ats_group).filter(JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != "").distinct().order_by(JobTrack.ats_group.asc()).all()
    return {"statuses": JOB_TRACK_STATUS_VALUES, "filter_options": {"ats_groups": [x for (x,) in options]}, "rows": [to_out(x) for x in rows]}


@router.patch("/applications/bulk")
def bulk_update_apps(payload: BulkUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(JobTrack).filter(JobTrack.id.in_(payload.ids), JobTrack.user_id == user.id).all()
    now = datetime.utcnow()
    updated = 0
    failed = []
    for item in items:
        data = payload.patch.model_dump(exclude_unset=True)
        for key in ["company", "title", "status", "notes"]:
            if key in data:
                setattr(item, key, data[key])
        if "applied_at" in data:
            item.applied_at = parse_dt(data["applied_at"])
        if "follow_up_at" in data:
            item.follow_up_at = parse_dt(data["follow_up_at"])
        if data.get("mark_applied"):
            item.status = "applied"
            item.applied_at = now
        item.updated_at = now
        updated += 1
    db.commit()
    return {"updated": updated, "failed": failed}


@router.post("/from-rows/bulk")
def bulk_create_from_rows(payload: BulkFromRowsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(CsvRow).filter(CsvRow.id.in_(payload.row_ids), CsvRow.user_id == user.id).all()
    now = datetime.utcnow()
    created = 0
    updated_count = 0
    skipped = 0
    for row in rows:
        existing = db.query(JobTrack).filter_by(user_id=user.id, url=row.url).first()
        if existing:
            existing.csv_row_id = row.id
            existing.open_count = (existing.open_count or 0) + 1
            existing.last_opened_at = now
            existing.updated_at = now
            existing.company = existing.company or row.company_guess
            existing.title = existing.title or row.title
            existing.ats_group = existing.ats_group or row.ats_group
            existing.search_bucket = existing.search_bucket or row.search_bucket
            existing.resume_match_score = existing.resume_match_score or row.resume_match_score
            updated_count += 1
        else:
            item = JobTrack(
                user_id=user.id, csv_row_id=row.id, url=row.url,
                company=row.company_guess, title=row.title,
                ats_group=row.ats_group, search_bucket=row.search_bucket,
                resume_match_score=row.resume_match_score,
                status="opened", opened_at=now, last_opened_at=now, open_count=1,
            )
            db.add(item)
            created += 1
    db.commit()
    return {"created": created, "updated": updated_count, "skipped": skipped}


@router.patch("/applications/{item_id}")
def update_app(item_id: int, payload: JobTrackUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(JobTrack).filter_by(id=item_id, user_id=user.id).first()
    if not item:
        raise HTTPException(404, "Application not found")
    data = payload.model_dump(exclude_unset=True)
    for key in ["company", "title", "status", "notes"]:
        if key in data:
            setattr(item, key, data[key])
    if "applied_at" in data:
        item.applied_at = parse_dt(data["applied_at"])
    if "follow_up_at" in data:
        item.follow_up_at = parse_dt(data["follow_up_at"])
    if data.get("mark_applied"):
        item.status = "applied"
        item.applied_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.get("/stats")
def stats(today_start: str | None = Query(None), today_end: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    start = parse_dt(today_start)
    end = parse_dt(today_end)
    opened_today = query.filter(JobTrack.opened_at.isnot(None))
    applied_today = query.filter(JobTrack.applied_at.isnot(None))
    if start and end:
        opened_today = opened_today.filter(JobTrack.opened_at >= start, JobTrack.opened_at < end)
        applied_today = applied_today.filter(JobTrack.applied_at >= start, JobTrack.applied_at < end)
    now = datetime.utcnow()
    return {"total_opened": query.count(), "total_applied": query.filter(JobTrack.applied_at.isnot(None)).count(), "opened_today": opened_today.count() if start and end else 0, "applied_today": applied_today.count() if start and end else 0, "last_24_hours": query.filter(JobTrack.opened_at >= now - timedelta(hours=24)).count(), "follow_ups_due": query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now).count(), "interviews": query.filter(JobTrack.status == "interview").count(), "rejected": query.filter(JobTrack.status == "rejected").count()}


# ─── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    total_urls = db.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    total_opened = tracks.count()
    total_applied = tracks.filter(JobTrack.applied_at.isnot(None)).count()
    applied_today = tracks.filter(JobTrack.applied_at >= today_start).count()
    applied_7d = tracks.filter(JobTrack.applied_at >= week_start).count()
    opened_not_applied = tracks.filter(JobTrack.applied_at.is_(None), JobTrack.status == "opened").count()
    follow_ups_due = tracks.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now).count()
    interviews = tracks.filter(JobTrack.status == "interview").count()
    rejected = tracks.filter(JobTrack.status == "rejected").count()
    offers = tracks.filter(JobTrack.status == "offer").count()

    by_ats = db.query(JobTrack.ats_group, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != "").group_by(JobTrack.ats_group).order_by(desc(func.count(JobTrack.id))).limit(10).all()
    by_bucket = db.query(JobTrack.search_bucket, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.search_bucket.isnot(None), JobTrack.search_bucket != "").group_by(JobTrack.search_bucket).order_by(desc(func.count(JobTrack.id))).limit(10).all()
    by_status = db.query(JobTrack.status, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id).group_by(JobTrack.status).all()

    applied_scores = tracks.filter(JobTrack.applied_at.isnot(None), JobTrack.resume_match_score.isnot(None), JobTrack.resume_match_score != "").all()
    scores = []
    for t in applied_scores:
        try:
            s = float(str(t.resume_match_score).replace("%", "").replace(",", "").strip())
            scores.append(s)
        except (ValueError, TypeError):
            pass
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    daily = db.query(func.date(JobTrack.applied_at), func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.applied_at.isnot(None), JobTrack.applied_at >= now - timedelta(days=30)).group_by(func.date(JobTrack.applied_at)).order_by(func.date(JobTrack.applied_at)).all()

    top_opened = db.query(JobTrack.company, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.company.isnot(None), JobTrack.company != "").group_by(JobTrack.company).order_by(desc(func.count(JobTrack.id))).limit(10).all()
    top_applied = db.query(JobTrack.company, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.company.isnot(None), JobTrack.company != "", JobTrack.applied_at.isnot(None)).group_by(JobTrack.company).order_by(desc(func.count(JobTrack.id))).limit(10).all()

    return {
        "total_urls": total_urls, "total_opened": total_opened, "total_applied": total_applied,
        "applied_today": applied_today, "applied_7d": applied_7d,
        "opened_not_applied": opened_not_applied, "follow_ups_due": follow_ups_due,
        "interviews": interviews, "rejected": rejected, "offers": offers,
        "avg_applied_score": avg_score,
        "by_ats_group": [{"name": n, "count": c} for n, c in by_ats],
        "by_search_bucket": [{"name": n, "count": c} for n, c in by_bucket],
        "by_status": [{"name": n, "count": c} for n, c in by_status],
        "daily_applied": [{"date": str(d), "count": c} for d, c in daily],
        "top_companies_opened": [{"name": n, "count": c} for n, c in top_opened],
        "top_companies_applied": [{"name": n, "count": c} for n, c in top_applied],
    }


# ─── Saved Views ───────────────────────────────────────────────────────────────

@router.get("/views")
def list_views(view_type: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(SavedView).filter(SavedView.user_id == user.id)
    if view_type:
        query = query.filter(SavedView.view_type == view_type)
    views = query.order_by(SavedView.created_at.desc()).all()
    return [{"id": v.id, "name": v.name, "view_type": v.view_type, "filters": v.filters, "created_at": v.created_at} for v in views]


@router.post("/views")
def create_view(payload: SavedViewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(SavedView).filter_by(user_id=user.id, name=payload.name, view_type=payload.view_type).first()
    if existing:
        existing.filters = payload.filters
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "name": existing.name, "view_type": existing.view_type, "filters": existing.filters, "created_at": existing.created_at}
    view = SavedView(user_id=user.id, name=payload.name, view_type=payload.view_type, filters=payload.filters)
    db.add(view)
    db.commit()
    db.refresh(view)
    return {"id": view.id, "name": view.name, "view_type": view.view_type, "filters": view.filters, "created_at": view.created_at}


@router.delete("/views/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deleted = db.query(SavedView).filter_by(id=view_id, user_id=user.id).delete()
    db.commit()
    return {"deleted": deleted}


# ─── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sessions = db.query(SearchSession).filter(SearchSession.user_id == user.id).order_by(SearchSession.started_at.desc()).all()
    return [{"id": s.id, "name": s.name, "started_at": s.started_at, "ended_at": s.ended_at, "notes": s.notes} for s in sessions]


@router.post("/sessions")
def start_session(payload: SessionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = SearchSession(user_id=user.id, name=payload.name, notes=payload.notes)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "name": session.name, "started_at": session.started_at, "ended_at": session.ended_at, "notes": session.notes}


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(SearchSession).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if payload.notes is not None:
        session.notes = payload.notes
    if payload.end:
        session.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return {"id": session.id, "name": session.name, "started_at": session.started_at, "ended_at": session.ended_at, "notes": session.notes}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deleted = db.query(SearchSession).filter_by(id=session_id, user_id=user.id).delete()
    db.commit()
    return {"deleted": deleted}


# ─── Export ───────────────────────────────────────────────────────────────

EXPORT_DASHBOARD_FIELDS = CSV_COLUMNS + ["clicked", "clicked_at"]
EXPORT_APPLICATION_FIELDS = CSV_COLUMNS + [
    "clicked", "clicked_at",
    "app_status", "applied_at", "follow_up_at", "notes", "last_updated",
]


def _serialize_dashboard_row(row):
    out = {col: getattr(row, col) for col in CSV_COLUMNS}
    out["clicked"] = row.clicked
    out["clicked_at"] = str(row.clicked_at) if row.clicked_at else ""
    return out


def _serialize_application_row(row):
    out = {col: getattr(row.csv_row, col, None) for col in CSV_COLUMNS} if row.csv_row else {col: None for col in CSV_COLUMNS}
    out["url"] = row.url
    out["clicked"] = row.csv_row.clicked if row.csv_row else False
    out["clicked_at"] = str(row.csv_row.clicked_at) if row.csv_row and row.csv_row.clicked_at else ""
    out["app_status"] = row.status
    out["applied_at"] = str(row.applied_at) if row.applied_at else ""
    out["follow_up_at"] = str(row.follow_up_at) if row.follow_up_at else ""
    out["notes"] = row.notes or ""
    out["last_updated"] = str(row.updated_at) if row.updated_at else ""
    return out


def _to_csv_response(rows_dict, filename):
    if not rows_dict:
        return StreamingResponse(io.BytesIO(b""), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows_dict[0].keys()))
    writer.writeheader()
    writer.writerows(rows_dict)
    content = buf.getvalue().encode("utf-8")
    return StreamingResponse(io.BytesIO(content), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _to_json_response(rows_dict, filename):
    content = json.dumps(rows_dict, indent=2, default=str).encode("utf-8")
    return StreamingResponse(io.BytesIO(content), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/export/dashboard")
def export_dashboard(
    format: Literal["csv", "json"] = Query("csv"),
    ats_group: str | None = Query(None),
    row_ids: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(CsvRow).filter(CsvRow.user_id == user.id, CsvRow.archived.is_(False))
    if ats_group:
        query = query.filter(func.lower(CsvRow.ats_group) == ats_group.lower())
    if row_ids:
        id_list = [int(x) for x in row_ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(CsvRow.id.in_(id_list))
    rows = query.order_by(CsvRow.id.desc()).all()
    data = [_serialize_dashboard_row(r) for r in rows]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        return _to_json_response(data, f"dashboard_export_{ts}.json")
    return _to_csv_response(data, f"dashboard_export_{ts}.csv")


@router.get("/export/applications")
def export_applications(
    format: Literal["csv", "json"] = Query("csv"),
    status: str | None = Query(None),
    company: str | None = Query(None),
    ats_group: str | None = Query(None),
    search_bucket: str | None = Query(None),
    follow_up_due: bool = Query(False),
    opened_not_applied: bool = Query(False),
    q: str | None = Query(None),
    row_ids: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = filtered_query(db, user.id, status, company, ats_group, search_bucket, None, None, None, None, None, follow_up_due, opened_not_applied, q)
    if row_ids:
        id_list = [int(x) for x in row_ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(JobTrack.id.in_(id_list))
    rows = query.order_by(JobTrack.id.desc()).all()
    data = [_serialize_application_row(r) for r in rows]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        return _to_json_response(data, f"applications_export_{ts}.json")
    return _to_csv_response(data, f"applications_export_{ts}.csv")
