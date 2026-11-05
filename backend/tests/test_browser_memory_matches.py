"""EXT-12: read-only browser match correctness under a bounded company scan."""
from datetime import datetime
from uuid import uuid4

from app.models import CompanyAlias, JobTrack, User
from app.services.job_identity import (
    apply_persisted_job_identity,
    find_browser_applied_matches,
    normalize_company_alias_key,
)


def _owner(db_session):
    owner = User(email=f"ext12-{uuid4().hex}@example.test")
    db_session.add(owner)
    db_session.flush()
    return owner


def _applied(db_session, owner, url, *, company="Acme Corp", title="Backend Engineer",
             when=datetime(2026, 10, 1, 12, 0, 0), status="applied"):
    track = JobTrack(
        user_id=owner.id, url=url, company=company, title=title,
        status=status, applied_at=when,
    )
    assert apply_persisted_job_identity(track)
    db_session.add(track)
    return track


def test_ext_12_old_exact_and_canonical_survive_500_newer_possible_roles(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    original = "https://jobs.example.test/openings/Role-007?req=old&utm_source=first"
    old = _applied(
        db_session, owner, original,
        when=datetime(2024, 1, 2, 9, 0, 0), status="withdrawn",
    )
    for number in range(520):
        _applied(
            db_session, owner,
            f"https://jobs.example.test/openings/new-{number}?req=new-{number}",
        )
    _applied(db_session, foreign, original)
    db_session.commit()

    exact = find_browser_applied_matches(
        db_session, user_id=owner.id, url=original,
        company="Acme Corp", title="Backend Engineer",
    )
    assert exact["matches"][0]["track_id"] == old.id
    assert exact["matches"][0]["confidence"] == "exact"
    assert exact["matches"][0]["status"] == "withdrawn"
    assert len(exact["matches"]) == 20
    assert exact["company_history_count"] == 521
    assert exact["lookup_complete"] is False
    assert len({match["track_id"] for match in exact["matches"]}) == 20

    canonical = find_browser_applied_matches(
        db_session, user_id=owner.id,
        url="https://jobs.example.test/openings/Role-007?req=old&utm_source=second",
        company="Acme Corp", title="Backend Engineer",
    )
    assert canonical["matches"][0]["track_id"] == old.id
    assert canonical["matches"][0]["confidence"] == "canonical"
    assert canonical["matches"][0]["reason"] == "same_canonical_url"
    assert canonical["company_history_count"] == 521
    assert canonical["lookup_complete"] is False

    # A different requisition query is not canonical identity, even with an
    # otherwise identical path. With no title there are no possible guesses.
    different = find_browser_applied_matches(
        db_session, user_id=owner.id,
        url="https://jobs.example.test/openings/Role-007?req=other",
        company="Acme Corp", title=None,
    )
    assert different["matches"] == []
    assert different["lookup_complete"] is True


def test_ext_12_alias_aggregate_counts_all_applied_not_only_scanned(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    group = str(uuid4())
    db_session.add_all([
        CompanyAlias(
            user_id=owner.id, alias_key=normalize_company_alias_key(name),
            display_name=name, company_key=group,
        )
        for name in ("Acme Corp", "Acme Incorporated")
    ])
    old = _applied(
        db_session, owner, "https://jobs.example.test/acme/alias-old",
        company="Acme Incorporated", status="rejected",
        when=datetime(2025, 6, 1, 12, 0, 0),
    )
    recent = _applied(
        db_session, owner, "https://jobs.example.test/acme/new",
    )
    _applied(db_session, owner, "https://jobs.example.test/acme/saved",
             when=None, status="opened")
    _applied(db_session, foreign, "https://jobs.example.test/acme/foreign")
    db_session.commit()

    matches = find_browser_applied_matches(
        db_session, user_id=owner.id,
        url="https://jobs.example.test/acme/candidate",
        company="Acme Corp", title="Backend Engineer",
    )
    assert matches["lookup_complete"] is True
    assert matches["company_history_count"] == 2
    assert [(match["track_id"], match["reason"]) for match in matches["matches"]] == [
        (recent.id, "company_title_only"),
        (old.id, "company_alias_title"),
    ]
    assert all(match["applied_at"] is not None for match in matches["matches"])


def test_ext_12_owner_isolation_and_no_company_guess(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    url = "https://jobs.example.test/role/one"
    _applied(db_session, foreign, url)
    db_session.commit()

    result = find_browser_applied_matches(
        db_session, user_id=owner.id, url=url, company=None, title=None,
    )
    assert result == {
        "matches": [], "company_history_count": 0, "lookup_complete": True,
    }


# EXT-13: independent external/legacy visit facts versus applied evidence.
from app.models import CsvRow, JobVisit, UrlHistory
from app.services.browser_memory import read_browser_memory_facts
from app.services.job_identity import canonicalize_job_url


def test_ext_13_imported_and_saved_are_not_visits_or_applications(db_session):
    owner = _owner(db_session)
    url = "https://boards.example.test/role/13-imported"
    row = CsvRow(user_id=owner.id, upload_batch_id=str(uuid4()), url=url,
                 company_guess="Acme Corp", title="Backend Engineer", clicked=False)
    apply_persisted_job_identity(row)
    saved = JobTrack(user_id=owner.id, url=url, company="Acme Corp",
                     title="Backend Engineer", status="opened", opened_at=None,
                     applied_at=None)
    apply_persisted_job_identity(saved)
    db_session.add_all([row, saved, UrlHistory(user_id=owner.id, url=url)])
    db_session.commit()

    facts = read_browser_memory_facts(
        db_session, user_id=owner.id, url=url,
        company="Acme Corp", title="Backend Engineer",
    )
    assert facts["visit"] == {"visited": False, "first_visited_at": None}
    assert facts["matches"] == []
    assert facts["company_history_count"] == 0
    assert facts["company_known"] is True
    assert facts["lookup_complete"] is True


def test_ext_13_clicked_external_and_applied_facts_remain_independent(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    clicked_url = "https://boards.example.test/role/13-clicked?utm_source=listing"
    row = CsvRow(
        user_id=owner.id, upload_batch_id=str(uuid4()), url=clicked_url,
        clicked=True, clicked_at=datetime(2026, 5, 2, 11, 0, 0),
    )
    apply_persisted_job_identity(row)
    applied_url = "https://boards.example.test/role/13-applied"
    own_application = _applied(db_session, owner, applied_url)
    _applied(db_session, foreign, clicked_url)
    external_url = "https://boards.example.test/role/13-visit"
    identity = canonicalize_job_url(external_url)
    db_session.add_all([
        row, JobVisit(user_id=owner.id, canonical_url=identity.canonical_url,
                      canonical_url_hash=identity.canonical_url_hash),
    ])
    db_session.commit()

    clicked = read_browser_memory_facts(db_session, user_id=owner.id,
                                        url=clicked_url)
    assert clicked["visit"] == {
        "visited": True, "first_visited_at": "2026-05-02T11:00:00Z",
    }
    assert clicked["matches"] == []
    assert clicked["company_known"] is False

    application = read_browser_memory_facts(db_session, user_id=owner.id,
                                            url=applied_url)
    assert application["visit"] == {"visited": False, "first_visited_at": None}
    assert [item["track_id"] for item in application["matches"]] == [own_application.id]
    assert application["matches"][0]["confidence"] == "exact"

    external = read_browser_memory_facts(db_session, user_id=owner.id, url=external_url)
    assert external["visit"]["visited"] is True
    assert external["visit"]["first_visited_at"].endswith("Z")
    assert external["matches"] == []
    assert read_browser_memory_facts(
        db_session, user_id=foreign.id, url=external_url
    )["visit"]["visited"] is False


def test_ext_13_company_history_counts_other_roles_but_not_shared_ats_host(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    _applied(db_session, owner, "https://boards.example.test/company/other-role",
             company="Acme Corp", title="Staff Engineer", status="rejected")
    _applied(db_session, foreign, "https://boards.example.test/company/foreign",
             company="Acme Corp")
    _applied(db_session, owner, "https://boards.example.test/other-employer/role",
             company="Other Co", title="Backend Engineer")
    db_session.commit()

    result = read_browser_memory_facts(
        db_session, user_id=owner.id,
        url="https://boards.example.test/company/candidate",
        company="Acme Corp", title="Backend Engineer",
    )
    assert result["company_history_count"] == 1
    assert result["matches"] == []
    assert result["visit"]["visited"] is False

    unknown = read_browser_memory_facts(
        db_session, user_id=owner.id,
        url="https://boards.example.test/company/candidate",
        company=None, title="Backend Engineer",
    )
    assert unknown["company_known"] is False
    assert unknown["company_history_count"] == 0
    assert unknown["matches"] == []


# EXT-15: identity rules are deliberately conservative, and reads never merge.
def test_ext_15_tracking_variants_resolve_as_canonical_with_old_status(db_session):
    owner = _owner(db_session)
    url = "https://jobs.example.test/Jobs/42?req=abc&utm_source=board"
    item = _applied(db_session, owner, url, status="archived",
                    when=datetime(2024, 9, 4, 6, 0, 0))
    db_session.commit()
    baseline = (item.url, item.status, item.applied_at, item.updated_at)
    for suffix in (
        "utm_medium=email",
        "gclid=123",
        "fbclid=456",
        "utm_source=new&gclid=789&fbclid=xyz",
    ):
        candidate = f"https://jobs.example.test/Jobs/42?req=abc&{suffix}"
        result = find_browser_applied_matches(
            db_session, user_id=owner.id, url=candidate,
            company=None, title=None,
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["track_id"] == item.id
        assert result["matches"][0]["confidence"] == "canonical"
        assert result["matches"][0]["reason"] == "same_canonical_url"
        assert result["matches"][0]["status"] == "archived"
    db_session.refresh(item)
    assert (item.url, item.status, item.applied_at, item.updated_at) == baseline


def test_ext_15_requisition_path_and_unknown_parameters_do_not_merge(db_session):
    owner = _owner(db_session)
    original = "https://jobs.example.test/Jobs/42/?req=abc&step=1"
    item = _applied(db_session, owner, original)
    db_session.commit()
    alternatives = (
        "https://jobs.example.test/Jobs/42/?req=def&step=1",
        "https://jobs.example.test/jobs/42/?req=abc&step=1",
        "https://jobs.example.test/Jobs/42?req=abc&step=1",
        "https://jobs.example.test/Jobs/42/?req=abc&step=2",
        "https://jobs.example.test/Jobs/42/?step=1&req=abc",
        "https://jobs.example.test/Jobs/43/?req=abc&step=1",
    )
    for candidate in alternatives:
        result = find_browser_applied_matches(
            db_session, user_id=owner.id, url=candidate,
            company=None, title=None,
        )
        assert result == {
            "matches": [], "company_history_count": 0, "lookup_complete": True,
        }
    assert db_session.query(JobTrack).filter(JobTrack.id == item.id).one().url == original


def test_ext_15_alias_title_is_possible_only_and_shared_ats_host_is_not_company(db_session):
    owner = _owner(db_session)
    family = str(uuid4())
    for name in ("Acme Corp", "Acme Incorporated"):
        db_session.add(CompanyAlias(
            user_id=owner.id,
            alias_key=normalize_company_alias_key(name),
            display_name=name,
            company_key=family,
        ))
    old = _applied(
        db_session, owner, "https://boards.example.test/other/old?job=9",
        company="Acme Incorporated", title="Backend Engineer",
        status="rejected",
    )
    same_company_other_role = _applied(
        db_session, owner, "https://boards.example.test/other/other-role?job=10",
        company="Acme Corp", title="Site Engineer",
    )
    db_session.commit()
    before = (old.url, old.status, old.applied_at, same_company_other_role.url)

    possible = find_browser_applied_matches(
        db_session, user_id=owner.id,
        url="https://boards.example.test/other/new?job=11",
        company="Acme Corp", title="Backend Engineer",
    )
    assert possible["company_history_count"] == 2
    assert len(possible["matches"]) == 1
    assert possible["matches"][0]["track_id"] == old.id
    assert possible["matches"][0]["confidence"] == "possible"
    assert possible["matches"][0]["reason"] == "company_alias_title"

    unrelated = find_browser_applied_matches(
        db_session, user_id=owner.id,
        url="https://boards.example.test/other/new?job=11",
        company="Unrelated Employer", title="Backend Engineer",
    )
    assert unrelated["matches"] == []
    assert unrelated["company_history_count"] == 0
    db_session.refresh(old)
    assert (old.url, old.status, old.applied_at, same_company_other_role.url) == before


# EXT-45 performance acceptance is an isolated, synthetic database test. It does
# not time a cold Chrome worker or stand in for live OAuth/permission acceptance.
def test_ext_45_case_01_02_warm_lookup_with_ten_thousand_visits(db_session, client, caplog):
    import math
    import time
    from sqlalchemy import func, inspect, text

    login = client.post("/auth/dev-login", json={
        "email": f"ext45-{uuid4().hex}@example.test",
    })
    assert login.status_code == 200
    owner = db_session.get(User, login.json()["id"])
    other = _owner(db_session)
    original = "https://jobs.example.test/openings/ext45-old?req=old&utm_source=first"
    old = _applied(db_session, owner, original, status="withdrawn",
                   when=datetime(2024, 1, 2, 9, 0, 0))
    # Older definite matches must survive a deliberately dense employer scan.
    for number in range(520):
        _applied(db_session, owner,
                 f"https://jobs.example.test/openings/ext45-new-{number}?req={number}")

    # Exercise the real owner/hash unique index at the documented 10,000 cap.
    # Bulk insert is fixture setup, never an application endpoint or a quota bypass.
    visit_rows = []
    for number in range(10_000):
        url = original if number == 0 else f"https://jobs.example.test/visited/ext45-{number}"
        identity = canonicalize_job_url(url)
        visit_rows.append({
            "user_id": owner.id,
            "canonical_url": identity.canonical_url,
            "canonical_url_hash": identity.canonical_url_hash,
        })
    db_session.execute(JobVisit.__table__.insert(), visit_rows)
    _applied(db_session, other, original)
    db_session.commit()

    assert db_session.query(func.count(JobVisit.id)).filter_by(user_id=owner.id).scalar() == 10_000
    unique_names = {
        constraint["name"]
        for constraint in inspect(db_session.get_bind()).get_unique_constraints("job_visits")
    }
    assert "uq_job_visits_user_hash" in unique_names

    query = (
        "SELECT id FROM job_visits WHERE user_id = :owner "
        "AND canonical_url_hash = :digest LIMIT 1"
    )
    dialect = db_session.get_bind().dialect.name
    explain = "EXPLAIN QUERY PLAN " if dialect == "sqlite" else "EXPLAIN "
    plan = db_session.execute(text(explain + query), {
        "owner": owner.id,
        "digest": visit_rows[0]["canonical_url_hash"],
    }).all()
    # Inspect actual disposable query execution, not an invented "indexed" claim.
    # PostgreSQL is free to choose a different plan on tiny fixtures, but a 10k
    # fixture should use the existing owner/hash index on supported runtimes.
    assert plan
    assert any("index" in " ".join(map(str, row)).lower() for row in plan)

    def check():
        response = client.post("/crm/browser-memory/check", json={
            "url": original, "company": "Acme Corp", "title": "Backend Engineer",
        })
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["account_id"] == owner.id
        return body

    with caplog.at_level("INFO"):
        cold_start = time.perf_counter()
        cold_result = check()
        cold_ms = round((time.perf_counter() - cold_start) * 1000, 1)
        samples_ms = []
        for _ in range(30):
            start = time.perf_counter()
            result = check()
            samples_ms.append((time.perf_counter() - start) * 1000)
    assert cold_result["visit"]["visited"] is True
    assert result["matches"][0]["track_id"] == old.id
    assert result["matches"][0]["confidence"] == "exact"
    assert result["matches"][0]["status"] == "withdrawn"
    assert result["lookup_complete"] is False
    assert result["company_history_count"] == 521
    assert len(result["matches"]) <= 20
    assert read_browser_memory_facts(
        db_session, user_id=other.id,
        url="https://jobs.example.test/visited/ext45-9999",
    )["visit"]["visited"] is False

    warm = sorted(samples_ms)
    p95_ms = warm[math.ceil(len(warm) * 0.95) - 1]
    assert p95_ms <= 2000, f"EXT-45 warm p95 exceeds 2s: {p95_ms:.1f}ms"
    # Only aggregate/sanitized fields: never print URLs, account labels or SQL.
    print(f"EXT-45 benchmark action=check outcome=ok "
          f"transport=testclient dialect={dialect} visits=10000 samples=30 "
          f"cold_ms={cold_ms} warm_p95_ms={p95_ms:.1f} "
          f"query_plan=index")
    # Neither the real lookup nor its diagnostics may write private payload
    # sentinels or URL query fragments to application logs.
    for forbidden in ("ext45-old", "ext45-9999", "utm_source=first",
                      "Backend Engineer", "Acme Corp"):
        assert forbidden not in caplog.text


def test_ext_45_case_03_http_diagnostics_hide_payload_and_cookie_on_database_failure(
    client, caplog, monkeypatch,
):
    from sqlalchemy.exc import SQLAlchemyError
    from app.routers import browser_memory

    login = client.post("/auth/dev-login", json={
        "email": f"ext45-log-{uuid4().hex}@example.test",
    })
    assert login.status_code == 200
    cookie = client.cookies.get("session_token")
    assert cookie
    payload = {
        "url": "https://jobs.example.test/ext45-private-path?req=ext45-private-query",
        "company": "EXT45 Private Company", "title": "EXT45 Private Title",
    }
    caplog.clear()
    with caplog.at_level("INFO"):
        success = client.post("/crm/browser-memory/check", json=payload)
        assert success.status_code == 200

        def unavailable(*args, **kwargs):
            # Simulate a driver exception containing bound private SQL parameters.
            raise SQLAlchemyError(str(payload) + cookie)

        monkeypatch.setattr(browser_memory, "read_browser_memory_facts", unavailable)
        failed = client.post("/crm/browser-memory/check", json=payload)
    assert failed.status_code == 503
    assert failed.json() == {"detail": {
        "code": "browser_memory_unavailable",
        "message": "Browser memory is temporarily unavailable.",
    }}
    assert any(record.name == "httpx" and "503" in record.getMessage()
               for record in caplog.records)
    for forbidden in (*payload.values(), "ext45-private-query", "session_token", cookie):
        assert forbidden not in caplog.text
        assert forbidden not in failed.text
