import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, ColumnPreference, CsvRow, JobTrack, User
from ..schemas import ColumnPrefIn, RowDeleteIn
from ..services.lifecycle import LifecycleEventError, record_visit
from ..services.row_queries import (
    RowQuery,
    build_row_query,
    order_row_query,
    resolve_row_sort_column,
)
from .crm import emit_event, calculate_priority_score, calculate_triage

router = APIRouter(tags=["rows"])
logger = logging.getLogger(__name__)


class RetentionPreferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    retention_days: int | None


def _validate_retention_days(value: int | None) -> int | None:
    if value is None or value == 0 or 7 <= value <= 3650:
        return value
    raise HTTPException(
        status_code=422,
        detail="retention_days must be 0 (disabled) or between 7 and 3650 days",
    )


def _clean_columns(columns: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for col in columns:
        if col in CSV_COLUMNS and col not in seen:
            cleaned.append(col)
            seen.add(col)
    return cleaned

def _safe_sort_column(sort_by: str):
    """Compatibility wrapper around the shared row sort contract."""

    try:
        return resolve_row_sort_column(sort_by)
    except ValueError as exc:
        raise HTTPException(400, "Invalid sort column") from exc


def _parse_utc_naive(value: str | None):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _base_user_query(db: Session, user_id: int, ats_group: str | None = None):
    query = db.query(CsvRow).filter(CsvRow.user_id == user_id)
    if ats_group:
        query = query.filter(func.lower(CsvRow.ats_group) == ats_group.lower())
    return query


def _row_stats(
    db: Session,
    user_id: int,
    ats_group: str | None,
    clicked_today_start: str | None,
    clicked_today_end: str | None,
) -> dict:
    query = _base_user_query(db, user_id, ats_group)
    today_start = _parse_utc_naive(clicked_today_start)
    today_end = _parse_utc_naive(clicked_today_end)

    green_today_query = query.filter(CsvRow.clicked.is_(True), CsvRow.clicked_at.isnot(None))
    if today_start and today_end:
        green_today_query = green_today_query.filter(
            CsvRow.clicked_at >= today_start,
            CsvRow.clicked_at < today_end,
        )

    return {
        "total_urls": query.filter(CsvRow.url.isnot(None), CsvRow.url != "").count(),
        "green_urls": query.filter(CsvRow.clicked.is_(True)).count(),
        "green_today": green_today_query.count() if today_start and today_end else 0,
    }


def _ats_group_values(db: Session, user_id: int) -> list[str]:
    values = (
        db.query(CsvRow.ats_group)
        .filter(
            CsvRow.user_id == user_id,
            CsvRow.archived.is_(False),
            CsvRow.ats_group.isnot(None),
            CsvRow.ats_group != "",
        )
        .distinct()
        .order_by(CsvRow.ats_group.asc())
        .all()
    )
    return [value for (value,) in values if value]


def _filter_option_values(db: Session, user_id: int, column) -> list[str]:
    values = (
        db.query(column)
        .filter(
            CsvRow.user_id == user_id,
            CsvRow.archived.is_(False),
            column.isnot(None),
            column != "",
        )
        .distinct()
        .order_by(column.asc())
        .all()
    )
    return [value for (value,) in values if value]


@router.get("/rows")
def list_rows(
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
    q: str | None = Query(None),
    opened_only: bool = Query(False),
    unopened_only: bool = Query(False),
    openable_only: bool = Query(False),
    has_error: bool = Query(False),
    jd_missing: bool = Query(False),
    clicked_today_start: str | None = Query(None),
    clicked_today_end: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query_params = RowQuery(
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
        openable_only=openable_only,
        has_error=has_error,
        jd_missing=jd_missing,
    )
    query = build_row_query(db, user.id, query_params)
    total_count = query.count()

    rows = (
        order_row_query(query, query_params, _safe_sort_column)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    row_ids = [r.id for r in rows]
    track_map = {}
    if row_ids:
        tracks = db.query(JobTrack).filter(JobTrack.csv_row_id.in_(row_ids), JobTrack.user_id == user.id).all()
        track_map = {t.csv_row_id: t for t in tracks}

    return {
        "columns": CSV_COLUMNS,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "filters": {"ats_group": ats_group or ""},
        "filter_options": {
            "ats_groups": _ats_group_values(db, user.id),
            "location_groups": _filter_option_values(db, user.id, CsvRow.location_group),
            "search_buckets": _filter_option_values(db, user.id, CsvRow.search_bucket),
            "decisions": _filter_option_values(db, user.id, CsvRow.decision),
            "sponsorship_statuses": _filter_option_values(db, user.id, CsvRow.sponsorship_status),
            "fit_categories": _filter_option_values(db, user.id, CsvRow.fit_category),
            "seniority_levels": _filter_option_values(db, user.id, CsvRow.seniority_level),
            "work_models": _filter_option_values(db, user.id, CsvRow.work_model_extracted),
            "role_families": _filter_option_values(db, user.id, CsvRow.role_family),
        },
        "stats": _row_stats(
            db,
            user.id,
            ats_group,
            clicked_today_start,
            clicked_today_end,
        ),
        "rows": [
            {
                "id": row.id,
                "clicked": row.clicked,
                "clicked_at": row.clicked_at,
                "is_duplicate": row.is_duplicate,
                "duplicate_of_id": row.duplicate_of_id,
                "data": {col: getattr(row, col) for col in CSV_COLUMNS},
                "app_status": track_map[row.id].status if row.id in track_map else None,
                "app_id": track_map[row.id].id if row.id in track_map else None,
                "applied_at": str(track_map[row.id].applied_at) if row.id in track_map and track_map[row.id].applied_at else None,
                "follow_up_at": str(track_map[row.id].follow_up_at) if row.id in track_map and track_map[row.id].follow_up_at else None,
                "app_notes": (track_map[row.id].notes or "")[:80] if row.id in track_map else None,
                "priority_score": calculate_priority_score(row, track_map.get(row.id)) if hasattr(row, 'is_duplicate') else 0,
                "triage": calculate_triage(row, track_map.get(row.id)) if hasattr(row, 'is_duplicate') else "needs_review",
            }
            for row in rows
        ],
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total_count,
    }


@router.post("/rows/{row_id}/click")
def record_click(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(CsvRow).filter_by(id=row_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Row not found")
    operation_id = uuid4()
    started = perf_counter()
    if not row.clicked:
        try:
            record_visit(
                db,
                user_id=user.id,
                row=row,
                occurred_at=datetime.utcnow(),
                source="row_click",
            )
            emit_event(
                db,
                user.id,
                "row_opened",
                "csv_row",
                entity_id=row.id,
                metadata={"url": row.url},
            )
            db.commit()
            logger.info(
                "lifecycle_mutation action=row_click operation_id=%s outcome=success affected=1 elapsed_ms=%s",
                operation_id,
                int((perf_counter() - started) * 1000),
            )
        except LifecycleEventError as exc:
            db.rollback()
            status_code = 409 if exc.code == "event_key_conflict" else 400
            logger.warning(
                "lifecycle_mutation action=row_click operation_id=%s outcome=%s affected=0 elapsed_ms=%s",
                operation_id,
                exc.code,
                int((perf_counter() - started) * 1000),
            )
            raise HTTPException(status_code, exc.message) from exc
    else:
        logger.info(
            "lifecycle_mutation action=row_click operation_id=%s outcome=no_change affected=0 elapsed_ms=%s",
            operation_id,
            int((perf_counter() - started) * 1000),
        )
    return {"id": row.id, "clicked": row.clicked, "clicked_at": row.clicked_at}


@router.delete("/rows")
def delete_rows(
    payload: RowDeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not payload.row_ids:
        raise HTTPException(400, "No rows selected")

    query = db.query(CsvRow).filter(
        CsvRow.user_id == user.id,
        CsvRow.id.in_(payload.row_ids),
    )

    if payload.mode == "archive":
        # Bulk SQL bypasses ORM before_update events, so version is incremented
        # explicitly in the same statement as the archive transition.
        archive_now = datetime.utcnow()
        updated = query.filter(CsvRow.archived.is_(False)).update(
            {
                CsvRow.archived: True,
                CsvRow.archived_at: archive_now,
                CsvRow.version: CsvRow.version + 1,
            },
            synchronize_session=False,
        )
        db.commit()
        return {"archived": updated, "deleted": 0}

    # Application snapshots outlive their source CSV rows. Detach operations are
    # real JobTrack/CsvRow mutations and therefore advance optimistic versions.
    db.query(JobTrack).filter(
        JobTrack.user_id == user.id, JobTrack.csv_row_id.in_(payload.row_ids),
    ).update(
        {JobTrack.csv_row_id: None, JobTrack.version: JobTrack.version + 1},
        synchronize_session=False,
    )
    db.query(CsvRow).filter(
        CsvRow.user_id == user.id, CsvRow.duplicate_of_id.in_(payload.row_ids),
    ).update(
        {CsvRow.duplicate_of_id: None, CsvRow.version: CsvRow.version + 1},
        synchronize_session=False,
    )
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"archived": 0, "deleted": deleted}


@router.get("/preferences")
def get_preferences(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    pref = db.get(ColumnPreference, user.id)
    hidden_columns = pref.hidden_columns if pref else []
    column_order = pref.column_order if pref else []
    return {
        "hidden_columns": _clean_columns(hidden_columns),
        "column_order": _clean_columns(column_order),
        "retention_days": user.retention_days,
    }


@router.put("/preferences/retention")
def set_retention_preference(
    payload: RetentionPreferenceIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    retention_days = _validate_retention_days(payload.retention_days)
    user.retention_days = retention_days
    db.commit()
    db.refresh(user)
    return {"retention_days": user.retention_days}


@router.put("/preferences")
def set_preferences(
    payload: ColumnPrefIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hidden = _clean_columns(payload.hidden_columns)
    column_order = _clean_columns(payload.column_order)
    pref = db.get(ColumnPreference, user.id)
    if pref:
        pref.hidden_columns = hidden
        pref.column_order = column_order
    else:
        pref = ColumnPreference(
            user_id=user.id,
            hidden_columns=hidden,
            column_order=column_order,
        )
        db.add(pref)
    db.commit()
    return {
        "hidden_columns": hidden,
        "column_order": column_order,
        "retention_days": user.retention_days,
    }
