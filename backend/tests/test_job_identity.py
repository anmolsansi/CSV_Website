import pytest

from app.services.job_identity import (
    CANONICALIZATION_VERSION,
    JobIdentityError,
    canonicalize_job_url,
    classify_identity_match,
    normalize_company_alias_key,
)


def test_utm_variants_same_canonical_key():
    first = canonicalize_job_url(
        "HTTPS://Example.COM:443/Jobs/42?req=abc&utm_source=linkedin&utm_campaign=fall#details"
    )
    second = canonicalize_job_url(
        "https://example.com/Jobs/42?req=abc&utm_medium=email&fbclid=tracking"
    )

    assert first.rule_version == CANONICALIZATION_VERSION
    assert first.original_url.endswith("#details")
    assert first.canonical_url == "https://example.com/Jobs/42?req=abc"
    assert second.canonical_url == "https://example.com/Jobs/42?req=abc"
    assert first.canonical_url_hash == second.canonical_url_hash


def test_different_requisition_query_values_remain_distinct():
    first = canonicalize_job_url("https://jobs.example.com/opening?req=1001")
    second = canonicalize_job_url("https://jobs.example.com/opening?req=1002")

    assert first.canonical_url != second.canonical_url
    assert first.canonical_url_hash != second.canonical_url_hash


def test_path_case_and_duplicate_query_order_preserved():
    identity = canonicalize_job_url(
        "https://EXAMPLE.com/Jobs/Role/?id=2&id=1&x=A&utm_source=test#apply"
    )

    assert identity.canonical_url == (
        "https://example.com/Jobs/Role/?id=2&id=1&x=A"
    )
    assert identity.canonical_url != canonicalize_job_url(
        "https://example.com/jobs/Role/?id=2&id=1&x=A"
    ).canonical_url
    assert identity.canonical_url != canonicalize_job_url(
        "https://example.com/Jobs/Role/?id=1&id=2&x=A"
    ).canonical_url
    assert identity.canonical_url != canonicalize_job_url(
        "https://example.com/Jobs/Role?id=2&id=1&x=A"
    ).canonical_url


def test_credentialed_or_invalid_url_rejected():
    invalid_urls = [
        "https://user:secret@example.com/job",
        "https://example.com:99999/job",
        "ftp://example.com/job",
        "https:///missing-host",
        " https://example.com/job",
        "https://example.com/job ",
        "https://example.com/" + ("x" * 2030),
    ]

    for url in invalid_urls:
        with pytest.raises(JobIdentityError):
            canonicalize_job_url(url)


def test_company_similarity_is_possible_only():
    result = classify_identity_match(
        "https://jobs.example.com/opening?req=1001",
        "https://jobs.example.com/opening?req=1002",
        candidate_company="  Acme   Labs ",
        existing_company="acme labs",
        candidate_title="Senior Engineer",
        existing_title=" senior   engineer ",
    )

    assert result.confidence == "possible"
    assert result.reason == "company_title_only"

    unrelated = classify_identity_match(
        "https://jobs.example.com/opening?req=1001",
        "https://jobs.example.com/opening?req=1002",
        candidate_company="Acme Labs",
        existing_company="Acme Laboratory",
        candidate_title="Senior Engineer",
        existing_title="Senior Engineer",
    )
    assert unrelated.confidence is None
    assert unrelated.reason == "no_identity_match"


def test_exact_and_canonical_reason_codes_are_distinct():
    exact = classify_identity_match(
        "https://example.com/job?id=1",
        "https://example.com/job?id=1",
    )
    canonical = classify_identity_match(
        "https://EXAMPLE.com:443/job?id=1&utm_source=a",
        "https://example.com/job?id=1&utm_source=b#fragment",
    )

    assert exact.confidence == "exact"
    assert exact.reason == "same_original_url"
    assert canonical.confidence == "canonical"
    assert canonical.reason == "same_canonical_url"


def test_default_ports_fragments_and_unicode_domain_are_normalized():
    identity = canonicalize_job_url(
        "https://BÜCHER.example:443/Jobs#section"
    )
    http_identity = canonicalize_job_url("http://Example.com:80/Jobs")

    assert identity.canonical_url == "https://xn--bcher-kva.example/Jobs"
    assert http_identity.canonical_url == "http://example.com/Jobs"


def test_nondefault_port_is_preserved():
    identity = canonicalize_job_url("https://Example.com:8443/Job")
    assert identity.canonical_url == "https://example.com:8443/Job"


def test_only_explicit_tracking_keys_are_removed():
    identity = canonicalize_job_url(
        "https://example.com/job?utm_source=x&gclid=y&fbclid=z"
        "&campaign_id=keep&utmish=keep&utm_source_id=keep"
    )

    assert identity.canonical_url == (
        "https://example.com/job?campaign_id=keep&utmish=keep&utm_source_id=keep"
    )


def test_company_alias_key_normalization_is_independent_and_unicode_safe():
    assert normalize_company_alias_key("  Example   COMPANY  ") == "example company"
    assert normalize_company_alias_key("Straße GmbH") == "strasse gmbh"

    with pytest.raises(JobIdentityError):
        normalize_company_alias_key("   ")
