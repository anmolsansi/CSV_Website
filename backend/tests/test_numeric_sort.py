from decimal import Decimal

import pytest
from sqlalchemy import column, create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import sessionmaker

from app.models import Base, CsvRow, JobTrack, User
from app.services.numeric_values import (
    MAX_NUMERIC_TEXT_LENGTH,
    install_sqlite_numeric_adapter,
    numeric_text_expression,
    parse_numeric_text,
)
from app.services.row_queries import (
    ApplicationQuery,
    RowQuery,
    build_application_query,
    build_row_query,
    order_application_query,
    order_row_query,
)
from app.routers.crm import num_expr, parse_dt


ACCEPTED_NUMERIC_TEXT = [
    ("2", Decimal("2")),
    (" 10 ", Decimal("10")),
    ("85%", Decimal("85")),
    ("1,000", Decimal("1000")),
    ("$99.50", Decimal("99.50")),
    ("-3", Decimal("-3")),
    ("+.5", Decimal("0.5")),
    ("1.", Decimal("1")),
    ("1 234.50", Decimal("1234.50")),
]

REJECTED_NUMERIC_TEXT = [
    None,
    "",
    "   ",
    "invalid",
    "12abc",
    "1.2.3",
    "--3",
    "$",
    "NaN",
    "Infinity",
    "-Infinity",
    "1e6",
]


def _sqlite_session():
    install_sqlite_numeric_adapter()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _user(db, email="numeric@jobgrid.test"):
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"numeric-{suffix}",
        url=f"https://example.com/{suffix}",
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _track(db, user, row, suffix, score):
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        company=f"Company {suffix}",
        title=f"Role {suffix}",
        resume_match_score=score,
        status="opened",
    )
    db.add(track)
    db.flush()
    return track


@pytest.mark.parametrize(("raw", "expected"), ACCEPTED_NUMERIC_TEXT)
def test_negative_decimal_percentage_currency(raw, expected):
    assert parse_numeric_text(raw) == expected


@pytest.mark.parametrize("raw", REJECTED_NUMERIC_TEXT)
def test_rejected_numeric_text_is_null(raw):
    assert parse_numeric_text(raw) is None


def test_long_or_nonfinite_value_is_null():
    assert parse_numeric_text("9" * MAX_NUMERIC_TEXT_LENGTH) == Decimal(
        "9" * MAX_NUMERIC_TEXT_LENGTH
    )
    assert parse_numeric_text("9" * (MAX_NUMERIC_TEXT_LENGTH + 1)) is None
    assert parse_numeric_text(float("inf")) is None
    assert parse_numeric_text(float("nan")) is None


def test_new_sqlite_engine_registers_deterministic_numeric_function():
    install_sqlite_numeric_adapter()
    install_sqlite_numeric_adapter()
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "select jobgrid_numeric(?)", ("$1,000.50",)
            ).scalar_one() == pytest.approx(1000.5)
            assert connection.exec_driver_sql(
                "select jobgrid_numeric(?)", ("invalid",)
            ).scalar_one() is None
    finally:
        engine.dispose()


def test_numeric_order_not_lexical():
    engine, db = _sqlite_session()
    try:
        user = _user(db)
        values = ["2", "10", "85%", "1,000", "$99.50", "-3", "", "invalid"]
        rows = [
            _row(db, user, f"sort-{index}", resume_match_score=value)
            for index, value in enumerate(values)
        ]

        params = RowQuery(sort_by="resume_match_score", sort_dir="asc")
        ordered = order_row_query(
            build_row_query(db, user.id, params),
            params,
        ).all()

        valid_by_value = {row.resume_match_score: row.id for row in rows}
        expected_valid = [
            valid_by_value["-3"],
            valid_by_value["2"],
            valid_by_value["10"],
            valid_by_value["85%"],
            valid_by_value["$99.50"],
            valid_by_value["1,000"],
        ]
        expected_null = sorted(
            [valid_by_value[""], valid_by_value["invalid"]],
            reverse=True,
        )
        assert [row.id for row in ordered] == expected_valid + expected_null
    finally:
        db.close()
        engine.dispose()


def test_invalid_values_last_both_directions():
    engine, db = _sqlite_session()
    try:
        user = _user(db, "null-order@jobgrid.test")
        low = _row(db, user, "low", resume_match_score="2")
        high = _row(db, user, "high", resume_match_score="10")
        invalid_one = _row(db, user, "invalid-one", resume_match_score="")
        invalid_two = _row(db, user, "invalid-two", resume_match_score="oops")

        expected_null_ids = sorted([invalid_one.id, invalid_two.id], reverse=True)
        for direction, expected_valid_ids in (
            ("asc", [low.id, high.id]),
            ("desc", [high.id, low.id]),
        ):
            params = RowQuery(sort_by="resume_match_score", sort_dir=direction)
            result = order_row_query(
                build_row_query(db, user.id, params),
                params,
            ).all()
            assert [row.id for row in result] == expected_valid_ids + expected_null_ids
    finally:
        db.close()
        engine.dispose()


def test_equal_numeric_values_tie_by_descending_id():
    engine, db = _sqlite_session()
    try:
        user = _user(db, "tie@jobgrid.test")
        first = _row(db, user, "tie-first", resume_match_score="10")
        second = _row(db, user, "tie-second", resume_match_score="$10.00")
        params = RowQuery(sort_by="resume_match_score", sort_dir="asc")
        result = order_row_query(build_row_query(db, user.id, params), params).all()
        assert [row.id for row in result] == [second.id, first.id]
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    "field",
    ["page_number", "posted_age_days", "jd_text_length", "resume_match_score"],
)
def test_each_numeric_csv_field_sorts_with_shared_contract(field):
    engine, db = _sqlite_session()
    try:
        user = _user(db, f"{field}@jobgrid.test")
        low = _row(db, user, f"{field}-low", **{field: "2"})
        high = _row(db, user, f"{field}-high", **{field: "10"})
        invalid = _row(db, user, f"{field}-invalid", **{field: "invalid"})
        params = RowQuery(sort_by=field, sort_dir="asc")
        result = order_row_query(build_row_query(db, user.id, params), params).all()
        assert [row.id for row in result] == [low.id, high.id, invalid.id]
    finally:
        db.close()
        engine.dispose()


def test_salary_filters_use_shared_numeric_contract():
    engine, db = _sqlite_session()
    try:
        user = _user(db, "salary@jobgrid.test")
        low = _row(
            db,
            user,
            "salary-low",
            salary_min_extracted="$99.50",
            salary_max_extracted="$150.00",
        )
        high = _row(
            db,
            user,
            "salary-high",
            salary_min_extracted="1,000",
            salary_max_extracted="1,200",
        )
        _row(
            db,
            user,
            "salary-invalid",
            salary_min_extracted="unknown",
            salary_max_extracted="unknown",
        )

        min_query = build_row_query(db, user.id, RowQuery(salary_min=100))
        assert [row.id for row in min_query.all()] == [high.id]

        max_query = build_row_query(db, user.id, RowQuery(salary_max=200))
        assert [row.id for row in max_query.all()] == [low.id]
    finally:
        db.close()
        engine.dispose()


def test_application_score_and_posted_age_use_shared_numeric_contract():
    engine, db = _sqlite_session()
    try:
        user = _user(db, "applications@jobgrid.test")
        young = _row(db, user, "young", posted_age_days="2")
        older = _row(db, user, "older", posted_age_days="10")
        invalid_age = _row(db, user, "invalid-age", posted_age_days="unknown")

        young_track = _track(db, user, young, "young", "85%")
        older_track = _track(db, user, older, "older", "$99.50")
        invalid_track = _track(db, user, invalid_age, "invalid", "invalid")

        age_params = ApplicationQuery(
            posted_age_min=5,
            sort_by="resume_match_score",
            sort_dir="desc",
        )
        age_query = build_application_query(
            db,
            user.id,
            age_params,
            numeric_expression=num_expr,
            parse_datetime=parse_dt,
        )
        age_result = order_application_query(age_query, age_params, num_expr).all()
        assert [track.id for track in age_result] == [older_track.id]

        score_params = ApplicationQuery(max_score=90, sort_by="resume_match_score")
        score_query = build_application_query(
            db,
            user.id,
            score_params,
            numeric_expression=num_expr,
            parse_datetime=parse_dt,
        )
        assert [track.id for track in score_query.all()] == [young_track.id]

        sort_params = ApplicationQuery(
            sort_by="resume_match_score",
            sort_dir="desc",
        )
        sort_result = order_application_query(
            build_application_query(
                db,
                user.id,
                sort_params,
                numeric_expression=num_expr,
                parse_datetime=parse_dt,
            ),
            sort_params,
            num_expr,
        ).all()
        assert [track.id for track in sort_result] == [
            older_track.id,
            young_track.id,
            invalid_track.id,
        ]
    finally:
        db.close()
        engine.dispose()


def test_postgresql_and_sqlite_numeric_expression_compile_by_dialect():
    expression = select(numeric_text_expression(column("score")))

    postgres_sql = str(expression.compile(dialect=postgresql.dialect()))
    assert "char_length(score) > 128" in postgres_sql
    assert "regexp_replace(score" in postgres_sql
    assert "~ '^[+-]?" in postgres_sql
    assert "CAST(" in postgres_sql
    assert " AS NUMERIC)" in postgres_sql
    assert "jobgrid_numeric(score)" not in postgres_sql

    sqlite_sql = str(expression.compile(dialect=sqlite.dialect()))
    assert "jobgrid_numeric(score)" in sqlite_sql
    assert "regexp_replace" not in sqlite_sql


def test_numeric_reads_do_not_modify_stored_source_text():
    engine, db = _sqlite_session()
    try:
        user = _user(db, "stored-text@jobgrid.test")
        original = "$ 1,000.50 %"
        row = _row(db, user, "stored-text", resume_match_score=original)
        params = RowQuery(sort_by="resume_match_score", sort_dir="asc")
        order_row_query(build_row_query(db, user.id, params), params).all()
        db.expire_all()
        assert db.get(CsvRow, row.id).resume_match_score == original
    finally:
        db.close()
        engine.dispose()
