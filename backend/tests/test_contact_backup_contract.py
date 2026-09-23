import json
from datetime import datetime
from uuid import uuid4

from app.contact_models import ApplicationContact, Contact, Interview
from app.models import JobTrack, User
from app.services.contact_backups import export_backup_v2_with_contacts, restore_backup_payload_with_contacts


def test_backup_maps_all_relationships(db_session):
    source = User(email=f"f8-backup-source-{uuid4()}@example.test", timezone="America/Chicago")
    target = User(email=f"f8-backup-target-{uuid4()}@example.test", timezone="UTC")
    db_session.add_all([source, target])
    db_session.flush()

    track = JobTrack(
        user_id=source.id,
        url=f"https://example.test/jobs/{uuid4()}",
        company="Acme",
        title="Backend Engineer",
    )
    contact = Contact(
        user_id=source.id,
        name="Recruiter",
        email="private@example.test",
        notes="private recruiter note",
    )
    db_session.add_all([track, contact])
    db_session.flush()
    link = ApplicationContact(
        user_id=source.id,
        track_id=track.id,
        contact_id=contact.id,
        role="recruiter",
        referral_source="conference",
    )
    interview = Interview(
        user_id=source.id,
        track_id=track.id,
        contact_id=contact.id,
        starts_at=datetime(2026, 10, 5, 16, 0),
        ends_at=datetime(2026, 10, 5, 17, 0),
        timezone="America/Chicago",
        kind="video",
        round_label="Technical",
        preparation_notes="private prep",
    )
    db_session.add_all([link, interview])
    db_session.commit()

    payload = export_backup_v2_with_contacts(db_session, source.id)
    extension = payload["f8_private"]
    sections = extension["sections"]
    assert len(sections["contacts"]) == 1
    assert len(sections["application_contacts"]) == 1
    assert len(sections["interviews"]) == 1
    assert sections["application_contacts"][0]["contact_ref"] == sections["contacts"][0]["backup_ref"]
    assert sections["interviews"][0]["contact_ref"] == sections["contacts"][0]["backup_ref"]
    assert sections["interviews"][0]["track_ref"] == sections["application_contacts"][0]["track_ref"]
    assert sections["contacts"][0]["notes"] == "private recruiter note"
    assert sections["interviews"][0]["preparation_notes"] == "private prep"

    result = restore_backup_payload_with_contacts(
        db_session,
        target.id,
        json.dumps(payload).encode("utf-8"),
        "merge_missing",
    )
    assert result["counts"]["contacts"]["created"] == 1
    assert result["counts"]["application_contacts"]["created"] == 1
    assert result["counts"]["interviews"]["created"] == 1

    restored_contact = db_session.query(Contact).filter(Contact.user_id == target.id).one()
    restored_track = db_session.query(JobTrack).filter(JobTrack.user_id == target.id, JobTrack.url == track.url).one()
    restored_link = db_session.query(ApplicationContact).filter(ApplicationContact.user_id == target.id).one()
    restored_interview = db_session.query(Interview).filter(Interview.user_id == target.id).one()
    assert restored_link.track_id == restored_track.id
    assert restored_link.contact_id == restored_contact.id
    assert restored_interview.track_id == restored_track.id
    assert restored_interview.contact_id == restored_contact.id
    assert restored_interview.timezone == "America/Chicago"
    assert restored_interview.starts_at == datetime(2026, 10, 5, 16, 0)
