"""JG-016 regressions for atomic validation across every application writer."""

from datetime import datetime
import uuid

import pytest

from app.models import CsvRow, JobLifecycleEvent, JobTrack, User


@pytest.fixture
def writer_user(client, db_session):
    email = f"jg016-{uuid.uuid4()}@example.test"
    assert client.post("/auth/dev-login", json={"email": email}).status_code == 200
    user = db_session.query(User).filter_by(email=email).one()
    user.timezone = "Asia/Kolkata"
    db_session.commit()
    return client, db_session, user


def _add_row(db, user, *, url=None, company="Example Co", title="Engineer"):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id="jg016-test",
        url=url or f"https://example.test/jobs/{uuid.uuid4()}",
        title=title,
        company_guess=company,
        ats_group="greenhouse",
    )
    db.add(row)
    db.commit()
    return row


def _track(db, user, url):
    db.expire_all()
    return db.query(JobTrack).filter_by(user_id=user.id, url=url).one()


def test_endpoint_matrix_invalid_status_never_200(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    single = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "definitely_invalid"},
    )
    bulk = client.patch(
        "/crm/applications/bulk",
        json={"ids": [app["id"]], "patch": {"status": "definitely_invalid"}},
    )
    from_rows = client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [row.id], "status": "definitely_invalid"},
    )
    external_url = "https://external.example.test/invalid-status"
    external = client.post(
        "/crm/import/external",
        json=[{"url": external_url, "status": "definitely_invalid"}],
    )

    assert single.status_code == 422
    assert bulk.status_code == 422
    assert from_rows.status_code == 422
    assert external.status_code == 422

    db.expire_all()
    stored = db.get(JobTrack, app["id"])
    assert stored.status == "opened"
    assert db.query(JobTrack).filter_by(user_id=user.id, url=external_url).count() == 0


def test_second_invalid_record_rolls_back_batch(writer_user):
    client, db, user = writer_user
    first_url = "https://external.example.test/valid-first"
    response = client.post(
        "/crm/import/external",
        json=[
            {
                "url": first_url,
                "company": "Valid Co",
                "status": "opened",
            },
            {
                "url": "ftp://external.example.test/invalid-second",
                "company": "Invalid Co",
                "status": "opened",
            },
        ],
    )

    assert response.status_code == 422
    db.expire_all()
    assert db.query(JobTrack).filter_by(user_id=user.id, url=first_url).count() == 0


def test_date_clear_with_applied_status_rejected(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    applied = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "applied"},
    )
    assert applied.status_code == 200

    before = _track(db, user, row.url).applied_at
    assert before is not None

    cleared = client.patch(
        f"/crm/applications/{app['id']}",
        json={"applied_at": None},
    )

    assert cleared.status_code == 422
    detail = cleared.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["fields"][0]["field"] == "applied_at"

    after = _track(db, user, row.url)
    assert after.status == "applied"
    assert after.applied_at == before


def test_concurrent_duplicate_returns_safe_conflict_or_existing_record(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user)

    first = client.post(f"/crm/from-row/{row.id}")
    second = client.post(f"/crm/from-row/{row.id}")

    assert first.status_code == 200
    assert second.status_code in {200, 409}
    if second.status_code == 200:
        assert second.json()["id"] == first.json()["id"]

    db.expire_all()
    assert db.query(JobTrack).filter_by(user_id=user.id, url=row.url).count() == 1


def test_date_only_patch_uses_authenticated_account_timezone(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    response = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "applied", "applied_at": "2026-01-02"},
    )

    assert response.status_code == 200
    assert _track(db, user, row.url).applied_at == datetime(2026, 1, 1, 18, 30)


def test_applypilot_retry_preserves_first_applied_at(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    first = client.post(
        "/crm/applypilot/import",
        json=[
            {
                "url": app["url"],
                "submitted": True,
                "submitted_at": "2026-09-18T04:30:00Z",
            }
        ],
    )
    second = client.post(
        "/crm/applypilot/import",
        json=[{"url": app["url"], "submitted": True}],
    )

    assert first.status_code == 200
    assert second.status_code == 200
    track = _track(db, user, row.url)
    assert track.applied_at == datetime(2026, 9, 18, 4, 30)
    assert (
        db.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="applied_date_corrected",
        )
        .count()
        == 0
    )


def test_from_rows_rejects_foreign_id_before_any_write(writer_user):
    client, db, user = writer_user
    own_row = _add_row(db, user)

    foreign_user = User(email=f"foreign-{uuid.uuid4()}@example.test")
    db.add(foreign_user)
    db.flush()
    foreign_row = CsvRow(
        user_id=foreign_user.id,
        upload_batch_id="jg016-foreign",
        url=f"https://foreign.example.test/{uuid.uuid4()}",
        title="Foreign",
        company_guess="Foreign Co",
    )
    db.add(foreign_row)
    db.commit()

    response = client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [own_row.id, foreign_row.id]},
    )

    assert response.status_code == 404
    db.expire_all()
    assert db.query(JobTrack).filter_by(user_id=user.id, url=own_row.url).count() == 0


def test_from_row_rejects_invalid_source_url_without_write(writer_user):
    client, db, user = writer_user
    row = _add_row(db, user, url="ftp://example.test/not-http")

    response = client.post(f"/crm/from-row/{row.id}")

    assert response.status_code == 422
    db.expire_all()
    assert db.query(JobTrack).filter_by(user_id=user.id).count() == 0


def test_external_import_date_only_and_overlong_text_are_prevalidated(writer_user):
    client, db, user = writer_user
    good_url = "https://external.example.test/date-only"
    good = client.post(
        "/crm/import/external",
        json=[
            {
                "url": good_url,
                "status": "applied",
                "applied_at": "2026-01-02",
            }
        ],
    )
    assert good.status_code == 200
    assert _track(db, user, good_url).applied_at == datetime(2026, 1, 1, 18, 30)

    bad_url = "https://external.example.test/too-long"
    bad = client.post(
        "/crm/import/external",
        json=[{"url": bad_url, "company": "x" * 301, "status": "opened"}],
    )
    assert bad.status_code == 422
    db.expire_all()
    assert db.query(JobTrack).filter_by(user_id=user.id, url=bad_url).count() == 0


def test_legacy_validation_report_is_aggregate_and_account_scoped(writer_user):
    client, db, user = writer_user
    own = JobTrack(
        user_id=user.id,
        url="ftp://legacy.example.test/own",
        company="Legacy",
        title="Legacy",
        status="legacy_status",
        opened_at=datetime(2026, 9, 1, 12, 0),
    )
    foreign_user = User(email=f"report-foreign-{uuid.uuid4()}@example.test")
    db.add_all([own, foreign_user])
    db.flush()
    foreign = JobTrack(
        user_id=foreign_user.id,
        url="ftp://legacy.example.test/foreign",
        company="Foreign",
        title="Foreign",
        status="foreign_invalid",
        opened_at=datetime(2026, 9, 1, 12, 0),
    )
    db.add(foreign)
    db.commit()

    response = client.get("/crm/applications/validation-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["repair_mode"] == "manual_only"
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["invalid_status"] == 1
    assert payload["counts"]["invalid_url"] == 1
    assert "legacy.example.test" not in response.text
