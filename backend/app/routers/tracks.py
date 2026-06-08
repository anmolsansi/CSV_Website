from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CsvRow, JobTrack, User
from ..schemas import JobTrackUpdateIn

router = APIRouter(prefix="/tracks", tags=["tracks"])

STATUSES = ["opened", "submitted", "follow_up", "interview", "rejected", "offer", "not_pursuing"]
SORT_FIELDS = ["company", "title", "status", "opened_at", "submitted_at", "follow_up_at", "created_at", "updated_at"]


def parse_date(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def out(track):
    return {
        "id": track.id,
        "csv_row_id": track.csv_row_id,
        "url": track.url,
        "company": track.company,
        "title": track.title,
        "ats_group": track.ats_group,
        "search_bucket": track.search_bucket,
        "resume_match_score": track.resume_match_score,
        "status": track.status,
        "opened_at": track.opened_at,
        "submitted_at": track.submitted_at,
        "follow_up_at": track.follow_up_at,
        "notes": track.notes,
        "open_count": track.open_count,
        "last_opened_at": track.last_opened_at,
        "created_at": track.created_at,
        "updated_at": track.updated_at,
    }


def create_or_update_track(db, user_id, row, now):
    track = db.query(JobTrack).filter_by(user_id=user_id, url=row.url).first()
    if track:
        track.csv_row_id = row.id
        track.open_count = (track.open_count or 0) + 1
        track.last_opened_at = now
        track.updated_at = now
        if not track.company:
            track.company = row.company_guess
        if not track.title:
            track.title = row.title
        return track

    track = JobTrack(
        user_id=user_id,
        csv_row_id=row.id,
        url=row.url,
        company=row.company_guess,
        title=row.title,
        ats_group=row.ats_group,
        search_bucket=row.search_bucket,
        resume_match_score=row.resume_match_score,
        status="opened",
        opened_at=now,
        last_opened_at=now,
        open_count=1,
    )
    db.add(track)
    return track


@router.get("")
def list_tracks(
    status: str | None = Query(None),
    company: str | None = Query(None),
    ats_group: str | None = Query(None),
    quick_range: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    q: str | None = Query(None),
    sort_by: str = Query("opened_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    due_only: bool = Query(False),
    opened_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    if status:
        query = query.filter(JobTrack.status == status)
    if company:
        query = query.filter(func.lower(JobTrack.company).contains(company.lower()))
    if ats_group:
        query = query.filter(func.lower(JobTrack.ats_group) == ats_group.lower())
    if q:
        needle = q.lower()
        query = query.filter(or_(func.lower(JobTrack.company).contains(needle), func.lower(JobTrack.title).contains(needle), func.lower(JobTrack.url).contains(needle)))

    now = datetime.utcnow()
    start = parse_date(date_from)
    end = parse_date(date_to)
    if quick_range == "last_24_hours":
        start = now - timedelta(hours=24)
        end = now
    elif quick_range == "last_7_days":
        start = now - timedelta(days=7)
        end = now
    elif quick_range == "last_30_days":
        start = now - timedelta(days=30)
        end = now
    if start:
        query = query.filter(JobTrack.opened_at >= start)
    if end:
        query = query.filter(JobTrack.opened_at < end)
    if due_only:
        query = query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now)
    if opened_only:
        query = query.filter(JobTrack.submitted_at.is_(None), JobTrack.status == "opened")

    if sort_by not in SORT_FIELDS:
        sort_by = "opened_at"
    order = asc if sort_dir == "asc" else desc
    rows = query.order_by(order(getattr(JobTrack, sort_by)).nullslast(), JobTrack.id.desc()).all()
    opts = db.query(JobTrack.ats_group).filter(JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != "").distinct().order_by(JobTrack.ats_group.asc()).all()
    return {"statuses": STATUSES, "filter_options": {"ats_groups": [x for (x,) in opts]}, "rows": [out(row) for row in rows]}


@router.get("/stats")
def stats(today_start: str | None = Query(None), today_end: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    start = parse_date(today_start)
    end = parse_date(today_end)
    opened_today = query.filter(JobTrack.opened_at.isnot(None))
    submitted_today = query.filter(JobTrack.submitted_at.isnot(None))
    if start and end:
        opened_today = opened_today.filter(JobTrack.opened_at >= start, JobTrack.opened_at < end)
        submitted_today = submitted_today.filter(JobTrack.submitted_at >= start, JobTrack.submitted_at < end)
    now = datetime.utcnow()
    return {
        "total_opened": query.count(),
        "total_submitted": query.filter(JobTrack.submitted_at.isnot(None)).count(),
        "opened_today": opened_today.count() if start and end else 0,
        "submitted_today": submitted_today.count() if start and end else 0,
        "last_24_hours": query.filter(JobTrack.opened_at >= now - timedelta(hours=24)).count(),
        "follow_ups_due": query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now).count(),
        "interviews": query.filter(JobTrack.status == "interview").count(),
        "rejected": query.filter(JobTrack.status == "rejected").count(),
    }


@router.patch("/{track_id}")
def update_track(track_id: int, payload: JobTrackUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    track = db.query(JobTrack).filter_by(id=track_id, user_id=user.id).first()
    if not track:
        raise HTTPException(404, "Record not found")
    data = payload.model_dump(exclude_unset=True)
    now = datetime.utcnow()
    for key in ["company", "title", "status", "notes"]:
        if key in data:
            setattr(track, key, data[key])
    if "submitted_at" in data:
        track.submitted_at = parse_date(data["submitted_at"])
    if "follow_up_at" in data:
        track.follow_up_at = parse_date(data["follow_up_at"])
    if data.get("mark_submitted"):
        track.status = "submitted"
        track.submitted_at = now
    track.updated_at = now
    db.commit()
    db.refresh(track)
    return out(track)


@router.delete("/{track_id}")
def delete_track(track_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deleted = db.query(JobTrack).filter_by(id=track_id, user_id=user.id).delete()
    db.commit()
    return {"deleted": deleted}
