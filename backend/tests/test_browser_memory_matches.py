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
