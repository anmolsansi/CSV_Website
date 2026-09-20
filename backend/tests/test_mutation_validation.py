from datetime import datetime

import pytest

from app.schemas import JobTrackUpdateIn
from app.services.validation import (
    MAX_BULK_IDS,
    MAX_COMPANY_TITLE_CHARS,
    MAX_JOB_URL_CHARS,
    MAX_NOTES_CHARS,
    STATUS_VALUES,
    ValidationContractError,
    explicit_model_fields,
    format_error_detail,
    normalize_bulk_ids,
    parse_timestamp,
    require_owned_bulk_ids,
    validate_job_url,
    validate_status,
    validate_text_limits,
)


@pytest.mark.parametrize("status", STATUS_VALUES)
def test_parameterized_status_allowed_and_rejected(status):
    assert validate_status(status) == status


@pytest.mark.parametrize("status", ["", "unknown", "APPLIED", 123, None])
def test_parameterized_status_allowed_and_rejected_invalid(status):
    with pytest.raises(ValidationContractError) as exc_info:
        validate_status(status)

    error = exc_info.value
    assert error.status_code == 422
    assert error.field == "status"
    assert error.code == "validation_error"


def test_omitted_null_empty_date_semantics():
    omitted = JobTrackUpdateIn(company="Acme")
    assert explicit_model_fields(omitted) == {"company": "Acme"}

    explicit_null = JobTrackUpdateIn(applied_at=None)
    assert explicit_model_fields(explicit_null) == {"applied_at": None}
    assert parse_timestamp(
        explicit_model_fields(explicit_null)["applied_at"],
        field="applied_at",
    ) is None

    explicit_empty = JobTrackUpdateIn(follow_up_at="")
    assert explicit_model_fields(explicit_empty) == {"follow_up_at": ""}
    assert parse_timestamp(
        explicit_model_fields(explicit_empty)["follow_up_at"],
        field="follow_up_at",
    ) is None

    with pytest.raises(ValidationContractError) as exc_info:
        parse_timestamp(None, field="applied_at", allow_clear=False)

    assert exc_info.value.to_detail() == {
        "code": "validation_error",
        "fields": [
            {"field": "applied_at", "message": "This timestamp cannot be cleared."}
        ],
    }


def test_date_only_kolkata_conversion():
    assert parse_timestamp(
        "2026-01-02",
        timezone_name="Asia/Kolkata",
        field="applied_at",
    ) == datetime(2026, 1, 1, 18, 30)

    assert parse_timestamp(
        "2026-01-02T00:00:00+05:30",
        field="applied_at",
    ) == datetime(2026, 1, 1, 18, 30)

    assert parse_timestamp(
        "2026-01-02T00:00:00Z",
        field="applied_at",
    ) == datetime(2026, 1, 2, 0, 0)

    for value, timezone_name in [
        ("2026-01-02T00:00:00", None),
        ("2026-02-30", "Asia/Kolkata"),
        ("2026-01-02", None),
        ("not-a-date", "Asia/Kolkata"),
    ]:
        with pytest.raises(ValidationContractError):
            parse_timestamp(
                value,
                timezone_name=timezone_name,
                field="applied_at",
            )


def test_url_and_text_limits():
    accepted_url = "https://jobs.example.com/apply?source=jobgrid"
    assert validate_job_url(accepted_url) == accepted_url

    accepted = validate_text_limits(
        {
            "company": "c" * MAX_COMPANY_TITLE_CHARS,
            "title": "t" * MAX_COMPANY_TITLE_CHARS,
            "notes": "n" * MAX_NOTES_CHARS,
        }
    )
    assert len(accepted["company"]) == MAX_COMPANY_TITLE_CHARS
    assert len(accepted["title"]) == MAX_COMPANY_TITLE_CHARS
    assert len(accepted["notes"]) == MAX_NOTES_CHARS

    for value in [
        "ftp://jobs.example.com/1",
        "https:///missing-host",
        "https://user:secret@jobs.example.com/1",
        "https://jobs.example.com/a path",
    ]:
        with pytest.raises(ValidationContractError):
            validate_job_url(value)

    with pytest.raises(ValidationContractError) as exc_info:
        validate_job_url(
            "https://jobs.example.com/" + ("a" * MAX_JOB_URL_CHARS)
        )
    assert exc_info.value.status_code == 413
    assert exc_info.value.field == "url"

    for field, value in [
        ("company", "c" * (MAX_COMPANY_TITLE_CHARS + 1)),
        ("title", "t" * (MAX_COMPANY_TITLE_CHARS + 1)),
        ("notes", "n" * (MAX_NOTES_CHARS + 1)),
    ]:
        with pytest.raises(ValidationContractError) as exc_info:
            validate_text_limits({field: value})
        assert exc_info.value.field == field


def test_bulk_duplicate_missing_foreign_and_max_count():
    normalized = normalize_bulk_ids([3, 1, 3, 2, 1])
    assert normalized.ids == (3, 1, 2)
    assert normalized.source_indices == {
        3: (0, 2),
        1: (1, 4),
        2: (3,),
    }
    assert require_owned_bulk_ids(normalized, {1, 2, 3}) == (3, 1, 2)

    with pytest.raises(ValidationContractError) as exc_info:
        require_owned_bulk_ids(normalized, {1, 2})
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"
    assert exc_info.value.field == "ids[0]"
    assert exc_info.value.message == "One or more applications were not found."

    maximum = normalize_bulk_ids(list(range(1, MAX_BULK_IDS + 1)))
    assert len(maximum.ids) == MAX_BULK_IDS

    with pytest.raises(ValidationContractError):
        normalize_bulk_ids(list(range(1, MAX_BULK_IDS + 2)))

    for values in [[], [0], [-1], [True], ["1"]]:
        with pytest.raises(ValidationContractError):
            normalize_bulk_ids(values)


def test_compatibility_error_formatter():
    assert format_error_detail("Invalid datetime value") == {
        "code": "validation_error",
        "fields": [
            {"field": "__root__", "message": "Invalid datetime value"}
        ],
    }

    assert format_error_detail({"status": "Invalid status"}) == {
        "code": "validation_error",
        "fields": [{"field": "status", "message": "Invalid status"}],
    }

    new_detail = {
        "code": "invalid_application",
        "fields": [
            {"field": "status", "message": "Invalid status"},
            {"field": "applied_at", "message": "Invalid date"},
        ],
    }
    assert format_error_detail(new_detail) == new_detail

    safe = format_error_detail(
        {"payload": {"secret": "do-not-echo"}},
        default_code="invalid_request",
    )
    assert safe == {
        "code": "invalid_request",
        "fields": [{"field": "__root__", "message": "Validation failed."}],
    }
    assert "do-not-echo" not in str(safe)
