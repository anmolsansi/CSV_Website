import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contact_models import ApplicationContact, Contact, Interview
from app.contact_schemas import InterviewCreateRequest, validate_interview_window
from app.models import JobTrack, User
from app.services import email_transport
from app.services.calendar_export import build_interview_ics
from app.services.contact_backups import (
    export_backup_v2_with_contacts,
    restore_backup_payload_with_contacts,
)


def _auth_user(db):
    user = db.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db.add(user)
        db.flush()
    return user


def _track(db, user, suffix, **kwargs):
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jg056/{suffix}-{uuid4()}",
        company="Acme",
        title="Software Engineer",
        **kwargs,
    )
    db.add(track)
    db.flush()
    return track


def _parse_single_event(ics_bytes):
    text = ics_bytes.decode("utf-8")
    physical = text.split("\r\n")
    logical = []
    for line in physical:
        if line.startswith(" ") and logical:
            logical[-1] += line[1:]
        else:
            logical.append(line)
    assert logical.count("BEGIN:VCALENDAR") == 1
    assert logical.count("BEGIN:VEVENT") == 1
    assert logical.count("END:VEVENT") == 1
    start = logical.index("BEGIN:VEVENT")
    end = logical.index("END:VEVENT", start)
    properties = {}
    for line in logical[start + 1 : end]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        properties[name.split(";", 1)[0]] = value
    return properties


def test_foreign_search_zero_results(auth_client, db_session):
    _auth_user(db_session)
    foreign = User(email=f"foreign-{uuid4()}@example.test", timezone="UTC")
    db_session.add(foreign)
    db_session.flush()
    unique_name = f"OnlyForeign-{uuid4()}"
    db_session.add(
        Contact(
            user_id=foreign.id,
            name=unique_name,
            email="private-foreign@example.test",
            notes="must never cross account boundary",
        )
    )
    db_session.commit()

    response = auth_client.get("/crm/contacts", params={"q": unique_name, "limit": 100})
    assert response.status_code == 200
    assert response.json() == {"contacts": []}


def test_ics_parser_reads_exactly_one_correct_event(db_session):
    user = User(email=f"ics-{uuid4()}@example.test", timezone="America/Chicago")
    db_session.add(user)
    db_session.flush()
    track = _track(db_session, user, "ics")
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 11, 1, 7, 30),
        ends_at=datetime(2026, 11, 1, 8, 30),
        timezone="America/Chicago",
        kind="video",
        location="Room A\nBEGIN:VEVENT\nSUMMARY:Injected",
        notes="private note absent from calendar",
        preparation_notes="private prep absent from calendar",
        round_label="Hiring Manager",
        version=3,
    )
    db_session.add(interview)
    db_session.flush()

    properties = _parse_single_event(build_interview_ics(interview, track))
    assert properties["DTSTART"] == "20261101T073000Z"
    assert properties["DTEND"] == "20261101T083000Z"
    assert properties["SEQUENCE"] == "2"
    assert properties["SUMMARY"].startswith("Hiring Manager")
    assert "private note" not in json.dumps(properties)
    assert "private prep" not in json.dumps(properties)


def test_dst_overlap_and_gap_require_explicit_instants():
    with pytest.raises(ValidationError):
        InterviewCreateRequest(
            starts_at="2026-11-01T01:30:00",
            ends_at="2026-11-01T02:30:00",
            timezone="America/Chicago",
            kind="video",
        )

    first_overlap = InterviewCreateRequest(
        starts_at="2026-11-01T01:30:00-05:00",
        ends_at="2026-11-01T02:00:00-05:00",
        timezone="America/Chicago",
        kind="video",
    )
    second_overlap = InterviewCreateRequest(
        starts_at="2026-11-01T01:30:00-06:00",
        ends_at="2026-11-01T02:00:00-06:00",
        timezone="America/Chicago",
        kind="video",
    )
    first_start, _ = validate_interview_window(first_overlap.starts_at, first_overlap.ends_at)
    second_start, _ = validate_interview_window(second_overlap.starts_at, second_overlap.ends_at)
    assert second_start - first_start == __import__("datetime").timedelta(hours=1)

    before_gap = InterviewCreateRequest(
        starts_at="2026-03-08T01:30:00-06:00",
        ends_at="2026-03-08T01:45:00-06:00",
        timezone="America/Chicago",
        kind="phone",
    )
    after_gap = InterviewCreateRequest(
        starts_at="2026-03-08T03:30:00-05:00",
        ends_at="2026-03-08T03:45:00-05:00",
        timezone="America/Chicago",
        kind="phone",
    )
    before_start, _ = validate_interview_window(before_gap.starts_at, before_gap.ends_at)
    after_start, _ = validate_interview_window(after_gap.starts_at, after_gap.ends_at)
    assert after_start - before_start == __import__("datetime").timedelta(hours=1)


def test_deleted_contact_notes_absent_from_normal_read(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, "deleted-contact")
    contact = Contact(
        user_id=user.id,
        name="Private Recruiter",
        email="private@example.test",
        notes="private deleted note",
    )
    db_session.add(contact)
    db_session.flush()
    link = ApplicationContact(
        user_id=user.id,
        track_id=track.id,
        contact_id=contact.id,
        role="recruiter",
    )
    db_session.add(link)
    db_session.commit()

    deleted = auth_client.delete(f"/crm/contacts/{contact.id}", params={"version": 1})
    assert deleted.status_code == 204

    search = auth_client.get("/crm/contacts", params={"q": "Private Recruiter"})
    assert search.status_code == 200
    assert search.json() == {"contacts": []}

    linked = auth_client.get(f"/crm/tracks/{track.id}/contacts")
    assert linked.status_code == 200
    payload = linked.json()["contacts"]
    assert len(payload) == 1
    assert payload[0]["role"] == "recruiter"
    assert payload[0]["contact"]["name"] == "Deleted contact"
    assert payload[0]["contact"]["notes"] is None
    assert payload[0]["contact"]["email"] is None


def test_interview_cancel_preserves_application_history(auth_client, db_session):
    user = _auth_user(db_session)
    applied_at = datetime(2026, 9, 1, 12, 0)
    track = _track(
        db_session,
        user,
        "cancel-history",
        status="applied",
        applied_at=applied_at,
        notes="hand-entered application note",
    )
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="UTC",
        kind="video",
        status="scheduled",
        notes="interview history",
    )
    db_session.add(interview)
    db_session.commit()

    response = auth_client.patch(
        f"/crm/interviews/{interview.id}",
        json={"version": 1, "status": "cancelled"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    db_session.expire_all()
    restored_track = db_session.query(JobTrack).filter_by(id=track.id).one()
    restored_interview = db_session.query(Interview).filter_by(id=interview.id).one()
    assert restored_track.status == "applied"
    assert restored_track.applied_at == applied_at
    assert restored_track.notes == "hand-entered application note"
    assert restored_interview.status == "cancelled"
    assert restored_interview.notes == "interview history"


def test_restored_interview_links_and_notes_match(db_session):
    source = User(email=f"f8-source-{uuid4()}@example.test", timezone="America/Chicago")
    target = User(email=f"f8-target-{uuid4()}@example.test", timezone="UTC")
    db_session.add_all([source, target])
    db_session.flush()
    track = _track(db_session, source, "backup")
    contact = Contact(
        user_id=source.id,
        name="Recruiter",
        email="private@example.test",
        notes="contact note",
    )
    db_session.add(contact)
    db_session.flush()
    db_session.add(
        ApplicationContact(
            user_id=source.id,
            track_id=track.id,
            contact_id=contact.id,
            role="interviewer",
            referral_source="conference",
        )
    )
    interview = Interview(
        user_id=source.id,
        track_id=track.id,
        contact_id=contact.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="America/Chicago",
        kind="video",
        notes="interview note",
        preparation_notes="prep note",
        round_label="Technical",
    )
    db_session.add(interview)
    db_session.commit()

    exported = export_backup_v2_with_contacts(db_session, source.id)
    result = restore_backup_payload_with_contacts(
        db_session,
        target.id,
        json.dumps(exported).encode("utf-8"),
        "merge_missing",
    )
    assert result["counts"]["contacts"]["created"] == 1
    assert result["counts"]["application_contacts"]["created"] == 1
    assert result["counts"]["interviews"]["created"] == 1

    restored_contact = db_session.query(Contact).filter_by(user_id=target.id).one()
    restored_track = db_session.query(JobTrack).filter_by(user_id=target.id, url=track.url).one()
    restored_link = db_session.query(ApplicationContact).filter_by(user_id=target.id).one()
    restored_interview = db_session.query(Interview).filter_by(user_id=target.id).one()
    assert restored_contact.notes == "contact note"
    assert restored_link.contact_id == restored_contact.id
    assert restored_link.track_id == restored_track.id
    assert restored_interview.contact_id == restored_contact.id
    assert restored_interview.track_id == restored_track.id
    assert restored_interview.notes == "interview note"
    assert restored_interview.preparation_notes == "prep note"
    assert restored_interview.starts_at == datetime(2026, 10, 5, 16, 0)
    assert restored_interview.ends_at == datetime(2026, 10, 5, 17, 0)


def test_no_outbound_message_side_effect(auth_client, db_session, monkeypatch):
    user = _auth_user(db_session)
    track = _track(db_session, user, "no-outbound")
    db_session.commit()
    sent = []

    def fail_if_called(message):
        sent.append(message)
        raise AssertionError("F8 contact/interview actions must not send outbound mail")

    monkeypatch.setattr(email_transport, "send_via_smtp", fail_if_called)

    contact_response = auth_client.post(
        "/crm/contacts",
        headers={"Idempotency-Key": str(uuid4())},
        json={"name": "Recruiter", "email": "recruiter@example.test", "notes": "private"},
    )
    assert contact_response.status_code == 201, contact_response.text

    interview_response = auth_client.post(
        f"/crm/tracks/{track.id}/interviews",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "contact_id": contact_response.json()["id"],
            "starts_at": "2026-10-05T16:00:00Z",
            "ends_at": "2026-10-05T17:00:00Z",
            "timezone": "UTC",
            "kind": "video",
            "meeting_url": "https://meet.example.test/private-room",
        },
    )
    assert interview_response.status_code == 201, interview_response.text
    assert sent == []
