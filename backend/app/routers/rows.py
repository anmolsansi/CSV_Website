from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, asc, case, cast, desc, func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, ColumnPreference, CsvRow, User
from ..schemas import ColumnPrefIn, RowDeleteIn

router = APIRouter(tags=["rows"])

NUMERIC_SORT_COLUMNS = {
    "page_number",
    "posted_age_days",
    "jd_text_length",
    "resume_match_score",
}


def _clean_columns(columns: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for col in columns:
        if col in CSV_COLUMNS and col not in seen:
            cleaned.append(col)
            seen.add(col)
    return cleaned


def _numeric_sort_expression(column):
    """Sort text-backed numeric columns as numbers, not strings."""
    cleaned = func.nullif(func.regexp_replace(column, r"[%,$,\s]", "", "g"), "")
    return case(
        (cleaned.op("~")(r"^-?\d+(\.\d+)?$"), cast(cleaned, Float)),
        else_=None,
    )


def _safe_sort_column(sort_by: str):
    if sort_by == "created_at":
        return CsvRow.created_at
    if sort_by == "clicked_at":
        return CsvRow.clicked_at
    if sort_by not in CSV_COLUMNS:
        raise HTTPException(400, "Invalid sort column")

    column = getattr(CsvRow, sort_by)
    if sort_by in NUMERIC_SORT_COLUMNS:
        return _numeric_sort_expression(column)
    return column


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


@router.get("/rows")
def list_rows(
    sort_by: str = Query("created_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    ats_group: str | None = Query(None),
    clicked_today_start: str | None = Query(None),
    clicked_today_end: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sort_column = _safe_sort_column(sort_by)
    order_func = asc if sort_dir == "asc" else desc

    query = _base_user_query(db, user.id, ats_group).filter(CsvRow.archived.is_(False))

    rows = (
        query
        .order_by(order_func(sort_column).nullslast(), CsvRow.id.desc())
        .all()
    )
    return {
        "columns": CSV_COLUMNS,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "filters": {"ats_group": ats_group or ""},
        "filter_options": {"ats_groups": _ats_group_values(db, user.id)},
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
                "data": {col: getattr(row, col) for col in CSV_COLUMNS},
            }
            for row in rows
        ],
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
    if not row.clicked:
        row.clicked = True
        row.clicked_at = datetime.utcnow()
        db.commit()
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
        updated = query.update({CsvRow.archived: True}, synchronize_session=False)
        db.commit()
        return {"archived": updated, "deleted": 0}

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
    }


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
    return {"hidden_columns": hidden, "column_order": column_order}
