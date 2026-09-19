from datetime import datetime
from uuid import uuid4

from app.models import CsvRow, JobTrack, User
from app.routers import crm as crm_router
from app.routers import email as email_router
from app.services.lifecycle import metric_counts, write_event


class FrozenDateTime(datetime):
    @classmethod
    def utcnow(cls):
        return cls(2026, 9, 20, 1, 0, 0)


def _user(db_session, *, timezone="UTC"):
    user = User(
        email=f"jg011-{uuid4().hex}@jobgrid.dev",
        timezone=timezone,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_shared_metrics_agree_across_analytics_goals_and_weekly(db_session, monkeypatch):
    monkeypatch.setattr(crm_router, "datetime", FrozenDateTime)
    user = _user(db_session, timezone="Asia/Kolkata")

    saved = JobTrack(
        user_id=user.id,
        url=f"https://example.com/{uuid4().hex}/saved",
        status="opened",
        created_at=datetime(2026, 9, 19, 22, 0, 0),
    )
    db_session.add(saved)
    db_session.flush()

    visit_url = f"https://example.com/{uuid4().hex}/visited"
    apply_url = f"https://example.com/{uuid4().hex}/applied"
    visit = write_event(
        db_session,
        user_id=user.id,
        job_url=visit_url,
        kind="first_visited",
        occurred_at=datetime(2026, 9, 19, 23, 0, 0),
        source="test",
    )
    applied = write_event(
        db_session,
        user_id=user.id,
        job_url=apply_url,
        kind="first_applied",
        occurred_at=datetime(2026, 9, 20, 0, 15, 0),
        source="test",
    )
    # Replay the same first facts to prove retries do not inflate totals.
    write_event(
        db_session,
        user_id=user.id,
        job_url=visit_url,
        kind="first_visited",
        occurred_at=visit.occurred_at,
        source="test",
    )
    write_event(
        db_session,
        user_id=user.id,
        job_url=apply_url,
        kind="first_applied",
        occurred_at=applied.occurred_at,
        source="test",
    )
    db_session.commit()

    analytics = crm_router.analytics(db=db_session, user=user)
    goals = crm_router.goal_progress(db=db_session, user=user)
    weekly = crm_router.weekly_report(db=db_session, user=user)

    assert analytics["total_opened"] == 1
    assert analytics["total_saved"] == 1
    assert analytics["total_applied"] == 1
    assert analytics["applied_today"] == 1
    assert analytics["applied_7d"] == 1
    assert analytics["opened_not_applied"] == 1

    assert goals["today"]["opened"] == 1
    assert goals["today"]["applied"] == 1

    assert weekly["opened"] == 1
    assert weekly["saved"] == 1
    assert weekly["applied"] == 1


def test_daily_boundary_api_uses_same_account_local_interval(db_session, monkeypatch):
    monkeypatch.setattr(crm_router, "datetime", FrozenDateTime)
    user = _user(db_session, timezone="Asia/Kolkata")

    # At 2026-09-20 01:00 UTC, the Kolkata local day starts at 18:30 UTC
    # on September 19. Only the second fact belongs to today's local day.
    write_event(
        db_session,
        user_id=user.id,
        job_url=f"https://example.com/{uuid4().hex}/before",
        kind="first_applied",
        occurred_at=datetime(2026, 9, 19, 18, 29, 59),
        source="test",
    )
    write_event(
        db_session,
        user_id=user.id,
        job_url=f"https://example.com/{uuid4().hex}/inside",
        kind="first_applied",
        occurred_at=datetime(2026, 9, 19, 18, 30, 1),
        source="test",
    )
    db_session.commit()

    analytics = crm_router.analytics(db=db_session, user=user)
    goals = crm_router.goal_progress(db=db_session, user=user)

    assert analytics["total_applied"] == 2
    assert analytics["applied_today"] == 1
    assert goals["today"]["applied"] == 1


def test_historical_visit_survives_source_row_delete(db_session, monkeypatch):
    monkeypatch.setattr(crm_router, "datetime", FrozenDateTime)
    user = _user(db_session)
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg011-{uuid4().hex[:24]}",
        url=f"https://example.com/{uuid4().hex}/source",
        clicked=True,
        clicked_at=datetime(2026, 9, 19, 20, 0, 0),
    )
    db_session.add(row)
    db_session.flush()
    write_event(
        db_session,
        user_id=user.id,
        job_url=row.url,
        kind="first_visited",
        occurred_at=row.clicked_at,
        source="test",
        csv_row_id=row.id,
    )
    db_session.commit()

    db_session.delete(row)
    db_session.commit()

    assert metric_counts(db_session, user_id=user.id)["visited"] == 1
    assert crm_router.analytics(db=db_session, user=user)["total_opened"] == 1


def test_metric_reads_are_account_scoped(db_session, monkeypatch):
    monkeypatch.setattr(crm_router, "datetime", FrozenDateTime)
    owner = _user(db_session)
    other = _user(db_session)
    for user in (owner, other):
        write_event(
            db_session,
            user_id=user.id,
            job_url=f"https://example.com/{user.id}/visited",
            kind="first_visited",
            occurred_at=datetime(2026, 9, 19, 20, 0, 0),
            source="test",
        )
    db_session.commit()

    assert crm_router.analytics(db=db_session, user=owner)["total_opened"] == 1
    assert crm_router.analytics(db=db_session, user=other)["total_opened"] == 1


def test_digest_source_matches_weekly_and_goals_without_real_smtp(db_session, monkeypatch):
    monkeypatch.setattr(crm_router, "datetime", FrozenDateTime)
    user = _user(db_session)
    saved = JobTrack(
        user_id=user.id,
        url=f"https://example.com/{uuid4().hex}/saved",
        status="opened",
        created_at=datetime(2026, 9, 19, 20, 0, 0),
    )
    db_session.add(saved)
    write_event(
        db_session,
        user_id=user.id,
        job_url=f"https://example.com/{uuid4().hex}/visited",
        kind="first_visited",
        occurred_at=datetime(2026, 9, 19, 21, 0, 0),
        source="test",
    )
    write_event(
        db_session,
        user_id=user.id,
        job_url=f"https://example.com/{uuid4().hex}/applied",
        kind="first_applied",
        occurred_at=datetime(2026, 9, 19, 22, 0, 0),
        source="test",
    )
    db_session.commit()

    expected_weekly = crm_router.weekly_report(db=db_session, user=user)
    expected_goals = crm_router.goal_progress(db=db_session, user=user)
    captured = {}

    def capture_digest(subject, data):
        captured["subject"] = subject
        captured["data"] = data
        return "<html><body>digest</body></html>"

    monkeypatch.setattr(email_router, "weekly_digest", capture_digest)
    monkeypatch.setattr(email_router, "_send_via_smtp", lambda message: captured.setdefault("sent", True))
    monkeypatch.setattr(email_router.settings, "EMAIL_FROM", "noreply@jobgrid.dev")

    result = email_router.send_weekly_digest(db=db_session, user=user)

    assert result["status"] == "sent"
    assert captured["sent"] is True
    assert captured["data"]["opened"] == expected_weekly["opened"] == 1
    assert captured["data"]["saved"] == expected_weekly["saved"] == 1
    assert captured["data"]["applied"] == expected_weekly["applied"] == 1
    assert captured["data"]["goal_progress"] == expected_goals
