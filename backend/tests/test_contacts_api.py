from datetime import datetime, timezone
from uuid import uuid4

from app.contact_models import Contact, Interview
from app.models import JobTrack, ReminderDelivery, User


def _auth_user(db):
    user = db.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db.add(user)
        db.flush()
    return user


def _track(db, user, suffix):
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/f8/{suffix}-{uuid4()}",
        company="Acme",
        title="Software Engineer",
    )
    db.add(track)
    db.flush()
    return track


def test_cancel_suppresses_unsent_reminder(auth_client, db_session):
    user = _auth_user(db_session)
    track = _track(db_session, user, "cancel-reminder")
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="UTC",
        kind="video",
        status="scheduled",
    )
    db_session.add(interview)
    db_session.flush()
    delivery = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=f"interview:{interview.id}:2026-10-05T16:00:00Z",
        channel="in_app",
        status="pending",
        scheduled_at=datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc),
        version=1,
    )
    db_session.add(delivery)
    db_session.commit()

    response = auth_client.patch(
        f"/crm/interviews/{interview.id}",
        json={"version": 1, "status": "cancelled"},
    )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    refreshed = db_session.query(ReminderDelivery).filter_by(id=delivery.id).one()
    assert refreshed.status == "cancelled"
    assert refreshed.last_error_code == "interview_changed"
    assert refreshed.version == 2


def test_contact_search_is_owner_scoped(auth_client, db_session):
    owner = _auth_user(db_session)
    foreign = User(email=f"foreign-{uuid4()}@example.test", timezone="UTC")
    db_session.add(foreign)
    db_session.flush()
    db_session.add_all([
        Contact(user_id=owner.id, name="Owner Recruiter", email="owner@example.test"),
        Contact(user_id=foreign.id, name="Foreign Recruiter", email="foreign@example.test"),
    ])
    db_session.commit()

    response = auth_client.get("/crm/contacts", params={"q": "Recruiter", "limit": 100})
    assert response.status_code == 200
    contacts = response.json()["contacts"]
    assert any(item["name"] == "Owner Recruiter" for item in contacts)
    assert all(item["name"] != "Foreign Recruiter" for item in contacts)
