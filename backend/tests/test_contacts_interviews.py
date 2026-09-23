from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.contact_models import ApplicationContact, Contact, Interview, MutationReceipt
from app.models import JobTrack, User
from app.services.calendar_export import build_interview_ics
from app.services.contacts import ContactServiceError, link_application_contact, serialize_interview


def _user(db, prefix: str) -> User:
    row = User(email=f"{prefix}-{uuid4()}@example.test", timezone="America/Chicago")
    db.add(row)
    db.flush()
    return row


def _track(db, user: User, suffix: str = "1") -> JobTrack:
    row = JobTrack(user_id=user.id, url=f"https://example.test/jobs/{uuid4()}-{suffix}", company="Acme", title="Engineer")
    db.add(row)
    db.flush()
    return row


def test_cross_user_association_rejected(db_session):
    owner = _user(db_session, "f8-owner")
    other = _user(db_session, "f8-other")
    track = _track(db_session, owner)
    contact = Contact(user_id=other.id, name="Foreign Recruiter")
    db_session.add(contact)
    db_session.flush()

    with pytest.raises(ContactServiceError) as exc:
        link_application_contact(
            db_session,
            user_id=owner.id,
            track_id=track.id,
            operation_key=str(uuid4()),
            payload={"contact_id": contact.id, "role": "recruiter", "referral_source": None},
        )
    assert exc.value.status_code == 404


def test_duplicate_role_link_single_row(db_session):
    user = _user(db_session, "f8-duplicate")
    track = _track(db_session, user)
    contact = Contact(user_id=user.id, name="Recruiter")
    db_session.add(contact)
    db_session.flush()

    first, replayed_first = link_application_contact(
        db_session,
        user_id=user.id,
        track_id=track.id,
        operation_key=str(uuid4()),
        payload={"contact_id": contact.id, "role": "recruiter", "referral_source": None},
    )
    second, replayed_second = link_application_contact(
        db_session,
        user_id=user.id,
        track_id=track.id,
        operation_key=str(uuid4()),
        payload={"contact_id": contact.id, "role": "recruiter", "referral_source": None},
    )
    db_session.flush()

    assert first.id == second.id
    assert replayed_first is False
    assert replayed_second is True
    assert db_session.query(ApplicationContact).filter_by(track_id=track.id).count() == 1


def test_end_before_start422(auth_client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(user)
        db_session.flush()
    track = _track(db_session, user, "bad-range")
    db_session.commit()

    response = auth_client.post(
        f"/crm/tracks/{track.id}/interviews",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "starts_at": "2026-10-05T16:00:00Z",
            "ends_at": "2026-10-05T15:00:00Z",
            "timezone": "America/Chicago",
            "kind": "video",
        },
    )
    assert response.status_code == 422


def test_contact_delete_preserves_interview_marker(auth_client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(user)
        db_session.flush()
    track = _track(db_session, user, "delete-marker")
    db_session.commit()

    contact_response = auth_client.post(
        "/crm/contacts",
        headers={"Idempotency-Key": str(uuid4())},
        json={"name": "Private Recruiter", "email": "private@example.test", "notes": "private note"},
    )
    assert contact_response.status_code == 201, contact_response.text
    contact = contact_response.json()

    interview_response = auth_client.post(
        f"/crm/tracks/{track.id}/interviews",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "contact_id": contact["id"],
            "starts_at": "2026-10-05T16:00:00Z",
            "ends_at": "2026-10-05T17:00:00Z",
            "timezone": "America/Chicago",
            "kind": "video",
            "preparation_notes": "do not export",
        },
    )
    assert interview_response.status_code == 201, interview_response.text

    deleted = auth_client.delete(f"/crm/contacts/{contact['id']}?version={contact['version']}")
    assert deleted.status_code == 204

    listed = auth_client.get(f"/crm/tracks/{track.id}/interviews")
    assert listed.status_code == 200
    marker = listed.json()["interviews"][0]["contact"]
    assert marker["name"] == "Deleted contact"
    assert marker["email"] is None
    assert marker["notes"] is None


def test_stale_interview_edit409(auth_client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(user)
        db_session.flush()
    track = _track(db_session, user, "stale")
    db_session.commit()

    created = auth_client.post(
        f"/crm/tracks/{track.id}/interviews",
        headers={"Idempotency-Key": str(uuid4())},
        json={"starts_at": "2026-10-05T16:00:00Z", "ends_at": "2026-10-05T17:00:00Z", "timezone": "UTC", "kind": "phone"},
    ).json()
    first = auth_client.patch(f"/crm/interviews/{created['id']}", json={"version": created["version"], "round_label": "Screen"})
    assert first.status_code == 200, first.text
    stale = auth_client.patch(f"/crm/interviews/{created['id']}", json={"version": created["version"], "round_label": "Old write"})
    assert stale.status_code == 409


def test_foreign_contact_and_ics404(auth_client, db_session):
    owner = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if owner is None:
        owner = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(owner)
        db_session.flush()
    foreign = _user(db_session, "f8-foreign-ics")
    track = _track(db_session, foreign, "ics")
    contact = Contact(user_id=foreign.id, name="Foreign")
    db_session.add(contact)
    db_session.flush()
    interview = Interview(
        user_id=foreign.id,
        track_id=track.id,
        contact_id=contact.id,
        starts_at=datetime(2026, 11, 1, 7, 30),
        ends_at=datetime(2026, 11, 1, 8, 30),
        timezone="America/Chicago",
        kind="video",
    )
    db_session.add(interview)
    db_session.commit()

    assert auth_client.get(f"/crm/interviews/{interview.id}/calendar.ics").status_code == 404
    assert auth_client.post(
        f"/crm/tracks/{_track(db_session, owner, 'foreign-contact').id}/contacts",
        headers={"Idempotency-Key": str(uuid4())},
        json={"contact_id": contact.id, "role": "recruiter"},
    ).status_code == 404


def test_ics_injection_cannot_add_second_event(db_session):
    user = _user(db_session, "f8-ics-injection")
    track = _track(db_session, user, "inject")
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="UTC",
        kind="video",
        location="Room 1\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Injected",
        notes="private notes must not appear",
        preparation_notes="private prep must not appear",
    )
    db_session.add(interview)
    db_session.flush()
    text = build_interview_ics(interview, track).decode("utf-8")

    assert text.count("BEGIN:VEVENT") == 1
    assert text.count("END:VEVENT") == 1
    assert "private notes" not in text
    assert "private prep" not in text
    assert "Room 1\\nEND:VEVENT\\nBEGIN:VEVENT\\nSUMMARY:Injected" in text


def test_ics_dst_instant_correct(db_session):
    user = _user(db_session, "f8-dst")
    track = _track(db_session, user, "dst")
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 11, 1, 7, 30),
        ends_at=datetime(2026, 11, 1, 8, 30),
        timezone="America/Chicago",
        kind="video",
    )
    db_session.add(interview)
    db_session.flush()
    text = build_interview_ics(interview, track).decode("utf-8")
    assert "DTSTART:20261101T073000Z" in text
    assert "DTEND:20261101T083000Z" in text


def test_idempotency_key_reuse_with_different_payload409(auth_client):
    key = str(uuid4())
    first = auth_client.post("/crm/contacts", headers={"Idempotency-Key": key}, json={"name": "One"})
    assert first.status_code == 201, first.text
    second = auth_client.post("/crm/contacts", headers={"Idempotency-Key": key}, json={"name": "Two"})
    assert second.status_code == 409
