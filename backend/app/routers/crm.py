import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import CSV_COLUMNS, JOB_TRACK_STATUS_VALUES, ApplyPilotBatch, AuditEvent, CompanyAlias, CsvRow, JobLifecycleEvent, JobTrack, SavedView, SearchSession, User, UserGoal
from ..scoring import _parse_score, priority_score as scoring_priority_score, improved_triage as scoring_triage, skills_extraction
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..schemas import ApplyPilotResultIn, BulkFromRowsIn, BulkUpdateIn, JobTrackUpdateIn, SavedViewIn, SessionIn, SessionUpdateIn
from ..services.capture import transfer_capture_notes
from ..services.job_identity import (
    JobIdentityError,
    apply_persisted_job_identity,
    canonicalize_job_url,
    normalize_company_alias_key,
)
from ..services.lifecycle import (
    LifecycleEventError,
    apply_job_track_changes,
    coerce_operation_id,
    count_visited_without_applied,
    local_day_utc_bounds,
    metric_counts,
    rolling_week_utc_bounds,
    validate_timezone_name,
)
from ..services.numeric_values import numeric_text_expression
from ..services.row_queries import (
    ApplicationQuery,
    RowQuery,
    build_application_query,
    build_row_query,
    order_application_query,
    order_row_query,
    resolve_row_sort_column,
)
from ..services.reminders import sync_track_reminder, sync_user_reminders
from ..services.retention import (
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    count_eligible_rows,
    maintenance_health,
)
from ..services.validation import (
    ValidationContractError,
    explicit_model_fields,
    legacy_invalid_application_counts,
    normalize_bulk_ids,
    parse_timestamp,
    prepare_job_track_patch,
    require_owned_bulk_ids,
    validate_job_url,
    validate_status,
    validate_text_limits,
)

router = APIRouter(prefix="/crm", tags=["crm"])
logger = logging.getLogger(__name__)
SORT_FIELDS = {"company", "title", "ats_group", "search_bucket", "resume_match_score", "status", "opened_at", "applied_at", "follow_up_at", "created_at", "updated_at", "priority_score", "triage"}


def parse_dt(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _request_operation_id(value: str | None) -> UUID:
    try:
        return coerce_operation_id(value)
    except LifecycleEventError as exc:
        raise HTTPException(400, exc.message) from exc


def _log_lifecycle_outcome(
    *,
    action: str,
    operation_id: UUID,
    outcome: str,
    affected: int,
    started: float,
    warning: bool = False,
):
    log = logger.warning if warning else logger.info
    log(
        "lifecycle_mutation action=%s operation_id=%s outcome=%s affected=%s elapsed_ms=%s",
        action,
        operation_id,
        outcome,
        affected,
        int((perf_counter() - started) * 1000),
    )


def _raise_lifecycle_http(
    db: Session,
    exc: LifecycleEventError,
    *,
    action: str,
    operation_id: UUID,
    affected: int,
    started: float,
):
    db.rollback()
    if exc.code == "event_key_conflict":
        status_code = 409
    elif exc.code in {"inaccessible_csv_row", "inaccessible_job_track"}:
        status_code = 404
    else:
        status_code = 400
    _log_lifecycle_outcome(
        action=action,
        operation_id=operation_id,
        outcome=exc.code,
        affected=affected,
        started=started,
        warning=True,
    )
    raise HTTPException(status_code, exc.message) from exc


def _raise_validation_http(
    db: Session,
    exc: ValidationContractError,
    *,
    action: str,
    operation_id: UUID,
    started: float,
):
    db.rollback()
    _log_lifecycle_outcome(
        action=action,
        operation_id=operation_id,
        outcome=exc.code,
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def _raise_integrity_http(
    db: Session,
    exc: IntegrityError,
    *,
    action: str,
    operation_id: UUID,
    started: float,
):
    db.rollback()
    _log_lifecycle_outcome(
        action=action,
        operation_id=operation_id,
        outcome="conflict",
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "conflict",
            "fields": [
                {
                    "field": "__root__",
                    "message": "The application changed concurrently. Reload and retry.",
                }
            ],
            "request_id": str(operation_id),
        },
    ) from exc


def _raise_unexpected_http(
    db: Session,
    exc: Exception,
    *,
    action: str,
    operation_id: UUID,
    started: float,
):
    db.rollback()
    logger.exception(
        "application_mutation action=%s operation_id=%s outcome=internal_error affected=0 elapsed_ms=%s",
        action,
        operation_id,
        int((perf_counter() - started) * 1000),
    )
    raise HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "fields": [
                {"field": "__root__", "message": "The request could not be completed."}
            ],
            "request_id": str(operation_id),
        },
    ) from exc


def _prepare_application_patch(
    payload: JobTrackUpdateIn,
    *,
    user: User,
    item: JobTrack,
) -> dict:
    return prepare_job_track_patch(
        explicit_model_fields(payload),
        timezone_name=user.timezone,
        current_status=item.status,
        current_applied_at=item.applied_at,
    )


def _validate_row_application_seed(row: CsvRow) -> None:
    validate_job_url(row.url, field="url")
    validate_text_limits(
        {
            "company": row.company_guess,
            "title": row.title,
        }
    )


def _apply_track_patch(
    db: Session,
    *,
    user_id: int,
    item: JobTrack,
    data: dict,
    source: str,
    operation_id: UUID,
    now: datetime,
):
    for key in ["company", "title", "notes"]:
        if key in data:
            setattr(item, key, data[key])

    lifecycle_kwargs = {}
    for key in ["status", "applied_at", "follow_up_at", "mark_applied"]:
        if key in data:
            lifecycle_kwargs[key] = data[key]

    apply_job_track_changes(
        db,
        user_id=user_id,
        item=item,
        source=source,
        operation_id=operation_id,
        now=now,
        **lifecycle_kwargs,
    )
    apply_persisted_job_identity(item)
    if "follow_up_at" in lifecycle_kwargs or "status" in lifecycle_kwargs:
        sync_track_reminder(
            db,
            user_id=user_id,
            track_id=item.id,
            now_utc=now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now,
        )


def num_expr(col):
    """Compatibility wrapper around the shared text-backed numeric adapter."""

    return numeric_text_expression(col)


def to_out(item):
    return {"id": item.id, "csv_row_id": item.csv_row_id, "url": item.url, "company": item.company, "title": item.title, "ats_group": item.ats_group, "search_bucket": item.search_bucket, "resume_match_score": item.resume_match_score, "status": item.status, "opened_at": item.opened_at, "applied_at": item.applied_at, "follow_up_at": item.follow_up_at, "notes": item.notes, "session_id": item.session_id, "open_count": item.open_count, "last_opened_at": item.last_opened_at, "created_at": item.created_at, "updated_at": item.updated_at, "is_duplicate": getattr(item, 'is_duplicate', False), "duplicate_of_id": getattr(item, 'duplicate_of_id', None)}


def upsert_from_row(db, user_id, row, now):
    apply_persisted_job_identity(row)
    item = db.query(JobTrack).filter_by(user_id=user_id, url=row.url).first()
    if item:
        apply_persisted_job_identity(item)
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
    apply_persisted_job_identity(item)
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
    return scoring_priority_score(row, track)


def calculate_triage(row, track=None, priority_score=0):
    return scoring_triage(row, track, score=priority_score)


def generate_job_summary(row):
    jd = row.jd_text or ""
    if len(jd) < 50:
        return {"summary": "No JD text available", "matched_skills": [], "missing_skills": [], "bullets": [], "outreach": "", "risks": ["Missing job description"]}
    sentences = [s.strip() for s in jd.replace("\n", " ").split(".") if len(s.strip()) > 10]
    summary = ". ".join(sentences[:3]) + "." if sentences else "No summary available"
    extracted = skills_extraction(jd)
    found = extracted["all_matched"]
    return {
        "summary": summary[:500],
        "matched_skills": found[:10],
        "missing_skills": [],
        "bullets": [f"Experience with {skill}" for skill in found[:3]],
        "outreach": f"Hi, I'm interested in the {row.title or 'open'} role at {row.company_guess or 'your company'}.",
        "risks": [] if len(jd) > 200 else ["Short JD"],
    }


def generate_resume_checklist(row):
    jd = row.jd_text or ""
    extracted = skills_extraction(jd)
    required = extracted["all_matched"]
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
    """Compatibility wrapper for callers migrated in later R2 tickets."""
    params = ApplicationQuery(
        status=status, company=company, ats_group=ats_group, search_bucket=search_bucket,
        quick_range=quick_range, date_from=date_from, date_to=date_to,
        min_score=min_score, max_score=max_score, follow_up_due=follow_up_due,
        opened_not_applied=opened_not_applied, q=q, location_group=location_group,
        decision=decision, sponsorship_status=sponsorship_status,
        posted_age_min=posted_age_min, posted_age_max=posted_age_max,
        follow_up_today=follow_up_today, follow_up_overdue=follow_up_overdue,
        follow_up_none=follow_up_none, has_error=has_error, jd_missing=jd_missing,
        date_applied_from=date_applied_from, date_applied_to=date_applied_to,
        applied_only=applied_only,
    )
    return build_application_query(
        db, user_id, params, numeric_expression=num_expr, parse_datetime=parse_dt
    )

@router.post("/from-row/{row_id}")
def create_from_row(
    row_id: int,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
        if not row:
            raise HTTPException(404, "Row not found")
        _validate_row_application_seed(row)
        item = upsert_from_row(db, user.id, row, datetime.utcnow())
        db.commit()
        db.refresh(item)
        _log_lifecycle_outcome(
            action="from_row",
            operation_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
        response = to_out(item)
        warning_context = _find_application_matches(
            db,
            user_id=user.id,
            url=row.url,
            company=row.company_guess,
            title=row.title,
        )
        response["warning_candidates"] = warning_context["matches"]
        return response
    except ValidationContractError as exc:
        _raise_validation_http(
            db, exc, action="from_row", operation_id=operation_id, started=started
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db, exc, action="from_row", operation_id=operation_id, started=started
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db, exc, action="from_row", operation_id=operation_id, started=started
        )


@router.get("/applications")
def list_apps(status: str | None = Query(None), company: str | None = Query(None), ats_group: str | None = Query(None), search_bucket: str | None = Query(None), quick_range: str | None = Query(None), date_from: str | None = Query(None), date_to: str | None = Query(None), min_score: float | None = Query(None), max_score: float | None = Query(None), follow_up_due: bool = Query(False), opened_not_applied: bool = Query(False), q: str | None = Query(None), sort_by: str = Query("opened_at"), sort_dir: Literal["asc", "desc"] = Query("desc"),
              location_group: str | None = Query(None), decision: str | None = Query(None), sponsorship_status: str | None = Query(None), posted_age_min: float | None = Query(None), posted_age_max: float | None = Query(None),
              follow_up_today: bool = Query(False), follow_up_overdue: bool = Query(False), follow_up_none: bool = Query(False), has_error: bool = Query(False), jd_missing: bool = Query(False),
              date_applied_from: str | None = Query(None), date_applied_to: str | None = Query(None), applied_only: bool = Query(False),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if sort_by not in SORT_FIELDS:
        sort_by = "opened_at"
    query_params = ApplicationQuery(
        status=status, company=company, ats_group=ats_group, search_bucket=search_bucket,
        quick_range=quick_range, date_from=date_from, date_to=date_to,
        min_score=min_score, max_score=max_score, follow_up_due=follow_up_due,
        opened_not_applied=opened_not_applied, q=q, location_group=location_group,
        decision=decision, sponsorship_status=sponsorship_status,
        posted_age_min=posted_age_min, posted_age_max=posted_age_max,
        follow_up_today=follow_up_today, follow_up_overdue=follow_up_overdue,
        follow_up_none=follow_up_none, has_error=has_error, jd_missing=jd_missing,
        date_applied_from=date_applied_from, date_applied_to=date_applied_to,
        applied_only=applied_only, sort_by=sort_by, sort_dir=sort_dir,
    )
    query = build_application_query(
        db, user.id, query_params, numeric_expression=num_expr, parse_datetime=parse_dt
    )
    total_count = query.count()
    sort_by_is_computed = sort_by in ("priority_score", "triage")
    if sort_by_is_computed:
        rows = query.order_by(JobTrack.id.desc()).all()
    else:
        rows = (
            order_application_query(query, query_params, num_expr)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

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


@router.get("/applications/validation-report")
def application_validation_report(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {
        "counts": legacy_invalid_application_counts(db, user_id=user.id),
        "repair_mode": "manual_only",
    }


@router.patch("/applications/bulk")
def bulk_update_apps(
    payload: BulkUpdateIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        normalized = normalize_bulk_ids(payload.ids, field="ids")
        items = (
            db.query(JobTrack)
            .filter(JobTrack.id.in_(normalized.ids), JobTrack.user_id == user.id)
            .all()
        )
        by_id = {item.id: item for item in items}
        require_owned_bulk_ids(normalized, by_id, field="ids")
        ordered_items = [by_id[item_id] for item_id in normalized.ids]

        prepared = [
            (item, _prepare_application_patch(payload.patch, user=user, item=item))
            for item in ordered_items
        ]
        now = datetime.utcnow()
        for item, data in prepared:
            _apply_track_patch(
                db,
                user_id=user.id,
                item=item,
                data=data,
                source="bulk_patch",
                operation_id=operation_id,
                now=now,
            )
        db.commit()
        _log_lifecycle_outcome(
            action="bulk_patch",
            operation_id=operation_id,
            outcome="success",
            affected=len(ordered_items),
            started=started,
        )
        return {"updated": len(ordered_items), "failed": []}
    except ValidationContractError as exc:
        _raise_validation_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="bulk_patch",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )


@router.post("/from-rows/bulk")
def bulk_create_from_rows(
    payload: BulkFromRowsIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        normalized = normalize_bulk_ids(payload.row_ids, field="row_ids")
        rows = (
            db.query(CsvRow)
            .filter(CsvRow.id.in_(normalized.ids), CsvRow.user_id == user.id)
            .all()
        )
        by_id = {row.id: row for row in rows}
        require_owned_bulk_ids(normalized, by_id, field="row_ids")
        ordered_rows = [by_id[row_id] for row_id in normalized.ids]

        status_supplied = "status" in payload.model_fields_set
        target_status = validate_status(payload.status) if status_supplied else None
        for row in ordered_rows:
            _validate_row_application_seed(row)

        now = datetime.utcnow()
        existing_tracks = {
            item.url: item
            for item in (
                db.query(JobTrack)
                .filter(
                    JobTrack.user_id == user.id,
                    JobTrack.url.in_([row.url for row in ordered_rows]),
                )
                .all()
            )
        }
        created = 0
        items = []
        for row in ordered_rows:
            apply_persisted_job_identity(row)
            item = existing_tracks.get(row.url)
            if item is None:
                item = JobTrack(
                    user_id=user.id,
                    url=row.url,
                    status="opened",
                    opened_at=row.clicked_at,
                    last_opened_at=row.clicked_at,
                    open_count=1 if row.clicked else 0,
                )
                apply_persisted_job_identity(item)
                db.add(item)
                db.flush()
                existing_tracks[row.url] = item
                created += 1
            else:
                apply_persisted_job_identity(item)
            item.csv_row_id = row.id
            item.notes = transfer_capture_notes(
                item.notes,
                row.capture_notes,
                append=payload.capture_notes_mode == "append",
            )
            for field, source_field in [
                ("company", "company_guess"),
                ("title", "title"),
                ("ats_group", "ats_group"),
                ("search_bucket", "search_bucket"),
                ("resume_match_score", "resume_match_score"),
            ]:
                setattr(item, field, getattr(item, field) or getattr(row, source_field))
            if status_supplied:
                apply_job_track_changes(
                    db,
                    user_id=user.id,
                    item=item,
                    source="bulk_from_rows",
                    operation_id=operation_id,
                    now=now,
                    status=target_status,
                )
            else:
                item.updated_at = now
            items.append(item)

        emit_event(
            db,
            user.id,
            "row_sent_to_applications",
            "bulk",
            metadata={"count": len(items)},
        )
        db.flush()
        application_ids = [item.id for item in items]
        db.commit()
        _log_lifecycle_outcome(
            action="bulk_from_rows",
            operation_id=operation_id,
            outcome="success",
            affected=len(items),
            started=started,
        )
        return {
            "created": created,
            "updated": len(items) - created,
            "skipped": 0,
            "application_ids": application_ids,
        }
    except ValidationContractError as exc:
        _raise_validation_http(
            db,
            exc,
            action="bulk_from_rows",
            operation_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="bulk_from_rows",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db,
            exc,
            action="bulk_from_rows",
            operation_id=operation_id,
            started=started,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db,
            exc,
            action="bulk_from_rows",
            operation_id=operation_id,
            started=started,
        )


@router.patch("/applications/{item_id}")
def update_app(
    item_id: int,
    payload: JobTrackUpdateIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        item = db.query(JobTrack).filter_by(id=item_id, user_id=user.id).first()
        if not item:
            raise HTTPException(404, "Application not found")

        data = _prepare_application_patch(payload, user=user, item=item)
        _apply_track_patch(
            db,
            user_id=user.id,
            item=item,
            data=data,
            source="application_patch",
            operation_id=operation_id,
            now=datetime.utcnow(),
        )
        db.commit()
        db.refresh(item)
        _log_lifecycle_outcome(
            action="application_patch",
            operation_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return to_out(item)
    except ValidationContractError as exc:
        _raise_validation_http(
            db,
            exc,
            action="application_patch",
            operation_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="application_patch",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db,
            exc,
            action="application_patch",
            operation_id=operation_id,
            started=started,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db,
            exc,
            action="application_patch",
            operation_id=operation_id,
            started=started,
        )


def _retention_profile_response(db: Session, user: User) -> dict:
    archive_after_days = int(user.retention_days or 0)
    return {
        "archive_after_days": archive_after_days,
        "eligible_row_count": count_eligible_rows(
            db,
            user_id=user.id,
            retention_days=archive_after_days,
        ),
        "maintenance": maintenance_health(
            db,
            auto_archive_enabled=settings.AUTO_ARCHIVE_AFTER_DAYS > 0,
            cleanup_interval_minutes=settings.CLEANUP_INTERVAL_MINUTES,
        ),
        "purge_available": False,
        "archived_rows_ui_available": False,
        "recovery_message": (
            "Archived rows are preserved. Until JG-062 ships recovery requires "
            "the existing API/operator workflow."
        ),
    }


@router.get("/profile/retention")
def get_profile_retention(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the saved policy, read-only eligibility preview, and safe health."""
    return _retention_profile_response(db, user)


@router.patch("/profile/retention")
def update_profile_retention(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if set(payload) != {"archive_after_days"}:
        raise HTTPException(
            422,
            "Request body must contain exactly one field: archive_after_days.",
        )

    value = payload.get("archive_after_days")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or (value != 0 and not MIN_RETENTION_DAYS <= value <= MAX_RETENTION_DAYS)
    ):
        raise HTTPException(
            422,
            "archive_after_days must be 0 (disabled) or between 7 and 3650 days.",
        )

    user.retention_days = value
    db.commit()
    db.refresh(user)
    return _retention_profile_response(db, user)


@router.get("/profile/timezone")
def get_profile_timezone(
    user: User = Depends(get_current_user),
):
    return {"timezone": validate_timezone_name(user.timezone)}


@router.patch("/profile/timezone")
def update_profile_timezone(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if set(payload) != {"timezone"}:
        raise HTTPException(
            422,
            "Request body must contain exactly one field: timezone.",
        )
    try:
        timezone_name = validate_timezone_name(payload.get("timezone"))
    except LifecycleEventError as exc:
        raise HTTPException(422, exc.message) from exc

    user.timezone = timezone_name
    sync_user_reminders(
        db,
        user_id=user.id,
        now_utc=datetime.now(timezone.utc),
    )
    db.commit()
    db.refresh(user)
    return {"timezone": user.timezone}


@router.get("/stats")
def stats(today_start: str | None = Query(None), today_end: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    start = parse_dt(today_start)
    end = parse_dt(today_end)
    lifetime_metrics = metric_counts(db, user_id=user.id)
    today_metrics = (
        metric_counts(db, user_id=user.id, start=start, end=end)
        if start and end
        else {"visited": 0, "applied": 0}
    )
    now = datetime.utcnow()
    last_24_hours = metric_counts(
        db,
        user_id=user.id,
        start=now - timedelta(hours=24),
        end=now,
    )["visited"]
    return {
        "total_opened": lifetime_metrics["visited"],
        "total_saved": lifetime_metrics["saved"],
        "total_applied": lifetime_metrics["applied"],
        "opened_today": today_metrics["visited"],
        "applied_today": today_metrics["applied"],
        "last_24_hours": last_24_hours,
        "follow_ups_due": tracks.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now).count(),
        "interviews": tracks.filter(JobTrack.status == "interview").count(),
        "rejected": tracks.filter(JobTrack.status == "rejected").count(),
    }
# ─── Analytics

# ─── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    today_start, today_end = local_day_utc_bounds(user.timezone, reference=now)
    week_start, week_end = rolling_week_utc_bounds(user.timezone, reference=now)

    total_urls = db.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    lifetime_metrics = metric_counts(db, user_id=user.id)
    today_metrics = metric_counts(
        db, user_id=user.id, start=today_start, end=today_end
    )
    week_metrics = metric_counts(
        db, user_id=user.id, start=week_start, end=week_end
    )
    total_opened = lifetime_metrics["visited"]
    total_saved = lifetime_metrics["saved"]
    total_applied = lifetime_metrics["applied"]
    applied_today = today_metrics["applied"]
    applied_7d = week_metrics["applied"]
    opened_not_applied = count_visited_without_applied(db, user_id=user.id)
    follow_ups_due = tracks.filter(JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at <= now).count()
    interviews = tracks.filter(JobTrack.status == "interview").count()
    rejected = tracks.filter(JobTrack.status == "rejected").count()
    offers = tracks.filter(JobTrack.status == "offer").count()

    by_ats = db.query(JobTrack.ats_group, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.ats_group.isnot(None), JobTrack.ats_group != "").group_by(JobTrack.ats_group).order_by(desc(func.count(JobTrack.id))).limit(10).all()
    by_bucket = db.query(JobTrack.search_bucket, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id, JobTrack.search_bucket.isnot(None), JobTrack.search_bucket != "").group_by(JobTrack.search_bucket).order_by(desc(func.count(JobTrack.id))).limit(10).all()
    by_status = db.query(JobTrack.status, func.count(JobTrack.id)).filter(JobTrack.user_id == user.id).group_by(JobTrack.status).all()

    applied_scores = (
        db.query(JobTrack)
        .join(JobLifecycleEvent, JobLifecycleEvent.job_track_id == JobTrack.id)
        .filter(
            JobTrack.user_id == user.id,
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind == "first_applied",
            JobTrack.resume_match_score.isnot(None),
            JobTrack.resume_match_score != "",
        )
        .all()
    )
    scores = []
    for t in applied_scores:
        try:
            s = float(str(t.resume_match_score).replace("%", "").replace(",", "").strip())
            scores.append(s)
        except (ValueError, TypeError):
            pass
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    daily = (
        db.query(func.date(JobLifecycleEvent.occurred_at), func.count(JobLifecycleEvent.id))
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind == "first_applied",
            JobLifecycleEvent.occurred_at >= now - timedelta(days=30),
        )
        .group_by(func.date(JobLifecycleEvent.occurred_at))
        .order_by(func.date(JobLifecycleEvent.occurred_at))
        .all()
    )

    top_opened = (
        db.query(CsvRow.company_guess, func.count(JobLifecycleEvent.id))
        .join(JobLifecycleEvent, JobLifecycleEvent.csv_row_id == CsvRow.id)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind == "first_visited",
            CsvRow.user_id == user.id,
            CsvRow.company_guess.isnot(None),
            CsvRow.company_guess != "",
        )
        .group_by(CsvRow.company_guess)
        .order_by(desc(func.count(JobLifecycleEvent.id)))
        .limit(10)
        .all()
    )
    top_applied = (
        db.query(JobTrack.company, func.count(JobLifecycleEvent.id))
        .join(JobLifecycleEvent, JobLifecycleEvent.job_track_id == JobTrack.id)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind == "first_applied",
            JobTrack.user_id == user.id,
            JobTrack.company.isnot(None),
            JobTrack.company != "",
        )
        .group_by(JobTrack.company)
        .order_by(desc(func.count(JobLifecycleEvent.id)))
        .limit(10)
        .all()
    )

    by_fit = db.query(CsvRow.fit_category, func.count(CsvRow.id)).filter(CsvRow.user_id == user.id, CsvRow.fit_category.isnot(None), CsvRow.fit_category != "").group_by(CsvRow.fit_category).order_by(desc(func.count(CsvRow.id))).all()
    by_seniority = db.query(CsvRow.seniority_level, func.count(CsvRow.id)).filter(CsvRow.user_id == user.id, CsvRow.seniority_level.isnot(None), CsvRow.seniority_level != "").group_by(CsvRow.seniority_level).order_by(desc(func.count(CsvRow.id))).all()
    by_work_model = db.query(CsvRow.work_model_extracted, func.count(CsvRow.id)).filter(CsvRow.user_id == user.id, CsvRow.work_model_extracted.isnot(None), CsvRow.work_model_extracted != "").group_by(CsvRow.work_model_extracted).order_by(desc(func.count(CsvRow.id))).all()
    by_role_family = db.query(CsvRow.role_family, func.count(CsvRow.id)).filter(CsvRow.user_id == user.id, CsvRow.role_family.isnot(None), CsvRow.role_family != "").group_by(CsvRow.role_family).order_by(desc(func.count(CsvRow.id))).all()

    return {
        "total_urls": total_urls, "total_opened": total_opened, "total_saved": total_saved, "total_applied": total_applied,
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
        "by_fit_category": [{"name": n, "count": c} for n, c in by_fit],
        "by_seniority": [{"name": n, "count": c} for n, c in by_seniority],
        "by_work_model": [{"name": n, "count": c} for n, c in by_work_model],
        "by_role_family": [{"name": n, "count": c} for n, c in by_role_family],
    }


@router.get("/analytics/funnel")
def funnel_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    uploaded = db.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    metrics = metric_counts(db, user_id=user.id)
    opened = metrics["visited"]
    sent_to_apps = metrics["saved"]
    applied = metrics["applied"]
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
    today_start, today_end = local_day_utc_bounds(user.timezone, reference=now)
    today_metrics = metric_counts(
        db, user_id=user.id, start=today_start, end=today_end
    )
    followups_today = db.query(AuditEvent).filter(
        AuditEvent.user_id == user.id,
        AuditEvent.event_type == "followup_set",
        AuditEvent.created_at >= today_start,
        AuditEvent.created_at < today_end,
    ).count()
    exports_today = db.query(AuditEvent).filter(
        AuditEvent.user_id == user.id,
        AuditEvent.event_type == "applypilot_batch_exported",
        AuditEvent.created_at >= today_start,
        AuditEvent.created_at < today_end,
    ).count()
    return {
        "goals": {"open_per_day": goal.open_per_day, "apply_per_day": goal.apply_per_day, "followup_per_day": goal.followup_per_day, "applypilot_per_day": goal.applypilot_per_day},
        "today": {"opened": today_metrics["visited"], "applied": today_metrics["applied"], "followups": followups_today, "exports": exports_today},
    }


@router.get("/analytics/weekly")
def weekly_report(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    week_start, week_end = rolling_week_utc_bounds(user.timezone, reference=now)
    weekly_metrics = metric_counts(
        db, user_id=user.id, start=week_start, end=week_end
    )
    uploaded = db.query(CsvRow).filter(
        CsvRow.user_id == user.id,
        CsvRow.created_at >= week_start,
        CsvRow.created_at < week_end,
    ).count()
    tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
    interviews = tracks.filter(
        JobTrack.status == "interview",
        JobTrack.updated_at >= week_start,
        JobTrack.updated_at < week_end,
    ).count()
    followups = db.query(AuditEvent).filter(
        AuditEvent.user_id == user.id,
        AuditEvent.event_type == "followup_set",
        AuditEvent.created_at >= week_start,
        AuditEvent.created_at < week_end,
    ).count()
    top_companies = db.query(JobTrack.company, func.count(JobTrack.id)).filter(
        JobTrack.user_id == user.id, JobTrack.company.isnot(None), JobTrack.company != "",
        JobTrack.created_at >= week_start, JobTrack.created_at < week_end,
    ).group_by(JobTrack.company).order_by(desc(func.count(JobTrack.id))).limit(5).all()
    next_followups = tracks.filter(
        JobTrack.follow_up_at.isnot(None), JobTrack.follow_up_at >= now,
        JobTrack.follow_up_at <= now + timedelta(days=7)
    ).order_by(JobTrack.follow_up_at.asc()).limit(10).all()
    return {
        "uploaded": uploaded,
        "opened": weekly_metrics["visited"],
        "saved": weekly_metrics["saved"],
        "applied": weekly_metrics["applied"],
        "interviews": interviews,
        "followups_completed": followups,
        "top_companies": [{"name": n, "count": c} for n, c in top_companies],
        "upcoming_followups": [{"id": t.id, "company": t.company, "title": t.title, "follow_up_at": str(t.follow_up_at)} for t in next_followups],
    }


# ─── Saved Views

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
def import_applypilot_results(
    results: list[ApplyPilotResultIn],
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        prepared = []
        for index, result in enumerate(results):
            url = validate_job_url(result.url, field=f"results[{index}].url")
            submitted_at = (
                parse_timestamp(
                    result.submitted_at,
                    timezone_name=user.timezone,
                    field=f"results[{index}].submitted_at",
                )
                if result.submitted_at not in (None, "")
                else None
            )
            note = f"ApplyPilot error: {result.error}" if result.error else None
            if note is not None:
                validate_text_limits({"notes": note})
            prepared.append((result, url, submitted_at, note))

        urls = list(dict.fromkeys(url for _, url, _, _ in prepared))
        tracks_by_url = {
            track.url: track
            for track in (
                db.query(JobTrack)
                .filter(JobTrack.user_id == user.id, JobTrack.url.in_(urls))
                .all()
                if urls
                else []
            )
        }

        updated = 0
        for result, url, submitted_at, note in prepared:
            track = tracks_by_url.get(url)
            if track is None:
                continue
            now = datetime.utcnow()
            if result.submitted:
                lifecycle_kwargs = {"status": "applied"}
                if submitted_at is not None:
                    lifecycle_kwargs["applied_at"] = submitted_at
                apply_job_track_changes(
                    db,
                    user_id=user.id,
                    item=track,
                    source="applypilot_import",
                    operation_id=operation_id,
                    now=now,
                    **lifecycle_kwargs,
                )
            else:
                track.updated_at = now
            if note is not None:
                track.notes = note
            updated += 1

        db.commit()
        _log_lifecycle_outcome(
            action="applypilot_import",
            operation_id=operation_id,
            outcome="success",
            affected=updated,
            started=started,
        )
        return {"updated": updated}
    except ValidationContractError as exc:
        _raise_validation_http(
            db,
            exc,
            action="applypilot_import",
            operation_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="applypilot_import",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db,
            exc,
            action="applypilot_import",
            operation_id=operation_id,
            started=started,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db,
            exc,
            action="applypilot_import",
            operation_id=operation_id,
            started=started,
        )


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

def _next_weekday(target_weekday, now=None):
    now = now or datetime.utcnow()
    days_ahead = target_weekday - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


@router.post("/applications/{item_id}/follow-up")
def set_follow_up_preset(
    item_id: int,
    preset: str = Query(...),
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.query(JobTrack).filter_by(id=item_id, user_id=user.id).first()
    if not item:
        raise HTTPException(404, "Application not found")

    now = datetime.utcnow()
    if preset == "3_days":
        follow_up_at = now + timedelta(days=3)
    elif preset == "7_days":
        follow_up_at = now + timedelta(days=7)
    elif preset == "next_monday":
        follow_up_at = _next_weekday(0, now)
    elif preset == "clear":
        follow_up_at = None
    else:
        raise HTTPException(
            400, "Invalid preset. Use: 3_days, 7_days, next_monday, clear"
        )

    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        apply_job_track_changes(
            db,
            user_id=user.id,
            item=item,
            source="followup_preset",
            operation_id=operation_id,
            now=now,
            follow_up_at=follow_up_at,
        )
        sync_track_reminder(
            db,
            user_id=user.id,
            track_id=item.id,
            now_utc=now.replace(tzinfo=timezone.utc),
        )
        emit_event(
            db,
            user.id,
            "followup_set",
            "job_track",
            entity_id=item.id,
            metadata={"preset": preset},
        )
        db.commit()
        db.refresh(item)
        _log_lifecycle_outcome(
            action="followup_preset",
            operation_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="followup_preset",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
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


# ─── Application identity matching ───────────────────────────────────

APPLICATION_MATCH_LIMIT = 20
APPLICATION_MATCH_SCAN_LIMIT = 100
APPLICATION_ALIAS_LIMIT = 100


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    return normalized or None


def _company_alias_group(
    db: Session,
    *,
    user_id: int,
    company: str | None,
) -> tuple[str | None, list[str], set[str]]:
    company_key = _normalized_text(company)
    if company_key is None:
        return None, [], set()

    try:
        alias_key = normalize_company_alias_key(company)
    except JobIdentityError:
        return company_key, [company.strip()], {company_key}

    anchor = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user_id,
            CompanyAlias.alias_key == alias_key,
        )
        .first()
    )
    if anchor is None:
        return alias_key, [company.strip()], {alias_key}

    aliases = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user_id,
            CompanyAlias.company_key == anchor.company_key,
        )
        .order_by(CompanyAlias.alias_key.asc())
        .limit(APPLICATION_ALIAS_LIMIT)
        .all()
    )
    names = list(dict.fromkeys([company.strip()] + [alias.display_name for alias in aliases]))
    keys = {alias.alias_key for alias in aliases}
    keys.add(alias_key)
    return alias_key, names, keys


def _find_application_matches(
    db: Session,
    *,
    user_id: int,
    url: str,
    company: str | None,
    title: str | None,
) -> dict:
    try:
        identity = canonicalize_job_url(url)
    except JobIdentityError as exc:
        raise HTTPException(
            422,
            detail={
                "code": "invalid_job_url",
                "fields": [{"field": "url", "message": str(exc)}],
            },
        ) from exc

    candidate_company_key, company_names, company_alias_keys = _company_alias_group(
        db,
        user_id=user_id,
        company=company,
    )
    company_sql_keys = sorted(
        {name.strip().lower() for name in company_names if name and name.strip()}
    )

    candidate_filters = [
        JobTrack.url == url,
        JobTrack.canonical_url_hash == identity.canonical_url_hash,
    ]
    if company_sql_keys:
        candidate_filters.append(
            func.lower(func.trim(JobTrack.company)).in_(company_sql_keys)
        )

    candidates = (
        db.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.applied_at.isnot(None),
            or_(*candidate_filters),
        )
        .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
        .limit(APPLICATION_MATCH_SCAN_LIMIT)
        .all()
    )

    candidate_title = _normalized_text(title)
    matches = []
    rank = {"exact": 0, "canonical": 1, "possible": 2}
    for item in candidates:
        confidence = None
        reason = None
        if item.url == url:
            confidence = "exact"
            reason = "same_original_url"
        elif (
            item.canonical_url_hash
            and item.canonical_url_hash == identity.canonical_url_hash
        ):
            confidence = "canonical"
            reason = "same_canonical_url"
        else:
            existing_company_key = _normalized_text(item.company)
            existing_title = _normalized_text(item.title)
            same_company = (
                candidate_company_key is not None
                and existing_company_key is not None
                and (
                    existing_company_key == candidate_company_key
                    or existing_company_key in company_alias_keys
                )
            )
            if same_company and candidate_title is not None and candidate_title == existing_title:
                confidence = "possible"
                reason = (
                    "company_title_only"
                    if existing_company_key == candidate_company_key
                    else "company_alias_title"
                )

        if confidence is None:
            continue
        matches.append(
            {
                "track_id": item.id,
                "confidence": confidence,
                "reason": reason,
                "company": item.company,
                "title": item.title,
                "status": item.status,
                "applied_at": item.applied_at,
            }
        )

    matches.sort(
        key=lambda item: (
            rank[item["confidence"]],
            -(item["applied_at"].timestamp() if item["applied_at"] else 0),
            -item["track_id"],
        )
    )

    history_count = 0
    if company_sql_keys:
        history_count = (
            db.query(func.count(JobTrack.id))
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.applied_at.isnot(None),
                func.lower(func.trim(JobTrack.company)).in_(company_sql_keys),
            )
            .scalar()
            or 0
        )

    return {
        "matches": matches[:APPLICATION_MATCH_LIMIT],
        "company_history_count": int(history_count),
    }


@router.get("/application-matches")
def application_matches_for_row(
    row_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(CsvRow)
        .filter(CsvRow.id == row_id, CsvRow.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Row not found")
    return _find_application_matches(
        db,
        user_id=user.id,
        url=row.url,
        company=row.company_guess,
        title=row.title,
    )


@router.post("/application-matches")
def application_matches_for_capture(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    allowed = {"url", "company", "title"}
    if not isinstance(payload, dict) or not set(payload).issubset(allowed) or "url" not in payload:
        raise HTTPException(
            422,
            "Request body must contain url and may contain company and title.",
        )

    url = payload.get("url")
    company = payload.get("company")
    title = payload.get("title")
    if not isinstance(url, str):
        raise HTTPException(422, "url must be a string.")
    for field, value, limit in (("company", company, 320), ("title", title, 500)):
        if value is not None and not isinstance(value, str):
            raise HTTPException(422, f"{field} must be a string.")
        if isinstance(value, str) and len(value) > limit:
            raise HTTPException(422, f"{field} must be at most {limit} characters.")

    return _find_application_matches(
        db,
        user_id=user.id,
        url=url,
        company=company,
        title=title,
    )


# ─── Company History ──────────────────────────────────────────────────

@router.get("/companies")
def list_companies(q: str = Query(""), page: int = Query(1, ge=1),
                   page_size: int = Query(50, ge=1, le=100),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = func.coalesce(func.nullif(func.trim(JobTrack.company), ""), "Unknown company")
    key = func.lower(name)
    query = db.query(func.min(name).label("company"), func.count(JobTrack.id).label("total"),
                     func.count(JobTrack.applied_at).label("applied")).filter(JobTrack.user_id == user.id)
    if q.strip():
        query = query.filter(key.contains(q.strip().lower(), autoescape=True))
    query = query.group_by(key)
    total = query.count()
    companies = query.order_by(key).offset((page - 1) * page_size).limit(page_size).all()
    return {"companies": [dict(company=c.company, total=c.total, applied=c.applied) for c in companies],
            "total_count": total, "page": page, "page_size": page_size,
            "has_next": page * page_size < total}


@router.get("/companies/{company:path}")
def company_history(company: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, company_names, _ = _company_alias_group(
        db,
        user_id=user.id,
        company=company,
    )
    normalized_names = sorted(
        {name.strip().lower() for name in company_names if name and name.strip()}
    ) or [company.strip().lower()]
    company_expr = func.lower(
        func.coalesce(func.nullif(func.trim(JobTrack.company), ""), "Unknown company")
    )
    tracks = (
        db.query(JobTrack)
        .filter(
            JobTrack.user_id == user.id,
            company_expr.in_(normalized_names),
        )
        .order_by(JobTrack.created_at.desc(), JobTrack.id.desc())
        .limit(500)
        .all()
    )
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

# ─── Import External Applications ──────────────────────────────────────

@router.post("/import/external")
def import_external_applications(
    payload: list[dict],
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _request_operation_id(x_operation_id)
    started = perf_counter()
    try:
        prepared = []
        for index, raw in enumerate(payload):
            url = validate_job_url(raw.get("url"), field=f"records[{index}].url")
            text = validate_text_limits(
                {
                    "company": raw.get("company", ""),
                    "title": raw.get("title", ""),
                    "notes": raw.get("notes", ""),
                }
            )
            status = validate_status(raw.get("status", "opened"), field=f"records[{index}].status")

            applied_supplied = "applied_at" in raw
            applied_at = (
                parse_timestamp(
                    raw.get("applied_at"),
                    timezone_name=user.timezone,
                    field=f"records[{index}].applied_at",
                )
                if applied_supplied
                else None
            )
            follow_up_supplied = "follow_up_at" in raw
            follow_up_at = (
                parse_timestamp(
                    raw.get("follow_up_at"),
                    timezone_name=user.timezone,
                    field=f"records[{index}].follow_up_at",
                )
                if follow_up_supplied
                else None
            )

            target_status = "applied" if applied_at is not None else status
            if applied_supplied and applied_at is None and target_status == "applied":
                raise ValidationContractError(
                    "Applied date cannot be cleared while status remains applied.",
                    field=f"records[{index}].applied_at",
                )
            prepared.append(
                {
                    "url": url,
                    "company": text["company"],
                    "title": text["title"],
                    "notes": text["notes"],
                    "status": target_status,
                    "applied_supplied": applied_supplied,
                    "applied_at": applied_at,
                    "follow_up_supplied": follow_up_supplied,
                    "follow_up_at": follow_up_at,
                }
            )

        urls = list(dict.fromkeys(record["url"] for record in prepared))
        existing_by_url = {
            item.url: item
            for item in (
                db.query(JobTrack)
                .filter(JobTrack.user_id == user.id, JobTrack.url.in_(urls))
                .all()
                if urls
                else []
            )
        }

        created = 0
        for record in prepared:
            if record["url"] in existing_by_url:
                apply_persisted_job_identity(existing_by_url[record["url"]])
                continue

            now = datetime.utcnow()
            track = JobTrack(
                user_id=user.id,
                url=record["url"],
                company=record["company"],
                title=record["title"],
                status="opened",
                notes=record["notes"],
                opened_at=now,
            )
            apply_persisted_job_identity(track)
            db.add(track)
            db.flush()
            existing_by_url[record["url"]] = track

            lifecycle_kwargs = {
                "status": record["status"],
                "infer_applied_at_from_status": False,
            }
            if record["applied_supplied"]:
                lifecycle_kwargs["applied_at"] = record["applied_at"]
            if record["follow_up_supplied"]:
                lifecycle_kwargs["follow_up_at"] = record["follow_up_at"]

            apply_job_track_changes(
                db,
                user_id=user.id,
                item=track,
                source="external_import",
                operation_id=operation_id,
                now=now,
                **lifecycle_kwargs,
            )
            created += 1

        db.commit()
        _log_lifecycle_outcome(
            action="external_import",
            operation_id=operation_id,
            outcome="success",
            affected=created,
            started=started,
        )
        return {"created": created}
    except ValidationContractError as exc:
        _raise_validation_http(
            db,
            exc,
            action="external_import",
            operation_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_http(
            db,
            exc,
            action="external_import",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        _raise_integrity_http(
            db,
            exc,
            action="external_import",
            operation_id=operation_id,
            started=started,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        _raise_unexpected_http(
            db,
            exc,
            action="external_import",
            operation_id=operation_id,
            started=started,
        )


# ─── Export ───────────────────────────────────────────────────────────────

EXPORT_DASHBOARD_FIELDS = CSV_COLUMNS + ["clicked", "clicked_at"]
EXPORT_APPLICATION_FIELDS = CSV_COLUMNS + [
    "clicked", "clicked_at",
    "app_status", "applied_at", "follow_up_at", "notes", "last_updated",
]
EXPORT_CHUNK_SIZE = 200
MAX_SELECTED_EXPORT_IDS = 500


def _serialize_dashboard_row(row, export_cols=None):
    cols = export_cols or CSV_COLUMNS
    out = {col: getattr(row, col) for col in cols}
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


def _spreadsheet_safe_csv_value(value):
    if not isinstance(value, str) or not value:
        return value
    stripped_control = value.lstrip("\t\r\n\v\f")
    if value[0] in "=+-@" or (
        stripped_control != value
        and stripped_control
        and stripped_control[0] in "=+-@"
    ):
        return "'" + value
    return value


def _csv_stream(rows, serializer, fieldnames, row_count):
    if row_count == 0:
        yield b""
        return

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    yield buf.getvalue().encode("utf-8")
    buf.seek(0)
    buf.truncate(0)

    for row in rows:
        serialized = serializer(row)
        writer.writerow({key: _spreadsheet_safe_csv_value(serialized.get(key)) for key in fieldnames})
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)


def _json_stream(rows, serializer):
    yield b"["
    first = True
    for row in rows:
        if not first:
            yield b",\n"
        yield json.dumps(serializer(row), ensure_ascii=False, default=str).encode("utf-8")
        first = False
    yield b"]"


def _to_streaming_csv_response(rows, serializer, fieldnames, filename, row_count):
    return StreamingResponse(
        _csv_stream(rows, serializer, fieldnames, row_count),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _to_streaming_json_response(rows, serializer, filename):
    return StreamingResponse(
        _json_stream(rows, serializer),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_export_ids(raw_ids: str | None, *, required: bool) -> list[int] | None:
    if raw_ids is None:
        if required:
            raise HTTPException(422, "row_ids is required for selected scope")
        return None
    if not raw_ids.strip():
        raise HTTPException(422, "row_ids must contain at least one positive integer")

    parts = raw_ids.split(",")
    if len(parts) > MAX_SELECTED_EXPORT_IDS:
        raise HTTPException(422, f"row_ids supports at most {MAX_SELECTED_EXPORT_IDS} IDs")

    parsed = []
    for part in parts:
        token = part.strip()
        if not token.isdigit() or int(token) <= 0:
            raise HTTPException(422, "row_ids must contain only positive integers")
        parsed.append(int(token))

    # Database IN predicates already collapse duplicates. Normalize them here so ownership
    # checks and the documented 500-ID boundary have one deterministic representation.
    return list(dict.fromkeys(parsed))


def _dashboard_export_columns(columns: str | None) -> list[str]:
    if columns is None:
        return list(CSV_COLUMNS)
    requested = [item.strip() for item in columns.split(",") if item.strip()]
    if not requested:
        raise HTTPException(400, "columns must contain at least one CSV column")
    invalid = [item for item in requested if item not in CSV_COLUMNS]
    if invalid:
        raise HTTPException(400, "Unknown export column")
    return list(dict.fromkeys(requested))


def _filter_present(value) -> bool:
    if isinstance(value, bool):
        return value
    return value is not None and value != ""


def _bounded_filter_flags(values: dict) -> dict[str, bool]:
    return {key: _filter_present(value) for key, value in values.items()}


def _application_computed_sort_value(track, sort_by):
    csv_row = track.csv_row
    if not csv_row:
        return 0 if sort_by == "priority_score" else "needs_review"
    priority_score = calculate_priority_score(csv_row, track)
    if sort_by == "priority_score":
        return priority_score
    return calculate_triage(csv_row, track, priority_score)


def _ordered_application_export_rows(query, params):
    if params.sort_by not in ("priority_score", "triage"):
        return order_application_query(query, params, num_expr).yield_per(EXPORT_CHUNK_SIZE)

    # The live applications table uses Python ordering for these two computed fields.
    # Preserve that behavior while avoiding a second materialized list of serialized dicts.
    rows = query.order_by(JobTrack.id.desc()).all()
    rows.sort(
        key=lambda track: _application_computed_sort_value(track, params.sort_by),
        reverse=(params.sort_dir == "desc"),
    )
    return iter(rows)


@router.get("/export/dashboard")
def export_dashboard(
    format: Literal["csv", "json"] = Query("csv"),
    scope: Literal["all", "filtered", "selected"] | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    ats_group: str | None = Query(None),
    location_group: str | None = Query(None),
    search_bucket: str | None = Query(None),
    decision: str | None = Query(None),
    sponsorship_status: str | None = Query(None),
    fit_category: str | None = Query(None),
    seniority_level: str | None = Query(None),
    work_model: str | None = Query(None),
    role_family: str | None = Query(None),
    salary_min: float | None = Query(None),
    salary_max: float | None = Query(None),
    q: str | None = Query(None, max_length=500),
    opened_only: bool = Query(False),
    unopened_only: bool = Query(False),
    has_error: bool = Query(False),
    jd_missing: bool = Query(False),
    openable_only: bool = Query(False),
    row_ids: str | None = Query(None),
    columns: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    export_cols = _dashboard_export_columns(columns)
    selected_ids = _parse_export_ids(row_ids, required=(scope == "selected"))
    if scope in ("all", "filtered") and selected_ids is not None:
        raise HTTPException(400, "row_ids requires scope=selected")

    params = RowQuery(
        sort_by=sort_by,
        sort_dir=sort_dir,
        ats_group=ats_group,
        location_group=location_group,
        search_bucket=search_bucket,
        decision=decision,
        sponsorship_status=sponsorship_status,
        fit_category=fit_category,
        seniority_level=seniority_level,
        work_model=work_model,
        role_family=role_family,
        salary_min=salary_min,
        salary_max=salary_max,
        q=q,
        opened_only=opened_only,
        unopened_only=unopened_only,
        has_error=has_error,
        jd_missing=jd_missing,
        openable_only=openable_only,
    )
    try:
        resolve_row_sort_column(sort_by)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if scope == "all":
        query = build_row_query(db, user.id, RowQuery(sort_by=sort_by, sort_dir=sort_dir))
    elif scope == "selected":
        owned_ids = {
            row_id
            for (row_id,) in db.query(CsvRow.id).filter(
                CsvRow.user_id == user.id,
                CsvRow.archived.is_(False),
                CsvRow.id.in_(selected_ids),
            ).all()
        }
        if owned_ids != set(selected_ids):
            raise HTTPException(404, "One or more selected rows were not found")
        query = db.query(CsvRow).filter(
            CsvRow.user_id == user.id,
            CsvRow.archived.is_(False),
            CsvRow.id.in_(selected_ids),
        )
    else:
        # Omitted scope preserves the legacy behavior: supplied filters apply, and a
        # supplied row_ids list intersects that result. Invalid/foreign IDs no longer
        # fall back to exporting the account's full dataset.
        query = build_row_query(db, user.id, params)
        if selected_ids is not None:
            owned_ids = {
                row_id
                for (row_id,) in db.query(CsvRow.id).filter(
                    CsvRow.user_id == user.id,
                    CsvRow.archived.is_(False),
                    CsvRow.id.in_(selected_ids),
                ).all()
            }
            if owned_ids != set(selected_ids):
                raise HTTPException(404, "One or more selected rows were not found")
            query = query.filter(CsvRow.id.in_(selected_ids))

    row_count = query.count()
    ordered_rows = order_row_query(query, RowQuery(sort_by=sort_by, sort_dir=sort_dir)).yield_per(EXPORT_CHUNK_SIZE)
    filter_flags = _bounded_filter_flags({
        "ats_group": ats_group,
        "location_group": location_group,
        "search_bucket": search_bucket,
        "decision": decision,
        "sponsorship_status": sponsorship_status,
        "fit_category": fit_category,
        "seniority_level": seniority_level,
        "work_model": work_model,
        "role_family": role_family,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "q": q,
        "opened_only": opened_only,
        "unopened_only": unopened_only,
        "has_error": has_error,
        "jd_missing": jd_missing,
        "openable_only": openable_only,
        "selected": selected_ids is not None,
    })
    emit_event(
        db,
        user.id,
        "rows_exported",
        "dashboard",
        metadata={"count": row_count, "format": format, "filter_flags": filter_flags},
    )
    db.commit()

    serializer = lambda row: _serialize_dashboard_row(row, export_cols)
    fieldnames = export_cols + ["clicked", "clicked_at"]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        return _to_streaming_json_response(ordered_rows, serializer, f"dashboard_export_{ts}.json")
    return _to_streaming_csv_response(
        ordered_rows,
        serializer,
        fieldnames,
        f"dashboard_export_{ts}.csv",
        row_count,
    )


@router.get("/export/applications")
def export_applications(
    format: Literal["csv", "json"] = Query("csv"),
    scope: Literal["all", "filtered", "selected"] | None = Query(None),
    status: str | None = Query(None),
    company: str | None = Query(None),
    ats_group: str | None = Query(None),
    search_bucket: str | None = Query(None),
    quick_range: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    min_score: float | None = Query(None),
    max_score: float | None = Query(None),
    follow_up_due: bool = Query(False),
    opened_not_applied: bool = Query(False),
    q: str | None = Query(None, max_length=500),
    location_group: str | None = Query(None),
    decision: str | None = Query(None),
    sponsorship_status: str | None = Query(None),
    posted_age_min: float | None = Query(None),
    posted_age_max: float | None = Query(None),
    follow_up_today: bool = Query(False),
    follow_up_overdue: bool = Query(False),
    follow_up_none: bool = Query(False),
    has_error: bool = Query(False),
    jd_missing: bool = Query(False),
    date_applied_from: str | None = Query(None),
    date_applied_to: str | None = Query(None),
    applied_only: bool = Query(False),
    sort_by: str = Query("opened_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    row_ids: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    selected_ids = _parse_export_ids(row_ids, required=(scope == "selected"))
    if scope in ("all", "filtered") and selected_ids is not None:
        raise HTTPException(400, "row_ids requires scope=selected")
    if sort_by not in SORT_FIELDS:
        sort_by = "opened_at"

    params = ApplicationQuery(
        status=status,
        company=company,
        ats_group=ats_group,
        search_bucket=search_bucket,
        quick_range=quick_range,
        date_from=date_from,
        date_to=date_to,
        min_score=min_score,
        max_score=max_score,
        follow_up_due=follow_up_due,
        opened_not_applied=opened_not_applied,
        q=q,
        location_group=location_group,
        decision=decision,
        sponsorship_status=sponsorship_status,
        posted_age_min=posted_age_min,
        posted_age_max=posted_age_max,
        follow_up_today=follow_up_today,
        follow_up_overdue=follow_up_overdue,
        follow_up_none=follow_up_none,
        has_error=has_error,
        jd_missing=jd_missing,
        date_applied_from=date_applied_from,
        date_applied_to=date_applied_to,
        applied_only=applied_only,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    try:
        if scope == "all":
            query = build_application_query(
                db,
                user.id,
                ApplicationQuery(sort_by=sort_by, sort_dir=sort_dir),
                numeric_expression=num_expr,
                parse_datetime=parse_dt,
            )
        elif scope == "selected":
            owned_ids = {
                track_id
                for (track_id,) in db.query(JobTrack.id).filter(
                    JobTrack.user_id == user.id,
                    JobTrack.id.in_(selected_ids),
                ).all()
            }
            if owned_ids != set(selected_ids):
                raise HTTPException(404, "One or more selected applications were not found")
            query = db.query(JobTrack).filter(
                JobTrack.user_id == user.id,
                JobTrack.id.in_(selected_ids),
            )
        else:
            query = build_application_query(
                db,
                user.id,
                params,
                numeric_expression=num_expr,
                parse_datetime=parse_dt,
            )
            if selected_ids is not None:
                owned_ids = {
                    track_id
                    for (track_id,) in db.query(JobTrack.id).filter(
                        JobTrack.user_id == user.id,
                        JobTrack.id.in_(selected_ids),
                    ).all()
                }
                if owned_ids != set(selected_ids):
                    raise HTTPException(404, "One or more selected applications were not found")
                query = query.filter(JobTrack.id.in_(selected_ids))
    except ValueError as exc:
        raise HTTPException(422, "Invalid application export filter") from exc

    row_count = query.count()
    ordering_params = ApplicationQuery(sort_by=sort_by, sort_dir=sort_dir)
    ordered_rows = _ordered_application_export_rows(query, ordering_params)
    filter_flags = _bounded_filter_flags({
        "status": status,
        "company": company,
        "ats_group": ats_group,
        "search_bucket": search_bucket,
        "quick_range": quick_range,
        "date_from": date_from,
        "date_to": date_to,
        "min_score": min_score,
        "max_score": max_score,
        "follow_up_due": follow_up_due,
        "opened_not_applied": opened_not_applied,
        "q": q,
        "location_group": location_group,
        "decision": decision,
        "sponsorship_status": sponsorship_status,
        "posted_age_min": posted_age_min,
        "posted_age_max": posted_age_max,
        "follow_up_today": follow_up_today,
        "follow_up_overdue": follow_up_overdue,
        "follow_up_none": follow_up_none,
        "has_error": has_error,
        "jd_missing": jd_missing,
        "date_applied_from": date_applied_from,
        "date_applied_to": date_applied_to,
        "applied_only": applied_only,
        "selected": selected_ids is not None,
    })
    emit_event(
        db,
        user.id,
        "rows_exported",
        "applications",
        metadata={"count": row_count, "format": format, "filter_flags": filter_flags},
    )
    db.commit()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        return _to_streaming_json_response(
            ordered_rows,
            _serialize_application_row,
            f"applications_export_{ts}.json",
        )
    return _to_streaming_csv_response(
        ordered_rows,
        _serialize_application_row,
        EXPORT_APPLICATION_FIELDS,
        f"applications_export_{ts}.csv",
        row_count,
    )
