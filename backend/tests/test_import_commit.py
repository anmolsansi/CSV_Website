import json
from datetime import datetime
from uuid import uuid4

import pytest

from app.models import CsvRow, JobTrack, User
from app.services.job_identity import apply_persisted_job_identity
from app.services import imports as import_service


def _auth_user(db):
    user = db.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _preview(auth_client, content: bytes):
    response = auth_client.post(
        "/crm/imports/preview",
        files={"file": ("jobs.csv", content, "text/csv")},
        data={"mapping": json.dumps({"0": "url", "1": "title"}), "options": "{}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_row(db, user, *, url, title="Old title", clicked=True):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=url,
        title=title,
        clicked=clicked,
        clicked_at=datetime(2026, 9, 1, 10, 0) if clicked else None,
    )
    apply_persisted_job_identity(row)
    db.add(row)
    db.flush()
    return row


def test_update_title_preserves_notes_clicked_applied(auth_client, db_session):
    user = _auth_user(db_session)
    url = f"https://example.test/import/update-{uuid4()}"
    row = _seed_row(db_session, user, url=url, title="Old title", clicked=True)
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=url,
        title="Application title",
        company="Acme",
        status="applied",
        notes="hand-entered note",
        applied_at=datetime(2026, 8, 20, 12, 0),
    )
    db_session.add(track)
    db_session.commit()

    preview = _preview(auth_client, f"url,title\n{url},New imported title\n".encode())
    assert preview["counts"] == {
        "create": 0,
        "exact_duplicate": 1,
        "possible_duplicate": 0,
        "invalid": 0,
    }
    response = auth_client.post(
        f"/crm/imports/{preview['preview_id']}/commit",
        json={
            "version": preview["version"],
            "idempotency_key": str(uuid4()),
            "mode": "update_selected",
            "update_fields": ["title"],
            "invalid_policy": "reject",
            "replace_empty": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["counts"] == {
        "created": 0,
        "updated": 1,
        "skipped": 0,
        "invalid": 0,
    }

    db_session.expire_all()
    stored_row = db_session.query(CsvRow).filter_by(id=row.id).one()
    stored_track = db_session.query(JobTrack).filter_by(id=track.id).one()
    assert stored_row.title == "New imported title"
    assert stored_row.clicked is True
    assert stored_row.clicked_at == datetime(2026, 9, 1, 10, 0)
    assert stored_track.status == "applied"
    assert stored_track.applied_at == datetime(2026, 8, 20, 12, 0)
    assert stored_track.notes == "hand-entered note"
    assert stored_track.title == "Application title"


def test_destination_changed_after_preview409(auth_client, db_session):
    user = _auth_user(db_session)
    url = f"https://example.test/import/conflict-{uuid4()}"
    preview = _preview(auth_client, f"url,title\n{url},Planned\n".encode())

    _seed_row(
        db_session,
        user,
        url=f"https://example.test/import/unrelated-{uuid4()}",
        title="Concurrent destination change",
        clicked=False,
    )
    db_session.commit()

    response = auth_client.post(
        f"/crm/imports/{preview['preview_id']}/commit",
        json={
            "version": preview["version"],
            "idempotency_key": str(uuid4()),
            "mode": "insert_only",
            "update_fields": [],
            "invalid_policy": "reject",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "destination_changed"
    db_session.expire_all()
    assert db_session.query(CsvRow).filter_by(user_id=user.id, url=url).first() is None


def test_replayed_commit_identical_result(auth_client, db_session):
    user = _auth_user(db_session)
    url = f"https://example.test/import/replay-{uuid4()}"
    preview = _preview(auth_client, f"url,title\n{url},Replay Engineer\n".encode())
    key = str(uuid4())
    payload = {
        "version": preview["version"],
        "idempotency_key": key,
        "mode": "insert_only",
        "update_fields": [],
        "invalid_policy": "reject",
    }
    first = auth_client.post(f"/crm/imports/{preview['preview_id']}/commit", json=payload)
    assert first.status_code == 200, first.text
    second = auth_client.post(f"/crm/imports/{preview['preview_id']}/commit", json=payload)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert first.json()["counts"] == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "invalid": 0,
    }
    db_session.expire_all()
    assert db_session.query(CsvRow).filter_by(user_id=user.id, url=url).count() == 1


def test_last_row_failure_rolls_back_all(auth_client, db_session, monkeypatch):
    user = _auth_user(db_session)
    url1 = f"https://example.test/import/rollback-a-{uuid4()}"
    url2 = f"https://example.test/import/rollback-b-{uuid4()}"
    preview = _preview(
        auth_client,
        f"url,title\n{url1},First\n{url2},Second\n".encode(),
    )
    before = db_session.query(CsvRow).filter(CsvRow.user_id == user.id).count()

    original = import_service._create_csv_row
    calls = {"count": 0}

    def fail_on_second(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("synthetic last-row write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(import_service, "_create_csv_row", fail_on_second)
    response = auth_client.post(
        f"/crm/imports/{preview['preview_id']}/commit",
        json={
            "version": preview["version"],
            "idempotency_key": str(uuid4()),
            "mode": "insert_only",
            "update_fields": [],
            "invalid_policy": "reject",
        },
    )
    assert response.status_code == 500
    assert calls["count"] == 2

    db_session.expire_all()
    after = db_session.query(CsvRow).filter(CsvRow.user_id == user.id).count()
    assert after == before
    assert db_session.query(CsvRow).filter(CsvRow.url.in_([url1, url2])).count() == 0


def test_foreign_preview_commit_is_not_found(auth_client, db_session):
    owner = _auth_user(db_session)
    foreign = User(email=f"foreign-import-{uuid4()}@example.test", timezone="UTC")
    db_session.add(foreign)
    db_session.flush()
    preview = import_service.create_import_preview(
        db_session,
        user_id=foreign.id,
        raw=b"url,title\nhttps://example.test/foreign-import,Foreign\n",
        filename="foreign.csv",
        content_type="text/csv",
        mapping_value={"0": "url", "1": "title"},
    )
    db_session.commit()

    response = auth_client.post(
        f"/crm/imports/{preview.id}/commit",
        json={
            "version": 1,
            "idempotency_key": str(uuid4()),
            "mode": "insert_only",
            "update_fields": [],
            "invalid_policy": "reject",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "import_preview_not_found"
    assert owner.id != foreign.id
