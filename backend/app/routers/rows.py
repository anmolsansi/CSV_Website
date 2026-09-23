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
from ..schemas import ColumnPrefIn, PermanentDeletePreviewIn, RowDeleteIn, RowRestoreIn
from ..services.bulk_actions import (
    archive_rows,
    permanent_delete_preview,
    permanent_delete_rows,
    restore_archived_rows,
)
from ..services.lifecycle import LifecycleEventError, record_visit
from ..services.row_queries import (
    RowQuery,
    build_row_query,
    order_row_query,
    resolve_row_sort_column,
)
from ..undo_schemas import UndoContractError
from .crm import emit_event, calculate_priority_score, calculate_triage

router = APIRouter(tags=["rows"])
logger = logging.getLogger(__name__)


class RetentionPreferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    retention_days: int | None


def _raise_undo_contract(exc: UndoContractError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


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
    # Existing dashboard totals intentionally include archived source rows. This
    # preserves the long-standing "clean table only, numbers stay the same"
    # contract while Archive becomes recoverable.
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


def _scope_filter(query, archive_scope: str):
    if archive_scope == "active":
        return query.filter(CsvRow.archived.is_(False))
    if archive_scope == "archived":
        return query.filter(CsvRow.archived.is_(True))
    if archive_scope == "all":
        return query
    raise HTTPException(422, "Invalid archive_scope")


def _ats_group_values(db: Session, user_id: int, archive_scope: str) -> list[str]:
    query = db.query(CsvRow.ats_group).filter(
        CsvRow.user_id == user_id,
        CsvRow.ats_group.isnot(None),
        CsvRow.ats_group != "",
    )
    values = (
        _scope_filter(query, archive_scope)
        .distinct()
        .order_by(CsvRow.ats_group.asc())
        .all()
    )
    return [value for (value,) in values if value]


def _filter_option_values(db: Session, user_id: int, column, archive_scope: str) -> list[str]:
    query = db.query(column).filter(
        CsvRow.user_id == user_id,
        column.isnot(None),
        column != "",
    )
    values = (
        _scope_filter(query, archive_scope)
        .distinct()
        .order_by(column.asc())
        .all()
    )
    return [value for (value,) in values if value]


def _legacy_delete_rows(db: Session, *, user_id: int, row_ids: list[int]) -> dict:
    """Keep the pre-F10 omitted-mode DELETE /rows contract for legacy callers.

    First-party F10 clients always send an explicit mode. This compatibility
    adapter exists only for historical callers that send exactly row_ids. It
    deletes the source row while detaching the two source references so durable
    application history remains available.
    """
    unique_ids = list(dict.fromkeys(row_ids))
    rows = db.query(CsvRow).filter(
        CsvRow.user_id == user_id,
        CsvRow.id.in_(unique_ids),
    ).all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(unique_ids):
        raise HTTPException(404, "One or more rows not found")

    tracks = db.query(JobTrack).filter(
        JobTrack.user_id == user_id,
        JobTrack.csv_row_id.in_(unique_ids),
    ).all()
    for track in tracks:
        track.csv_row_id = None

    duplicates = db.query(CsvRow).filter(
        CsvRow.user_id == user_id,
        CsvRow.duplicate_of_id.in_(unique_ids),
    ).all()
    for duplicate in duplicates:
        duplicate.duplicate_of_id = None
    db.flush()

    for row_id in unique_ids:
        db.delete(by_id[row_id])
    db.flush()
    return {
        "deleted": len(unique_ids),
        "archived": 0,
        "detached_applications": len(tracks),
        "detached_duplicates": len(duplicates),
        "legacy_compatibility": True,
    }


@router.get("/rows")
def list_rows(
    sort_by: str = Query("created_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    archive_scope: Literal["active", "archived", "all"] = Query("active"),
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
        archive_scope=archive_scope,
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
        "archive_scope": archive_scope,
        "filters": {"ats_group": ats_group or ""},
        "filter_options": {
            "ats_groups": _ats_group_values(db, user.id, archive_scope),
            "location_groups": _filter_option_values(db, user.id, CsvRow.location_group, archive_scope),
            "search_buckets": _filter_option_values(db, user.id, CsvRow.search_bucket, archive_scope),
            "decisions": _filter_option_values(db, user.id, CsvRow.decision, archive_scope),
            "sponsorship_statuses": _filter_option_values(db, user.id, CsvRow.sponsorship_status, archive_scope),
            "fit_categories": _filter_option_values(db, user.id, CsvRow.fit_category, archive_scope),
            "seniority_levels": _filter_option_values(db, user.id, CsvRow.seniority_level, archive_scope),
            "work_models": _filter_option_values(db, user.id, CsvRow.work_model_extracted, archive_scope),
            "role_families": _filter_option_values(db, user.id, CsvRow.role_family, archive_scope),
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
                "version": int(row.version),
                "archived": bool(row.archived),
                "archived_at": row.archived_at,
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


@router.post("/rows/restore")
def restore_rows(
    payload: RowRestoreIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        result = restore_archived_rows(
            db,
            user_id=user.id,
            row_ids=payload.row_ids,
            expected_versions=payload.expected_versions,
            mode=payload.mode,
        )
        db.commit()
        return result
    except UndoContractError as exc:
        db.rollback()
        _raise_undo_contract(exc)


@router.post("/rows/permanent-delete/preview")
def preview_permanent_delete(
    payload: PermanentDeletePreviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return permanent_delete_preview(
            db,
            user_id=user.id,
            row_ids=payload.row_ids,
            expected_versions=payload.expected_versions,
        )
    except UndoContractError as exc:
        db.rollback()
        _raise_undo_contract(exc)


@router.delete("/rows")
def delete_rows(
    payload: RowDeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not payload.row_ids:
        raise HTTPException(400, "No rows selected")

    try:
        # Compatibility is intentionally keyed to field omission rather than the
        # default value. Explicit F10 mode="delete" never bypasses preview/token
        # checks, while older clients that only sent row_ids keep their frozen
        # release contract until they can migrate.
        if "mode" not in payload.model_fields_set:
            result = _legacy_delete_rows(db, user_id=user.id, row_ids=payload.row_ids)
            db.commit()
            return result

        if payload.mode == "archive":
            result = archive_rows(
                db,
                user_id=user.id,
                row_ids=payload.row_ids,
                request_key=payload.request_key,
                expected_versions=payload.expected_versions,
            )
            db.commit()
            return result

        result = permanent_delete_rows(
            db,
            user_id=user.id,
            row_ids=payload.row_ids,
            confirmation_token=payload.confirmation_token,
            expected_versions=payload.expected_versions,
        )
        db.commit()
        return result
    except UndoContractError as exc:
        db.rollback()
        _raise_undo_contract(exc)
    except Exception:
        db.rollback()
        raise


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
