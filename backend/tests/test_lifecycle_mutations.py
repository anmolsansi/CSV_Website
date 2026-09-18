"""JG-009 regressions for lifecycle facts emitted by every active writer."""

from datetime import datetime
import uuid

import pytest

from app.models import CsvRow, JobLifecycleEvent, JobTrack, User


@pytest.fixture
def mutation_user(client, db_session):
    email = f"jg009-{uuid.uuid4()}@example.test"
    assert client.post("/auth/dev-login", json={"email": email}).status_code == 200
    user = db_session.query(User).filter_by(email=email).one()
    return client, db_session, user


def _add_row(db, user, *, suffix=None):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id="jg009-test",
        url=f"https://example.test/jobs/{suffix or uuid.uuid4()}",
        title="Lifecycle Engineer",
        company_guess="Example Co",
        ats_group="greenhouse",
    )
    db.add(row)
    db.commit()
    return row


def _event_kinds(db, user):
    db.expire_all()
    return [
        event.kind
        for event in (
            db.query(JobLifecycleEvent)
            .filter(JobLifecycleEvent.user_id == user.id)
            .order_by(JobLifecycleEvent.id.asc())
            .all()
        )
    ]


@pytest.mark.parametrize(
    ("writer", "expected_kinds"),
    [
        ("click", ["first_visited"]),
        ("from_row", []),
        ("from_rows_applied", ["first_applied", "status_changed"]),
        ("application_patch", ["first_applied", "status_changed"]),
        ("bulk_patch", ["first_applied", "status_changed"]),
        ("followup_preset", ["followup_changed"]),
        ("external_import", ["first_applied", "status_changed"]),
        ("applypilot_import", ["first_applied", "status_changed"]),
    ],
)
def test_all_writer_paths_emit_same_facts(mutation_user, writer, expected_kinds):
    client, db, user = mutation_user
    row = _add_row(db, user, suffix=writer)

    if writer == "click":
        response = client.post(f"/rows/{row.id}/click")
    elif writer == "from_row":
        response = client.post(f"/crm/from-row/{row.id}")
    elif writer == "from_rows_applied":
        response = client.post(
            "/crm/from-rows/bulk",
            json={"row_ids": [row.id], "status": "applied"},
        )
    elif writer == "application_patch":
        app = client.post(f"/crm/from-row/{row.id}").json()
        response = client.patch(
            f"/crm/applications/{app['id']}",
            json={"status": "applied"},
        )
    elif writer == "bulk_patch":
        app = client.post(f"/crm/from-row/{row.id}").json()
        response = client.patch(
            "/crm/applications/bulk",
            json={"ids": [app["id"]], "patch": {"status": "applied"}},
        )
    elif writer == "followup_preset":
        app = client.post(f"/crm/from-row/{row.id}").json()
        response = client.post(f"/crm/applications/{app['id']}/follow-up?preset=3_days")
    elif writer == "external_import":
        response = client.post(
            "/crm/import/external",
            json=[
                {
                    "url": "https://external.example.test/jobs/1",
                    "company": "External Co",
                    "status": "applied",
                    "applied_at": "2026-09-18T04:30:00Z",
                }
            ],
        )
    else:
        app = client.post(f"/crm/from-row/{row.id}").json()
        response = client.post(
            "/crm/applypilot/import",
            json=[
                {
                    "url": app["url"],
                    "submitted": True,
                    "submitted_at": "2026-09-18T04:30:00Z",
                }
            ],
        )

    assert response.status_code == 200
    assert _event_kinds(db, user) == expected_kinds


def test_repeat_patch_same_status(mutation_user):
    client, db, user = mutation_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    first = client.patch(f"/crm/applications/{app['id']}", json={"status": "interview"})
    second = client.patch(f"/crm/applications/{app['id']}", json={"status": "interview"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert _event_kinds(db, user) == ["status_changed"]


def test_bulk_partial_failure(mutation_user):
    client, db, user = mutation_user
    row = _add_row(db, user)
    own_app = client.post(f"/crm/from-row/{row.id}").json()

    other = User(email=f"foreign-{uuid.uuid4()}@example.test")
    db.add(other)
    db.flush()
    foreign = JobTrack(
        user_id=other.id,
        url=f"https://foreign.example.test/{uuid.uuid4()}",
        status="opened",
        opened_at=datetime(2026, 9, 18, 1, 0, 0),
    )
    db.add(foreign)
    db.commit()

    response = client.patch(
        "/crm/applications/bulk",
        json={
            "ids": [own_app["id"], foreign.id],
            "patch": {"status": "applied"},
        },
    )

    assert response.status_code == 404
    db.expire_all()
    own_track = db.get(JobTrack, own_app["id"])
    assert own_track.status == "opened"
    assert own_track.applied_at is None
    assert _event_kinds(db, user) == []


def test_applypilot_replay(mutation_user):
    client, db, user = mutation_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()
    payload = [
        {
            "url": app["url"],
            "submitted": True,
            "submitted_at": "2026-09-18T04:30:00Z",
        }
    ]

    first = client.post("/crm/applypilot/import", json=payload)
    second = client.post("/crm/applypilot/import", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    db.expire_all()
    track = db.get(JobTrack, app["id"])
    assert track.applied_at == datetime(2026, 9, 18, 4, 30, 0)
    assert (
        db.query(JobLifecycleEvent)
        .filter_by(user_id=user.id, kind="first_applied")
        .count()
        == 1
    )
    assert (
        db.query(JobLifecycleEvent)
        .filter_by(user_id=user.id, kind="status_changed")
        .count()
        == 1
    )


def test_reused_operation_id_conflict_is_409_and_rolls_back(mutation_user):
    client, db, user = mutation_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()
    operation_id = str(uuid.uuid4())
    headers = {"X-Operation-ID": operation_id}

    first = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "interview"},
        headers=headers,
    )
    conflict = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "rejected"},
        headers=headers,
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    db.expire_all()
    assert db.get(JobTrack, app["id"]).status == "interview"
    assert (
        db.query(JobLifecycleEvent)
        .filter_by(user_id=user.id, kind="status_changed")
        .count()
        == 1
    )


def test_external_import_preserves_declared_date_without_inventing_one(mutation_user):
    client, db, user = mutation_user
    declared_url = "https://external.example.test/declared"
    status_only_url = "https://external.example.test/status-only"

    response = client.post(
        "/crm/import/external",
        json=[
            {
                "url": declared_url,
                "status": "applied",
                "applied_at": "2026-09-17T20:00:00Z",
            },
            {"url": status_only_url, "status": "applied"},
        ],
    )

    assert response.status_code == 200
    assert response.json() == {"created": 2}
    db.expire_all()
    declared = db.query(JobTrack).filter_by(user_id=user.id, url=declared_url).one()
    status_only = db.query(JobTrack).filter_by(user_id=user.id, url=status_only_url).one()
    assert declared.applied_at == datetime(2026, 9, 17, 20, 0, 0)
    assert status_only.status == "applied"
    assert status_only.applied_at is None
    assert (
        db.query(JobLifecycleEvent)
        .filter_by(user_id=user.id, kind="first_applied")
        .count()
        == 1
    )


def test_applied_date_correction_keeps_first_fact_and_backward_status_keeps_date(
    mutation_user,
):
    client, db, user = mutation_user
    row = _add_row(db, user)
    app = client.post(f"/crm/from-row/{row.id}").json()

    first = client.patch(
        f"/crm/applications/{app['id']}",
        json={"applied_at": "2026-09-17T12:00:00Z", "status": "applied"},
    )
    corrected = client.patch(
        f"/crm/applications/{app['id']}",
        json={"applied_at": "2026-09-16T12:00:00Z"},
    )
    moved_back = client.patch(
        f"/crm/applications/{app['id']}",
        json={"status": "opened"},
    )

    assert first.status_code == 200
    assert corrected.status_code == 200
    assert moved_back.status_code == 200
    db.expire_all()
    track = db.get(JobTrack, app["id"])
    assert track.applied_at == datetime(2026, 9, 16, 12, 0, 0)
    assert track.status == "opened"
    kinds = _event_kinds(db, user)
    assert kinds.count("first_applied") == 1
    assert kinds.count("applied_date_corrected") == 1
    assert kinds.count("status_changed") == 2
