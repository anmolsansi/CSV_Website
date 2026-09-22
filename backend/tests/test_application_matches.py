from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

from app.models import CompanyAlias, CsvRow, JobTrack, User
from app.services.job_identity import (
    apply_persisted_job_identity,
    normalize_company_alias_key,
)


def _login(client, db_session, prefix: str) -> User:
    email = f"{prefix}-{uuid4().hex[:10]}@test.dev"
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200
    db_session.expire_all()
    return db_session.query(User).filter_by(email=email).one()


def _row(
    db_session,
    user: User,
    *,
    url: str,
    company: str = "Acme Corp",
    title: str = "Backend Engineer",
    clicked: bool = False,
) -> CsvRow:
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg031-{uuid4()}",
        url=url,
        company_guess=company,
        title=title,
        clicked=clicked,
        clicked_at=datetime(2026, 9, 20, 12, 0, 0) if clicked else None,
    )
    apply_persisted_job_identity(row)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _track(
    db_session,
    user: User,
    *,
    url: str,
    company: str = "Acme Corp",
    title: str = "Backend Engineer",
    status: str = "applied",
    applied_at: datetime | None = datetime(2026, 9, 20, 15, 30, 0),
) -> JobTrack:
    track = JobTrack(
        user_id=user.id,
        url=url,
        company=company,
        title=title,
        status=status,
        opened_at=datetime(2026, 9, 20, 14, 0, 0),
        applied_at=applied_at,
        last_opened_at=datetime(2026, 9, 20, 14, 0, 0),
    )
    apply_persisted_job_identity(track)
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)
    return track


def test_visited_only_has_no_applied_warning(client, db_session):
    user = _login(client, db_session, "jg031-visited")
    row = _row(
        db_session,
        user,
        url="https://jobs.example.test/role/visited",
        clicked=True,
    )
    _track(
        db_session,
        user,
        url=row.url,
        status="opened",
        applied_at=None,
    )

    response = client.get("/crm/application-matches", params={"row_id": row.id})

    assert response.status_code == 200
    assert response.json() == {"matches": [], "company_history_count": 0}


def test_exact_match_returns_prior_application_date(client, db_session):
    user = _login(client, db_session, "jg031-exact")
    row = _row(db_session, user, url="https://jobs.example.test/role/exact")
    prior = _track(
        db_session,
        user,
        url=row.url,
        applied_at=datetime(2026, 9, 18, 9, 45, 0),
    )

    response = client.get("/crm/application-matches", params={"row_id": row.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_history_count"] == 1
    assert len(payload["matches"]) == 1
    match = payload["matches"][0]
    assert match["track_id"] == prior.id
    assert match["confidence"] == "exact"
    assert match["reason"] == "same_original_url"
    assert match["status"] == "applied"
    assert match["applied_at"].startswith("2026-09-18T09:45:00")


def test_canonical_warning_does_not_block_reapply(client, db_session):
    user = _login(client, db_session, "jg031-canonical")
    prior = _track(
        db_session,
        user,
        url="https://jobs.example.test/role/42?req=abc&utm_source=first",
    )
    row = _row(
        db_session,
        user,
        url="https://jobs.example.test/role/42?req=abc&utm_source=second",
    )

    warning = client.get("/crm/application-matches", params={"row_id": row.id})
    assert warning.status_code == 200
    assert warning.json()["matches"][0]["track_id"] == prior.id
    assert warning.json()["matches"][0]["confidence"] == "canonical"

    created = client.post(f"/crm/from-row/{row.id}")
    assert created.status_code == 200
    assert created.json()["warning_candidates"][0]["confidence"] == "canonical"

    reapplied = client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [row.id], "status": "applied"},
    )
    assert reapplied.status_code == 200
    assert reapplied.json()["created"] + reapplied.json()["updated"] == 1

    db_session.expire_all()
    current = (
        db_session.query(JobTrack)
        .filter(JobTrack.user_id == user.id, JobTrack.url == row.url)
        .one()
    )
    assert current.id != prior.id
    assert current.applied_at is not None
    assert current.status == "applied"


def test_slash_company_navigation_works(client, db_session):
    user = _login(client, db_session, "jg031-slash")
    track = _track(
        db_session,
        user,
        url="https://jobs.example.test/role/slash",
        company="Research/AI Labs",
    )

    encoded = quote("Research/AI Labs", safe="")
    response = client.get(f"/crm/companies/{encoded}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Research/AI Labs"
    assert payload["total"] == 1
    assert payload["roles"][0]["track_id"] == track.id


def test_foreign_alias_cannot_be_deleted(client, db_session):
    owner = _login(client, db_session, "jg031-alias-owner")
    alias = CompanyAlias(
        user_id=owner.id,
        alias_key=normalize_company_alias_key("Acme Incorporated"),
        display_name="Acme Incorporated",
        company_key=str(uuid4()),
    )
    db_session.add(alias)
    db_session.commit()
    db_session.refresh(alias)

    other = _login(client, db_session, "jg031-alias-other")
    assert other.id != owner.id

    response = client.delete(f"/crm/company-aliases/{alias.id}")

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.query(CompanyAlias).filter_by(id=alias.id).one().user_id == owner.id


def test_alias_conflict_returns_409_and_preserves_proposed_label(client, db_session):
    user = _login(client, db_session, "jg031-alias-conflict")

    first = client.post(
        "/crm/company-aliases",
        json={"company": "Acme Corp", "alias": "Acme Incorporated"},
    )
    assert first.status_code == 200
    assert first.json()["created"] is True

    conflict = client.post(
        "/crm/company-aliases",
        json={"company": "Different Holdings", "alias": "Acme Incorporated"},
    )

    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["code"] == "alias_conflict"
    assert detail["proposed_label"] == "Acme Incorporated"


def test_alias_grouping_changes_history_only(client, db_session):
    user = _login(client, db_session, "jg031-alias-history")
    first = _track(
        db_session,
        user,
        url="https://jobs.example.test/acme/1",
        company="Acme Corp",
    )
    second = _track(
        db_session,
        user,
        url="https://jobs.example.test/acme-inc/2",
        company="Acme Incorporated",
        title="Platform Engineer",
    )

    created = client.post(
        "/crm/company-aliases",
        json={"company": "Acme Corp", "alias": "Acme Incorporated"},
    )
    assert created.status_code == 200
    assert created.json()["group_history_count"] == 2

    grouped = client.get("/crm/companies/Acme%20Corp")
    assert grouped.status_code == 200
    assert grouped.json()["total"] == 2
    assert {role["track_id"] for role in grouped.json()["roles"]} == {first.id, second.id}

    alias_row = next(
        item
        for item in created.json()["aliases"]
        if item["display_name"] == "Acme Incorporated"
    )
    removed = client.delete(f"/crm/company-aliases/{alias_row['id']}")
    assert removed.status_code == 200

    db_session.expire_all()
    assert db_session.query(JobTrack).filter_by(user_id=user.id).count() == 2
