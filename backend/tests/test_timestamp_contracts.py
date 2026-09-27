import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.backup_schemas import validate_backup_v2
from app.database import get_db
from app.main import app
from app.models import (
    JobTrack,
    ReminderDelivery,
    ReminderPreference,
    User,
    WorkItem,
    WorkItemOverride,
)
from app.reminder_schemas import (
    ReminderContractError,
    apply_delivery_transition,
    reminder_occurrence_key,
)
from app.services.backups import export_backup_v2, restore_backup_v2
from app.services.today import serialize_work_item
from app.time_utils import normalize_utc_instant, same_utc_instant
from app.today_schemas import SnoozeRequest, manual_action_key


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _parse_wire_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None and parsed.utcoffset() is not None
    return normalize_utc_instant(parsed)


def test_normalize_utc_instant_handles_offsets_dst_and_legacy_naive():
    positive = datetime(
        2026,
        9,
        24,
        20,
        30,
        0,
        123456,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    negative = datetime(
        2026,
        9,
        24,
        8,
        0,
        0,
        654321,
        tzinfo=timezone(-timedelta(hours=7)),
    )
    legacy_naive = datetime(2026, 9, 24, 15, 0, 0, 777888)

    assert normalize_utc_instant(positive) == datetime(
        2026, 9, 24, 15, 0, 0, 123456, tzinfo=timezone.utc
    )
    assert normalize_utc_instant(negative) == datetime(
        2026, 9, 24, 15, 0, 0, 654321, tzinfo=timezone.utc
    )
    assert normalize_utc_instant(legacy_naive) == datetime(
        2026, 9, 24, 15, 0, 0, 777888, tzinfo=timezone.utc
    )

    new_york = ZoneInfo("America/New_York")
    overlap_early = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0)
    overlap_late = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    assert normalize_utc_instant(overlap_early) == datetime(
        2026, 11, 1, 5, 30, tzinfo=timezone.utc
    )
    assert normalize_utc_instant(overlap_late) == datetime(
        2026, 11, 1, 6, 30, tzinfo=timezone.utc
    )
    assert not same_utc_instant(overlap_early, overlap_late)


def test_user_timestamp_inputs_still_require_explicit_timezone_offsets():
    with pytest.raises(ValidationError):
        SnoozeRequest(
            action_key="manual:1",
            until=datetime(2026, 9, 24, 15, 0, 0),
            version=1,
        )

    delivery = SimpleNamespace(status="sending", sent_at=None, version=1)
    with pytest.raises(ReminderContractError) as exc:
        apply_delivery_transition(
            delivery,
            "sent",
            sent_at=datetime(2026, 9, 24, 15, 0, 0),
        )
    assert exc.value.code == "sent_at_timezone_required"


def test_sqlite_instants_survive_reload_wire_serialization_and_backup(
    sqlite_acceptance_engine,
):
    Session = sessionmaker(bind=sqlite_acceptance_engine)
    db = Session()
    try:
        source = User(
            email=f"c05-source-{uuid4()}@example.test",
            timezone="America/New_York",
        )
        destination = User(
            email=f"c05-destination-{uuid4()}@example.test",
            timezone="UTC",
        )
        db.add_all([source, destination])
        db.flush()

        track = JobTrack(
            user_id=source.id,
            url=f"https://example.test/c05/{uuid4()}",
            company="C05 Test",
            title="Engineer",
            status="follow_up",
            follow_up_at=datetime(2026, 9, 25, 15, 0, 0),
        )
        item = WorkItem(
            user_id=source.id,
            description="C05 persisted snooze",
            due_at=datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc),
            priority=2,
            state="pending",
            version=1,
        )
        preference = ReminderPreference(
            user_id=source.id,
            enabled=False,
            channel="in_app",
            local_time="09:00",
            quiet_start="21:00",
            quiet_end="08:00",
        )
        db.add_all([track, item, preference])
        db.flush()

        snooze_input = datetime(
            2026,
            9,
            24,
            20,
            30,
            0,
            111222,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        )
        snooze_request = SnoozeRequest(
            action_key=manual_action_key(item.id),
            until=snooze_input,
            version=1,
        )
        expected_snooze = datetime(
            2026, 9, 24, 15, 0, 0, 111222, tzinfo=timezone.utc
        )
        assert snooze_request.until == expected_snooze
        db.add(
            WorkItemOverride(
                user_id=source.id,
                action_key=snooze_request.action_key,
                snoozed_until=snooze_request.until,
                version=1,
            )
        )

        due = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
        scheduled_input = datetime(
            2026,
            9,
            25,
            8,
            0,
            0,
            222333,
            tzinfo=timezone(-timedelta(hours=7)),
        )
        expected_scheduled = datetime(
            2026, 9, 25, 15, 0, 0, 222333, tzinfo=timezone.utc
        )
        accepted_input = datetime(
            2026,
            9,
            25,
            20,
            30,
            5,
            333444,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        )
        expected_sent = datetime(
            2026, 9, 25, 15, 0, 5, 333444, tzinfo=timezone.utc
        )
        delivery = ReminderDelivery(
            user_id=source.id,
            track_id=track.id,
            occurrence_key=reminder_occurrence_key(
                track_id=track.id,
                due_at=due,
                notification_local_date=datetime(2026, 9, 25).date(),
            ),
            channel="in_app",
            status="pending",
            scheduled_at=normalize_utc_instant(scheduled_input),
            version=1,
        )
        db.add(delivery)
        db.flush()
        apply_delivery_transition(delivery, "sending")
        apply_delivery_transition(delivery, "sent", sent_at=accepted_input)
        assert delivery.sent_at == expected_sent

        source_id = source.id
        destination_id = destination.id
        delivery_id = delivery.id
        item_id = item.id
        db.commit()
    finally:
        db.close()

    reloaded = Session()
    try:
        override = reloaded.query(WorkItemOverride).filter_by(
            user_id=source_id
        ).one()
        delivery = reloaded.get(ReminderDelivery, delivery_id)
        item = reloaded.get(WorkItem, item_id)

        # This is the SQLite behavior C-05 must tolerate: tzinfo is dropped on
        # reload even though these columns are declared DateTime(timezone=True).
        assert override.snoozed_until.tzinfo is None
        assert delivery.scheduled_at.tzinfo is None
        assert delivery.sent_at.tzinfo is None
        assert delivery.read_at is None

        assert normalize_utc_instant(override.snoozed_until) == expected_snooze
        assert normalize_utc_instant(delivery.scheduled_at) == expected_scheduled
        assert normalize_utc_instant(delivery.sent_at) == expected_sent
        assert normalize_utc_instant(override.snoozed_until).microsecond == 111222
        assert normalize_utc_instant(delivery.scheduled_at).microsecond == 222333
        assert normalize_utc_instant(delivery.sent_at).microsecond == 333444

        today_item = serialize_work_item(item, override)
        assert today_item["snoozed_until"] == "2026-09-24T15:00:00.111222Z"

        # Same accepted instant remains idempotent after persistence reload even
        # when the caller supplies the original non-UTC offset.
        prior_version = delivery.version
        apply_delivery_transition(delivery, "sent", sent_at=accepted_input)
        assert delivery.version == prior_version
        with pytest.raises(ReminderContractError) as changed:
            apply_delivery_transition(
                delivery,
                "sent",
                sent_at=accepted_input + timedelta(microseconds=1),
            )
        assert changed.value.code == "sent_at_immutable"

        exported = export_backup_v2(reloaded, source_id)
        portable_override = exported["sections"]["work_item_overrides"][0]
        portable_delivery = exported["sections"]["reminder_deliveries"][0]
        assert portable_override["snoozed_until"] == "2026-09-24T15:00:00.111222Z"
        assert portable_delivery["scheduled_at"] == "2026-09-25T15:00:00.222333Z"
        assert portable_delivery["sent_at"] == "2026-09-25T15:00:05.333444Z"
        assert portable_delivery["read_at"] is None

        restored = restore_backup_v2(
            reloaded,
            destination_id,
            validate_backup_v2(exported),
            "merge_missing",
        )
        assert restored["counts"]["work_item_overrides"]["created"] == 1
        assert restored["counts"]["reminder_deliveries"]["created"] == 1
        reloaded.expire_all()

        restored_override = reloaded.query(WorkItemOverride).filter_by(
            user_id=destination_id
        ).one()
        restored_delivery = reloaded.query(ReminderDelivery).filter_by(
            user_id=destination_id
        ).one()
        assert normalize_utc_instant(restored_override.snoozed_until) == expected_snooze
        assert normalize_utc_instant(restored_delivery.scheduled_at) == expected_scheduled
        assert normalize_utc_instant(restored_delivery.sent_at) == expected_sent
        assert restored_delivery.read_at is None

        reexported = export_backup_v2(reloaded, destination_id)
        reexported_delivery = reexported["sections"]["reminder_deliveries"][0]
        assert reexported_delivery["sent_at"] == "2026-09-25T15:00:05.333444Z"
    finally:
        reloaded.close()

    def override_get_db():
        request_db = Session()
        try:
            yield request_db
        finally:
            request_db.close()

    def override_get_current_user():
        return SimpleNamespace(id=source_id, timezone="America/New_York")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        with TestClient(app) as client:
            response = client.get("/crm/reminders")
        assert response.status_code == 200, response.text
        wire_delivery = next(
            row for row in response.json()["items"] if row["id"] == delivery_id
        )
        assert _parse_wire_instant(wire_delivery["scheduled_at"]) == expected_scheduled
        assert _parse_wire_instant(wire_delivery["sent_at"]) == expected_sent
        assert wire_delivery["read_at"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_c05_original_regressions_execute_against_sqlite(tmp_path):
    database_path = tmp_path / "c05-original-regressions.sqlite3"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "TEST_AUTH": "true",
            "SECRET_KEY": "c05-sqlite-regression-secret",
            "FRONTEND_URL": "http://localhost:5173",
            "ENVIRONMENT": "test",
            "RUN_MAINTENANCE_JOBS": "false",
            "RUN_REMINDER_WORKER": "false",
            "REMINDER_EMAIL_DELIVERY_ENABLED": "false",
        }
    )
    env.pop("TEST_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_backup_contract.py::test_backup_round_trip_retains_snooze_and_manual_action",
            "tests/test_reminder_models.py::test_illegal_state_transition_rejected",
            "-q",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "C-05 SQLite regression subprocess failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "2 passed" in result.stdout
