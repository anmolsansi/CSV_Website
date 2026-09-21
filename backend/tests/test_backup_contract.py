import copy
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.backup_schemas import (
    BACKUP_SCHEMA_REVISION,
    BACKUP_V2_SECTIONS,
    CSV_ROW_TEXT_FIELDS,
    ApplyPilotBatchBackupV2,
    AuditEventBackupV2,
    BackupContractError,
    ColumnPreferenceBackupV2,
    CompanyAliasBackupV2,
    CsvRowBackupV2,
    JobTrackBackupV2,
    JobLifecycleEventBackupV2,
    MODEL_FIELD_INVENTORY,
    SavedViewBackupV2,
    SearchSessionBackupV2,
    UrlHistoryBackupV2,
    UserGoalBackupV2,
    UserProfileBackupV2,
    WorkItemBackupV2,
    WorkItemOverrideBackupV2,
    adapt_v1_backup,
    compute_sections_checksum,
    inventory_gaps,
    parse_backup_json,
    validate_backup_v2,
)
from app.models import (
    CSV_COLUMNS,
    ApplyPilotBatch,
    AuditEvent,
    ColumnPreference,
    CompanyAlias,
    CsvRow,
    JobTrack,
    JobLifecycleEvent,
    MaintenanceStatus,
    OAuthIdentity,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
    UserGoal,
    WorkItem,
    WorkItemOverride,
)
from app.services.backups import export_backup_v2, restore_backup_v2
from app.today_schemas import followup_action_key, manual_action_key

NOW = "2026-09-16T09:30:00Z"


def _complete_csv_row(**overrides):
    record = {name: None for name in CsvRowBackupV2.model_fields}
    record.update(
        {
            "backup_ref": "row-1",
            "upload_batch_id": "batch-1",
            "created_at": NOW,
            "clicked": False,
            "clicked_at": None,
            "archived": False,
            "is_duplicate": False,
            "duplicate_of_ref": None,
            "url": "https://example.com/job/1",
        }
    )
    record.update(overrides)
    return record


def _complete_track(**overrides):
    record = {name: None for name in JobTrackBackupV2.model_fields}
    record.update(
        {
            "backup_ref": "track-1",
            "csv_row_ref": "row-1",
            "url": "https://example.com/job/1",
            "status": "opened",
            "open_count": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    record.update(overrides)
    return record


def _valid_payload():
    sections = {name: [] for name in BACKUP_V2_SECTIONS}
    sections["csv_rows"] = [_complete_csv_row(page_number="", jd_text=None)]
    sections["job_tracks"] = [_complete_track(notes="", applied_at=None)]
    payload = {
        "version": "2.0",
        "backup_id": str(uuid4()),
        "exported_at": NOW,
        "schema_revision": BACKUP_SCHEMA_REVISION,
        "sections": sections,
        "counts": {name: len(records) for name, records in sections.items()},
    }
    payload["checksum_sha256"] = compute_sections_checksum(sections)
    return payload


def _rechecksum(payload):
    payload["counts"] = {
        name: len(payload["sections"][name]) for name in BACKUP_V2_SECTIONS
    }
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])
    return payload


def test_assert_complete_model_field_inventory():
    models = {
        "User": User,
        "OAuthIdentity": OAuthIdentity,
        "UrlHistory": UrlHistory,
        "CsvRow": CsvRow,
        "JobTrack": JobTrack,
        "CompanyAlias": CompanyAlias,
        "JobLifecycleEvent": JobLifecycleEvent,
        "SavedView": SavedView,
        "SearchSession": SearchSession,
        "ColumnPreference": ColumnPreference,
        "AuditEvent": AuditEvent,
        "ApplyPilotBatch": ApplyPilotBatch,
        "UserGoal": UserGoal,
        "WorkItem": WorkItem,
        "WorkItemOverride": WorkItemOverride,
        "MaintenanceStatus": MaintenanceStatus,
    }

    assert tuple(CSV_COLUMNS) == CSV_ROW_TEXT_FIELDS
    assert inventory_gaps(models) == {}
    assert all(
        entry.reason.strip()
        for fields in MODEL_FIELD_INVENTORY.values()
        for entry in fields.values()
    )
    assert not any(
        entry.disposition == "migration_blocker"
        for fields in MODEL_FIELD_INVENTORY.values()
        for entry in fields.values()
    )


def test_frozen_section_record_allowlists_are_strict():
    expected_models = {
        "csv_rows": CsvRowBackupV2,
        "url_history": UrlHistoryBackupV2,
        "job_tracks": JobTrackBackupV2,
        "company_aliases": CompanyAliasBackupV2,
        "work_items": WorkItemBackupV2,
        "work_item_overrides": WorkItemOverrideBackupV2,
        "lifecycle_events": JobLifecycleEventBackupV2,
        "saved_views": SavedViewBackupV2,
        "sessions": SearchSessionBackupV2,
        "audit_events": AuditEventBackupV2,
        "applypilot_batches": ApplyPilotBatchBackupV2,
        "column_preferences": ColumnPreferenceBackupV2,
        "user_goal": UserGoalBackupV2,
        "user_profile": UserProfileBackupV2,
    }
    assert tuple(expected_models) == BACKUP_V2_SECTIONS
    for model in expected_models.values():
        assert model.model_config["extra"] == "forbid"
        assert model.model_config["strict"] is True
        assert "backup_ref" in model.model_fields


def test_null_empty_false_zero_round_trip():
    payload = _valid_payload()
    validated = validate_backup_v2(json.dumps(payload))
    dumped = validated.model_dump(mode="json")

    row = dumped["sections"]["csv_rows"][0]
    track = dumped["sections"]["job_tracks"][0]
    assert row["jd_text"] is None
    assert row["page_number"] == ""
    assert row["clicked"] is False
    assert track["open_count"] == 0
    assert track["notes"] == ""
    assert track["applied_at"] is None

    reparsed = validate_backup_v2(json.dumps(dumped))
    assert reparsed.model_dump(mode="json") == dumped


def test_older_v2_without_lifecycle_section_keeps_original_checksum_contract():
    payload = _valid_payload()
    payload["sections"].pop("lifecycle_events")
    payload["counts"].pop("lifecycle_events")
    payload["sections"].pop("user_profile")
    payload["counts"].pop("user_profile")
    payload["schema_revision"] = "2.0.0"
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])

    validated = validate_backup_v2(json.dumps(payload))
    assert validated.sections.lifecycle_events == []
    assert validated.counts.lifecycle_events == 0
    assert validated.sections.user_profile == []
    assert validated.counts.user_profile == 0


def test_v21_without_user_profile_keeps_original_checksum_contract():
    payload = _valid_payload()
    payload["sections"].pop("user_profile")
    payload["counts"].pop("user_profile")
    payload["schema_revision"] = "2.1.0"
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])

    validated = validate_backup_v2(json.dumps(payload))
    assert validated.sections.user_profile == []
    assert validated.counts.user_profile == 0


def test_pre_jg030_v2_without_company_aliases_keeps_original_checksum_contract():
    payload = _valid_payload()
    payload["sections"].pop("company_aliases")
    payload["counts"].pop("company_aliases")
    payload["schema_revision"] = "2.4.0"
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])

    validated = validate_backup_v2(json.dumps(payload))
    assert validated.sections.company_aliases == []
    assert validated.counts.company_aliases == 0


def test_pre_jg025_v2_without_today_sections_keeps_original_checksum_contract():
    payload = _valid_payload()
    payload["sections"].pop("work_items")
    payload["sections"].pop("work_item_overrides")
    payload["counts"].pop("work_items")
    payload["counts"].pop("work_item_overrides")
    payload["schema_revision"] = "2.3.0"
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])

    validated = validate_backup_v2(json.dumps(payload))
    assert validated.sections.work_items == []
    assert validated.counts.work_items == 0
    assert validated.sections.work_item_overrides == []
    assert validated.counts.work_item_overrides == 0


def test_unknown_section_or_ownership_field():
    payload = _valid_payload()
    payload["sections"]["users"] = []
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_schema")

    payload = _valid_payload()
    payload["sections"]["csv_rows"][0]["user_id"] = 999
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_schema")


def test_duplicate_refs_and_bad_checksum():
    payload = _valid_payload()
    duplicate = copy.deepcopy(payload["sections"]["csv_rows"][0])
    duplicate["url"] = "https://example.com/job/2"
    payload["sections"]["csv_rows"].append(duplicate)
    _rechecksum(payload)

    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (409, "duplicate_backup_ref")
    assert exc.value.as_detail()["section"] == "csv_rows"

    payload = _valid_payload()
    payload["checksum_sha256"] = "0" * 64
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_checksum")


def test_duplicate_json_keys_and_non_finite_numbers_are_rejected():
    with pytest.raises(BackupContractError) as exc:
        parse_backup_json('{"version":"2.0","version":"2.0"}')
    assert (exc.value.status_code, exc.value.code) == (400, "duplicate_json_key")

    with pytest.raises(BackupContractError) as exc:
        parse_backup_json('{"value":NaN}')
    assert (exc.value.status_code, exc.value.code) == (400, "non_finite_number")


def test_reference_targets_and_field_limits_are_checked_before_restore():
    payload = _valid_payload()
    payload["sections"]["job_tracks"][0]["csv_row_ref"] = "missing-row"
    _rechecksum(payload)
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (
        409,
        "conflicting_reference_graph",
    )

    payload = _valid_payload()
    payload["sections"]["lifecycle_events"] = [{
        "backup_ref": "event-1",
        "event_key": "operation:00000000-0000-4000-8000-000000000001",
        "job_url": "https://example.com/job/1",
        "csv_row_ref": "missing-row",
        "job_track_ref": "track-1",
        "kind": "status_changed",
        "occurred_at": NOW,
        "recorded_at": NOW,
        "source": "test",
        "payload": {"from": "opened", "to": "applied"},
    }]
    _rechecksum(payload)
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (
        409,
        "conflicting_reference_graph",
    )

    payload = _valid_payload()
    payload["sections"]["job_tracks"][0]["notes"] = "x" * 20_001
    _rechecksum(payload)
    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (413, "field_too_large")


def test_v1_adapter_records_missing_fields_without_inference():
    legacy = {
        "version": "1.0",
        "exported_at": "2026-09-12T12:00:00",
        "csv_rows": [{"url": "https://example.com/job/1", "title": "Engineer"}],
        "job_tracks": [
            {
                "url": "https://example.com/job/1",
                "status": "applied",
                "notes": "legacy note",
            }
        ],
        "saved_views": [],
        "sessions": [],
        "audit_events": [],
        "applypilot_batches": [],
    }

    adapted = adapt_v1_backup(legacy)
    track = adapted.sections["job_tracks"][0]

    assert "incomplete_legacy_backup" in adapted.warnings
    assert {"url_history", "column_preferences", "user_goal"} <= adapted.absent_sections
    assert "applied_at" in track.missing_fields
    assert "opened_at" in track.missing_fields
    assert "applied_at" not in track.data
    assert "opened_at" not in track.data
    assert track.data["status"] == "applied"


def test_v1_adapter_rejects_ownership_injection():
    with pytest.raises(BackupContractError) as exc:
        adapt_v1_backup({"version": "1.0", "user_id": 7})
    assert (exc.value.status_code, exc.value.code) == (
        400,
        "ownership_field_forbidden",
    )

def test_backup_lifecycle_roundtrip_preserves_occurrence_without_derived_first_events(
    db_session,
):
    source = User(email=f"jg008-backup-source-{uuid4()}@example.test")
    db_session.add(source)
    db_session.flush()
    row = CsvRow(
        user_id=source.id,
        upload_batch_id="jg008-backup",
        url="https://backup-lifecycle.example/job/1",
        clicked=True,
        clicked_at=datetime(2026, 9, 18, 8, 15, 0),
    )
    db_session.add(row)
    db_session.flush()
    track = JobTrack(
        user_id=source.id,
        csv_row_id=row.id,
        url=row.url,
        status="applied",
        applied_at=datetime(2026, 9, 18, 8, 30, 0),
    )
    db_session.add(track)
    db_session.flush()
    occurred_at = datetime(2026, 9, 18, 8, 31, 45)
    recorded_at = datetime(2026, 9, 18, 8, 32, 0)
    source_event = JobLifecycleEvent(
        user_id=source.id,
        event_key=f"operation:{uuid4()}",
        job_url=row.url,
        csv_row_id=row.id,
        job_track_id=track.id,
        kind="status_changed",
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        source="backup_test",
        payload={"from": "opened", "to": "applied"},
    )
    db_session.add(source_event)
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    assert payload["counts"]["lifecycle_events"] == 1
    assert payload["sections"]["lifecycle_events"][0]["occurred_at"].startswith(
        "2026-09-18T08:31:45"
    )

    destination = User(email=f"jg008-backup-dest-{uuid4()}@example.test")
    db_session.add(destination)
    db_session.commit()
    db_session.refresh(destination)

    result = restore_backup_v2(
        db_session,
        destination.id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert result["counts"]["lifecycle_events"] == {
        "created": 1,
        "skipped": 0,
        "conflicts": 0,
    }

    db_session.expire_all()
    events = db_session.query(JobLifecycleEvent).filter_by(
        user_id=destination.id
    ).all()
    assert len(events) == 1
    restored = events[0]
    assert restored.event_key == source_event.event_key
    assert restored.kind == "status_changed"
    assert restored.occurred_at == occurred_at
    assert restored.recorded_at == recorded_at
    assert restored.payload == {"from": "opened", "to": "applied"}
    assert restored.csv_row_id is not None
    assert restored.job_track_id is not None
    assert db_session.query(JobLifecycleEvent).filter(
        JobLifecycleEvent.user_id == destination.id,
        JobLifecycleEvent.kind.in_(["first_visited", "first_applied"]),
    ).count() == 0



def test_timezone_profile_backup_roundtrip_and_replay(db_session):
    source = User(
        email=f"jg010-profile-source-{uuid4()}@example.test",
        timezone="Asia/Kolkata",
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    payload = export_backup_v2(db_session, source.id)
    assert payload["schema_revision"] == BACKUP_SCHEMA_REVISION
    assert payload["counts"]["user_profile"] == 1
    assert payload["sections"]["user_profile"][0]["timezone"] == "Asia/Kolkata"

    destination = User(
        email=f"jg010-profile-dest-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(destination)
    db_session.commit()
    db_session.refresh(destination)

    result = restore_backup_v2(
        db_session,
        destination.id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert result["counts"]["user_profile"] == {
        "created": 1,
        "skipped": 0,
        "conflicts": 0,
    }

    db_session.expire_all()
    restored_user = db_session.get(User, destination.id)
    assert restored_user.timezone == "Asia/Kolkata"

    restored_user.timezone = "America/New_York"
    db_session.commit()

    replay = restore_backup_v2(
        db_session,
        destination.id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert replay["counts"]["user_profile"] == {
        "created": 0,
        "skipped": 1,
        "conflicts": 0,
    }
    db_session.expire_all()
    assert db_session.get(User, destination.id).timezone == "America/New_York"


def test_invalid_backup_timezone_is_rejected():
    payload = _valid_payload()
    payload["sections"]["user_profile"] = [{
        "backup_ref": "profile-1",
        "timezone": "+05:30",
    }]
    _rechecksum(payload)

    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_schema")


def test_multiple_user_profiles_are_rejected():
    payload = _valid_payload()
    payload["sections"]["user_profile"] = [
        {"backup_ref": "profile-1", "timezone": "UTC"},
        {"backup_ref": "profile-2", "timezone": "Asia/Kolkata"},
    ]
    _rechecksum(payload)

    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_schema")


def test_backup_preserves_archive_state(db_session):
    archived_at = datetime(2026, 9, 20, 5, 45, 0)
    source = User(
        email="archive-backup-source@jobgrid.dev",
        timezone="America/Chicago",
        retention_days=30,
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(
        CsvRow(
            user_id=source.id,
            upload_batch_id="jg012-source",
            url="https://example.com/jg012/archive-state",
            title="Archive State",
            clicked=True,
            archived=True,
            archived_at=archived_at,
        )
    )
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    assert payload["schema_revision"] == BACKUP_SCHEMA_REVISION
    assert payload["sections"]["csv_rows"][0]["archived"] is True
    assert payload["sections"]["csv_rows"][0]["archived_at"] == "2026-09-20T05:45:00Z"
    assert payload["sections"]["user_profile"][0]["retention_days"] == 30

    target = User(
        email="archive-backup-target@jobgrid.dev",
        timezone="UTC",
        retention_days=None,
    )
    db_session.add(target)
    db_session.commit()
    target_id = target.id

    document = validate_backup_v2(payload)
    result = restore_backup_v2(db_session, target_id, document, "merge_missing")
    assert result["counts"]["csv_rows"]["created"] == 1
    assert result["counts"]["user_profile"]["created"] == 1

    db_session.expire_all()
    restored = (
        db_session.query(CsvRow)
        .filter_by(
            user_id=target_id,
            url="https://example.com/jg012/archive-state",
        )
        .one()
    )
    restored_user = db_session.get(User, target_id)
    assert restored.archived is True
    assert restored.archived_at == archived_at
    assert restored_user.retention_days == 30
    assert restored_user.timezone == "America/Chicago"


def test_older_v2_backup_defaults_new_retention_fields_to_null():
    payload = _valid_payload()
    payload["schema_revision"] = "2.2.0"
    payload["sections"]["csv_rows"][0].pop("archived_at", None)
    if payload["sections"]["user_profile"]:
        payload["sections"]["user_profile"][0].pop("retention_days", None)
    payload["checksum_sha256"] = compute_sections_checksum(payload["sections"])

    document = validate_backup_v2(payload)
    assert document.sections.csv_rows[0].archived_at is None
    if document.sections.user_profile:
        assert document.sections.user_profile[0].retention_days is None


def test_v22_profile_without_retention_days_keeps_original_checksum_contract():
    payload = _valid_payload()
    payload["schema_revision"] = "2.2.0"
    payload["sections"]["user_profile"] = [
        {"backup_ref": "profile-legacy", "timezone": "UTC"}
    ]
    _rechecksum(payload)

    document = validate_backup_v2(payload)
    assert document.sections.user_profile[0].retention_days is None


@pytest.mark.parametrize("retention_days", [-1, 1, 6, 3651])
def test_backup_rejects_invalid_retention_days(retention_days):
    payload = _valid_payload()
    payload["sections"]["user_profile"] = [
        {
            "backup_ref": "profile-invalid-retention",
            "timezone": "UTC",
            "retention_days": retention_days,
        }
    ]
    _rechecksum(payload)

    with pytest.raises(BackupContractError) as exc:
        validate_backup_v2(payload)
    assert (exc.value.status_code, exc.value.code) == (400, "invalid_schema")


def test_backup_round_trip_retains_snooze_and_manual_action(db_session):
    source = User(email=f"jg025-backup-source-{uuid4()}@example.test")
    db_session.add(source)
    db_session.flush()

    row = CsvRow(
        user_id=source.id,
        upload_batch_id="jg025",
        url=f"https://today-backup.example/jobs/{uuid4()}",
        title="Platform Engineer",
    )
    view = SavedView(
        user_id=source.id,
        name=f"Today shortlist {uuid4()}",
        view_type="job_links",
        filters={"decision": "SHORTLIST"},
    )
    track = JobTrack(
        user_id=source.id,
        url=row.url,
        status="follow_up",
        follow_up_at=datetime(2026, 9, 25, 9, 30, 0),
    )
    db_session.add_all([row, view, track])
    db_session.flush()

    item = WorkItem(
        user_id=source.id,
        track_id=track.id,
        row_id=row.id,
        source_view_id=view.id,
        origin_key=f"view:{view.id}:row:{row.id}",
        description="Send tailored portfolio",
        due_at=datetime(2026, 9, 24, 12, 0, 0),
        priority=3,
        state="pending",
        version=2,
    )
    db_session.add(item)
    db_session.flush()

    manual_snooze = datetime(2026, 9, 24, 15, 0, 0, tzinfo=timezone.utc)
    followup_snooze = datetime(2026, 9, 26, 9, 30, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            WorkItemOverride(
                user_id=source.id,
                action_key=manual_action_key(item.id),
                snoozed_until=manual_snooze,
                version=2,
            ),
            WorkItemOverride(
                user_id=source.id,
                action_key=followup_action_key(track.id, track.follow_up_at),
                snoozed_until=followup_snooze,
                version=1,
            ),
        ]
    )
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    assert payload["counts"]["work_items"] == 1
    assert payload["counts"]["work_item_overrides"] == 2
    portable_item = payload["sections"]["work_items"][0]
    assert portable_item["track_ref"] is not None
    assert portable_item["row_ref"] is not None
    assert portable_item["source_view_ref"] is not None
    assert portable_item["origin_key"] == (
        f"view:{portable_item['source_view_ref']}:row:{portable_item['row_ref']}"
    )
    assert all(
        "action_key" not in override
        for override in payload["sections"]["work_item_overrides"]
    )

    destination = User(email=f"jg025-backup-dest-{uuid4()}@example.test")
    db_session.add(destination)
    db_session.commit()
    destination_id = destination.id

    result = restore_backup_v2(
        db_session,
        destination_id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert result["counts"]["work_items"] == {
        "created": 1,
        "skipped": 0,
        "conflicts": 0,
    }
    assert result["counts"]["work_item_overrides"] == {
        "created": 2,
        "skipped": 0,
        "conflicts": 0,
    }

    db_session.expire_all()
    restored_item = db_session.query(WorkItem).filter_by(
        user_id=destination_id
    ).one()
    restored_track = db_session.query(JobTrack).filter_by(
        user_id=destination_id
    ).one()
    restored_row = db_session.query(CsvRow).filter_by(
        user_id=destination_id
    ).one()
    restored_view = db_session.query(SavedView).filter_by(
        user_id=destination_id
    ).one()

    assert restored_item.description == "Send tailored portfolio"
    assert restored_item.track_id == restored_track.id
    assert restored_item.row_id == restored_row.id
    assert restored_item.source_view_id == restored_view.id
    assert restored_item.origin_key == (
        f"view:{restored_view.id}:row:{restored_row.id}"
    )

    overrides = {
        override.action_key: override
        for override in db_session.query(WorkItemOverride).filter_by(
            user_id=destination_id
        ).all()
    }
    manual_key = manual_action_key(restored_item.id)
    followup_key = followup_action_key(
        restored_track.id, restored_track.follow_up_at
    )
    assert set(overrides) == {manual_key, followup_key}
    assert overrides[manual_key].snoozed_until == manual_snooze
    assert overrides[manual_key].version == 2
    assert overrides[followup_key].snoozed_until == followup_snooze

    replay = restore_backup_v2(
        db_session,
        destination_id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert replay["counts"]["work_items"]["skipped"] == 1
    assert replay["counts"]["work_item_overrides"]["skipped"] == 2


def test_backup_import_invalid_json_returns_parser_400(auth_client):
    response = auth_client.post(
        "/crm/backup/import?mode=verify_only",
        files={"file": ("invalid.json", b'{"version":', "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_json"
    assert "traceback" not in response.text.lower()
