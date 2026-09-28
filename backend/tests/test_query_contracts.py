from datetime import datetime

from app.models import CsvRow, JobTrack, User
from app.routers.crm import num_expr, parse_dt
from app.routers.rows import _safe_sort_column
from app.services.row_queries import (
    ApplicationQuery,
    RowQuery,
    build_application_query,
    build_row_query,
    order_application_query,
    order_row_query,
)


def _user(db, email):
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=values.pop("url", f"https://example.com/{suffix}"),
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _track(db, user, row, suffix, **values):
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id if row else None,
        url=values.pop("url", row.url if row else f"https://example.com/app/{suffix}"),
        opened_at=values.pop("opened_at", datetime(2026, 9, 1, 12, 0, 0)),
        **values,
    )
    db.add(track)
    db.flush()
    return track


def _row_ids(db, user_id, params):
    query = build_row_query(db, user_id, params)
    return [row.id for row in order_row_query(query, params, _safe_sort_column).all()]


def test_each_filter_and_pair(db_session):
    user = _user(db_session, "filters@jobgrid.test")
    expected = _row(
        db_session,
        user,
        "expected",
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
        salary_max_extracted="210000",
        company_guess="Acme",
        title="Backend Engineer",
        clicked=True,
        error="parser warning",
        jd_text_length="0",
    )
    _row(
        db_session,
        user,
        "control",
        ats_group="lever",
        location_group="onsite",
        search_bucket="frontend",
        decision="reject",
        sponsorship_status="negative",
        fit_category="weak",
        seniority_level="junior",
        work_model_extracted="onsite",
        role_family="design",
        salary_min_extracted="90000",
        salary_max_extracted="120000",
        company_guess="Other",
        title="Designer",
        clicked=False,
        jd_text_length="500",
    )

    params = RowQuery(
        ats_group="GREENHOUSE",
        location_group="REMOTE",
        search_bucket="BACKEND",
        decision="KEEP",
        sponsorship_status="POSITIVE",
        fit_category="STRONG",
        seniority_level="SENIOR",
        work_model="REMOTE",
        role_family="SOFTWARE",
        salary_min=140000,
        salary_max=220000,
        q="backend",
        opened_only=True,
        has_error=True,
        jd_missing=True,
        openable_only=True,
    )
    assert _row_ids(db_session, user.id, params) == [expected.id]

    track = _track(
        db_session,
        user,
        expected,
        "expected",
        company="Acme",
        title="Backend Engineer",
        ats_group="greenhouse",
        search_bucket="backend",
        status="opened",
        notes="priority candidate",
    )
    app_params = ApplicationQuery(
        status="opened",
        company="ac",
        ats_group="GREENHOUSE",
        search_bucket="BACKEND",
        location_group="REMOTE",
        decision="KEEP",
        sponsorship_status="POSITIVE",
        has_error=True,
        jd_missing=True,
        q="priority",
        sort_by="opened_at",
    )
    app_query = build_application_query(
        db_session,
        user.id,
        app_params,
        numeric_expression=num_expr,
        parse_datetime=parse_dt,
    )
    app_rows = order_application_query(app_query, app_params, num_expr).all()
    assert [item.id for item in app_rows] == [track.id]


def test_two_users_same_url_no_query_leaks_ownership(db_session):
    first = _user(db_session, "first@jobgrid.test")
    second = _user(db_session, "second@jobgrid.test")
    shared_url = "https://example.com/shared"
    first_row = _row(db_session, first, "first", url=shared_url, title="Shared")
    second_row = _row(db_session, second, "second", url=shared_url, title="Shared")
    first_track = _track(db_session, first, first_row, "first", company="Acme")
    second_track = _track(db_session, second, second_row, "second", company="Acme")

    assert _row_ids(db_session, first.id, RowQuery(q="shared")) == [first_row.id]
    assert _row_ids(db_session, second.id, RowQuery(q="shared")) == [second_row.id]

    first_apps = build_application_query(
        db_session,
        first.id,
        ApplicationQuery(company="Acme"),
        numeric_expression=num_expr,
        parse_datetime=parse_dt,
    ).all()
    second_apps = build_application_query(
        db_session,
        second.id,
        ApplicationQuery(company="Acme"),
        numeric_expression=num_expr,
        parse_datetime=parse_dt,
    ).all()
    assert [item.id for item in first_apps] == [first_track.id]
    assert [item.id for item in second_apps] == [second_track.id]


def test_null_and_empty_columns_keep_documented_semantics(db_session):
    user = _user(db_session, "nulls@jobgrid.test")
    null_jd = _row(db_session, user, "null-jd", jd_text_length=None, error=None)
    empty_jd = _row(db_session, user, "empty-jd", jd_text_length="", error="")
    zero_jd = _row(db_session, user, "zero-jd", jd_text_length="0", error="failed")
    complete = _row(db_session, user, "complete", jd_text_length="450", error=None)

    missing_ids = set(_row_ids(db_session, user.id, RowQuery(jd_missing=True)))
    assert missing_ids == {null_jd.id, empty_jd.id, zero_jd.id}

    error_ids = _row_ids(db_session, user.id, RowQuery(has_error=True))
    assert error_ids == [zero_jd.id]
    assert complete.id not in missing_ids


def test_page_boundaries_and_ties_are_deterministic(db_session):
    user = _user(db_session, "paging@jobgrid.test")
    rows = [
        _row(db_session, user, f"tie-{index}", title="Same title")
        for index in range(5)
    ]
    params = RowQuery(sort_by="title", sort_dir="asc")
    query = build_row_query(db_session, user.id, params)
    ordered = order_row_query(query, params, _safe_sort_column)

    page_one = [row.id for row in ordered.offset(0).limit(2).all()]
    page_two = [row.id for row in ordered.offset(2).limit(2).all()]
    page_three = [row.id for row in ordered.offset(4).limit(2).all()]
    expected = sorted((row.id for row in rows), reverse=True)

    assert page_one + page_two + page_three == expected
    assert len(set(page_one + page_two + page_three)) == 5


def test_confirmed_usa_accepts_only_explicit_affirmative_values(db_session):
    user = _user(db_session, "confirmed-usa@jobgrid.test")
    affirmative = [
        _row(db_session, user, "usa-true", is_usa_role="true"),
        _row(db_session, user, "usa-yes", is_usa_role=" YES "),
        _row(db_session, user, "usa-one", is_usa_role="1"),
    ]
    _row(db_session, user, "usa-false", is_usa_role="false")
    _row(db_session, user, "usa-no", is_usa_role="no")
    _row(db_session, user, "usa-zero", is_usa_role="0")
    _row(db_session, user, "usa-empty", is_usa_role="")
    _row(db_session, user, "usa-null", is_usa_role=None)

    actual = set(_row_ids(db_session, user.id, RowQuery(confirmed_usa=True)))
    assert actual == {row.id for row in affirmative}


def test_unique_company_keeps_first_row_in_active_sort_and_keeps_unknowns(db_session):
    user = _user(db_session, "unique-company@jobgrid.test")
    alpha = _row(
        db_session,
        user,
        "acme-alpha",
        company_guess="Acme",
        title="Alpha Engineer",
    )
    zulu = _row(
        db_session,
        user,
        "acme-zulu",
        company_guess=" acme ",
        title="Zulu Engineer",
    )
    other = _row(
        db_session,
        user,
        "other",
        company_guess="Other Co",
        title="Middle Engineer",
    )
    blank = _row(db_session, user, "blank", company_guess="", title="Blank Company")
    missing = _row(db_session, user, "missing", company_guess=None, title="Missing Company")

    ascending = _row_ids(
        db_session,
        user.id,
        RowQuery(unique_company=True, sort_by="title", sort_dir="asc"),
    )
    descending = _row_ids(
        db_session,
        user.id,
        RowQuery(unique_company=True, sort_by="title", sort_dir="desc"),
    )

    assert alpha.id in ascending
    assert zulu.id not in ascending
    assert zulu.id in descending
    assert alpha.id not in descending
    assert {other.id, blank.id, missing.id}.issubset(set(ascending))
    assert {other.id, blank.id, missing.id}.issubset(set(descending))


def test_unique_company_and_confirmed_usa_compose_with_ats_filter(db_session):
    user = _user(db_session, "combined-filters@jobgrid.test")
    expected = _row(
        db_session,
        user,
        "ashby-acme-a",
        ats_group="ashby",
        company_guess="Acme",
        title="A Engineer",
        is_usa_role="yes",
    )
    _row(
        db_session,
        user,
        "ashby-acme-z",
        ats_group="ashby",
        company_guess=" ACME ",
        title="Z Engineer",
        is_usa_role="true",
    )
    other = _row(
        db_session,
        user,
        "ashby-other",
        ats_group="ashby",
        company_guess="Other Co",
        title="B Engineer",
        is_usa_role="1",
    )
    _row(
        db_session,
        user,
        "ashby-non-usa",
        ats_group="ashby",
        company_guess="Outside Co",
        title="C Engineer",
        is_usa_role="false",
    )
    _row(
        db_session,
        user,
        "greenhouse-usa",
        ats_group="greenhouse",
        company_guess="Greenhouse Co",
        title="D Engineer",
        is_usa_role="true",
    )

    actual = _row_ids(
        db_session,
        user.id,
        RowQuery(
            ats_group="ASHBY",
            unique_company=True,
            confirmed_usa=True,
            sort_by="title",
            sort_dir="asc",
        ),
    )
    assert actual == [expected.id, other.id]
