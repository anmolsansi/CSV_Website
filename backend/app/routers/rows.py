from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, ColumnPreference, CsvRow, User
from ..schemas import ColumnPrefIn

router = APIRouter(tags=["rows"])


@router.get("/rows")
def list_rows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(CsvRow)
        .filter_by(user_id=user.id)
        .order_by(CsvRow.created_at.desc())
        .all()
    )
    return {
        "columns": CSV_COLUMNS,
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


@router.get("/preferences")
def get_preferences(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    pref = db.get(ColumnPreference, user.id)
    return {"hidden_columns": pref.hidden_columns if pref else []}


@router.put("/preferences")
def set_preferences(
    payload: ColumnPrefIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hidden = [c for c in payload.hidden_columns if c in CSV_COLUMNS]
    pref = db.get(ColumnPreference, user.id)
    if pref:
        pref.hidden_columns = hidden
    else:
        pref = ColumnPreference(user_id=user.id, hidden_columns=hidden)
        db.add(pref)
    db.commit()
    return {"hidden_columns": hidden}
