import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, CsvRow, User

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("")
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = await file.read()
    # sep=None lets pandas sniff comma vs tab delimiter.
    df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", dtype=str)
    df = df.where(pd.notnull(df), None)

    if "url" not in df.columns:
        raise HTTPException(400, "CSV must contain a 'url' column")

    batch_id = str(uuid.uuid4())
    records = []
    seen = set()
    for _, r in df.iterrows():
        url = r.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        row = {col: r.get(col) for col in CSV_COLUMNS}
        row["user_id"] = user.id
        row["upload_batch_id"] = batch_id
        records.append(row)

    inserted = 0
    if records:
        stmt = (
            pg_insert(CsvRow)
            .values(records)
            .on_conflict_do_nothing(index_elements=["user_id", "url"])
        )
        result = db.execute(stmt)
        db.commit()
        inserted = result.rowcount

    return {
        "batch_id": batch_id,
        "received": len(records),
        "inserted": inserted,
        "skipped_duplicates": len(records) - inserted,
    }
