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

EXPECTED_COLUMNS = set(CSV_COLUMNS)


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
    filename = file.filename or "unknown.csv"

    # sep=None lets pandas sniff comma vs tab delimiter.
    df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", dtype=str)
    df = df.where(pd.notnull(df), None)

    detected_columns = list(df.columns)
    missing_expected = sorted(EXPECTED_COLUMNS - set(detected_columns))
    unknown_extra = sorted(set(detected_columns) - EXPECTED_COLUMNS)

    if "url" not in df.columns:
        raise HTTPException(
            400,
            detail={
                "error": "CSV must contain a 'url' column",
                "filename": filename,
                "columns_detected": detected_columns,
                "missing_expected_columns": missing_expected,
            },
        )

    batch_id = str(uuid.uuid4())
    incoming_rows = []
    history_records = []
    seen_in_upload = set()
    duplicate_in_upload = 0
    missing_url_count = 0
    invalid_rows = []  # rows without URLs for optional download

    existing_history_urls = {
        url
        for (url,) in db.query(UrlHistory.url)
        .filter(UrlHistory.user_id == user.id)
        .all()
    }

    for idx, r in df.iterrows():
        url = _clean_url(r.get("url"))
        if not url:
            missing_url_count += 1
            invalid_rows.append({col: r.get(col) for col in detected_columns})
            continue

        if url in seen_in_upload:
            duplicate_in_upload += 1
            invalid_rows.append({col: r.get(col) for col in detected_columns})
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

    # Build invalid rows CSV in memory for download
    invalid_rows_csv = None
    if invalid_rows:
        buf = io.StringIO()
        invalid_df = pd.DataFrame(invalid_rows)
        invalid_df.to_csv(buf, index=False)
        invalid_rows_csv = buf.getvalue()

    return {
        "filename": filename,
        "batch_id": batch_id,
        "total_rows_received": len(df),
        "unique_urls_received": len(seen_in_upload),
        "inserted": inserted,
        "duplicate_in_upload": duplicate_in_upload,
        "duplicate_from_history": skipped_history_duplicates,
        "rows_missing_url": missing_url_count,
        "columns_detected": detected_columns,
        "missing_expected_columns": missing_expected,
        "unknown_extra_columns": unknown_extra,
        "invalid_rows_csv": invalid_rows_csv,
    }
