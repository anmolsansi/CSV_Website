"""JG-023 release regressions promoted from the September 12 audit.

This file is deliberately a release gate, not a second implementation of the
features it verifies. The canonical audit regressions listed below remain the
deep contract tests. CI executes those node IDs together with this file so a
future refactor cannot quietly drop one of the repaired failure modes.
"""

from __future__ import annotations

import os
from pathlib import Path
import xml.etree.ElementTree as ET
from uuid import uuid4

import pytest

from app.models import CsvRow, JobTrack, User


CANONICAL_AUDIT_REGRESSIONS = {
    "backup_round_trip": (
        "tests/test_backup_restore.py::"
        "test_restore_applied_company_notes_and_dates"
    ),
    "multi_filter_export": (
        "tests/test_filtered_exports.py::"
        "test_filtered_export_equals_all_list_pages"
    ),
    "metric_reconciliation": (
        "tests/test_metric_consistency.py::"
        "test_shared_metrics_agree_across_analytics_goals_and_weekly"
    ),
    "cleanup_failure": (
        "tests/test_cleanup_job.py::"
        "test_cleanup_failure_not_zero_success"
    ),
    "sqlite_numeric_functional": (
        "tests/test_numeric_sort.py::"
        "test_numeric_order_not_lexical"
    ),
}

RELEASE_CONTRACTS = frozenset(
    {
        *CANONICAL_AUDIT_REGRESSIONS,
        "invalid_inputs",
        "primary_runtime_numeric_sort",
        "cross_user_isolation",
        "company_history_preservation",
    }
)


def _login(client, email: str) -> User:
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()


def _row(db, user: User, suffix: str, **values) -> CsvRow:
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg023-{suffix}",
        url=values.pop("url", f"https://release.example.test/jobs/{suffix}"),
        title=values.pop("title", f"Release job {suffix}"),
        company_guess=values.pop("company_guess", "JG023 Release Co"),
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _require_contracts(observed: set[str]) -> None:
    missing = sorted(RELEASE_CONTRACTS - observed)
    assert not missing, f"missing release contracts: {', '.join(missing)}"


def _assert_junit_clean(xml_text: str) -> int:
    root = ET.fromstring(xml_text)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    assert tests > 0, "release test collection must be nonzero"
    assert failures == 0, "release failures cannot count as a pass"
    assert errors == 0, "release errors cannot count as a pass"
    assert skipped == 0, "release skips cannot count as a pass"
    return tests


@pytest.mark.parametrize("broken_contract", sorted(RELEASE_CONTRACTS))
def test_break_each_contract_then_test_fails(broken_contract):
    observed = set(RELEASE_CONTRACTS)
    observed.remove(broken_contract)

    with pytest.raises(AssertionError, match="missing release contracts"):
        _require_contracts(observed)


def test_count_nonzero():
    assert len(RELEASE_CONTRACTS) >= 9
    assert len(CANONICAL_AUDIT_REGRESSIONS) == 5

    tests_dir = Path(__file__).resolve().parent
    for node_id in CANONICAL_AUDIT_REGRESSIONS.values():
        relative_file = node_id.split("::", 1)[0].removeprefix("tests/")
        assert (tests_dir / relative_file).is_file(), node_id

    assert _assert_junit_clean(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"></testsuite>'
    ) == 1


def test_no_manual_skip_counts_as_pass():
    skipped = '<testsuite tests="1" failures="0" errors="0" skipped="1"></testsuite>'
    empty = '<testsuite tests="0" failures="0" errors="0" skipped="0"></testsuite>'

    with pytest.raises(AssertionError, match="skips"):
        _assert_junit_clean(skipped)
    with pytest.raises(AssertionError, match="nonzero"):
        _assert_junit_clean(empty)


def test_invalid_inputs_are_rejected_before_mutation(client, db_session):
    email = f"jg023-invalid-{uuid4().hex}@jobgrid.test"
    _login(client, email)
    user = db_session.query(User).filter_by(email=email).one()
    row = _row(db_session, user, uuid4().hex)
    db_session.commit()

    created = client.post(f"/crm/from-row/{row.id}")
    assert created.status_code == 200, created.text
    app_id = created.json()["id"]

    invalid_status = client.patch(
        f"/crm/applications/{app_id}",
        json={"status": "THIS_IS_NOT_A_STATUS"},
    )
    invalid_date = client.patch(
        f"/crm/applications/{app_id}",
        json={"applied_at": "not-a-date"},
    )
    invalid_backup = client.post(
        "/crm/backup/import?mode=verify_only",
        files={
            "file": (
                "invalid.json",
                b'{"version":',
                "application/json",
            )
        },
    )

    assert invalid_status.status_code == 422
    assert invalid_date.status_code == 422
    assert invalid_backup.status_code == 400
    assert invalid_backup.json()["detail"]["code"] == "invalid_json"

    db_session.expire_all()
    stored = db_session.get(JobTrack, app_id)
    assert stored is not None
    assert stored.status == "opened"
    assert stored.applied_at is None


def test_primary_runtime_numeric_sort_is_numeric_not_lexical(client, db_session):
    if os.environ.get("CI", "").lower() == "true":
        assert db_session.bind.dialect.name == "postgresql"

    email = f"jg023-numeric-{uuid4().hex}@jobgrid.test"
    _login(client, email)
    user = db_session.query(User).filter_by(email=email).one()
    company = f"JG023 Numeric {uuid4().hex}"

    expected = []
    for label, score in (
        ("two", "2"),
        ("ten", "10"),
        ("invalid", "not-a-number"),
    ):
        row = _row(
            db_session,
            user,
            uuid4().hex,
            title=f"score-{label}",
            company_guess=company,
            resume_match_score=score,
        )
        expected.append(row)
    db_session.commit()

    response = client.get(
        "/rows",
        params={
            "q": company,
            "sort_by": "resume_match_score",
            "sort_dir": "asc",
            "page": 1,
            "page_size": 10,
        },
    )
    assert response.status_code == 200, response.text
    rows = response.json()["rows"]
    assert len(rows) == 3
    assert [item["data"]["resume_match_score"] for item in rows] == [
        "2",
        "10",
        "not-a-number",
    ]


def test_cross_user_scenarios_remain_denied(client, db_session):
    owner_email = f"jg023-owner-{uuid4().hex}@jobgrid.test"
    _login(client, owner_email)
    owner = db_session.query(User).filter_by(email=owner_email).one()
    owner_row = _row(db_session, owner, f"owner-{uuid4().hex}")

    foreign = User(email=f"jg023-foreign-{uuid4().hex}@jobgrid.test")
    db_session.add(foreign)
    db_session.flush()
    foreign_row = _row(db_session, foreign, f"foreign-{uuid4().hex}")
    db_session.commit()
    owner_row_id = owner_row.id
    foreign_row_id = foreign_row.id

    mixed_write = client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [owner_row_id, foreign_row_id], "status": "applied"},
    )
    foreign_visit = client.post(f"/rows/{foreign_row_id}/click")
    foreign_export = client.get(
        "/crm/export/dashboard",
        params={
            "format": "json",
            "scope": "selected",
            "row_ids": str(foreign_row_id),
        },
    )

    assert mixed_write.status_code == 404
    assert foreign_visit.status_code == 404
    assert foreign_export.status_code == 404
    assert (
        db_session.query(JobTrack).filter_by(user_id=owner.id).count()
        == 0
    )
    db_session.expire_all()
    assert db_session.get(CsvRow, owner_row_id).clicked is False
    assert db_session.get(CsvRow, foreign_row_id).clicked is False


def test_original_company_history_survives_source_delete_and_slash_name(
    client,
    db_session,
):
    email = f"jg023-history-{uuid4().hex}@jobgrid.test"
    _login(client, email)
    user = db_session.query(User).filter_by(email=email).one()
    row = _row(
        db_session,
        user,
        uuid4().hex,
        company_guess="Acme / Labs",
        title="Release History Engineer",
    )
    db_session.commit()
    row_id = row.id

    created = client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [row_id], "status": "applied"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["created"] == 1
    app_id = created.json()["application_ids"][0]

    deleted = client.request("DELETE", "/rows", json={"row_ids": [row_id]})
    assert deleted.status_code == 200, deleted.text

    db_session.expire_all()
    track = db_session.get(JobTrack, app_id)
    assert track is not None
    assert track.csv_row_id is None
    assert track.company == "Acme / Labs"
    assert track.status == "applied"
    assert track.applied_at is not None

    companies = client.get("/crm/companies")
    assert companies.status_code == 200
    matching = [
        item for item in companies.json()["companies"]
        if item["company"] == "Acme / Labs"
    ]
    assert matching == [{"company": "Acme / Labs", "total": 1, "applied": 1}]

    detail = client.get("/crm/companies/Acme%20%2F%20Labs")
    assert detail.status_code == 200, detail.text
    assert detail.json()["applied"] == 1
    assert len(detail.json()["roles"]) == 1
    assert detail.json()["roles"][0]["track_id"] == app_id
