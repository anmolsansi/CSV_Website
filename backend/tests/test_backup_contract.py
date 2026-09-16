import copy
import json
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
    CsvRowBackupV2,
    JobTrackBackupV2,
    MODEL_FIELD_INVENTORY,
    SavedViewBackupV2,
    SearchSessionBackupV2,
    UrlHistoryBackupV2,
    UserGoalBackupV2,
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
    CsvRow,
    JobTrack,
    OAuthIdentity,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
    UserGoal,
)

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
        "SavedView": SavedView,
        "SearchSession": SearchSession,
        "ColumnPreference": ColumnPreference,
        "AuditEvent": AuditEvent,
        "ApplyPilotBatch": ApplyPilotBatch,
        "UserGoal": UserGoal,
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
        "saved_views": SavedViewBackupV2,
        "sessions": SearchSessionBackupV2,
        "audit_events": AuditEventBackupV2,
        "applypilot_batches": ApplyPilotBatchBackupV2,
        "column_preferences": ColumnPreferenceBackupV2,
        "user_goal": UserGoalBackupV2,
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
