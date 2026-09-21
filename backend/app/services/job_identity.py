"""Conservative job/company identity helpers for the F2 duplicate-warning flow.

JG-029 is intentionally pure: these helpers derive identity signals without
mutating persisted URLs or deciding that similar jobs are the same record.
Persistence and backfill are owned by JG-030.
"""

from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address
import re
from typing import Literal
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
