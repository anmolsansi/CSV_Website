from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.evidence_schemas import (
    EvidenceContractError,
    EvidenceCreateData,
    evidence_create_payload_hash,
    validate_confirmation_url,
)
from app.models import (
    ApplicationEvidence,
    EvidenceCreateReceipt,
    JobLifecycleEvent,
    JobTrack,
    User,
)
from app.services.evidence import (
    EvidenceServiceError,
    purge_expired_evidence_recovery_state,
    require_owned_track,
)
from app.services.lifecycle import LifecycleEventError, validate_event_payload, write_event


def _user(db_session, prefix: str) -> User:
    item = User(email=f"{prefix}-{uuid4()}@example.test")
    db_session.add(item)
    db_session.flush()
    return item


def _track(db_session, user: User, suffix: str) -> JobTrack:
    item = JobTrack(
        user_id=user.id,
        url=f"https://evidence.example/jobs/{suffix}-{uuid4()}",
        status="opened",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_evidence_track_owner_checked(db_session):
    owner = _user(db_session, "evidence-owner")
    other = _user(db_session, "evidence-other")
    owned_track = _track(db_session, owner, "owned")
    foreign_track = _track(db_session, other, "foreign")

    assert require_owned_track(
        db_session, user_id=owner.id, track_id=owned_track.id
    ).id == owned_track.id

    with pytest.raises(EvidenceServiceError) as exc:
        require_owned_track(
            db_session, user_id=owner.id, track_id=foreign_track.id
        )
    assert exc.value.code == "inaccessible_job_track"

    foreign_evidence = ApplicationEvidence(
        user_id=other.id,
        track_id=foreign_track.id,
        kind="note",
        body="Private foreign evidence",
        version=1,
    )
    db_session.add(foreign_evidence)
    db_session.flush()

    with pytest.raises(LifecycleEventError) as event_exc:
        write_event(
            db_session,
            user_id=owner.id,
            job_url=owned_track.url,
            kind="evidence_added",
            occurred_at=datetime.utcnow(),
            source="evidence_test",
            payload={
                "evidence_id": foreign_evidence.id,
                "evidence_kind": "note",
            },
            job_track_id=owned_track.id,
            operation_id=uuid4(),
        )
    assert event_exc.value.code == "inaccessible_evidence"


def test_unknown_event_payload_field_rejected():
    with pytest.raises(LifecycleEventError) as exc:
        validate_event_payload(
            "evidence_added",
            {
                "evidence_id": 1,
                "evidence_kind": "note",
                "body": "private text must never enter lifecycle payload",
            },
        )
    assert exc.value.code == "invalid_event_payload"


def test_original_event_immutable_after_correction(db_session):
    user = _user(db_session, "immutable-event")
    track = _track(db_session, user, "immutable")
    now = datetime(2026, 9, 22, 8, 30, 0)

    original = write_event(
        db_session,
        user_id=user.id,
        job_url=track.url,
        kind="status_changed",
        occurred_at=now,
        source="evidence_test",
        payload={"from": "opened", "to": "applied"},
        job_track_id=track.id,
        operation_id=uuid4(),
    )
    db_session.flush()
    original_id = original.id
    original_payload = dict(original.payload)

    correction = write_event(
        db_session,
        user_id=user.id,
        job_url=track.url,
        kind="status_changed",
        occurred_at=now + timedelta(minutes=1),
        source="evidence_test",
        payload={
            "from": "applied",
            "to": "opened",
            "correction_of": original_id,
            "reason": "Recorded the wrong status.",
        },
        job_track_id=track.id,
        operation_id=uuid4(),
    )
    db_session.flush()
    db_session.expire_all()

    persisted_original = db_session.get(JobLifecycleEvent, original_id)
    assert persisted_original.payload == original_payload
    assert correction.id != original_id
    assert db_session.query(JobLifecycleEvent).filter_by(
        user_id=user.id, job_track_id=track.id
    ).count() == 2


def test_correction_reason_and_confirmation_url_validation():
    valid = EvidenceCreateData(
        kind="confirmation_url",
        body="https://example.com/application/123",
    )
    digest = evidence_create_payload_hash(
        track_id=7,
        data=valid,
    )
    assert len(digest) == 64

    with pytest.raises(EvidenceContractError):
        validate_confirmation_url("https://user:secret@example.com/private")


def test_receipt_uniqueness_is_owner_scoped(db_session):
    user = _user(db_session, "receipt-owner")
    track = _track(db_session, user, "receipt")
    evidence = ApplicationEvidence(
        user_id=user.id,
        track_id=track.id,
        kind="note",
        body="Receipt target",
        version=1,
    )
    db_session.add(evidence)
    db_session.flush()
    request_key = str(uuid4())

    db_session.add(
        EvidenceCreateReceipt(
            user_id=user.id,
            request_key=request_key,
            payload_hash="a" * 64,
            evidence_id=evidence.id,
        )
    )
    db_session.flush()

    db_session.add(
        EvidenceCreateReceipt(
            user_id=user.id,
            request_key=request_key,
            payload_hash="b" * 64,
            evidence_id=evidence.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_soft_delete_recovery_retention_is_bounded(db_session):
    user = _user(db_session, "retention-owner")
    track = _track(db_session, user, "retention")
    now = datetime(2026, 9, 22, 9, 0, 0)
    old_deleted_at = now - timedelta(days=31)
    fresh_deleted_at = now - timedelta(days=5)

    expired = ApplicationEvidence(
        user_id=user.id,
        track_id=track.id,
        kind="note",
        body="Expired recovery body",
        version=2,
        is_deleted=True,
        updated_at=old_deleted_at,
    )
    fresh = ApplicationEvidence(
        user_id=user.id,
        track_id=track.id,
        kind="confirmation_text",
        body="Fresh recovery body",
        version=2,
        is_deleted=True,
        updated_at=fresh_deleted_at,
    )
    db_session.add_all([expired, fresh])
    db_session.flush()

    old_receipt = EvidenceCreateReceipt(
        user_id=user.id,
        request_key=str(uuid4()),
        payload_hash="c" * 64,
        evidence_id=expired.id,
        created_at=old_deleted_at,
    )
    fresh_receipt = EvidenceCreateReceipt(
        user_id=user.id,
        request_key=str(uuid4()),
        payload_hash="d" * 64,
        evidence_id=fresh.id,
        created_at=fresh_deleted_at,
    )
    db_session.add_all([old_receipt, fresh_receipt])
    db_session.flush()
    old_receipt_id = old_receipt.id
    fresh_receipt_id = fresh_receipt.id

    result = purge_expired_evidence_recovery_state(
        db_session, now=now, limit=500
    )
    db_session.flush()

    assert result.bodies_blanked == 1
    assert result.receipts_deleted == 1
    assert expired.body is None
    assert expired.updated_at == old_deleted_at
    assert fresh.body == "Fresh recovery body"
    assert db_session.get(EvidenceCreateReceipt, old_receipt_id) is None
    assert db_session.get(EvidenceCreateReceipt, fresh_receipt_id) is not None
