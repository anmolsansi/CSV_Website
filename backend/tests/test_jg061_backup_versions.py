import json
from uuid import uuid4

from app.models import CsvRow, JobTrack, User
from app.services.import_backups import (
    export_backup_v2_with_import_mappings,
    restore_backup_payload_with_import_mappings,
)


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_row_and_track_versions_round_trip_through_portable_backup(db_session):
    source = _user(db_session, "jg061-backup-source")
    row = CsvRow(
        user_id=source.id,
        upload_batch_id=str(uuid4()),
        url=f"https://example.test/jobs/{uuid4()}",
        title="Versioned row",
        version=7,
    )
    db_session.add(row)
    db_session.flush()
    track = JobTrack(
        user_id=source.id,
        csv_row_id=row.id,
        url=row.url,
        title=row.title,
        status="opened",
        version=4,
    )
    db_session.add(track)
    db_session.commit()

    backup = export_backup_v2_with_import_mappings(db_session, source.id)
    assert backup["schema_revision"] == "2.13.0"
    assert backup["sections"]["csv_rows"][0]["version"] == 7
    assert backup["sections"]["job_tracks"][0]["version"] == 4

    destination = _user(db_session, "jg061-backup-destination")
    result = restore_backup_payload_with_import_mappings(
        db_session,
        destination.id,
        json.dumps(backup).encode("utf-8"),
        "merge_missing",
    )
    assert result["counts"]["csv_rows"]["created"] == 1
    assert result["counts"]["job_tracks"]["created"] == 1

    restored_row = db_session.query(CsvRow).filter_by(
        user_id=destination.id,
        url=row.url,
    ).one()
    restored_track = db_session.query(JobTrack).filter_by(
        user_id=destination.id,
        url=row.url,
    ).one()
    assert restored_row.version == 7
    assert restored_track.version == 4
    assert restored_track.csv_row_id == restored_row.id
