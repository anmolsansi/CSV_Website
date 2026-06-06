import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CSV_COLUMNS, CsvRow, UrlHistory, User

router = APIRouter(prefix="/upload", tags=["upload"])


def _clean_url(url) -> str | None:
    if url is None:
        return None
    cleaned = str(url).strip()
    return cleaned or None


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
    incoming_rows = []
    history_records = []
    seen_in_upload = set()
    duplicate_in_upload = 0

    existing_history_urls = {
        url
        for (url,) in db.query(UrlHistory.url)
        .filter(UrlHistory.user_id == user.id)
        .all()
    }

    for _, r in df.iterrows():
        url = _clean_url(r.get("url"))
        if not url:
            continue

        if url in seen_in_upload:
            duplicate_in_upload += 1
            continue
        seen_in_upload.add(url)

        if url in existing_history_urls:
            continue

        row = {col: r.get(col) for col in CSV_COLUMNS}
        row["url"] = url
        row["user_id"] = user.id
        row["upload_batch_id"] = batch_id
        incoming_rows.append(row)
        history_records.append({"user_id": user.id, "url": url})

    inserted = 0
    if incoming_rows:
        history_stmt = (
            pg_insert(UrlHistory)
            .values(history_records)
            .on_conflict_do_nothing(index_elements=["user_id", "url"])
        )
        db.execute(history_stmt)

        rows_stmt = (
            pg_insert(CsvRow)
            .values(incoming_rows)
            .on_conflict_do_nothing(index_elements=["user_id", "url"])
        )
        result = db.execute(rows_stmt)
        inserted = result.rowcount
        db.commit()

    skipped_history_duplicates = len(seen_in_upload) - len(incoming_rows)

    return {
        "batch_id": batch_id,
        "unique_urls_received": len(seen_in_upload),
        "inserted": inserted,
        "skipped_existing_url_history": skipped_history_duplicates,
        "skipped_duplicate_in_upload": duplicate_in_upload,
        "skipped_duplicates": skipped_history_duplicates + duplicate_in_upload,
    }
