from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import event

from app.models import CompanyAlias, CsvRow, JobTrack, User
from app.routers.crm import APPLICATION_MATCH_LIMIT, APPLICATION_MATCH_SCAN_LIMIT
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
        upload_batch_id=str(uuid4()),
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

def test_jg032_labeled_false_positive_matrix(client, db_session):
    user = _login(client, db_session, "jg032-matrix")
    exact = _track(
        db_session,
        user,
        url="https://jobs.example.test/matrix/exact?req=100",
        company="Exact Systems",
        title="Backend Engineer",
    )
    canonical = _track(
        db_session,
        user,
        url="https://jobs.example.test/matrix/canonical?req=200&utm_source=first",
        company="Canonical Systems",
        title="Site Reliability Engineer",
    )
    same_company = _track(
        db_session,
        user,
        url="https://jobs.example.test/matrix/company/REQ-300",
        company="Gamma Labs",
        title="Platform Engineer",
    )
    unrelated = _track(
        db_session,
        user,
        url="https://jobs.example.test/matrix/unrelated/REQ-400",
        company="Other Labs",
        title="Data Engineer",
    )
    before_ids = {
        item.id
        for item in db_session.query(JobTrack).filter(JobTrack.user_id == user.id).all()
    }

    matrix = [
        (
            "exact",
            {
                "url": exact.url,
                "company": "Exact Systems",
                "title": "Backend Engineer",
            },
            [("exact", "same_original_url", exact.id)],
        ),
        (
            "tracking_variant",
            {
                "url": "https://jobs.example.test/matrix/canonical?req=200&utm_source=second&utm_campaign=jg032",
                "company": "Canonical Systems",
                "title": "Site Reliability Engineer",
            },
            [("canonical", "same_canonical_url", canonical.id)],
        ),
        (
            "same_company_new_role",
            {
                "url": "https://jobs.example.test/matrix/company/REQ-301",
                "company": "Gamma Labs",
                "title": "Machine Learning Engineer",
            },
            [],
        ),
        (
            "unrelated_similar_title",
            {
                "url": "https://jobs.example.test/matrix/other/REQ-401",
                "company": "Unrelated Systems",
                "title": unrelated.title,
            },
            [],
        ),
    ]

    for label, payload, expected in matrix:
        response = client.post("/crm/application-matches", json=payload)
        assert response.status_code == 200, label
        observed = [
            (item["confidence"], item["reason"], item["track_id"])
            for item in response.json()["matches"]
        ]
        assert observed == expected, label

    db_session.expire_all()
    after = (
        db_session.query(JobTrack)
        .filter(JobTrack.user_id == user.id)
        .order_by(JobTrack.id.asc())
        .all()
    )
    assert {item.id for item in after} == before_ids
    assert len(after) == 4
    assert all(item.duplicate_of_id is None for item in after)
    assert same_company.id in before_ids


def test_new_requisition_not_exact_duplicate(client, db_session):
    user = _login(client, db_session, "jg032-requisition")
    prior = _track(
        db_session,
        user,
        url="https://jobs.example.test/acme/jobs/REQ-100?source=careers",
        company="Acme Corp",
        title="Backend Engineer",
    )

    response = client.post(
        "/crm/application-matches",
        json={
            "url": "https://jobs.example.test/acme/jobs/REQ-101?source=careers",
            "company": "Acme Corp",
            "title": "Backend Engineer",
        },
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["track_id"] == prior.id
    assert matches[0]["confidence"] == "possible"
    assert matches[0]["reason"] == "company_title_only"
    assert all(item["confidence"] not in {"exact", "canonical"} for item in matches)


def test_source_delete_retains_warning(client, db_session):
    user = _login(client, db_session, "jg032-source-delete")
    row = _row(
        db_session,
        user,
        url="https://jobs.example.test/source-delete/REQ-500?req=500",
        company="Durable History Co",
        title="Backend Engineer",
    )

    created = client.post(f"/crm/from-row/{row.id}")
    assert created.status_code == 200
    track_id = created.json()["id"]

    applied = client.patch(
        f"/crm/applications/{track_id}",
        json={"mark_applied": True},
    )
    assert applied.status_code == 200
    assert applied.json()["applied_at"] is not None

    deleted = client.request(
        "DELETE",
        "/rows",
        json={"row_ids": [row.id], "mode": "delete"},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"archived": 0, "deleted": 1}

    db_session.expire_all()
    retained = (
        db_session.query(JobTrack)
        .filter(JobTrack.id == track_id, JobTrack.user_id == user.id)
        .one()
    )
    assert retained.csv_row_id is None
    assert retained.applied_at is not None

    warning = client.post(
        "/crm/application-matches",
        json={
            "url": row.url,
            "company": row.company_guess,
            "title": row.title,
        },
    )
    assert warning.status_code == 200
    assert [
        (item["track_id"], item["confidence"], item["reason"])
        for item in warning.json()["matches"]
    ] == [(track_id, "exact", "same_original_url")]


def test_alias_remove_changes_grouping_only(client, db_session):
    user = _login(client, db_session, "jg032-alias-remove")
    first = _track(
        db_session,
        user,
        url="https://jobs.example.test/alias-group/acme/REQ-1",
        company="Acme Corp",
        title="Backend Engineer",
        applied_at=datetime(2026, 9, 18, 10, 0, 0),
    )
    second = _track(
        db_session,
        user,
        url="https://jobs.example.test/alias-group/acme-inc/REQ-2",
        company="Acme Incorporated",
        title="Backend Engineer",
        applied_at=datetime(2026, 9, 19, 10, 0, 0),
    )
    before = {
        item.id: (item.url, item.status, item.applied_at)
        for item in (first, second)
    }

    created = client.post(
        "/crm/company-aliases",
        json={"company": "Acme Corp", "alias": "Acme Incorporated"},
    )
    assert created.status_code == 200
    alias_row = next(
        item
        for item in created.json()["aliases"]
        if item["display_name"] == "Acme Incorporated"
    )

    grouped = client.post(
        "/crm/application-matches",
        json={
            "url": "https://jobs.example.test/alias-group/candidate/REQ-3",
            "company": "Acme Incorporated",
            "title": "Backend Engineer",
        },
    )
    assert grouped.status_code == 200
    assert {
        (item["track_id"], item["confidence"], item["reason"])
        for item in grouped.json()["matches"]
    } == {
        (first.id, "possible", "company_alias_title"),
        (second.id, "possible", "company_title_only"),
    }

    removed = client.delete(f"/crm/company-aliases/{alias_row['id']}")
    assert removed.status_code == 200

    after_remove = client.post(
        "/crm/application-matches",
        json={
            "url": "https://jobs.example.test/alias-group/candidate/REQ-3",
            "company": "Acme Incorporated",
            "title": "Backend Engineer",
        },
    )
    assert after_remove.status_code == 200
    assert [
        (item["track_id"], item["confidence"], item["reason"])
        for item in after_remove.json()["matches"]
    ] == [(second.id, "possible", "company_title_only")]

    db_session.expire_all()
    persisted = (
        db_session.query(JobTrack)
        .filter(JobTrack.user_id == user.id)
        .order_by(JobTrack.id.asc())
        .all()
    )
    assert len(persisted) == 2
    assert {
        item.id: (item.url, item.status, item.applied_at)
        for item in persisted
    } == before


def test_matching_query_bounded_for_large_fixture(client, db_session):
    user = _login(client, db_session, "jg032-bounded")
    tracks = []
    for index in range(APPLICATION_MATCH_SCAN_LIMIT + 40):
        track = JobTrack(
            user_id=user.id,
            url=f"https://jobs.example.test/bounded/REQ-{index}",
            company="Bounded Query Co",
            title="Backend Engineer",
            status="applied",
            opened_at=datetime(2026, 9, 18, 8, 0, 0),
            applied_at=datetime(2026, 9, 18, 9, 0, 0),
            last_opened_at=datetime(2026, 9, 18, 8, 0, 0),
        )
        apply_persisted_job_identity(track)
        tracks.append(track)
    db_session.add_all(tracks)
    db_session.commit()

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
        response = client.post(
            "/crm/application-matches",
            json={
                "url": "https://jobs.example.test/bounded/CANDIDATE",
                "company": "Bounded Query Co",
                "title": "Backend Engineer",
            },
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    payload = response.json()
    assert APPLICATION_MATCH_SCAN_LIMIT == 100
    assert APPLICATION_MATCH_LIMIT == 20
    assert len(payload["matches"]) == APPLICATION_MATCH_LIMIT
    assert payload["company_history_count"] == APPLICATION_MATCH_SCAN_LIMIT + 40
    assert all(item["confidence"] == "possible" for item in payload["matches"])
    assert all(item["reason"] == "company_title_only" for item in payload["matches"])

    job_track_selects = [
        statement.lower()
        for statement in statements
        if "from job_tracks" in statement.lower()
    ]
    candidate_selects = [
        statement
        for statement in job_track_selects
        if "order by job_tracks.applied_at" in statement
    ]
    assert len(candidate_selects) == 1
    assert "limit" in candidate_selects[0]
    assert len(job_track_selects) == 2
    assert len(statements) <= 5

    db_session.expire_all()
    assert (
        db_session.query(JobTrack)
        .filter(JobTrack.user_id == user.id)
        .count()
        == APPLICATION_MATCH_SCAN_LIMIT + 40
    )

