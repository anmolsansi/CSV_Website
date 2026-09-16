from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def stage_service() -> None:
    path = Path("backend/app/services/row_queries.py")
    text = path.read_text()
    text = replace_once(
        text,
        "from sqlalchemy import Float, asc, desc, func, or_\n",
        "from sqlalchemy import Float, asc, case, desc, func, or_\n",
        "service sqlalchemy imports",
    )
    text = replace_once(
        text,
        "from ..models import CsvRow, JobTrack\n",
        "from ..models import CSV_COLUMNS, CsvRow, JobTrack\n",
        "service model imports",
    )
    anchor = "\n\ndef build_row_query(db: Session, user_id: int, params: RowQuery) -> Query:\n"
    resolver = r'''

ROW_NUMERIC_SORT_COLUMNS = frozenset({
    "page_number",
    "posted_age_days",
    "jd_text_length",
    "resume_match_score",
})


def resolve_row_sort_column(sort_by: str):
    """Resolve the shared RowQuery sort expression without depending on a router."""
    if sort_by == "created_at":
        return CsvRow.created_at
    if sort_by == "clicked_at":
        return CsvRow.clicked_at
    if sort_by not in CSV_COLUMNS:
        raise ValueError("Invalid sort column")

    column = getattr(CsvRow, sort_by)
    if sort_by in ROW_NUMERIC_SORT_COLUMNS:
        cleaned = func.nullif(func.regexp_replace(column, r"[%,$,\s]", "", "g"), "")
        return case(
            (cleaned.op("~")(r"^-?\d+(\.\d+)?$"), func.cast(cleaned, Float)),
            else_=None,
        )
    return column
'''
    if anchor not in text:
        raise RuntimeError("service build_row_query anchor missing")
    text = text.replace(anchor, resolver + anchor, 1)
    old_order = '''def order_row_query(
    query: Query,
    params: RowQuery,
    sort_column_resolver: Callable[[str], object],
) -> Query:
    """Apply the current row sort adapter plus the stable id-desc tie breaker."""
    sort_column = sort_column_resolver(params.sort_by)
    order_func = asc if params.sort_dir == "asc" else desc
    return query.order_by(order_func(sort_column).nullslast(), CsvRow.id.desc())
'''
    new_order = '''def order_row_query(
    query: Query,
    params: RowQuery,
    sort_column_resolver: Callable[[str], object] | None = None,
) -> Query:
    """Apply the shared row ordering plus the stable id-desc tie breaker."""
    resolver = sort_column_resolver or resolve_row_sort_column
    sort_column = resolver(params.sort_by)
    order_func = asc if params.sort_dir == "asc" else desc
    return query.order_by(order_func(sort_column).nullslast(), CsvRow.id.desc())
'''
    text = replace_once(text, old_order, new_order, "service order_row_query")
    path.write_text(text)


def stage_router() -> None:
    path = Path("backend/app/routers/crm.py")
    text = path.read_text()
    text = replace_once(
        text,
        "from ..services.row_queries import ApplicationQuery, build_application_query, order_application_query\n",
        "from ..services.row_queries import (\n"
        "    ApplicationQuery,\n"
        "    RowQuery,\n"
        "    build_application_query,\n"
        "    build_row_query,\n"
        "    order_application_query,\n"
        "    order_row_query,\n"
        "    resolve_row_sort_column,\n"
        ")\n",
        "crm row query imports",
    )
    marker = "# ─── Export ───────────────────────────────────────────────────────────────\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError("crm export marker missing")
    export_block = r'''# ─── Export ───────────────────────────────────────────────────────────────

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
'''
    text = text[:start] + export_block
    path.write_text(text)


def stage_tests() -> None:
    path = Path("backend/tests/test_filtered_exports.py")
    if path.exists():
        raise RuntimeError("test_filtered_exports.py already exists")
    path.write_text(r'''import csv
import io
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.models import CsvRow, JobTrack, User


def _login(client, email):
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200


def _session(engine):
    return sessionmaker(bind=engine)()


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg006-{suffix}",
        url=values.pop("url", f"https://jobs.example/{suffix}"),
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _track(db, user, row, suffix, **values):
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id if row else None,
        url=values.pop("url", row.url if row else f"https://jobs.example/app/{suffix}"),
        opened_at=values.pop("opened_at", datetime(2026, 9, 1, 12, 0, 0)),
        **values,
    )
    db.add(track)
    db.flush()
    return track


def test_filtered_export_equals_all_list_pages(client, engine):
    email = "jg006-parity@jobgrid.test"
    _login(client, email)

    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        expected_urls = []
        for index in range(61):
            row = _row(
                db,
                user,
                f"match-{index}",
                title=f"Engineer {index:03d}",
                company_guess="Acme",
                ats_group="greenhouse",
                location_group="remote",
                search_bucket="backend",
                decision="keep",
                sponsorship_status="positive",
                fit_category="strong",
                seniority_level="senior",
                work_model_extracted="remote",
                role_family="software",
                salary_min_extracted="150000",
                salary_max_extracted="220000",
                clicked=False,
                jd_text_length="500",
            )
            expected_urls.append(row.url)
        _row(
            db,
            user,
            "control-onsite",
            title="Engineer onsite",
            company_guess="Acme",
            ats_group="greenhouse",
            location_group="onsite",
            search_bucket="backend",
            decision="keep",
            sponsorship_status="positive",
        )
        _row(
            db,
            user,
            "control-sponsorship",
            title="Engineer remote negative",
            company_guess="Acme",
            ats_group="greenhouse",
            location_group="remote",
            search_bucket="backend",
            decision="keep",
            sponsorship_status="negative",
        )
        db.commit()
    finally:
        db.close()

    filters = {
        "location_group": "remote",
        "search_bucket": "backend",
        "decision": "keep",
        "sponsorship_status": "positive",
        "q": "Engineer",
        "sort_by": "title",
        "sort_dir": "asc",
    }
    list_urls = []
    page = 1
    while True:
        response = client.get("/rows", params={**filters, "page": page, "page_size": 25})
        assert response.status_code == 200
        payload = response.json()
        list_urls.extend(item["data"]["url"] for item in payload["rows"])
        if not payload["has_next"]:
            break
        page += 1

    export = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "filtered", **filters},
    )
    assert export.status_code == 200
    export_urls = [item["url"] for item in export.json()]

    assert len(list_urls) == 61
    assert len(export_urls) == 61
    assert export_urls == list_urls
    assert export_urls == sorted(expected_urls)
    assert "https://jobs.example/control-onsite" not in export_urls
    assert "https://jobs.example/control-sponsorship" not in export_urls


def test_selected_empty_never_exports_all(client, engine):
    email = "jg006-empty-selected@jobgrid.test"
    _login(client, email)
    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        _row(db, user, "safe-existing", title="Existing")
        db.commit()
    finally:
        db.close()

    empty = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "selected", "row_ids": ""},
    )
    assert empty.status_code == 422
    assert "attachment" not in empty.headers.get("content-disposition", "")

    malformed = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "scope": "selected", "row_ids": "not-an-id"},
    )
    assert malformed.status_code == 422
    assert "attachment" not in malformed.headers.get("content-disposition", "")


def test_selected_foreign_id(client, engine):
    owner_email = "jg006-owner@jobgrid.test"
    foreign_email = "jg006-foreign@jobgrid.test"
    _login(client, owner_email)

    db = _session(engine)
    try:
        owner = db.query(User).filter_by(email=owner_email).one()
        foreign = User(email=foreign_email)
        db.add(foreign)
        db.flush()
        own_row = _row(db, owner, "owned", title="Owned")
        foreign_row = _row(db, foreign, "foreign", title="Foreign")
        db.commit()
        own_id = own_row.id
        foreign_id = foreign_row.id
    finally:
        db.close()

    response = client.get(
        "/crm/export/dashboard",
        params={
            "format": "json",
            "scope": "selected",
            "row_ids": f"{own_id},{foreign_id}",
        },
    )
    assert response.status_code == 404
    assert "attachment" not in response.headers.get("content-disposition", "")


def test_formula_cells_escaped_in_csv_only(client, engine):
    email = "jg006-formula@jobgrid.test"
    _login(client, email)
    original_title = '=HYPERLINK("https://evil.test","click")'
    original_company = "\t+SUM(1,1)"

    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        row = _row(
            db,
            user,
            "formula",
            title=original_title,
            company_guess=original_company,
        )
        db.commit()
        row_id = row.id
    finally:
        db.close()

    common = {
        "scope": "selected",
        "row_ids": str(row_id),
        "columns": "title,company_guess",
    }
    json_response = client.get(
        "/crm/export/dashboard",
        params={**common, "format": "json"},
    )
    assert json_response.status_code == 200
    json_row = json_response.json()[0]
    assert json_row["title"] == original_title
    assert json_row["company_guess"] == original_company

    csv_response = client.get(
        "/crm/export/dashboard",
        params={**common, "format": "csv"},
    )
    assert csv_response.status_code == 200
    reader = csv.DictReader(io.StringIO(csv_response.text))
    assert reader.fieldnames == ["title", "company_guess", "clicked", "clicked_at"]
    csv_row = next(reader)
    assert csv_row["title"] == "'" + original_title
    assert csv_row["company_guess"] == "'" + original_company

    db = _session(engine)
    try:
        stored = db.query(CsvRow).filter_by(id=row_id).one()
        assert stored.title == original_title
        assert stored.company_guess == original_company
    finally:
        db.close()


def test_unknown_dashboard_column_is_rejected(client, engine):
    email = "jg006-column@jobgrid.test"
    _login(client, email)
    response = client.get(
        "/crm/export/dashboard",
        params={"format": "json", "columns": "title,not_a_real_column"},
    )
    assert response.status_code == 400
    assert "attachment" not in response.headers.get("content-disposition", "")


def test_application_export_uses_shared_filters_and_order(client, engine):
    email = "jg006-apps@jobgrid.test"
    _login(client, email)
    db = _session(engine)
    try:
        user = db.query(User).filter_by(email=email).one()
        first_row = _row(
            db,
            user,
            "app-first",
            title="Backend A",
            company_guess="Acme",
            location_group="remote",
            decision="keep",
            sponsorship_status="positive",
        )
        second_row = _row(
            db,
            user,
            "app-second",
            title="Backend B",
            company_guess="Acme",
            location_group="remote",
            decision="keep",
            sponsorship_status="positive",
        )
        control_row = _row(
            db,
            user,
            "app-control",
            title="Backend C",
            company_guess="Acme",
            location_group="onsite",
            decision="keep",
            sponsorship_status="positive",
        )
        first = _track(
            db,
            user,
            first_row,
            "app-first",
            company="Acme",
            title="Backend A",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 1, 9, 0, 0),
        )
        second = _track(
            db,
            user,
            second_row,
            "app-second",
            company="Acme",
            title="Backend B",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 2, 9, 0, 0),
        )
        _track(
            db,
            user,
            control_row,
            "app-control",
            company="Acme",
            title="Backend C",
            ats_group="greenhouse",
            search_bucket="backend",
            status="opened",
            opened_at=datetime(2026, 9, 3, 9, 0, 0),
        )
        db.commit()
        expected_urls = [first.url, second.url]
    finally:
        db.close()

    response = client.get(
        "/crm/export/applications",
        params={
            "format": "json",
            "scope": "filtered",
            "status": "opened",
            "ats_group": "greenhouse",
            "search_bucket": "backend",
            "location_group": "remote",
            "decision": "keep",
            "sponsorship_status": "positive",
            "sort_by": "opened_at",
            "sort_dir": "asc",
        },
    )
    assert response.status_code == 200
    assert [item["url"] for item in response.json()] == expected_urls


def test_application_selected_scope_rejects_foreign_track(client, engine):
    owner_email = "jg006-app-owner@jobgrid.test"
    foreign_email = "jg006-app-foreign@jobgrid.test"
    _login(client, owner_email)
    db = _session(engine)
    try:
        owner = db.query(User).filter_by(email=owner_email).one()
        foreign = User(email=foreign_email)
        db.add(foreign)
        db.flush()
        owner_row = _row(db, owner, "app-owned-row", title="Owned")
        foreign_row = _row(db, foreign, "app-foreign-row", title="Foreign")
        owner_track = _track(db, owner, owner_row, "app-owned-track", status="opened")
        foreign_track = _track(db, foreign, foreign_row, "app-foreign-track", status="opened")
        db.commit()
        owner_track_id = owner_track.id
        foreign_track_id = foreign_track.id
    finally:
        db.close()

    response = client.get(
        "/crm/export/applications",
        params={
            "format": "json",
            "scope": "selected",
            "row_ids": f"{owner_track_id},{foreign_track_id}",
        },
    )
    assert response.status_code == 404
    assert "attachment" not in response.headers.get("content-disposition", "")
''')


def stage_docs() -> None:
    path = Path("docs/JOBGRID_BUILD_GUIDE.md")
    text = path.read_text().rstrip() + "\n"
    if "## JG-006 shared filtered export contract" in text:
        raise RuntimeError("JG-006 build-guide section already exists")
    text += r'''

## JG-006 shared filtered export contract

JG-006 routes ordinary Dashboard and Applications exports through the same account-scoped query contracts used by the live tables. It does not change portable backup behavior, application-versus-visit semantics, or database schema.

`GET /crm/export/dashboard` now accepts the complete `RowQuery` filter/sort set using the same snake_case wire names as `GET /rows`: `sort_by`, `sort_dir`, `ats_group`, `location_group`, `search_bucket`, `decision`, `sponsorship_status`, `fit_category`, `seniority_level`, `work_model`, `role_family`, `salary_min`, `salary_max`, `q`, `opened_only`, `unopened_only`, `has_error`, `jd_missing`, and `openable_only`. Filtered export does not reuse table pagination. It applies the same primary sort, null-last behavior, and `CsvRow.id DESC` tie breaker as the table.

`GET /crm/export/applications` accepts every `ApplicationQuery` filter already supported by the applications table, including date/score/follow-up and row-derived filters, plus `sort_by` and `sort_dir`. Non-computed ordering uses the shared SQL query builder. `priority_score` and `triage` preserve the table's existing Python-computed ordering behavior, including the stable descending-ID tie order.

Both export endpoints accept additive `scope=all|filtered|selected`:

- omitted `scope` preserves legacy behavior: supplied filters apply, and valid `row_ids` intersect that result;
- `scope=all` exports the authenticated account's unarchived rows/applications without filter predicates;
- `scope=filtered` applies the shared filter contract with no offset or limit;
- `scope=selected` requires a non-empty comma-separated list of at most 500 positive IDs owned by the authenticated account. Missing, malformed, or foreign IDs reject the whole request instead of falling back to all data.

Dashboard `columns` is an ordered allowlist of persisted `CSV_COLUMNS`. Unknown or empty requested columns return HTTP 400. `clicked` and `clicked_at` remain appended compatibility fields.

CSV serialization is spreadsheet-safe by default. Text beginning with `=`, `+`, `-`, `@`, or control whitespace followed by one of those markers is prefixed with a single quote only in the downloaded CSV stream. Stored values and JSON exports remain lossless. Export rows are serialized incrementally in bounded iteration rather than duplicated into a second in-memory list. Empty CSV behavior remains an empty body and JSON remains `[]`.

Export audit events contain only the exported count, format, and a fixed map of boolean filter-presence flags. Filter values, URLs, notes, job descriptions, and other private text are not written into export event metadata.

Focused verification:

```sh
cd backend
python -m compileall app
pytest tests/test_filtered_exports.py -q
pytest tests/test_query_contracts.py -q
pytest tests/ -q
```

The JG-006 regression fixture proves 61 filtered Dashboard matches have the exact same order as all paginated `GET /rows` pages, selected scope never falls back to all rows, foreign selected IDs reject the complete request, CSV formula protection does not mutate JSON/storage, requested column order is preserved, and application export consumes row-derived shared filters and stable ordering.

Rollback is code-only: revert the JG-006 router/service changes together. There is no migration and no persisted export-format transformation to reverse. Local verification does not claim staging acceptance or production release.
'''
    path.write_text(text)


STAGES = {
    "service": stage_service,
    "router": stage_router,
    "tests": stage_tests,
    "docs": stage_docs,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        raise SystemExit(f"usage: {sys.argv[0]} <{'|'.join(STAGES)}>")
    STAGES[sys.argv[1]]()
