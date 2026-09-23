from datetime import datetime

from app.contact_models import Interview
from app.models import JobTrack, User
from app.services.calendar_export import build_interview_ics


def _fixture(db):
    user = User(email="calendar-f8@example.test", timezone="America/Chicago")
    db.add(user)
    db.flush()
    track = JobTrack(
        user_id=user.id,
        url="https://example.test/calendar-f8",
        company="Acme, Inc.",
        title="Platform; Engineer",
    )
    db.add(track)
    db.flush()
    return user, track


def _content_lines(text: str) -> list[str]:
    return text.split("\r\n")


def test_ics_parser_shape_is_exactly_one_event(db_session):
    user, track = _fixture(db_session)
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 11, 1, 7, 30),
        ends_at=datetime(2026, 11, 1, 8, 30),
        timezone="America/Chicago",
        kind="video",
        location="Room A\r\nEND:VEVENT\r\nBEGIN:VEVENT",
        notes="private interview note",
        preparation_notes="private preparation note",
        round_label="Hiring Manager",
        version=3,
    )
    db_session.add(interview)
    db_session.flush()

    text = build_interview_ics(interview, track).decode("utf-8")
    lines = _content_lines(text)
    assert lines.count("BEGIN:VCALENDAR") == 1
    assert lines.count("BEGIN:VEVENT") == 1
    assert lines.count("END:VEVENT") == 1
    assert "DTSTART:20261101T073000Z" in lines
    assert "DTEND:20261101T083000Z" in lines
    assert "SEQUENCE:2" in lines
    assert "private interview note" not in text
    assert "private preparation note" not in text


def test_ics_user_text_cannot_inject_properties(db_session):
    user, track = _fixture(db_session)
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="UTC",
        kind="onsite",
        location="HQ\nSUMMARY:Injected\nBEGIN:VEVENT",
    )
    db_session.add(interview)
    db_session.flush()

    text = build_interview_ics(interview, track).decode("utf-8")
    lines = _content_lines(text)
    assert lines.count("BEGIN:VEVENT") == 1
    assert "SUMMARY:Injected" not in lines
    assert "LOCATION:HQ\\nSUMMARY:Injected\\nBEGIN:VEVENT" in text


def test_ics_lines_are_folded_to_rfc5545_octet_limit(db_session):
    user, track = _fixture(db_session)
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="UTC",
        kind="video",
        location="é" * 120,
    )
    db_session.add(interview)
    db_session.flush()

    lines = build_interview_ics(interview, track).split(b"\r\n")
    assert all(len(line) <= 75 for line in lines if line)
