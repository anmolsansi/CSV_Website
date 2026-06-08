from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, asc, case, cast, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import JOB_TRACK_STATUS_VALUES, CsvRow, JobTrack, SavedView, SearchSession, User
from ..schemas import JobTrackUpdateIn, SavedViewIn, SessionIn, SessionUpdateIn

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
