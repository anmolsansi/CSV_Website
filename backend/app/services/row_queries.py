from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from sqlalchemy import Float, asc, case, desc, func, or_
from sqlalchemy.orm import Query, Session

from ..models import CSV_COLUMNS, CsvRow, JobTrack


@dataclass(frozen=True)
class RowQuery:
    sort_by: str = "created_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    ats_group: str | None = None
    location_group: str | None = None
    search_bucket: str | None = None
    decision: str | None = None
    sponsorship_status: str | None = None
    fit_category: str | None = None
    seniority_level: str | None = None
    work_model: str | None = None
    role_family: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    q: str | None = None
    opened_only: bool = False
    unopened_only: bool = False
    has_error: bool = False
    jd_missing: bool = False
    openable_only: bool = False


@dataclass(frozen=True)
class ApplicationQuery:
    status: str | None = None
    company: str | None = None
    ats_group: str | None = None
    search_bucket: str | None = None
    quick_range: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_score: float | None = None
    max_score: float | None = None
    follow_up_due: bool = False
    opened_not_applied: bool = False
    q: str | None = None
    location_group: str | None = None
    decision: str | None = None
    sponsorship_status: str | None = None
    posted_age_min: float | None = None
    posted_age_max: float | None = None
    follow_up_today: bool = False
    follow_up_overdue: bool = False
    follow_up_none: bool = False
    has_error: bool = False
    jd_missing: bool = False
    date_applied_from: str | None = None
    date_applied_to: str | None = None
    applied_only: bool = False
    sort_by: str = "opened_at"
    sort_dir: Literal["asc", "desc"] = "desc"


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


def build_row_query(db: Session, user_id: int, params: RowQuery) -> Query:
    """Build the account-scoped CsvRow predicate query without pagination."""
    query = db.query(CsvRow).filter(
        CsvRow.user_id == user_id,
        CsvRow.archived.is_(False),
    )

    equality_filters = (
        (params.ats_group, CsvRow.ats_group),
        (params.location_group, CsvRow.location_group),
        (params.search_bucket, CsvRow.search_bucket),
        (params.decision, CsvRow.decision),
        (params.sponsorship_status, CsvRow.sponsorship_status),
        (params.fit_category, CsvRow.fit_category),
        (params.seniority_level, CsvRow.seniority_level),
        (params.work_model, CsvRow.work_model_extracted),
        (params.role_family, CsvRow.role_family),
    )
    for value, column in equality_filters:
        if value:
            query = query.filter(func.lower(column) == value.lower())

    if params.salary_min is not None:
        query = query.filter(
            CsvRow.salary_min_extracted.isnot(None),
            func.cast(CsvRow.salary_min_extracted, Float) >= params.salary_min,
        )
    if params.salary_max is not None:
        query = query.filter(
            CsvRow.salary_max_extracted.isnot(None),
            func.cast(CsvRow.salary_max_extracted, Float) <= params.salary_max,
        )
    if params.has_error:
        query = query.filter(CsvRow.error.isnot(None), CsvRow.error != "")
    if params.jd_missing:
        query = query.filter(
            (CsvRow.jd_text_length.is_(None))
            | (CsvRow.jd_text_length == "")
            | (CsvRow.jd_text_length == "0")
        )
    if params.q:
        needle = params.q.lower()
        query = query.filter(
            func.lower(CsvRow.url).contains(needle)
            | func.lower(CsvRow.company_guess).contains(needle)
            | func.lower(CsvRow.title).contains(needle)
        )
    if params.opened_only:
        query = query.filter(CsvRow.clicked.is_(True))
    if params.unopened_only:
        query = query.filter(CsvRow.clicked.is_(False))
    if params.openable_only:
        url = func.lower(func.trim(CsvRow.url))
        query = query.filter(url.like("https://%") | url.like("http://%"))

    return query


def order_row_query(
    query: Query,
    params: RowQuery,
    sort_column_resolver: Callable[[str], object] | None = None,
) -> Query:
    """Apply the shared row ordering plus the stable id-desc tie breaker."""
    resolver = sort_column_resolver or resolve_row_sort_column
    sort_column = resolver(params.sort_by)
    order_func = asc if params.sort_dir == "asc" else desc
    return query.order_by(order_func(sort_column).nullslast(), CsvRow.id.desc())


def build_application_query(
    db: Session,
    user_id: int,
    params: ApplicationQuery,
    *,
    numeric_expression: Callable[[object], object],
    parse_datetime: Callable[[str | None], datetime | None],
    now: datetime | None = None,
) -> Query:
    """Build the account-scoped JobTrack predicate query without pagination."""
    query = db.query(JobTrack).filter(JobTrack.user_id == user_id)

    if params.status:
        query = query.filter(JobTrack.status == params.status)
    if params.company:
        query = query.filter(func.lower(JobTrack.company).contains(params.company.lower()))
    if params.ats_group:
        query = query.filter(func.lower(JobTrack.ats_group) == params.ats_group.lower())
    if params.search_bucket:
        query = query.filter(func.lower(JobTrack.search_bucket) == params.search_bucket.lower())

    row_filter_requested = any(
        (
            params.location_group,
            params.decision,
            params.sponsorship_status,
            params.has_error,
            params.jd_missing,
            params.posted_age_min is not None,
            params.posted_age_max is not None,
        )
    )
    if row_filter_requested:
        query = query.join(CsvRow, CsvRow.id == JobTrack.csv_row_id, isouter=True)
    if params.location_group:
        query = query.filter(func.lower(CsvRow.location_group) == params.location_group.lower())
    if params.decision:
        query = query.filter(func.lower(CsvRow.decision) == params.decision.lower())
    if params.sponsorship_status:
        query = query.filter(func.lower(CsvRow.sponsorship_status) == params.sponsorship_status.lower())
    if params.has_error:
        query = query.filter(CsvRow.error.isnot(None), CsvRow.error != "")
    if params.jd_missing:
        query = query.filter(
            (CsvRow.jd_text_length.is_(None))
            | (CsvRow.jd_text_length == "")
            | (CsvRow.jd_text_length == "0")
        )

    if params.q:
        needle = params.q.lower()
        query = query.filter(
            or_(
                func.lower(JobTrack.company).contains(needle),
                func.lower(JobTrack.title).contains(needle),
                func.lower(JobTrack.url).contains(needle),
                func.lower(JobTrack.notes).contains(needle),
            )
        )

    current_time = now or datetime.utcnow()
    start = parse_datetime(params.date_from)
    end = parse_datetime(params.date_to)
    if params.quick_range == "last_24_hours":
        start, end = current_time - timedelta(hours=24), current_time
    elif params.quick_range == "last_7_days":
        start, end = current_time - timedelta(days=7), current_time
    elif params.quick_range == "last_30_days":
        start, end = current_time - timedelta(days=30), current_time
    elif params.quick_range == "today":
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = today_start, today_start + timedelta(days=1)
    elif params.quick_range == "yesterday":
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = today_start - timedelta(days=1), today_start

    if start:
        query = query.filter(JobTrack.opened_at >= start)
    if end:
        query = query.filter(JobTrack.opened_at < end)

    if params.posted_age_min is not None:
        query = query.filter(numeric_expression(CsvRow.posted_age_days) >= params.posted_age_min)
    if params.posted_age_max is not None:
        query = query.filter(numeric_expression(CsvRow.posted_age_days) <= params.posted_age_max)

    score = numeric_expression(JobTrack.resume_match_score)
    if params.min_score is not None:
        query = query.filter(score >= params.min_score)
    if params.max_score is not None:
        query = query.filter(score <= params.max_score)

    if params.follow_up_due:
        query = query.filter(
            JobTrack.follow_up_at.isnot(None),
            JobTrack.follow_up_at <= current_time,
        )
    if params.follow_up_today:
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        query = query.filter(
            JobTrack.follow_up_at >= today_start,
            JobTrack.follow_up_at < today_end,
        )
    if params.follow_up_overdue:
        query = query.filter(
            JobTrack.follow_up_at.isnot(None),
            JobTrack.follow_up_at < current_time,
        )
    if params.follow_up_none:
        query = query.filter(JobTrack.follow_up_at.is_(None))
    if params.opened_not_applied:
        query = query.filter(
            JobTrack.applied_at.is_(None),
            JobTrack.status == "opened",
        )
    if params.applied_only:
        query = query.filter(JobTrack.applied_at.isnot(None))
    if params.date_applied_from:
        applied_start = parse_datetime(params.date_applied_from)
        if applied_start:
            query = query.filter(JobTrack.applied_at >= applied_start)
    if params.date_applied_to:
        applied_end = parse_datetime(params.date_applied_to)
        if applied_end:
            query = query.filter(JobTrack.applied_at < applied_end)

    return query


def order_application_query(
    query: Query,
    params: ApplicationQuery,
    numeric_expression: Callable[[object], object],
) -> Query:
    """Apply database-backed application ordering with a stable id-desc tie breaker."""
    order_func = asc if params.sort_dir == "asc" else desc
    sort_column = (
        numeric_expression(JobTrack.resume_match_score)
        if params.sort_by == "resume_match_score"
        else getattr(JobTrack, params.sort_by)
    )
    return query.order_by(order_func(sort_column).nullslast(), JobTrack.id.desc())
