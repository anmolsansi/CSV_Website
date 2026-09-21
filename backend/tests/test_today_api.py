from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.backup_schemas import validate_backup_v2
from app.config import settings
from app.models import (
    CsvRow,
    JobLifecycleEvent,
    JobTrack,
    SavedView,
    User,
    WorkItem,
    WorkItemOverride,
)
from app.services.backups import export_backup_v2, restore_backup_v2
from app.services.today import build_today_queue
from app.today_schemas import followup_action_key, manual_action_key


def _test_user(db_session):
    user = (
        db_session.query(User)
        .filter_by(email="test@jobgrid.dev")
        .first()
    )
    assert user is not None
    return user


def _reset(auth_client):
    response = auth_client.post("/test/reset")
    assert response.status_code == 200


def test_queue_local_midnight_and_dst(db_session):
    user = User(
        email=f"today-dst-{uuid4()}@example.test",
        timezone="America/New_York",
    )
    db_session.add(user)
    db_session.flush()

    reference = datetime(
        2026,
        3,
        8,
        16,
        0,
        tzinfo=timezone.utc,
    )
    overdue = JobTrack(
        user_id=user.id,
        url=f"https://example.test/{uuid4()}",
        company="Overdue Co",
        title="Engineer",
        status="follow_up",
        follow_up_at=datetime(2026, 3, 8, 4, 30),
    )
    tomorrow = JobTrack(
        user_id=user.id,
        url=f"https://example.test/{uuid4()}",
        company="Tomorrow Co",
        title="Engineer",
        status="follow_up",
        follow_up_at=datetime(2026, 3, 9, 4, 30),
    )
    terminal = JobTrack(
        user_id=user.id,
        url=f"https://example.test/{uuid4()}",
        company="Terminal Co",
        title="Engineer",
        status="rejected",
        follow_up_at=datetime(2026, 3, 8, 3, 0),
    )
    db_session.add_all([overdue, tomorrow, terminal])
    db_session.flush()

    due_today = WorkItem(
        user_id=user.id,
        description="Today item",
        due_at=datetime(
            2026,
            3,
            9,
            3,
            30,
            tzinfo=timezone.utc,
        ),
        priority=2,
        state="pending",
        version=1,
    )
    undated = WorkItem(
        user_id=user.id,
        description="Undated item",
        due_at=None,
        priority=1,
        state="pending",
        version=1,
    )
    db_session.add_all([due_today, undated])
    db_session.flush()

    result = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key="dst-test-secret",
        now=reference,
    )

    assert result["as_of"] == "2026-03-08T16:00:00Z"
    assert result["timezone"] == "America/New_York"
    assert result["counts"] == {
        "total": 3,
        "overdue": 1,
        "due_today": 1,
        "undated": 1,
    }
    assert [
        item["action_key"]
        for item in result["items"]
    ] == [
        followup_action_key(
            overdue.id,
            overdue.follow_up_at,
        ),
        manual_action_key(due_today.id),
        manual_action_key(undated.id),
    ]
    assert all(
        item["id"] != tomorrow.id
        for item in result["items"]
        if item["type"] == "followup"
    )
    assert all(
        item["id"] != terminal.id
        for item in result["items"]
        if item["type"] == "followup"
    )


def test_pagination_no_duplicates_for_fixed_fixture(db_session):
    user = User(
        email=f"today-page-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(user)
    db_session.flush()

    due = datetime(
        2026,
        9,
        21,
        9,
        0,
        tzinfo=timezone.utc,
    )
    for index in range(5):
        db_session.add(
            WorkItem(
                user_id=user.id,
                description=f"Task {index}",
                due_at=due + timedelta(minutes=index),
                priority=index % 3,
                state="pending",
                version=1,
            )
        )
    db_session.flush()

    reference = datetime(
        2026,
        9,
        21,
        8,
        0,
        tzinfo=timezone.utc,
    )
    seen: list[int] = []
    cursor = None
    as_of = None
    while True:
        page = build_today_queue(
            db_session,
            user_id=user.id,
            timezone_name="UTC",
            secret_key="pagination-secret",
            cursor=cursor,
            limit=2,
            now=reference,
        )
        if as_of is None:
            as_of = page["as_of"]
        assert page["as_of"] == as_of
        assert page["counts"]["total"] == 5
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_stale_version_returns409_without_write(
    auth_client,
    db_session,
):
    _reset(auth_client)
    created = auth_client.post(
        "/crm/work-items",
        json={
            "description": "First description",
            "priority": 1,
        },
    )
    assert created.status_code == 201
    item = created.json()

    updated = auth_client.patch(
        f"/crm/work-items/{item['id']}",
        json={
            "version": 1,
            "description": "Fresh description",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    stale = auth_client.patch(
        f"/crm/work-items/{item['id']}",
        json={
            "version": 1,
            "priority": 3,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"

    db_session.expire_all()
    stored = (
        db_session.query(WorkItem)
        .filter_by(id=item["id"])
        .one()
    )
    assert stored.description == "Fresh description"
    assert stored.priority == 1
    assert stored.version == 2


def test_snooze_persists_and_stale_snooze_conflicts(
    auth_client,
):
    _reset(auth_client)
    created = auth_client.post(
        "/crm/work-items",
        json={"description": "Snooze me"},
    )
    assert created.status_code == 201
    item = created.json()

    until = (
        datetime.now(timezone.utc)
        + timedelta(days=1)
    ).isoformat()
    snoozed = auth_client.post(
        "/crm/today/snooze",
        json={
            "action_key": item["action_key"],
            "until": until,
            "version": 1,
        },
    )
    assert snoozed.status_code == 200
    assert snoozed.json()["version"] == 2

    visible = auth_client.get("/crm/today")
    assert visible.status_code == 200
    assert item["action_key"] not in {
        row["action_key"]
        for row in visible.json()["items"]
    }

    with_snoozed = auth_client.get(
        "/crm/today",
        params={"include_snoozed": "true"},
    )
    assert with_snoozed.status_code == 200
    restored = next(
        row
        for row in with_snoozed.json()["items"]
        if row["action_key"] == item["action_key"]
    )
    assert restored["snooze_version"] == 2

    stale = auth_client.post(
        "/crm/today/snooze",
        json={
            "action_key": item["action_key"],
            "until": (
                datetime.now(timezone.utc)
                + timedelta(days=2)
            ).isoformat(),
            "version": 1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"


def test_followup_completion_does_not_increment_applied(
    auth_client,
    db_session,
):
    _reset(auth_client)
    user = _test_user(db_session)
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/{uuid4()}",
        company="Followup Co",
        title="Backend Engineer",
        status="follow_up",
        applied_at=None,
        follow_up_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(track)
    db_session.commit()
    action_key = followup_action_key(
        track.id,
        track.follow_up_at,
    )

    response = auth_client.post(
        "/crm/today/follow-up",
        json={
            "action_key": action_key,
            "resolution": "clear",
        },
        headers={"X-Operation-ID": str(uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["follow_up_at"] is None
    assert response.json()["status"] == "follow_up"

    db_session.expire_all()
    stored = (
        db_session.query(JobTrack)
        .filter_by(id=track.id)
        .one()
    )
    assert stored.applied_at is None
    kinds = [
        row.kind
        for row in db_session.query(JobLifecycleEvent)
        .filter_by(
            user_id=user.id,
            job_track_id=track.id,
        )
        .order_by(JobLifecycleEvent.id.asc())
        .all()
    ]
    assert "followup_changed" in kinds
    assert "first_applied" not in kinds


def test_foreign_action_returns404(
    auth_client,
    db_session,
):
    _reset(auth_client)
    foreign = User(
        email=f"foreign-today-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(foreign)
    db_session.flush()
    item = WorkItem(
        user_id=foreign.id,
        description="Foreign private task",
        state="pending",
        version=1,
    )
    db_session.add(item)
    db_session.commit()

    response = auth_client.post(
        "/crm/today/snooze",
        json={
            "action_key": manual_action_key(item.id),
            "until": (
                datetime.now(timezone.utc)
                + timedelta(days=1)
            ).isoformat(),
            "version": 1,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "action_not_found"


def test_from_view_preserves_query_sort_and_deduplicates(
    auth_client,
    db_session,
):
    _reset(auth_client)
    user = _test_user(db_session)
    batch = str(uuid4())
    rows = []
    for company, score, ats in [
        ("High", "90", "greenhouse"),
        ("Mid", "80", "greenhouse"),
        ("Low", "70", "greenhouse"),
        ("Other", "99", "lever"),
    ]:
        row = CsvRow(
            user_id=user.id,
            upload_batch_id=batch,
            url=f"https://example.test/{uuid4()}",
            company_guess=company,
            title="Engineer",
            resume_match_score=score,
            ats_group=ats,
        )
        db_session.add(row)
        rows.append(row)
    db_session.flush()
    view = SavedView(
        user_id=user.id,
        name="Greenhouse score",
        view_type="job_links",
        filters={
            "ats_group": "greenhouse",
            "sort_by": "resume_match_score",
            "sort_dir": "desc",
        },
    )
    db_session.add(view)
    db_session.commit()

    first = auth_client.post(
        "/crm/today/from-view",
        json={
            "view_id": view.id,
            "limit": 2,
            "request_id": str(uuid4()),
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["created"] == 2
    assert first_body["existing"] == 0
    assert first_body["completed"] == 0
    assert first_body["matched"] == 2
    assert [
        item["row_id"]
        for item in first_body["items"]
    ] == [rows[0].id, rows[1].id]

    second = auth_client.post(
        "/crm/today/from-view",
        json={
            "view_id": view.id,
            "limit": 2,
            "request_id": str(uuid4()),
        },
    )
    assert second.status_code == 200
    assert second.json()["created"] == 0
    assert second.json()["existing"] == 2

    first_item = first_body["items"][0]
    completed = auth_client.patch(
        f"/crm/work-items/{first_item['id']}",
        json={
            "version": first_item["version"],
            "state": "done",
        },
    )
    assert completed.status_code == 200

    third = auth_client.post(
        "/crm/today/from-view",
        json={
            "view_id": view.id,
            "limit": 2,
            "request_id": str(uuid4()),
        },
    )
    assert third.status_code == 200
    assert third.json()["created"] == 0
    assert third.json()["existing"] == 1
    assert third.json()["completed"] == 1
    assert len(third.json()["items"]) == 1


def test_today_requires_authentication(client):
    response = client.get("/crm/today")
    assert response.status_code == 401



def _sixty_action_fixture(db_session):
    reference = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    owner = User(
        email=f"jg028-owner-{uuid4()}@example.test",
        timezone="UTC",
    )
    foreign = User(
        email=f"jg028-foreign-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add_all([owner, foreign])
    db_session.flush()

    manual_overdue = [
        WorkItem(
            user_id=owner.id,
            description=f"Manual overdue {index}",
            due_at=datetime(2026, 9, 20, 8 + index, 0, tzinfo=timezone.utc),
            priority=index % 4,
            state="pending",
            version=1,
        )
        for index in range(8)
    ]
    manual_today = [
        WorkItem(
            user_id=owner.id,
            description=f"Manual today {index}",
            due_at=datetime(2026, 9, 21, 13 + index, 0, tzinfo=timezone.utc),
            priority=index % 4,
            state="pending",
            version=1,
        )
        for index in range(6)
    ]
    manual_undated = [
        WorkItem(
            user_id=owner.id,
            description=f"Manual undated {index}",
            due_at=None,
            priority=index % 4,
            state="pending",
            version=1,
        )
        for index in range(5)
    ]
    manual_tomorrow = [
        WorkItem(
            user_id=owner.id,
            description=f"Manual tomorrow {index}",
            due_at=datetime(2026, 9, 22, 12 + index, 0, tzinfo=timezone.utc),
            priority=1,
            state="pending",
            version=1,
        )
        for index in range(3)
    ]
    manual_done = [
        WorkItem(
            user_id=owner.id,
            description=f"Manual done {index}",
            due_at=datetime(2026, 9, 20, 9 + index, 0, tzinfo=timezone.utc),
            priority=1,
            state="done",
            version=1,
            completed_at=reference,
        )
        for index in range(3)
    ]
    foreign_manual = [
        WorkItem(
            user_id=foreign.id,
            description=f"Foreign manual {index}",
            due_at=datetime(2026, 9, 21, 14 + index, 0, tzinfo=timezone.utc),
            priority=1,
            state="pending",
            version=1,
        )
        for index in range(5)
    ]
    db_session.add_all(
        manual_overdue
        + manual_today
        + manual_undated
        + manual_tomorrow
        + manual_done
        + foreign_manual
    )
    db_session.flush()

    followup_overdue = [
        JobTrack(
            user_id=owner.id,
            url=f"https://jg028.example/overdue/{uuid4()}",
            company=f"Overdue {index}",
            title="Engineer",
            status="follow_up",
            follow_up_at=datetime(2026, 9, 20, 8 + index, 30),
        )
        for index in range(8)
    ]
    followup_today = [
        JobTrack(
            user_id=owner.id,
            url=f"https://jg028.example/today/{uuid4()}",
            company=f"Today {index}",
            title="Engineer",
            status="follow_up",
            follow_up_at=datetime(2026, 9, 21, 13 + index, 30),
        )
        for index in range(6)
    ]
    followup_tomorrow = [
        JobTrack(
            user_id=owner.id,
            url=f"https://jg028.example/tomorrow/{uuid4()}",
            company=f"Tomorrow {index}",
            title="Engineer",
            status="follow_up",
            follow_up_at=datetime(2026, 9, 22, 10 + index, 30),
        )
        for index in range(5)
    ]
    terminal_statuses = ["rejected", "offer", "not_applying"]
    followup_terminal = [
        JobTrack(
            user_id=owner.id,
            url=f"https://jg028.example/terminal/{uuid4()}",
            company=f"Terminal {index}",
            title="Engineer",
            status=terminal_statuses[index % len(terminal_statuses)],
            follow_up_at=datetime(2026, 9, 20, 6 + index, 0),
        )
        for index in range(6)
    ]
    foreign_followups = [
        JobTrack(
            user_id=foreign.id,
            url=f"https://jg028.example/foreign/{uuid4()}",
            company=f"Foreign {index}",
            title="Engineer",
            status="follow_up",
            follow_up_at=datetime(2026, 9, 21, 14 + index, 30),
        )
        for index in range(5)
    ]
    db_session.add_all(
        followup_overdue
        + followup_today
        + followup_tomorrow
        + followup_terminal
        + foreign_followups
    )
    db_session.flush()

    snoozed_manual = manual_overdue[:2] + manual_today[:2]
    snoozed_followups = followup_overdue[:2] + followup_today[:2]
    snoozed_until = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            WorkItemOverride(
                user_id=owner.id,
                action_key=manual_action_key(item.id),
                snoozed_until=snoozed_until,
                version=2,
            )
            for item in snoozed_manual
        ]
        + [
            WorkItemOverride(
                user_id=owner.id,
                action_key=followup_action_key(track.id, track.follow_up_at),
                snoozed_until=snoozed_until,
                version=2,
            )
            for track in snoozed_followups
        ]
    )
    db_session.commit()

    expected_all = {
        *(manual_action_key(item.id) for item in manual_overdue),
        *(manual_action_key(item.id) for item in manual_today),
        *(manual_action_key(item.id) for item in manual_undated),
        *(followup_action_key(track.id, track.follow_up_at) for track in followup_overdue),
        *(followup_action_key(track.id, track.follow_up_at) for track in followup_today),
    }
    snoozed_keys = {
        *(manual_action_key(item.id) for item in snoozed_manual),
        *(followup_action_key(track.id, track.follow_up_at) for track in snoozed_followups),
    }
    return {
        "owner": owner,
        "foreign": foreign,
        "reference": reference,
        "expected_all": expected_all,
        "expected_visible": expected_all - snoozed_keys,
        "snoozed_keys": snoozed_keys,
    }


def test_fixed_fixture_membership_and_count_parity(db_session):
    fixture = _sixty_action_fixture(db_session)
    owner = fixture["owner"]

    assert (
        db_session.query(WorkItem).filter(
            WorkItem.user_id.in_([owner.id, fixture["foreign"].id])
        ).count()
        + db_session.query(JobTrack).filter(
            JobTrack.user_id.in_([owner.id, fixture["foreign"].id])
        ).count()
    ) == 60

    visible = build_today_queue(
        db_session,
        user_id=owner.id,
        timezone_name=owner.timezone,
        secret_key="jg028-fixed-fixture",
        now=fixture["reference"],
    )
    assert visible["counts"] == {
        "total": 25,
        "overdue": 12,
        "due_today": 8,
        "undated": 5,
    }
    assert {
        item["action_key"] for item in visible["items"]
    } == fixture["expected_visible"]
    assert not fixture["snoozed_keys"].intersection(
        item["action_key"] for item in visible["items"]
    )

    including_snoozed = build_today_queue(
        db_session,
        user_id=owner.id,
        timezone_name=owner.timezone,
        secret_key="jg028-fixed-fixture",
        include_snoozed=True,
        now=fixture["reference"],
    )
    assert including_snoozed["counts"] == {
        "total": 33,
        "overdue": 16,
        "due_today": 12,
        "undated": 5,
    }
    assert {
        item["action_key"] for item in including_snoozed["items"]
    } == fixture["expected_all"]



def test_no_n_plus_one_queue_queries(db_session):
    user = User(
        email=f"jg028-query-count-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(user)
    db_session.flush()

    for index in range(12):
        row = CsvRow(
            user_id=user.id,
            upload_batch_id=f"jg028-query-{index}",
            url=f"https://jg028-query.example/row/{uuid4()}",
            title=f"Role {index}",
            company_guess=f"Company {index}",
        )
        view = SavedView(
            user_id=user.id,
            name=f"JG028 query view {index}",
            view_type="job_links",
            filters={},
        )
        track = JobTrack(
            user_id=user.id,
            url=f"https://jg028-query.example/track/{uuid4()}",
            company=f"Company {index}",
            title=f"Role {index}",
            status="saved",
            follow_up_at=None,
        )
        db_session.add_all([row, view, track])
        db_session.flush()
        db_session.add(
            WorkItem(
                user_id=user.id,
                track_id=track.id,
                row_id=row.id,
                source_view_id=view.id,
                description=f"Sourced action {index}",
                priority=1,
                state="pending",
                version=1,
            )
        )
    db_session.commit()
    user_id = user.id
    db_session.expunge_all()

    statements = []

    def capture_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_statement)
    try:
        result = build_today_queue(
            db_session,
            user_id=user_id,
            timezone_name="UTC",
            secret_key="jg028-query-count",
            now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert len(result["items"]) == 12
    assert len(statements) == 3
    source_query = statements[0].lower()
    assert "join job_tracks" in source_query
    assert "join csv_rows" in source_query
    assert "join saved_views" in source_query


def test_today_postgres_query_plans_use_owner_due_indexes(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL query-plan acceptance runs in repository CI.")

    fixture = _sixty_action_fixture(db_session)
    owner = fixture["owner"]
    db_session.execute(text("SET LOCAL enable_seqscan = off"))

    manual_plan = "\n".join(
        row[0]
        for row in db_session.execute(
            text(
                """
                EXPLAIN (COSTS OFF)
                SELECT id
                FROM work_items
                WHERE user_id = :user_id
                  AND state = 'pending'
                  AND (due_at IS NULL OR due_at < :day_end)
                """
            ),
            {
                "user_id": owner.id,
                "day_end": datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc),
            },
        )
    )
    assert "ix_work_items_user_due" in manual_plan

    followup_plan = "\n".join(
        row[0]
        for row in db_session.execute(
            text(
                """
                EXPLAIN (COSTS OFF)
                SELECT id
                FROM job_tracks
                WHERE user_id = :user_id
                  AND follow_up_at IS NOT NULL
                  AND follow_up_at < :day_end
                  AND status NOT IN ('rejected', 'offer', 'not_applying')
                """
            ),
            {
                "user_id": owner.id,
                "day_end": datetime(2026, 9, 22, 0, 0),
            },
        )
    )
    assert (
        "ix_job_tracks_user_id" in followup_plan
        or "ix_job_tracks_follow_up_at" in followup_plan
    )


def test_today_source_detachment_preserves_manual_action(db_session):
    user = User(
        email=f"jg028-detach-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(user)
    db_session.flush()
    view = SavedView(
        user_id=user.id,
        name=f"Detach source {uuid4()}",
        view_type="job_links",
        filters={},
    )
    db_session.add(view)
    db_session.flush()
    item = WorkItem(
        user_id=user.id,
        source_view_id=view.id,
        description="Keep this action after source deletion",
        due_at=None,
        priority=1,
        state="pending",
        version=1,
    )
    db_session.add(item)
    db_session.commit()
    user_id = user.id
    item_id = item.id

    db_session.delete(view)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.query(WorkItem).filter_by(id=item_id).one()
    assert stored.source_view_id is None
    assert stored.description == "Keep this action after source deletion"

    queue_result = build_today_queue(
        db_session,
        user_id=user_id,
        timezone_name="UTC",
        secret_key="jg028-detach",
        now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    )
    assert [row["description"] for row in queue_result["items"]] == [
        "Keep this action after source deletion"
    ]
    assert queue_result["items"][0]["origin_label"] == "Manual"


def test_today_timezone_change_recomputes_membership(db_session):
    user = User(
        email=f"jg028-timezone-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(user)
    db_session.flush()
    item = WorkItem(
        user_id=user.id,
        description="Cross-midnight action",
        due_at=datetime(2026, 9, 22, 0, 30, tzinfo=timezone.utc),
        priority=1,
        state="pending",
        version=1,
    )
    db_session.add(item)
    db_session.commit()

    reference = datetime(2026, 9, 21, 23, 30, tzinfo=timezone.utc)
    utc_queue = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="jg028-timezone",
        now=reference,
    )
    assert utc_queue["items"] == []

    user.timezone = "Asia/Kolkata"
    db_session.commit()
    india_queue = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key="jg028-timezone",
        now=reference,
    )
    assert [row["action_key"] for row in india_queue["items"]] == [
        manual_action_key(item.id)
    ]
    assert india_queue["counts"] == {
        "total": 1,
        "overdue": 0,
        "due_today": 1,
        "undated": 0,
    }



def test_restore_reconstructs_today_items(db_session):
    fixture = _sixty_action_fixture(db_session)
    source = fixture["owner"]

    payload = export_backup_v2(db_session, source.id)
    assert payload["counts"]["work_items"] == 25
    assert payload["counts"]["job_tracks"] == 25
    assert payload["counts"]["work_item_overrides"] == 8

    destination = User(
        email=f"jg028-restore-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(destination)
    db_session.commit()
    destination_id = destination.id

    restored = restore_backup_v2(
        db_session,
        destination_id,
        validate_backup_v2(payload),
        "merge_missing",
    )
    assert restored["counts"]["work_items"] == {
        "created": 25,
        "skipped": 0,
        "conflicts": 0,
    }
    assert restored["counts"]["job_tracks"] == {
        "created": 25,
        "skipped": 0,
        "conflicts": 0,
    }
    assert restored["counts"]["work_item_overrides"] == {
        "created": 8,
        "skipped": 0,
        "conflicts": 0,
    }

    db_session.expire_all()
    queue_result = build_today_queue(
        db_session,
        user_id=destination_id,
        timezone_name="UTC",
        secret_key="jg028-restored-queue",
        now=fixture["reference"],
    )
    assert queue_result["counts"] == {
        "total": 25,
        "overdue": 12,
        "due_today": 8,
        "undated": 5,
    }
    assert sum(item["type"] == "manual" for item in queue_result["items"]) == 15
    assert sum(item["type"] == "followup" for item in queue_result["items"]) == 10

    restored_overrides = (
        db_session.query(WorkItemOverride)
        .filter_by(user_id=destination_id)
        .all()
    )
    assert len(restored_overrides) == 8
    assert all(
        row.user_id == destination_id
        for row in restored_overrides
    )

    including_snoozed = build_today_queue(
        db_session,
        user_id=destination_id,
        timezone_name="UTC",
        secret_key="jg028-restored-queue",
        include_snoozed=True,
        now=fixture["reference"],
    )
    assert including_snoozed["counts"] == {
        "total": 33,
        "overdue": 16,
        "due_today": 12,
        "undated": 5,
    }


def test_saved_view_page_two_uses_full_filtered_order_and_no_duplicate_actions(
    auth_client,
    db_session,
):
    _reset(auth_client)
    user = _test_user(db_session)
    batch = str(uuid4())
    matching_rows = []
    for index in range(25):
        row = CsvRow(
            user_id=user.id,
            upload_batch_id=batch,
            url=f"https://jg028-view.example/greenhouse/{uuid4()}",
            company_guess=f"Target {index:02}",
            title="Platform Engineer",
            resume_match_score=str(100 - index),
            ats_group="greenhouse",
        )
        db_session.add(row)
        matching_rows.append(row)
    for index in range(5):
        db_session.add(
            CsvRow(
                user_id=user.id,
                upload_batch_id=batch,
                url=f"https://jg028-view.example/lever/{uuid4()}",
                company_guess=f"Other {index:02}",
                title="Platform Engineer",
                resume_match_score=str(120 - index),
                ats_group="lever",
            )
        )
    db_session.flush()
    view = SavedView(
        user_id=user.id,
        name=f"JG028 full order {uuid4()}",
        view_type="job_links",
        filters={
            "ats_group": "greenhouse",
            "sort_by": "resume_match_score",
            "sort_dir": "desc",
        },
    )
    db_session.add(view)
    db_session.commit()

    page_one = auth_client.get(
        "/rows",
        params={
            "page": 1,
            "page_size": 10,
            "ats_group": "greenhouse",
            "sort_by": "resume_match_score",
            "sort_dir": "desc",
        },
    )
    page_two = auth_client.get(
        "/rows",
        params={
            "page": 2,
            "page_size": 10,
            "ats_group": "greenhouse",
            "sort_by": "resume_match_score",
            "sort_dir": "desc",
        },
    )
    assert page_one.status_code == 200
    assert page_two.status_code == 200
    expected_first_twenty = [
        row["id"]
        for row in page_one.json()["rows"] + page_two.json()["rows"]
    ]
    assert len(expected_first_twenty) == 20

    first = auth_client.post(
        "/crm/today/from-view",
        json={
            "view_id": view.id,
            "limit": 20,
            "request_id": str(uuid4()),
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["created"] == 20
    assert first_body["existing"] == 0
    assert first_body["matched"] == 20
    assert [
        item["row_id"] for item in first_body["items"]
    ] == expected_first_twenty

    repeated = auth_client.post(
        "/crm/today/from-view",
        json={
            "view_id": view.id,
            "limit": 20,
            "request_id": str(uuid4()),
        },
    )
    assert repeated.status_code == 200
    repeated_body = repeated.json()
    assert repeated_body["created"] == 0
    assert repeated_body["existing"] == 20
    assert repeated_body["completed"] == 0
    assert [
        item["row_id"] for item in repeated_body["items"]
    ] == expected_first_twenty
    assert (
        db_session.query(WorkItem)
        .filter(
            WorkItem.user_id == user.id,
            WorkItem.source_view_id == view.id,
        )
        .count()
    ) == 20
