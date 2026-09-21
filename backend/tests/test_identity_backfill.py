from __future__ import annotations

from uuid import uuid4

import pytest

from app.backup_schemas import BackupContractError, validate_backup_v2
from app.models import CompanyAlias, CsvRow, JobTrack, User
from app.services.backups import export_backup_v2, restore_backup_v2
from app.services.job_identity import (
    CANONICALIZATION_VERSION,
    backfill_identity_batch,
    canonicalize_job_url,
    normalize_company_alias_key,
)


def _user(db_session, prefix: str) -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    db_session.add(user)
    db_session.flush()
    return user


def test_backfill_retry_is_idempotent(db_session):
    user = _user(db_session, "jg030-idempotent")
    urls = [
        "https://jobs.example.test/role/1?utm_source=alpha",
        "https://jobs.example.test/role/2?gclid=tracking",
    ]
    rows = [
        CsvRow(user_id=user.id, upload_batch_id="jg030", url=url)
        for url in urls
    ]
    db_session.add_all(rows)
    db_session.commit()
    checkpoint = min(row.id for row in rows) - 1

    first = backfill_identity_batch(
        db_session, CsvRow, after_id=checkpoint, limit=len(rows)
    )
    db_session.commit()
    second = backfill_identity_batch(
        db_session, CsvRow, after_id=checkpoint, limit=len(rows)
    )

    assert (first.scanned, first.updated, first.unchanged, first.invalid) == (
        2,
        2,
        0,
        0,
    )
    assert (second.scanned, second.updated, second.unchanged, second.invalid) == (
        2,
        0,
        2,
        0,
    )


def test_canonical_collision_retains_two_tracks(db_session):
    user = _user(db_session, "jg030-collision")
    original = [
        "https://jobs.example.test/role/77?utm_source=one",
        "https://jobs.example.test/role/77?utm_campaign=two",
    ]
    seeded_tracks = [
        JobTrack(
            user_id=user.id,
            url=original[0],
            status="applied",
            notes="first application",
        ),
        JobTrack(
            user_id=user.id,
            url=original[1],
            status="interviewing",
            notes="second application",
        ),
    ]
    db_session.add_all(seeded_tracks)
    db_session.commit()
    checkpoint = min(track.id for track in seeded_tracks) - 1

    report = backfill_identity_batch(
        db_session, JobTrack, after_id=checkpoint, limit=len(seeded_tracks)
    )
    db_session.commit()
    tracks = (
        db_session.query(JobTrack)
        .filter(JobTrack.user_id == user.id)
        .order_by(JobTrack.id.asc())
        .all()
    )

    assert len(tracks) == 2
    assert [track.url for track in tracks] == original
    assert [track.status for track in tracks] == ["applied", "interviewing"]
    assert [track.notes for track in tracks] == [
        "first application",
        "second application",
    ]
    assert tracks[0].canonical_url_hash == tracks[1].canonical_url_hash
    assert report.collision_groups == 1
    assert report.collision_records == 2


def test_aliases_are_account_scoped(db_session):
    first = _user(db_session, "jg030-alias-a")
    second = _user(db_session, "jg030-alias-b")
    alias_key = normalize_company_alias_key("  Acme   Corp  ")

    db_session.add_all(
        [
            CompanyAlias(
                user_id=first.id,
                alias_key=alias_key,
                display_name="Acme Corp",
                company_key=str(uuid4()),
            ),
            CompanyAlias(
                user_id=second.id,
                alias_key=alias_key,
                display_name="ACME CORP",
                company_key=str(uuid4()),
            ),
        ]
    )
    db_session.commit()

    first_alias = db_session.query(CompanyAlias).filter_by(user_id=first.id).one()
    second_alias = db_session.query(CompanyAlias).filter_by(user_id=second.id).one()
    assert first_alias.alias_key == second_alias.alias_key == "acme corp"
    assert first_alias.company_key != second_alias.company_key


def test_backup_restores_alias_grouping(db_session):
    source = _user(db_session, "jg030-backup-source")
    company_key = str(uuid4())
    db_session.add_all(
        [
            CompanyAlias(
                user_id=source.id,
                alias_key=normalize_company_alias_key("Acme"),
                display_name="Acme",
                company_key=company_key,
            ),
            CompanyAlias(
                user_id=source.id,
                alias_key=normalize_company_alias_key("Acme Corporation"),
                display_name="Acme Corporation",
                company_key=company_key,
            ),
        ]
    )
    original_url = "https://jobs.example.test/role/99?utm_source=backup"
    row = CsvRow(
        user_id=source.id,
        upload_batch_id="jg030-backup",
        url=original_url,
        canonical_url="https://stale.invalid/",
        canonical_url_hash="f" * 64,
    )
    db_session.add(row)
    db_session.flush()
    track = JobTrack(
        user_id=source.id,
        csv_row_id=row.id,
        url=original_url,
        status="applied",
        notes="preserve me",
        canonical_url="https://stale.invalid/",
        canonical_url_hash="e" * 64,
    )
    db_session.add(track)
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    assert payload["identity_rule_version"] == CANONICALIZATION_VERSION
    assert payload["sections"]["csv_rows"][0]["url"] == original_url
    assert payload["sections"]["job_tracks"][0]["url"] == original_url
    assert "canonical_url" not in payload["sections"]["csv_rows"][0]
    assert "canonical_url_hash" not in payload["sections"]["job_tracks"][0]
    assert payload["counts"]["company_aliases"] == 2

    destination = _user(db_session, "jg030-backup-dest")
    db_session.commit()
    result = restore_backup_v2(
        db_session,
        destination.id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert result["counts"]["company_aliases"]["created"] == 2

    db_session.expire_all()
    aliases = (
        db_session.query(CompanyAlias)
        .filter(CompanyAlias.user_id == destination.id)
        .order_by(CompanyAlias.alias_key.asc())
        .all()
    )
    restored_row = db_session.query(CsvRow).filter_by(
        user_id=destination.id, url=original_url
    ).one()
    restored_track = db_session.query(JobTrack).filter_by(
        user_id=destination.id, url=original_url
    ).one()
    expected = canonicalize_job_url(original_url)

    assert len(aliases) == 2
    assert {alias.company_key for alias in aliases} == {company_key}
    assert restored_row.url == original_url
    assert restored_track.url == original_url
    assert restored_track.status == "applied"
    assert restored_track.notes == "preserve me"
    assert restored_row.canonical_url == expected.canonical_url
    assert restored_row.canonical_url_hash == expected.canonical_url_hash
    assert restored_track.canonical_url == expected.canonical_url
    assert restored_track.canonical_url_hash == expected.canonical_url_hash


def test_dry_run_writes_nothing(db_session):
    user = _user(db_session, "jg030-dry-run")
    row = CsvRow(
        user_id=user.id,
        upload_batch_id="jg030",
        url="https://jobs.example.test/role/123?utm_source=dry",
    )
    db_session.add(row)
    db_session.commit()

    report = backfill_identity_batch(
        db_session,
        CsvRow,
        after_id=row.id - 1,
        limit=1,
        dry_run=True,
    )
    db_session.flush()
    db_session.expire_all()
    persisted = db_session.query(CsvRow).filter_by(id=row.id).one()

    assert report.updated == 1
    assert report.dry_run is True
    assert persisted.canonical_url is None
    assert persisted.canonical_url_hash is None


def test_restore_rejects_unknown_recorded_identity_rule_before_mutation(db_session):
    source = _user(db_session, "jg030-rule-source")
    db_session.add(
        CsvRow(
            user_id=source.id,
            upload_batch_id="jg030",
            url="https://jobs.example.test/role/versioned",
        )
    )
    db_session.commit()
    payload = export_backup_v2(db_session, source.id)
    payload["identity_rule_version"] = "ccr-identity-999"

    destination = _user(db_session, "jg030-rule-dest")
    db_session.commit()
    with pytest.raises(BackupContractError) as exc:
        restore_backup_v2(
            db_session,
            destination.id,
            validate_backup_v2(payload),
            "verify_only",
        )

    assert exc.value.code == "unsupported_identity_rule_version"
    assert (
        db_session.query(CsvRow)
        .filter(CsvRow.user_id == destination.id)
        .count()
        == 0
    )
