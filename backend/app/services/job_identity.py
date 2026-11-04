"""Conservative job/company identity helpers for the F2 duplicate-warning flow.

The canonical helpers derive signals without mutating stored URLs. The
read-only applied-history lookup is shared by CRM and browser-memory callers.
Persistence and backfill remain separate responsibilities.
"""

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from ipaddress import ip_address
import re
from typing import Any, Literal

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..models import CompanyAlias, JobTrack
from urllib.parse import unquote_plus, urlsplit, urlunsplit


CANONICALIZATION_VERSION = "ccr-identity-1"
MAX_JOB_URL_LENGTH = 2048
_TRACKING_QUERY_KEYS = frozenset({"gclid", "fbclid"})
_WHITESPACE_RE = re.compile(r"\s+")

MatchConfidence = Literal["exact", "canonical", "possible"]


class JobIdentityError(ValueError):
    """Raised when an input cannot safely participate in job identity."""


@dataclass(frozen=True)
class CanonicalJobIdentity:
    original_url: str
    canonical_url: str
    canonical_url_hash: str
    rule_version: str = CANONICALIZATION_VERSION


@dataclass(frozen=True)
class IdentityMatch:
    confidence: MatchConfidence | None
    reason: str


def _canonical_host(hostname: str) -> str:
    try:
        address = ip_address(hostname)
    except ValueError:
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise JobIdentityError("URL host is not valid IDNA.") from exc
        return ascii_host.lower()

    if address.version == 6:
        return f"[{address.compressed.lower()}]"
    return address.compressed


def _is_tracking_query_key(raw_key: str) -> bool:
    try:
        key = unquote_plus(raw_key).casefold()
    except (UnicodeDecodeError, ValueError):
        key = raw_key.casefold()
    return key.startswith("utm_") or key in _TRACKING_QUERY_KEYS


def _filter_tracking_query(raw_query: str) -> str:
    if not raw_query:
        return ""

    kept: list[str] = []
    for segment in raw_query.split("&"):
        raw_key = segment.split("=", 1)[0]
        if _is_tracking_query_key(raw_key):
            continue
        kept.append(segment)
    return "&".join(kept)


def canonicalize_job_url(url: str) -> CanonicalJobIdentity:
    """Return a stable conservative canonical identity without rewriting input.

    Rules are intentionally narrow:
    - only HTTP(S);
    - lower-case scheme/host with one IDNA policy;
    - strip default ports and fragments;
    - remove only utm_* plus gclid/fbclid query keys;
    - preserve path bytes/case/trailing slash and all remaining query order.
    """

    if not isinstance(url, str) or not url:
        raise JobIdentityError("Job URL must be a non-empty string.")
    if len(url) > MAX_JOB_URL_LENGTH:
        raise JobIdentityError(
            f"Job URL must be at most {MAX_JOB_URL_LENGTH} characters."
        )
    if url != url.strip():
        raise JobIdentityError("Job URL must not contain surrounding whitespace.")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise JobIdentityError("Job URL is malformed.") from exc

    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise JobIdentityError("Job URL must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        raise JobIdentityError("Job URL must not contain credentials.")

    hostname = parsed.hostname
    if not hostname:
        raise JobIdentityError("Job URL must include a host.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise JobIdentityError("Job URL contains an invalid port.") from exc

    host = _canonical_host(hostname)
    default_port = 80 if scheme == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"

    query = _filter_tracking_query(parsed.query)
    canonical_url = urlunsplit((scheme, netloc, parsed.path, query, ""))
    canonical_hash = sha256(canonical_url.encode("utf-8")).hexdigest()

    return CanonicalJobIdentity(
        original_url=url,
        canonical_url=canonical_url,
        canonical_url_hash=canonical_hash,
    )


def normalize_company_alias_key(value: str) -> str:
    """Normalize an explicit owner-local company alias key.

    Display spelling is kept by callers. This function only derives the lookup
    key and deliberately does not perform fuzzy matching.
    """

    if not isinstance(value, str):
        raise JobIdentityError("Company name must be a string.")
    normalized = _WHITESPACE_RE.sub(" ", value.strip()).casefold()
    if not normalized:
        raise JobIdentityError("Company name must not be empty.")
    return normalized


def _normalize_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", value.strip()).casefold()
    return normalized or None


def classify_identity_match(
    candidate_url: str,
    existing_url: str,
    *,
    candidate_company: str | None = None,
    existing_company: str | None = None,
    candidate_title: str | None = None,
    existing_title: str | None = None,
) -> IdentityMatch:
    """Classify identity evidence without automatically merging records."""

    candidate = canonicalize_job_url(candidate_url)
    existing = canonicalize_job_url(existing_url)

    if candidate.original_url == existing.original_url:
        return IdentityMatch(confidence="exact", reason="same_original_url")

    if candidate.canonical_url_hash == existing.canonical_url_hash:
        return IdentityMatch(confidence="canonical", reason="same_canonical_url")

    if (
        candidate_company is not None
        and existing_company is not None
        and _normalize_title(candidate_title) is not None
        and _normalize_title(candidate_title) == _normalize_title(existing_title)
        and normalize_company_alias_key(candidate_company)
        == normalize_company_alias_key(existing_company)
    ):
        return IdentityMatch(confidence="possible", reason="company_title_only")

    return IdentityMatch(confidence=None, reason="no_identity_match")


@dataclass(frozen=True)
class IdentityBackfillReport:
    entity: str
    dry_run: bool
    after_id: int
    last_id: int | None
    scanned: int
    updated: int
    unchanged: int
    invalid: int
    collision_groups: int
    collision_records: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def persisted_identity_values(url: str) -> dict[str, str] | None:
    """Return derived storage values, or None for a legacy URL that cannot canonicalize.

    This helper deliberately does not make URL validation stricter for existing
    import paths. Callers that already reject malformed URLs keep doing so, while
    legacy/imported rows can remain usable with nullable derived identity fields.
    """

    try:
        identity = canonicalize_job_url(url)
    except JobIdentityError:
        return None
    return {
        "canonical_url": identity.canonical_url,
        "canonical_url_hash": identity.canonical_url_hash,
    }


def apply_persisted_job_identity(record: Any, *, url: str | None = None) -> bool:
    """Populate nullable derived identity fields without changing the original URL.

    Returns True when canonical identity could be derived. Invalid legacy URLs
    are left with null derived fields and are reported by the backfill instead
    of being deleted or rewritten.
    """

    original_url = url if url is not None else getattr(record, "url", None)
    values = persisted_identity_values(original_url)
    if values is None:
        record.canonical_url = None
        record.canonical_url_hash = None
        return False

    record.canonical_url = values["canonical_url"]
    record.canonical_url_hash = values["canonical_url_hash"]
    return True


def backfill_identity_batch(
    session: Any,
    model: Any,
    *,
    after_id: int = 0,
    limit: int = 500,
    dry_run: bool = False,
) -> IdentityBackfillReport:
    """Derive identity for one bounded, resumable ORM batch.

    The function never commits. The operational CLI owns commit/rollback so a
    500-record batch is one transaction. Collision reporting is count-only and
    never merges, deletes, or rewrites records.
    """

    if after_id < 0:
        raise ValueError("after_id must be non-negative")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")

    records = (
        session.query(model)
        .filter(model.id > after_id)
        .order_by(model.id.asc())
        .limit(limit)
        .all()
    )

    updated = 0
    unchanged = 0
    invalid = 0
    derived: list[tuple[int, str]] = []

    for record in records:
        values = persisted_identity_values(record.url)
        if values is None:
            invalid += 1
            continue

        derived.append((record.user_id, values["canonical_url_hash"]))
        changed = (
            record.canonical_url != values["canonical_url"]
            or record.canonical_url_hash != values["canonical_url_hash"]
        )
        if changed:
            updated += 1
            if not dry_run:
                record.canonical_url = values["canonical_url"]
                record.canonical_url_hash = values["canonical_url_hash"]
        else:
            unchanged += 1

    # Count collisions inside the bounded candidate set. On write runs, include
    # already-derived rows outside the current batch after flushing the updates.
    pair_counts = Counter(derived)
    if not dry_run and derived:
        session.flush()
        candidate_pairs = sorted(set(derived))
        persisted = (
            session.query(
                model.user_id,
                model.canonical_url_hash,
                func.count(model.id),
            )
            .filter(
                or_(
                    *[
                        and_(
                            model.user_id == user_id,
                            model.canonical_url_hash == canonical_hash,
                        )
                        for user_id, canonical_hash in candidate_pairs
                    ]
                )
            )
            .group_by(model.user_id, model.canonical_url_hash)
            .all()
        )
        pair_counts = Counter({
            (user_id, canonical_hash): count
            for user_id, canonical_hash, count in persisted
            if canonical_hash is not None
        })

    collision_counts = [count for count in pair_counts.values() if count > 1]
    return IdentityBackfillReport(
        entity=getattr(model, "__tablename__", model.__name__),
        dry_run=dry_run,
        after_id=after_id,
        last_id=records[-1].id if records else None,
        scanned=len(records),
        updated=updated,
        unchanged=unchanged,
        invalid=invalid,
        collision_groups=len(collision_counts),
        collision_records=sum(collision_counts),
    )


# Read-only applied application matching (EXT-11). The legacy CRM HTTP layer
# validates its request and maps JobIdentityError to its existing 422 response.
# The bounded legacy query behavior is preserved until the browser-specific
# completeness algorithm is introduced separately.
APPLICATION_MATCH_LIMIT = 20
APPLICATION_MATCH_SCAN_LIMIT = 100
APPLICATION_ALIAS_LIMIT = 100


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    return normalized or None


def _company_alias_group(
    db: Session,
    *,
    user_id: int,
    company: str | None,
) -> tuple[str | None, list[str], set[str]]:
    company_key = _normalized_text(company)
    if company_key is None:
        return None, [], set()

    try:
        alias_key = normalize_company_alias_key(company)
    except JobIdentityError:
        return company_key, [company.strip()], {company_key}

    anchor = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user_id,
            CompanyAlias.alias_key == alias_key,
        )
        .first()
    )
    if anchor is None:
        return alias_key, [company.strip()], {alias_key}

    aliases = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user_id,
            CompanyAlias.company_key == anchor.company_key,
        )
        .order_by(CompanyAlias.alias_key.asc())
        .limit(APPLICATION_ALIAS_LIMIT)
        .all()
    )
    names = list(dict.fromkeys([company.strip()] + [alias.display_name for alias in aliases]))
    keys = {alias.alias_key for alias in aliases}
    keys.add(alias_key)
    return alias_key, names, keys


def find_applied_matches(
    db: Session,
    *,
    user_id: int,
    url: str,
    company: str | None,
    title: str | None,
) -> dict:
    identity = canonicalize_job_url(url)

    candidate_company_key, company_names, company_alias_keys = _company_alias_group(
        db,
        user_id=user_id,
        company=company,
    )
    company_sql_keys = sorted(
        {name.strip().lower() for name in company_names if name and name.strip()}
    )

    candidate_filters = [
        JobTrack.url == url,
        JobTrack.canonical_url_hash == identity.canonical_url_hash,
    ]
    if company_sql_keys:
        candidate_filters.append(
            func.lower(func.trim(JobTrack.company)).in_(company_sql_keys)
        )

    candidates = (
        db.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.applied_at.isnot(None),
            or_(*candidate_filters),
        )
        .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
        .limit(APPLICATION_MATCH_SCAN_LIMIT)
        .all()
    )

    candidate_title = _normalized_text(title)
    matches = []
    rank = {"exact": 0, "canonical": 1, "possible": 2}
    for item in candidates:
        confidence = None
        reason = None
        if item.url == url:
            confidence = "exact"
            reason = "same_original_url"
        elif (
            item.canonical_url_hash
            and item.canonical_url_hash == identity.canonical_url_hash
        ):
            confidence = "canonical"
            reason = "same_canonical_url"
        else:
            existing_company_key = _normalized_text(item.company)
            existing_title = _normalized_text(item.title)
            same_company = (
                candidate_company_key is not None
                and existing_company_key is not None
                and (
                    existing_company_key == candidate_company_key
                    or existing_company_key in company_alias_keys
                )
            )
            if same_company and candidate_title is not None and candidate_title == existing_title:
                confidence = "possible"
                reason = (
                    "company_title_only"
                    if existing_company_key == candidate_company_key
                    else "company_alias_title"
                )

        if confidence is None:
            continue
        matches.append(
            {
                "track_id": item.id,
                "confidence": confidence,
                "reason": reason,
                "company": item.company,
                "title": item.title,
                "status": item.status,
                "applied_at": item.applied_at,
            }
        )

    matches.sort(
        key=lambda item: (
            rank[item["confidence"]],
            -(item["applied_at"].timestamp() if item["applied_at"] else 0),
            -item["track_id"],
        )
    )

    history_count = 0
    if company_sql_keys:
        history_count = (
            db.query(func.count(JobTrack.id))
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.applied_at.isnot(None),
                func.lower(func.trim(JobTrack.company)).in_(company_sql_keys),
            )
            .scalar()
            or 0
        )

    return {
        "matches": matches[:APPLICATION_MATCH_LIMIT],
        "company_history_count": int(history_count),
    }





def _browser_definite_applied_matches(
    db: Session, *, user_id: int, url: str, canonical_url: str, digest: str,
) -> list[dict]:
    """Look up original and canonical URL matches without any company scan cap.

    Separate bounded queries prevent a thousand new company roles from hiding
    an older exact record. Validate both the hash and the canonical URL.
    """
    base = db.query(JobTrack).filter(
        JobTrack.user_id == user_id, JobTrack.applied_at.isnot(None),
    )
    definite: list[dict] = []
    for confidence, reason, predicate in (
        ("exact", "same_original_url", JobTrack.url == url),
        (
            "canonical",
            "same_canonical_url",
            and_(
                JobTrack.canonical_url_hash == digest,
                JobTrack.canonical_url == canonical_url,
                JobTrack.url != url,
            ),
        ),
    ):
        rows = (
            base.filter(predicate)
            .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
            .limit(APPLICATION_MATCH_LIMIT)
            .all()
        )
        for item in rows:
            definite.append({
                "track_id": item.id,
                "confidence": confidence,
                "reason": reason,
                "company": item.company,
                "title": item.title,
                "status": item.status,
                "applied_at": item.applied_at,
            })
    return definite



BROWSER_POSSIBLE_MATCH_SCAN_LIMIT = 500


def find_browser_applied_matches(
    db: Session,
    *,
    user_id: int,
    url: str,
    company: str | None,
    title: str | None,
) -> dict:
    """Read-only browser lookup with complete definite identity checks.

    The existing CRM adapter still uses find_applied_matches and its original
    response/query limits. Only the new browser caller consumes lookup_complete.
    """
    identity = canonicalize_job_url(url)
    matches = _browser_definite_applied_matches(
        db,
        user_id=user_id,
        url=url,
        canonical_url=identity.canonical_url,
        digest=identity.canonical_url_hash,
    )
    seen_ids = {item["track_id"] for item in matches}
    candidate_key, company_names, alias_keys = _company_alias_group(
        db, user_id=user_id, company=company,
    )
    company_sql_keys = sorted({
        name.strip().lower() for name in company_names if name and name.strip()
    })
    candidate_title = _normalized_text(title)
    lookup_complete = True
    if company_sql_keys and candidate_title is not None:
        # Only *possible* matches are bounded. Definite URLs never enter this
        # candidate pool, so an older exact application cannot be crowded out.
        candidates = (
            db.query(JobTrack)
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.applied_at.isnot(None),
                func.lower(func.trim(JobTrack.company)).in_(company_sql_keys),
            )
            .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
            .limit(BROWSER_POSSIBLE_MATCH_SCAN_LIMIT)
            .all()
        )
        # At the boundary, conservatively report incompleteness. Never turn a
        # truncated scan into a definitive "no application" claim.
        lookup_complete = len(candidates) < BROWSER_POSSIBLE_MATCH_SCAN_LIMIT
        for item in candidates:
            if item.id in seen_ids or _normalized_text(item.title) != candidate_title:
                continue
            existing_key = _normalized_text(item.company)
            if not (
                candidate_key is not None
                and existing_key is not None
                and (existing_key == candidate_key or existing_key in alias_keys)
            ):
                continue
            matches.append({
                "track_id": item.id,
                "confidence": "possible",
                "reason": (
                    "company_title_only"
                    if existing_key == candidate_key
                    else "company_alias_title"
                ),
                "company": item.company,
                "title": item.title,
                "status": item.status,
                "applied_at": item.applied_at,
            })
            seen_ids.add(item.id)

    rank = {"exact": 0, "canonical": 1, "possible": 2}
    matches.sort(key=lambda item: (
        rank[item["confidence"]],
        -(item["applied_at"].timestamp() if item["applied_at"] else 0),
        -item["track_id"],
    ))
    history_count = 0
    if company_sql_keys:
        history_count = (
            db.query(func.count(JobTrack.id))
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.applied_at.isnot(None),
                func.lower(func.trim(JobTrack.company)).in_(company_sql_keys),
            )
            .scalar()
            or 0
        )
    return {
        "matches": matches[:APPLICATION_MATCH_LIMIT],
        "company_history_count": int(history_count),
        "lookup_complete": lookup_complete,
    }
