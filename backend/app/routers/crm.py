import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import Float, asc, case, cast, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, JOB_TRACK_STATUS_VALUES, ApplyPilotBatch, AuditEvent, CsvRow, JobTrack, SavedView, SearchSession, User, UserGoal
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..schemas import ApplyPilotResultIn, BulkFromRowsIn, BulkUpdateIn, JobTrackUpdateIn, SavedViewIn, SessionIn, SessionUpdateIn

router = APIRouter(prefix="/crm", tags=["crm"])
SORT_FIELDS = {"company", "title", "ats_group", "search_bucket", "resume_match_score", "status", "opened_at", "applied_at", "follow_up_at", "created_at", "updated_at", "priority_score", "triage"}


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
    return {"id": item.id, "csv_row_id": item.csv_row_id, "url": item.url, "company": item.company, "title": item.title, "ats_group": item.ats_group, "search_bucket": item.search_bucket, "resume_match_score": item.resume_match_score, "status": item.status, "opened_at": item.opened_at, "applied_at": item.applied_at, "follow_up_at": item.follow_up_at, "notes": item.notes, "session_id": item.session_id, "open_count": item.open_count, "last_opened_at": item.last_opened_at, "created_at": item.created_at, "updated_at": item.updated_at, "is_duplicate": getattr(item, 'is_duplicate', False), "duplicate_of_id": getattr(item, 'duplicate_of_id', None)}


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


def emit_event(db, user_id, event_type, entity_type, entity_id=None, metadata=None, session_id=None):
    try:
        if session_id is None:
            active = db.query(SearchSession).filter(
                SearchSession.user_id == user_id, SearchSession.ended_at.is_(None)
            ).first()
            session_id = active.id if active else None
        event = AuditEvent(
            user_id=user_id, session_id=session_id,
            event_type=event_type, entity_type=entity_type,
            entity_id=entity_id, metadata_json=metadata or {},
        )
        db.add(event)
    except Exception:
        pass


DEFAULT_SAVED_VIEWS = [
    {"name": "High score unopened", "view_type": "job_links", "filters": {"openedOnly": False}},
    {"name": "Opened not applied", "view_type": "applications", "filters": {"openedNotApplied": True}},
    {"name": "Follow-ups due", "view_type": "applications", "filters": {"followUpDue": True}},
    {"name": "Applied this week", "view_type": "applications", "filters": {"quickRange": "last_7_days", "status": "applied"}},
    {"name": "Greenhouse only", "view_type": "job_links", "filters": {"atsGroup": "greenhouse"}},
    {"name": "Sponsorship positive", "view_type": "job_links", "filters": {"sponsorshipStatus": "positive"}},
    {"name": "Sponsorship unclear", "view_type": "job_links", "filters": {"sponsorshipStatus": "unclear"}},
    {"name": "JD missing", "view_type": "job_links", "filters": {"jdMissing": True}},
    {"name": "Errors only", "view_type": "job_links", "filters": {"hasError": True}},
]


def _parse_score(value):
    try:
        return float(str(value or "0").replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def calculate_priority_score(row, track=None):
    try:
        score = 0.0
        resume_score = _parse_score(getattr(row, 'resume_match_score', None) or "0")
        score += resume_score * 0.4
        if getattr(row, 'sponsorship_status', None) == "positive":
            score += 15
        elif getattr(row, 'sponsorship_status', None) == "unclear":
            score += 5
        elif getattr(row, 'sponsorship_status', None) == "negative":
            score -= 10
        loc = (getattr(row, 'location_group', None) or "").lower()
        if "remote" in loc and "restricted" not in loc:
            score += 10
        elif "onsite" in loc or "hybrid" in loc:
            score += 5
        try:
            age = float(getattr(row, 'posted_age_days', None) or "999")
            if age <= 7:
                score += 15
            elif age <= 14:
                score += 10
            elif age <= 30:
                score += 5
            else:
                score -= 5
        except (ValueError, TypeError):
            pass
        if getattr(row, 'is_duplicate', False):
            score -= 20
        jd_len = _parse_score(getattr(row, 'jd_text_length', None))
        if jd_len == 0 or not getattr(row, 'jd_text', None):
            score -= 10
        if track:
            if track.status == "rejected":
                score -= 25
            if track.follow_up_at and hasattr(track.follow_up_at, 'timestamp') and track.follow_up_at < datetime.utcnow():
                score += 5
        return max(0, min(100, round(score, 1)))
    except Exception:
        return 0


def calculate_triage(row, track=None, priority_score=0):
    try:
        if getattr(row, 'is_duplicate', False):
            return "skip"
        if getattr(row, 'sponsorship_status', None) == "negative":
            return "skip"
        if track and track.status == "rejected":
            return "skip"
        jd_len = _parse_score(getattr(row, 'jd_text_length', None))
        if jd_len == 0 or not getattr(row, 'jd_text', None):
            return "needs_review"
        if getattr(row, 'error', None):
            return "needs_review"
        try:
            age = float(getattr(row, 'posted_age_days', None) or "999")
            if age > 60:
                return "skip"
        except (ValueError, TypeError):
            pass
        if priority_score >= 70:
            return "apply_now"
        elif priority_score >= 40:
            return "maybe"
        else:
            return "skip"
    except Exception:
        return "needs_review"


def generate_job_summary(row):
    jd = row.jd_text or ""
    if len(jd) < 50:
        return {"summary": "No JD text available", "matched_skills": [], "missing_skills": [], "bullets": [], "outreach": "", "risks": ["Missing job description"]}
    sentences = [s.strip() for s in jd.replace("\n", " ").split(".") if len(s.strip()) > 10]
    summary = ". ".join(sentences[:3]) + "." if sentences else "No summary available"
    tech_keywords = ["python", "javascript", "typescript", "react", "node", "aws", "docker", "kubernetes", "sql", "postgresql", "fastapi", "django", "flask", "java", "go", "rust", "c++", "machine learning", "ai", "data", "analytics", "devops", "ci/cd", "git", "rest", "graphql", "microservices", "agile", "scrum"]
    found = [kw for kw in tech_keywords if kw.lower() in jd.lower()]
    return {
        "summary": summary[:500],
        "matched_skills": found[:10],
        "missing_skills": [],
        "bullets": [f"Experience with {skill}" for skill in found[:3]],
        "outreach": f"Hi, I'm interested in the {row.title or 'open'} role at {row.company_guess or 'your company'}.",
        "risks": [] if jd_len > 200 else ["Short JD"],
    }


def generate_resume_checklist(row):
    jd = row.jd_text or ""
    tech_keywords = ["python", "javascript", "typescript", "react", "node", "aws", "docker", "kubernetes", "sql", "postgresql", "fastapi", "django", "flask", "java", "go", "rust", "c++", "machine learning", "ai", "data", "analytics", "devops", "ci/cd", "git", "rest", "graphql", "microservices", "agile", "scrum"]
    required = [kw for kw in tech_keywords if kw.lower() in jd.lower()]
    return {
        "required_skills": required[:15],
        "found_in_resume": [],
        "missing_skills": required[:5],
        "suggested_bullets": [f"Highlight experience with {skill}" for skill in required[:3]],
        "suggested_project": f"Emphasize a project using {required[0]}" if required else "Add a relevant project",
    }


def filtered_query(db, user_id, status=None, company=None, ats_group=None, search_bucket=None, quick_range=None, date_from=None, date_to=None, min_score=None, max_score=None, follow_up_due=False, opened_not_applied=False, q=None,
                   location_group=None, decision=None, sponsorship_status=None, posted_age_min=None, posted_age_max=None,
                   follow_up_today=False, follow_up_overdue=False, follow_up_none=False, has_error=False, jd_missing=False,
                   date_applied_from=None, date_applied_to=None, applied_only=False):
    query = db.query(JobTrack).filter(JobTrack.user_id == user_id)
    if status:
        query = query.filter(JobTrack.status == status)
    if company:
        query = query.filter(func.lower(JobTrack.company).contains(company.lower()))
    if ats_group:
        query = query.filter(func.lower(JobTrack.ats_group) == ats_group.lower())
    if search_bucket:
        query = query.filter(func.lower(JobTrack.search_bucket) == search_bucket.lower())
    if location_group:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(func.lower(CsvRow.location_group) == location_group.lower())
    if decision:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(func.lower(CsvRow.decision) == decision.lower())
    if sponsorship_status:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(func.lower(CsvRow.sponsorship_status) == sponsorship_status.lower())
    if has_error:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(CsvRow.error.isnot(None), CsvRow.error != "")
    if jd_missing:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter((CsvRow.jd_text_length.is_(None)) | (CsvRow.jd_text_length == "") | (CsvRow.jd_text_length == "0"))
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
    elif quick_range == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = today_start, today_start + timedelta(days=1)
    elif quick_range == "yesterday":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = today_start - timedelta(days=1), today_start
    if start:
        query = query.filter(JobTrack.opened_at >= start)
    if end:
        query = query.filter(JobTrack.opened_at < end)
    if posted_age_min is not None:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(num_expr(CsvRow.posted_age_days) >= posted_age_min)
    if posted_age_max is not None:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True).filter(num_expr(CsvRow.posted_age_days) <= posted_age_max)
    score = num_expr(JobTrack.resume_match_score)
    if min_score is not None:
        query = query.filter(score >= min_score)
    if max_score is not None:
        query = query.filter(score <= max_score)
    if follow_up_due:
        query = query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now)
    if follow_up_today:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        query = query.filter(JobTrack.follow_up_at >= today_start, JobTrack.follow_up_at < today_end)
    if follow_up_overdue:
        query = query.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at < now)
    if follow_up_none:
        query = query.filter(JobTrack.follow_up_at.is_(None))
    if opened_not_applied:
        query = query.filter(JobTrack.applied_at.is_(None), JobTrack.status == "opened")
    if applied_only:
        query = query.filter(JobTrack.applied_at.isnot(None))
    if date_applied_from:
        applied_start = parse_dt(date_applied_from)
        if applied_start:
            query = query.filter(JobTrack.applied_at >= applied_start)
    if date_applied_to:
        applied_end = parse_dt(date_applied_to)
        if applied_end:
            query = query.filter(JobTrack.applied_at < applied_end)
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
def list_apps(status: str | None = Query(None), company: str | None = Query(None), ats_group: str | None = Query(None), search_bucket: str | None = Query(None), quick_range: str | None = Query(None), date_from: str | None = Query(None), date_to: str | None = Query(None), min_score: float | None = Query(None), max_score: float | None = Query(None), follow_up_due: bool = Query(False), opened_not_applied: bool = Query(False), q: str | None = Query(None), sort_by: str = Query("opened_at"), sort_dir: Literal["asc", "desc"] = Query("desc"),
              location_group: str | None = Query(None), decision: str | None = Query(None), sponsorship_status: str | None = Query(None), posted_age_min: float | None = Query(None), posted_age_max: float | None = Query(None),
              follow_up_today: bool = Query(False), follow_up_overdue: bool = Query(False), follow_up_none: bool = Query(False), has_error: bool = Query(False), jd_missing: bool = Query(False),
              date_applied_from: str | None = Query(None), date_applied_to: str | None = Query(None), applied_only: bool = Query(False),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = filtered_query(db, user.id, status, company, ats_group, search_bucket, quick_range, date_from, date_to, min_score, max_score, follow_up_due, opened_not_applied, q,
                           location_group, decision, sponsorship_status, posted_age_min, posted_age_max,
                           follow_up_today, follow_up_overdue, follow_up_none, has_error, jd_missing,
                           date_applied_from, date_applied_to, applied_only)
    total = query.count()
    if sort_by not in SORT_FIELDS:
        sort_by = "opened_at"
    sort_by_is_computed = sort_by in ("priority_score", "triage")
    order = asc if sort_dir == "asc" else desc
    if not sort_by_is_computed:
        sort_col = num_expr(JobTrack.resume_match_score) if sort_by == "resume_match_score" else getattr(JobTrack, sort_by)

    total_count = query.count()

    if sort_by_is_computed:
        rows = query.order_by(JobTrack.id.desc()).all()
    else:
        rows = query.order_by(order(sort_col).nullslast(), JobTrack.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    options = db.query(JobTrack.ats_group).filter(JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != "").distinct().order_by(JobTrack.ats_group.asc()).all()
    location_options = db.query(CsvRow.location_group).join(JobTrack, JobTrack.csv_row_id == CsvRow.id).filter(JobTrack.user_id == user.id, CsvRow.location_group.isnot(None), CsvRow.location_group != "").distinct().order_by(CsvRow.location_group.asc()).all()
    decision_options = db.query(CsvRow.decision).join(JobTrack, JobTrack.csv_row_id == CsvRow.id).filter(JobTrack.user_id == user.id, CsvRow.decision.isnot(None), CsvRow.decision != "").distinct().order_by(CsvRow.decision.asc()).all()
    sponsorship_options = db.query(CsvRow.sponsorship_status).join(JobTrack, JobTrack.csv_row_id == CsvRow.id).filter(JobTrack.user_id == user.id, CsvRow.sponsorship_status.isnot(None), CsvRow.sponsorship_status != "").distinct().order_by(CsvRow.sponsorship_status.asc()).all()

    row_out = []
    for track in rows:
        out = to_out(track)
        csv_row = track.csv_row if hasattr(track, 'csv_row') and track.csv_row else (db.query(CsvRow).filter_by(id=track.csv_row_id).first() if track.csv_row_id else None)
        if csv_row:
            ps = calculate_priority_score(csv_row, track)
            out["priority_score"] = ps
            out["triage"] = calculate_triage(csv_row, track, ps)
        else:
            out["priority_score"] = 0
            out["triage"] = "needs_review"
        row_out.append(out)

    if sort_by_is_computed:
        row_out.sort(key=lambda x: x.get(sort_by) or 0, reverse=(sort_dir == "desc"))
        row_out = row_out[(page - 1) * page_size: page * page_size]

    return {
        "statuses": JOB_TRACK_STATUS_VALUES,
        "filter_options": {"ats_groups": [x for (x,) in options], "location_groups": [x for (x,) in location_options], "decisions": [x for (x,) in decision_options], "sponsorship_statuses": [x for (x,) in sponsorship_options]},
        "rows": row_out,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total_count,
    }


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
    emit_event(db, user.id, "row_sent_to_applications", "bulk", metadata={"count": created + updated_count})
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


@router.get("/analytics/funnel")
def funnel_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    uploaded = db.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    opened = tracks.count()
    sent_to_apps = tracks.filter(JobTrack.csv_row_id.isnot(None)).count()
    applied = tracks.filter(JobTrack.applied_at.isnot(None)).count()
    interview = tracks.filter(JobTrack.status == "interview").count()
    offer = tracks.filter(JobTrack.status == "offer").count()
    rejected = tracks.filter(JobTrack.status == "rejected").count()
    return {
        "stages": [
            {"name": "Uploaded", "count": uploaded},
            {"name": "Opened", "count": opened},
            {"name": "Sent to Applications", "count": sent_to_apps},
            {"name": "Applied", "count": applied},
            {"name": "Interview", "count": interview},
            {"name": "Offer", "count": offer},
        ],
        "rates": {
            "open_rate": round(opened / uploaded * 100, 1) if uploaded else 0,
            "application_rate": round(applied / opened * 100, 1) if opened else 0,
            "interview_rate": round(interview / applied * 100, 1) if applied else 0,
            "rejection_rate": round(rejected / applied * 100, 1) if applied else 0,
        },
    }


@router.get("/analytics/ats")
def ats_performance(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ats_groups = db.query(JobTrack.ats_group).filter(
        JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != ""
    ).distinct().all()
    result = []
    for (ats,) in ats_groups:
        tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id, JobTrack.ats_group == ats)
        total = tracks.count()
        applied = tracks.filter(JobTrack.applied_at.isnot(None)).count()
        interview = tracks.filter(JobTrack.status == "interview").count()
        rejected = tracks.filter(JobTrack.status == "rejected").count()
        scores = []
        for t in tracks.filter(JobTrack.resume_match_score.isnot(None), JobTrack.resume_match_score != "").all():
            try:
                scores.append(float(str(t.resume_match_score).replace("%", "").replace(",", "").strip()))
            except (ValueError, TypeError):
                pass
        result.append({
            "name": ats, "total": total, "applied": applied,
            "interviews": interview, "rejections": rejected,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        })
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


@router.get("/analytics/buckets")
def bucket_performance(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    buckets = db.query(JobTrack.search_bucket).filter(
        JobTrack.user_id == user.id, JobTrack.search_bucket.isnot(None), JobTrack.search_bucket != ""
    ).distinct().all()
    result = []
    for (bucket,) in buckets:
        tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id, JobTrack.search_bucket == bucket)
        total = tracks.count()
        applied = tracks.filter(JobTrack.applied_at.isnot(None)).count()
        interview = tracks.filter(JobTrack.status == "interview").count()
        opened_not_applied = tracks.filter(JobTrack.applied_at.is_(None), JobTrack.status == "opened").count()
        scores = []
        for t in tracks.filter(JobTrack.resume_match_score.isnot(None), JobTrack.resume_match_score != "").all():
            try:
                scores.append(float(str(t.resume_match_score).replace("%", "").replace(",", "").strip()))
            except (ValueError, TypeError):
                pass
        result.append({
            "name": bucket, "total": total, "applied": applied,
            "interviews": interview, "opened_not_applied": opened_not_applied,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        })
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


@router.get("/goals")
def get_goals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = db.query(UserGoal).filter_by(user_id=user.id).first()
    if not goal:
        return {"open_per_day": 30, "apply_per_day": 10, "followup_per_day": 5, "applypilot_per_day": 5}
    return {"open_per_day": goal.open_per_day, "apply_per_day": goal.apply_per_day, "followup_per_day": goal.followup_per_day, "applypilot_per_day": goal.applypilot_per_day}


@router.put("/goals")
def update_goals(open_per_day: int = Query(30), apply_per_day: int = Query(10), followup_per_day: int = Query(5), applypilot_per_day: int = Query(5), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = db.query(UserGoal).filter_by(user_id=user.id).first()
    if goal:
        goal.open_per_day = open_per_day
        goal.apply_per_day = apply_per_day
        goal.followup_per_day = followup_per_day
        goal.applypilot_per_day = applypilot_per_day
    else:
        goal = UserGoal(user_id=user.id, open_per_day=open_per_day, apply_per_day=apply_per_day, followup_per_day=followup_per_day, applypilot_per_day=applypilot_per_day)
        db.add(goal)
    db.commit()
    return {"open_per_day": goal.open_per_day, "apply_per_day": goal.apply_per_day, "followup_per_day": goal.followup_per_day, "applypilot_per_day": goal.applypilot_per_day}


@router.get("/analytics/goals")
def goal_progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = db.query(UserGoal).filter_by(user_id=user.id).first()
    if not goal:
        goal = UserGoal(user_id=user.id)
        db.add(goal)
        db.commit()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    opened_today = db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.event_type == "row_opened", AuditEvent.created_at >= today_start).count()
    applied_today = db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.event_type == "application_marked_applied", AuditEvent.created_at >= today_start).count()
    followups_today = db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.event_type == "followup_set", AuditEvent.created_at >= today_start).count()
    exports_today = db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.event_type == "applypilot_batch_exported", AuditEvent.created_at >= today_start).count()
    return {
        "goals": {"open_per_day": goal.open_per_day, "apply_per_day": goal.apply_per_day, "followup_per_day": goal.followup_per_day, "applypilot_per_day": goal.applypilot_per_day},
        "today": {"opened": opened_today, "applied": applied_today, "followups": followups_today, "exports": exports_today},
    }


@router.get("/analytics/weekly")
def weekly_report(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    week_start = now - timedelta(days=7)
    uploaded = db.query(CsvRow).filter(CsvRow.user_id == user.id, CsvRow.created_at >= week_start).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    opened = tracks.filter(JobTrack.opened_at >= week_start).count()
    applied = tracks.filter(JobTrack.applied_at >= week_start).count()
    interviews = tracks.filter(JobTrack.status == "interview", JobTrack.updated_at >= week_start).count()
    followups = db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.event_type == "followup_set", AuditEvent.created_at >= week_start).count()
    top_companies = db.query(JobTrack.company, func.count(JobTrack.id)).filter(
        JobTrack.user_id == user.id, JobTrack.company.isnot(None), JobTrack.company != "",
        JobTrack.created_at >= week_start
    ).group_by(JobTrack.company).order_by(desc(func.count(JobTrack.id))).limit(5).all()
    next_followups = tracks.filter(
        JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at >= now,
        JobTrack.follow_up_at <= now + timedelta(days=7)
    ).order_by(JobTrack.follow_up_at.asc()).limit(10).all()
    return {
        "uploaded": uploaded, "opened": opened, "applied": applied,
        "interviews": interviews, "followups_completed": followups,
        "top_companies": [{"name": n, "count": c} for n, c in top_companies],
        "upcoming_followups": [{"id": t.id, "company": t.company, "title": t.title, "follow_up_at": str(t.follow_up_at)} for t in next_followups],
    }


# ─── Saved Views ───────────────────────────────────────────────────────────────

@router.get("/views")
def list_views(view_type: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(SavedView).filter(SavedView.user_id == user.id)
    if view_type:
        query = query.filter(SavedView.view_type == view_type)
    views = query.order_by(SavedView.is_pinned.desc(), SavedView.created_at.desc()).all()
    return [{"id": v.id, "name": v.name, "view_type": v.view_type, "filters": v.filters, "is_pinned": v.is_pinned, "created_at": v.created_at} for v in views]


@router.post("/views")
def create_view(payload: SavedViewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(SavedView).filter_by(user_id=user.id, name=payload.name, view_type=payload.view_type).first()
    if existing:
        existing.filters = payload.filters
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "name": existing.name, "view_type": existing.view_type, "filters": existing.filters, "is_pinned": existing.is_pinned, "created_at": existing.created_at}
    view = SavedView(user_id=user.id, name=payload.name, view_type=payload.view_type, filters=payload.filters)
    db.add(view)
    db.commit()
    db.refresh(view)
    return {"id": view.id, "name": view.name, "view_type": view.view_type, "filters": view.filters, "is_pinned": view.is_pinned, "created_at": view.created_at}


@router.delete("/views/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deleted = db.query(SavedView).filter_by(id=view_id, user_id=user.id).delete()
    db.commit()
    return {"deleted": deleted}


@router.put("/views/{view_id}/pin")
def toggle_pin_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    view = db.query(SavedView).filter_by(id=view_id, user_id=user.id).first()
    if not view:
        raise HTTPException(404, "View not found")
    view.is_pinned = not view.is_pinned
    db.commit()
    db.refresh(view)
    return {"id": view.id, "is_pinned": view.is_pinned}


@router.post("/views/duplicate/{view_id}")
def duplicate_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    original = db.query(SavedView).filter_by(id=view_id, user_id=user.id).first()
    if not original:
        raise HTTPException(404, "View not found")
    new_view = SavedView(
        user_id=user.id, name=f"{original.name} (copy)",
        view_type=original.view_type, filters=original.filters,
    )
    db.add(new_view)
    db.commit()
    db.refresh(new_view)
    return {"id": new_view.id, "name": new_view.name, "view_type": new_view.view_type, "filters": new_view.filters, "is_pinned": new_view.is_pinned, "created_at": new_view.created_at}


@router.post("/views/defaults")
def create_default_views(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    created = 0
    for v in DEFAULT_SAVED_VIEWS:
        existing = db.query(SavedView).filter_by(user_id=user.id, name=v["name"], view_type=v["view_type"]).first()
        if not existing:
            view = SavedView(user_id=user.id, **v)
            db.add(view)
            created += 1
    db.commit()
    return {"created": created}


@router.get("/views/{view_id}")
def get_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    view = db.query(SavedView).filter_by(id=view_id, user_id=user.id).first()
    if not view:
        raise HTTPException(404, "View not found")
    return {"id": view.id, "name": view.name, "view_type": view.view_type, "filters": view.filters, "is_pinned": view.is_pinned, "created_at": view.created_at}


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


@router.get("/sessions/active")
def get_active_session(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(SearchSession).filter(
        SearchSession.user_id == user.id, SearchSession.ended_at.is_(None)
    ).order_by(SearchSession.started_at.desc()).first()
    if not session:
        return None
    from sqlalchemy import func as sa_func
    stats = {
        "uploads_count": db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.session_id == session.id, AuditEvent.event_type == "csv_uploaded").count(),
        "urls_opened": db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.session_id == session.id, AuditEvent.event_type == "row_opened").count(),
        "sent_to_applications": db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.session_id == session.id, AuditEvent.event_type == "row_sent_to_applications").count(),
        "applications_marked_applied": db.query(AuditEvent).filter(AuditEvent.user_id == user.id, AuditEvent.session_id == session.id, AuditEvent.event_type == "application_marked_applied").count(),
    }
    return {"id": session.id, "name": session.name, "started_at": session.started_at, "ended_at": session.ended_at, "notes": session.notes, "stats": stats}


@router.get("/audit")
def list_audit_events(event_type: str | None = Query(None), session_id: int | None = Query(None), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(AuditEvent).filter(AuditEvent.user_id == user.id)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    if session_id:
        query = query.filter(AuditEvent.session_id == session_id)
    events = query.order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [{"id": e.id, "event_type": e.event_type, "entity_type": e.entity_type, "entity_id": e.entity_id, "metadata_json": e.metadata_json, "session_id": e.session_id, "created_at": e.created_at} for e in events]


# ─── ApplyPilot Batches ─────────────────────────────────────────────────

def _serialize_for_applypilot(row):
    return {
        "job_id": row.job_id_guess or "",
        "company": row.company_guess or "",
        "title": row.title or "",
        "url": row.url or "",
        "ats_group": row.ats_group or "",
        "search_bucket": row.search_bucket or "",
        "resume_match_score": row.resume_match_score or "",
        "jd_text": row.jd_text or "",
        "sponsorship_status": row.sponsorship_status or "",
        "location_group": row.location_group or "",
        "posted_age_days": row.posted_age_days or "",
    }


def _calculate_readiness(row):
    checks = {
        "url_present": bool(row.url),
        "jd_text_present": bool(row.jd_text and len(row.jd_text) > 50),
        "company_present": bool(row.company_guess),
        "title_present": bool(row.title),
        "location_acceptable": row.location_group not in ["remote_restricted", "unknown"] if row.location_group else True,
        "sponsorship_acceptable": row.sponsorship_status not in ["negative"] if row.sponsorship_status else True,
        "resume_score_high": False,
        "not_duplicate": not row.is_duplicate,
    }
    try:
        score = float(str(row.resume_match_score or "0").replace("%", "").replace(",", "").strip())
        checks["resume_score_high"] = score >= 70
    except (ValueError, TypeError):
        pass
    passed = sum(checks.values())
    total = len(checks)
    if passed == total:
        return "ready"
    elif passed >= total * 0.6:
        return "needs_review"
    else:
        return "do_not_send"


@router.post("/applypilot/batches")
def create_applypilot_batch(row_ids: list[int], name: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(CsvRow).filter(CsvRow.id.in_(row_ids), CsvRow.user_id == user.id).all()
    if not rows:
        raise HTTPException(404, "No rows found")
    payload = [_serialize_for_applypilot(r) for r in rows]
    batch = ApplyPilotBatch(
        user_id=user.id,
        name=name or f"Batch {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        payload_json=payload,
        status="downloaded",
        job_count=len(payload),
    )
    db.add(batch)
    emit_event(db, user.id, "applypilot_batch_exported", "applypilot_batch", metadata={"job_count": len(payload)})
    db.commit()
    db.refresh(batch)
    return {"batch_id": batch.id, "name": batch.name, "status": batch.status, "job_count": batch.job_count}


@router.get("/applypilot/batches")
def list_applypilot_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batches = db.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user.id).order_by(ApplyPilotBatch.created_at.desc()).all()
    return [{"id": b.id, "name": b.name, "status": b.status, "job_count": b.job_count, "created_at": b.created_at, "updated_at": b.updated_at} for b in batches]


@router.get("/applypilot/batches/{batch_id}")
def get_applypilot_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.query(ApplyPilotBatch).filter_by(id=batch_id, user_id=user.id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    return {"id": batch.id, "name": batch.name, "status": batch.status, "job_count": batch.job_count, "payload_json": batch.payload_json, "created_at": batch.created_at}


@router.delete("/applypilot/batches/{batch_id}")
def delete_applypilot_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deleted = db.query(ApplyPilotBatch).filter_by(id=batch_id, user_id=user.id).delete()
    db.commit()
    return {"deleted": deleted}


@router.get("/applypilot/batches/{batch_id}/download")
def download_applypilot_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.query(ApplyPilotBatch).filter_by(id=batch_id, user_id=user.id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    content = json.dumps(batch.payload_json, indent=2).encode("utf-8")
    return StreamingResponse(io.BytesIO(content), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{batch.name}.json"'})


@router.post("/applypilot/import")
def import_applypilot_results(results: list[ApplyPilotResultIn], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    updated = 0
    for result in results:
        track = db.query(JobTrack).filter_by(user_id=user.id, url=result.url).first()
        if track:
            if result.submitted:
                track.status = "applied"
                track.applied_at = parse_dt(result.submitted_at) or datetime.utcnow()
            if result.error:
                track.notes = f"ApplyPilot error: {result.error}"
            track.updated_at = datetime.utcnow()
            updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/applypilot/readiness/{row_id}")
def get_applypilot_readiness(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    return {"row_id": row.id, "readiness": _calculate_readiness(row)}


# ─── Intelligence Layer ────────────────────────────────────────────────

@router.get("/intelligence/priority/{row_id}")
def get_priority_score(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    track = db.query(JobTrack).filter_by(user_id=user.id, csv_row_id=row.id).first()
    score = calculate_priority_score(row, track)
    triage = calculate_triage(row, track, score)
    return {"row_id": row.id, "priority_score": score, "triage": triage}


@router.get("/intelligence/summary/{row_id}")
def get_job_summary(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    summary = generate_job_summary(row)
    return {"row_id": row.id, "summary": summary}


@router.get("/intelligence/checklist/{row_id}")
def get_resume_checklist(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    checklist = generate_resume_checklist(row)
    return {"row_id": row.id, "checklist": checklist}


@router.get("/intelligence/batch")
def batch_intelligence(row_ids: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = [int(x) for x in row_ids.split(",") if x.strip().isdigit()]
    rows = db.query(CsvRow).filter(CsvRow.id.in_(ids), CsvRow.user_id == user.id).all()
    results = []
    for row in rows:
        track = db.query(JobTrack).filter_by(user_id=user.id, csv_row_id=row.id).first()
        score = calculate_priority_score(row, track)
        triage = calculate_triage(row, track, score)
        results.append({"row_id": row.id, "priority_score": score, "triage": triage, "url": row.url, "company": row.company_guess, "title": row.title})
    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


# ─── Follow-Up Presets ───────────────────────────────────────────────────

def _next_weekday(target_weekday):
    now = datetime.utcnow()
    days_ahead = target_weekday - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


@router.post("/applications/{item_id}/follow-up")
def set_follow_up_preset(item_id: int, preset: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(JobTrack).filter_by(id=item_id, user_id=user.id).first()
    if not item:
        raise HTTPException(404, "Application not found")
    now = datetime.utcnow()
    if preset == "3_days":
        item.follow_up_at = now + timedelta(days=3)
    elif preset == "7_days":
        item.follow_up_at = now + timedelta(days=7)
    elif preset == "next_monday":
        item.follow_up_at = _next_weekday(0)
    elif preset == "clear":
        item.follow_up_at = None
    else:
        raise HTTPException(400, "Invalid preset. Use: 3_days, 7_days, next_monday, clear")
    item.updated_at = now
    emit_event(db, user.id, "followup_set", "job_track", entity_id=item.id, metadata={"preset": preset})
    db.commit()
    db.refresh(item)
    return to_out(item)


# ─── Duplicate Management ────────────────────────────────────────────────

@router.post("/applications/{item_id}/mark-duplicate")
def mark_duplicate(item_id: int, duplicate_of_id: int | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(CsvRow).filter_by(id=item_id, user_id=user.id).first()
    if not item:
        raise HTTPException(404, "Row not found")
    if duplicate_of_id is not None:
        original = db.query(CsvRow).filter_by(id=duplicate_of_id, user_id=user.id).first()
        if not original:
            raise HTTPException(404, "Original row not found")
        item.is_duplicate = True
        item.duplicate_of_id = duplicate_of_id
    else:
        item.is_duplicate = not item.is_duplicate
        if not item.is_duplicate:
            item.duplicate_of_id = None
    db.commit()
    return {"id": item.id, "is_duplicate": item.is_duplicate, "duplicate_of_id": item.duplicate_of_id}


# ─── Duplicate Review ─────────────────────────────────────────────────

@router.get("/duplicates")
def list_duplicates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dupes = db.query(CsvRow).filter(CsvRow.user_id == user.id, CsvRow.is_duplicate.is_(True)).order_by(CsvRow.created_at.desc()).all()
    results = []
    for d in dupes:
        original = db.query(CsvRow).filter_by(id=d.duplicate_of_id).first() if d.duplicate_of_id else None
        reason = "unknown"
        if original:
            if d.url == original.url:
                reason = "same_url"
            elif d.canonical_company_job_key and d.canonical_company_job_key == original.canonical_company_job_key:
                reason = "same_canonical_key"
            elif d.company_guess == original.company_guess and d.title == original.title:
                reason = "same_company_title"
            elif d.job_id_guess and d.job_id_guess == original.job_id_guess:
                reason = "same_job_id"
        results.append({
            "id": d.id, "url": d.url, "company": d.company_guess, "title": d.title,
            "duplicate_of_id": d.duplicate_of_id, "reason": reason,
            "original_url": original.url if original else None,
            "original_company": original.company_guess if original else None,
        })
    return results


@router.post("/duplicates/{row_id}/resolve")
def resolve_duplicate(row_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    action = payload.get("action", "keep_both")
    if action == "mark_duplicate":
        row.is_duplicate = True
    elif action == "keep_both":
        row.is_duplicate = False
        row.duplicate_of_id = None
    elif action == "ignore_rule":
        row.is_duplicate = False
        row.duplicate_of_id = None
    db.commit()
    return {"id": row.id, "is_duplicate": row.is_duplicate, "action": action}


@router.post("/duplicates/merge")
def merge_duplicates(primary_id: int, duplicate_ids: list[int], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    primary = db.query(CsvRow).filter_by(id=primary_id, user_id=user.id).first()
    if not primary:
        raise HTTPException(404, "Primary row not found")
    for dup_id in duplicate_ids:
        dup = db.query(CsvRow).filter_by(id=dup_id, user_id=user.id).first()
        if dup:
            dup.is_duplicate = True
            dup.duplicate_of_id = primary_id
    db.commit()
    return {"merged": len(duplicate_ids), "primary_id": primary_id}


# ─── Company History ──────────────────────────────────────────────────

@router.get("/companies/{company}")
def company_history(company: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id, func.lower(JobTrack.company) == company.lower()).all()
    rows = []
    for t in tracks:
        rows.append({
            "track_id": t.id, "url": t.url, "title": t.title, "status": t.status,
            "opened_at": str(t.opened_at) if t.opened_at else None,
            "applied_at": str(t.applied_at) if t.applied_at else None,
            "follow_up_at": str(t.follow_up_at) if t.follow_up_at else None,
            "notes": t.notes, "ats_group": t.ats_group,
        })
    return {
        "company": company, "total": len(rows),
        "opened": len(rows), "applied": sum(1 for r in rows if r["applied_at"]),
        "interviews": sum(1 for r in rows if r["status"] == "interview"),
        "rejected": sum(1 for r in rows if r["status"] == "rejected"),
        "followups_due": sum(1 for r in rows if r["follow_up_at"]),
        "roles": rows,
    }


# ─── Backup / Restore ────────────────────────────────────────────────

@router.get("/backup/export")
def export_backup(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(CsvRow).filter(CsvRow.user_id == user.id).all()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id).all()
    views = db.query(SavedView).filter(SavedView.user_id == user.id).all()
    sessions = db.query(SearchSession).filter(SearchSession.user_id == user.id).all()
    events = db.query(AuditEvent).filter(AuditEvent.user_id == user.id).order_by(AuditEvent.created_at.desc()).limit(1000).all()
    batches = db.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user.id).all()
    backup = {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "csv_rows": [{"url": r.url, "company_guess": r.company_guess, "title": r.title, "ats_group": r.ats_group, "search_bucket": r.search_bucket, "resume_match_score": r.resume_match_score, "jd_text": r.jd_text, "sponsorship_status": r.sponsorship_status, "location_group": r.location_group, "created_at": str(r.created_at) if r.created_at else None} for r in rows],
        "job_tracks": [{"url": t.url, "company": t.company, "title": t.title, "status": t.status, "applied_at": str(t.applied_at) if t.applied_at else None, "follow_up_at": str(t.follow_up_at) if t.follow_up_at else None, "notes": t.notes, "created_at": str(t.created_at) if t.created_at else None} for t in tracks],
        "saved_views": [{"name": v.name, "view_type": v.view_type, "filters": v.filters, "is_pinned": v.is_pinned} for v in views],
        "sessions": [{"name": s.name, "started_at": str(s.started_at) if s.started_at else None, "ended_at": str(s.ended_at) if s.ended_at else None, "notes": s.notes} for s in sessions],
        "audit_events": [{"event_type": e.event_type, "entity_type": e.entity_type, "entity_id": e.entity_id, "metadata_json": e.metadata_json, "created_at": str(e.created_at) if e.created_at else None} for e in events],
        "applypilot_batches": [{"name": b.name, "payload_json": b.payload_json, "status": b.status, "job_count": b.job_count, "created_at": str(b.created_at) if b.created_at else None} for b in batches],
    }
    content = json.dumps(backup, indent=2, default=str).encode("utf-8")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(io.BytesIO(content), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="jobgrid_backup_{ts}.json"'})


@router.post("/backup/import")
def import_backup(db: Session = Depends(get_db), user: User = Depends(get_current_user), file: UploadFile = File(...)):
    content = file.file.read()
    backup = json.loads(content)
    imported = {"csv_rows": 0, "job_tracks": 0, "saved_views": 0, "sessions": 0}
    for r in backup.get("csv_rows", []):
        existing = db.query(CsvRow).filter_by(user_id=user.id, url=r.get("url")).first()
        if not existing:
            row = CsvRow(user_id=user.id, upload_batch_id="import", url=r.get("url", ""), company_guess=r.get("company_guess"), title=r.get("title"), ats_group=r.get("ats_group"), search_bucket=r.get("search_bucket"), resume_match_score=r.get("resume_match_score"), jd_text=r.get("jd_text"), sponsorship_status=r.get("sponsorship_status"), location_group=r.get("location_group"))
            db.add(row)
            imported["csv_rows"] += 1
    for v in backup.get("saved_views", []):
        existing = db.query(SavedView).filter_by(user_id=user.id, name=v.get("name"), view_type=v.get("view_type")).first()
        if not existing:
            view = SavedView(user_id=user.id, name=v.get("name"), view_type=v.get("view_type", "job_links"), filters=v.get("filters", {}), is_pinned=v.get("is_pinned", False))
            db.add(view)
            imported["saved_views"] += 1
    db.commit()
    return imported


# ─── Import External Applications ──────────────────────────────────────

@router.post("/import/external")
def import_external_applications(payload: list[dict], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    created = 0
    for item in payload:
        url = item.get("url", "")
        if not url:
            continue
        existing = db.query(JobTrack).filter_by(user_id=user.id, url=url).first()
        if existing:
            continue
        track = JobTrack(
            user_id=user.id, url=url,
            company=item.get("company", ""),
            title=item.get("title", ""),
            status=item.get("status", "opened"),
            notes=item.get("notes", ""),
            opened_at=datetime.utcnow(),
        )
        if item.get("applied_at"):
            track.applied_at = parse_dt(item["applied_at"])
            track.status = "applied"
        if item.get("follow_up_at"):
            track.follow_up_at = parse_dt(item["follow_up_at"])
        db.add(track)
        created += 1
    db.commit()
    return {"created": created}


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
    emit_event(db, user.id, "rows_exported", "dashboard", metadata={"count": len(data), "format": format})
    db.commit()
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
    emit_event(db, user.id, "rows_exported", "applications", metadata={"count": len(data), "format": format})
    db.commit()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        return _to_json_response(data, f"applications_export_{ts}.json")
    return _to_csv_response(data, f"applications_export_{ts}.csv")
