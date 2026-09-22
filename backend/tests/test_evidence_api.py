from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models import (
    ApplicationEvidence,
    EvidenceCreateReceipt,
    JobLifecycleEvent,
    JobTrack,
    User,
)
from app.services.lifecycle import (
    apply_job_track_changes,
    metric_counts,
    write_event,
)


def _auth_user(db_session) -> User:
    db_session.expire_all()
    return db_session.query(User).filter(User.email == "test@jobgrid.dev").one()


def _track(
    db_session,
    user: User,
    *,
    suffix: str,
    status: str = "opened",
    applied_at: datetime | None = None,
) -> JobTrack:
    item = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/{suffix}",
        company="Example",
        title="Engineer",
        status=status,
        applied_at=applied_at,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_create_retry_one_evidence_one_event(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="create-retry")
    key = str(uuid4())
    payload = {
        "kind": "confirmation_text",
        "body": "Application submitted successfully",
        "occurred_at": "2026-09-20T12:00:00Z",
    }

    first = auth_client.post(
        f"/crm/tracks/{track.id}/evidence",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    replay = auth_client.post(
        f"/crm/tracks/{track.id}/evidence",
        json=payload,
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]

    db_session.expire_all()
    assert (
        db_session.query(ApplicationEvidence)
        .filter_by(user_id=user.id, track_id=track.id)
        .count()
        == 1
    )
    assert (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="evidence_added",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(EvidenceCreateReceipt)
        .filter_by(user_id=user.id, request_key=key)
        .count()
        == 1
    )


def test_pagination_same_timestamp_stable(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="same-time")
    timestamp = datetime(2026, 9, 20, 12, 0, 0)

    for index in range(3):
        write_event(
            db_session,
            user_id=user.id,
            job_url=track.url,
            kind="followup_changed",
            occurred_at=timestamp,
            source="user",
            payload={"from": None, "to": f"2026-09-{21 + index:02d}T12:00:00"},
            job_track_id=track.id,
            operation_id=uuid4(),
        )
    for index in range(3):
        db_session.add(
            ApplicationEvidence(
                user_id=user.id,
                track_id=track.id,
                kind="note",
                body=f"note-{index}",
                occurred_at=timestamp,
                created_at=timestamp,
                updated_at=timestamp,
                version=1,
                is_deleted=False,
            )
        )
    db_session.commit()

    first = auth_client.get(f"/crm/tracks/{track.id}/timeline?limit=2")
    again = auth_client.get(f"/crm/tracks/{track.id}/timeline?limit=2")
    assert first.status_code == 200
    assert again.status_code == 200
    assert first.json() == again.json()

    seen: list[tuple[str, int]] = []
    cursor = None
    while True:
        suffix = "?limit=2" if cursor is None else f"?limit=2&before={cursor}"
        response = auth_client.get(f"/crm/tracks/{track.id}/timeline{suffix}")
        assert response.status_code == 200
        body = response.json()
        assert 1 <= len(body["items"]) <= 2
        seen.extend((item["type"], item["id"]) for item in body["items"])
        cursor = body["next_before"]
        if cursor is None:
            break

    assert len(seen) == 6
    assert len(set(seen)) == 6


def test_soft_deleted_body_absent(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="soft-delete")
    secret_body = "private confirmation reference"
    created = auth_client.post(
        f"/crm/tracks/{track.id}/evidence",
        json={"kind": "note", "body": secret_body},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]

    deleted = auth_client.delete(
        f"/crm/tracks/{track.id}/evidence/{evidence_id}",
        headers={"X-Operation-ID": str(uuid4())},
    )
    repeated = auth_client.delete(
        f"/crm/tracks/{track.id}/evidence/{evidence_id}",
        headers={"X-Operation-ID": str(uuid4())},
    )
    assert deleted.status_code == 204
    assert repeated.status_code == 204

    timeline = auth_client.get(f"/crm/tracks/{track.id}/timeline")
    assert timeline.status_code == 200
    evidence_item = next(
        item
        for item in timeline.json()["items"]
        if item["type"] == "evidence" and item["id"] == evidence_id
    )
    assert evidence_item["is_deleted"] is True
    assert "body" not in evidence_item
    assert secret_body not in timeline.text

    db_session.expire_all()
    stored = db_session.get(ApplicationEvidence, evidence_id)
    assert stored is not None
    assert stored.body == secret_body
    assert stored.is_deleted is True
    assert (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="evidence_deleted",
        )
        .count()
        == 1
    )


def test_foreign_timeline_returns404(auth_client, db_session):
    owner = User(email=f"other-{uuid4().hex}@example.test")
    db_session.add(owner)
    db_session.commit()
    track = _track(db_session, owner, suffix="foreign-timeline")

    foreign = auth_client.get(f"/crm/tracks/{track.id}/timeline")
    missing = auth_client.get("/crm/tracks/99999999/timeline")

    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "inaccessible_job_track"
    assert missing.status_code == 404


def test_correction_preserves_original_event_and_metrics(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="correction")
    original_applied_at = datetime(2026, 9, 18, 12, 0, 0)
    operation_id = uuid4()

    apply_job_track_changes(
        db_session,
        user_id=user.id,
        item=track,
        source="user",
        operation_id=operation_id,
        now=original_applied_at,
        status="applied",
        applied_at=original_applied_at,
        infer_applied_at_from_status=False,
    )
    db_session.commit()
    original_status_event = (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="status_changed",
        )
        .one()
    )
    original_event_id = original_status_event.id
    original_event_payload = dict(original_status_event.payload)
    before_metrics = metric_counts(db_session, user_id=user.id)
    assert before_metrics["applied"] == 1

    applied_correction = auth_client.post(
        f"/crm/tracks/{track.id}/applied-date-corrections",
        json={
            "applied_at": "2026-09-19T15:30:00Z",
            "reason": "Corrected from confirmation timestamp",
        },
        headers={"X-Operation-ID": str(uuid4())},
    )
    assert applied_correction.status_code == 200
    assert applied_correction.json()["applied_at"] == "2026-09-19T15:30:00Z"

    status_correction = auth_client.post(
        f"/crm/tracks/{track.id}/status-corrections",
        json={
            "expected_event_id": original_event_id,
            "restore_status": "opened",
            "reason": "Applied status was selected by mistake",
        },
        headers={"X-Operation-ID": str(uuid4())},
    )
    assert status_correction.status_code == 200
    assert status_correction.json()["status"] == "opened"

    db_session.expire_all()
    original = db_session.get(JobLifecycleEvent, original_event_id)
    assert original is not None
    assert original.payload == original_event_payload

    correction = (
        db_session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.job_track_id == track.id,
            JobLifecycleEvent.kind == "status_changed",
            JobLifecycleEvent.id != original_event_id,
        )
        .one()
    )
    assert correction.payload["correction_of"] == original_event_id
    assert correction.payload["from"] == "applied"
    assert correction.payload["to"] == "opened"
    assert correction.payload["reason"] == "Applied status was selected by mistake"

    date_correction = (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="applied_date_corrected",
        )
        .one()
    )
    assert date_correction.payload["reason"] == "Corrected from confirmation timestamp"
    assert date_correction.payload["from"] == "2026-09-18T12:00:00"
    assert date_correction.payload["to"] == "2026-09-19T15:30:00"

    after_metrics = metric_counts(db_session, user_id=user.id)
    assert after_metrics["applied"] == 1


def test_stale_edit_returns409_without_extra_event(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="stale-edit")
    created = auth_client.post(
        f"/crm/tracks/{track.id}/evidence",
        json={"kind": "note", "body": "original"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]

    changed = auth_client.patch(
        f"/crm/tracks/{track.id}/evidence/{evidence_id}",
        json={"version": 1, "body": "updated"},
        headers={"X-Operation-ID": str(uuid4())},
    )
    stale = auth_client.patch(
        f"/crm/tracks/{track.id}/evidence/{evidence_id}",
        json={"version": 1, "body": "stale write"},
        headers={"X-Operation-ID": str(uuid4())},
    )

    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_evidence_version"

    db_session.expire_all()
    assert (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="evidence_edited",
        )
        .count()
        == 1
    )


def test_invalid_evidence_returns422_without_partial_event(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="invalid-evidence")

    response = auth_client.post(
        f"/crm/tracks/{track.id}/evidence",
        json={"kind": "confirmation_url", "body": "javascript:alert(1)"},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 422
    db_session.expire_all()
    assert (
        db_session.query(ApplicationEvidence)
        .filter_by(user_id=user.id, track_id=track.id)
        .count()
        == 0
    )
    assert (
        db_session.query(JobLifecycleEvent)
        .filter_by(user_id=user.id, job_track_id=track.id)
        .count()
        == 0
    )


def test_status_correction_rejects_intervening_status_edit(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, suffix="status-race")
    first_time = datetime(2026, 9, 20, 10, 0, 0)
    second_time = datetime(2026, 9, 20, 11, 0, 0)

    apply_job_track_changes(
        db_session,
        user_id=user.id,
        item=track,
        source="user",
        operation_id=uuid4(),
        now=first_time,
        status="applied",
        applied_at=first_time,
        infer_applied_at_from_status=False,
    )
    db_session.flush()
    first_event = (
        db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
            kind="status_changed",
        )
        .one()
    )
    apply_job_track_changes(
        db_session,
        user_id=user.id,
        item=track,
        source="user",
        operation_id=uuid4(),
        now=second_time,
        status="interview",
        infer_applied_at_from_status=False,
    )
    db_session.commit()

    response = auth_client.post(
        f"/crm/tracks/{track.id}/status-corrections",
        json={
            "expected_event_id": first_event.id,
            "restore_status": "opened",
            "reason": "Trying to correct an event that is no longer latest",
        },
        headers={"X-Operation-ID": str(uuid4())},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "status_correction_conflict"
    db_session.expire_all()
    assert db_session.get(JobTrack, track.id).status == "interview"
