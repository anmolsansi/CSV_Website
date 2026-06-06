from datetime import datetime
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


def _ats_group_values(db: Session, user_id: int) -> list[str]:
    values = (
        db.query(CsvRow.ats_group)
        .filter(CsvRow.user_id == user_id, CsvRow.ats_group.isnot(None), CsvRow.ats_group != "")
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sort_column = _safe_sort_column(sort_by)
    order_func = asc if sort_dir == "asc" else desc

    query = db.query(CsvRow).filter_by(user_id=user.id)
    if ats_group:
        query = query.filter(func.lower(CsvRow.ats_group) == ats_group.lower())

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

    deleted = (
        db.query(CsvRow)
        .filter(CsvRow.user_id == user.id, CsvRow.id.in_(payload.row_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


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
