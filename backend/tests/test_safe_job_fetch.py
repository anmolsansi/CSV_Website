from __future__ import annotations

from collections import defaultdict

import pytest

from app.availability_schemas import apply_checker_evidence
from app.services import safe_job_fetch as safe_fetch_module
from app.services.safe_job_fetch import (
    PinnedHTTPTransport,
    SafeFetchResult,
    SafeJobFetchError,
    SafeJobFetcher,
    TransportResponse,
)


PUBLIC_IP = "93.184.216.34"


class FakeResolver:
    def __init__(self, answers):
        self.answers = answers
        self.calls = defaultdict(int)

    def resolve(self, hostname, port, *, timeout):
        del port, timeout
        self.calls[hostname] += 1
        value = self.answers[hostname]
        if callable(value):
            return value(self.calls[hostname])
        return value


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, pinned_ip, timeout, max_body_bytes):
        self.calls.append({
            "method": method,
            "url": url,
            "pinned_ip": pinned_ip,
            "timeout": timeout,
            "max_body_bytes": max_body_bytes,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.parametrize(
    ("answers", "url"),
    [
        (["127.0.0.1"], "http://private.test/job"),
        (["::1"], "https://private.test/job"),
        (["169.254.10.20"], "https://private.test/job"),
        ([PUBLIC_IP, "10.0.0.8"], "https://mixed.test/job"),
        ([PUBLIC_IP, "fd00::1"], "https://mixed.test/job"),
    ],
)
def test_ipv4_ipv6_private_and_mixed_dns_answers_blocked(answers, url):
    hostname = "mixed.test" if "mixed" in url else "private.test"
    resolver = FakeResolver({hostname: answers})
    transport = FakeTransport([TransportResponse(200, {})])
    result = SafeJobFetcher(resolver=resolver, transport=transport).check(url)

    assert result.failure_reason == "unsafe_destination"
    assert transport.calls == []


def test_dns_rebinding_cannot_change_pinned_destination():
    def rebinding(call_number):
        return [PUBLIC_IP] if call_number == 1 else ["127.0.0.1"]

    resolver = FakeResolver({"jobs.example": rebinding})
    transport = FakeTransport([TransportResponse(200, {})])
    result = SafeJobFetcher(resolver=resolver, transport=transport).check(
        "https://jobs.example/roles/123"
    )

    assert result == SafeFetchResult(http_status=200, redirect_count=0)
    assert resolver.calls["jobs.example"] == 1
    assert [call["pinned_ip"] for call in transport.calls] == [PUBLIC_IP]


def test_redirect_private_target_blocked():
    resolver = FakeResolver({
        "public.example": [PUBLIC_IP],
        "private.example": ["10.10.0.5"],
    })
    transport = FakeTransport([
        TransportResponse(302, {"location": "http://private.example/internal"}),
    ])

    result = SafeJobFetcher(resolver=resolver, transport=transport).check(
        "https://public.example/job"
    )

    assert result.failure_reason == "unsafe_destination"
    assert result.redirect_count == 1
    assert len(transport.calls) == 1
    assert transport.calls[0]["pinned_ip"] == PUBLIC_IP


def test_timeout_and403_unknown():
    resolver = FakeResolver({"jobs.example": [PUBLIC_IP]})

    timeout_transport = FakeTransport([
        SafeJobFetchError("timeout", "synthetic timeout"),
    ])
    timeout_result = SafeJobFetcher(
        resolver=resolver,
        transport=timeout_transport,
    ).check("https://jobs.example/timeout")
    timeout_evidence = apply_checker_evidence(
        "available",
        failure_reason=timeout_result.failure_reason,
    )
    assert timeout_evidence.state == "unknown"
    assert timeout_evidence.check_reason == "timeout"

    forbidden_transport = FakeTransport([TransportResponse(403, {})])
    forbidden_result = SafeJobFetcher(
        resolver=resolver,
        transport=forbidden_transport,
    ).check("https://jobs.example/forbidden")
    forbidden_evidence = apply_checker_evidence(
        "available",
        http_status=forbidden_result.http_status,
    )
    assert forbidden_evidence.state == "unknown"
    assert forbidden_evidence.check_reason == "http_403"


def test_404_unavailable_not_closed():
    resolver = FakeResolver({"jobs.example": [PUBLIC_IP]})
    transport = FakeTransport([TransportResponse(404, {})])

    result = SafeJobFetcher(resolver=resolver, transport=transport).check(
        "https://jobs.example/missing"
    )
    evidence = apply_checker_evidence("available", http_status=result.http_status)

    assert evidence.state == "unavailable"
    assert evidence.state != "closed"
    assert evidence.check_reason == "http_404"


def test_body_limit_stops_read(monkeypatch):
    observed = {}

    class FakeResponse:
        status = 200

        def read(self, size):
            observed["read_size"] = size
            return b"x" * size

        def getheaders(self):
            return []

    class FakeConnection:
        def __init__(self, host, port, *, pinned_ip, timeout):
            observed["host"] = host
            observed["port"] = port
            observed["pinned_ip"] = pinned_ip
            observed["timeout"] = timeout

        def request(self, method, path, headers):
            observed["method"] = method
            observed["path"] = path
            observed["headers"] = headers

        def getresponse(self):
            return FakeResponse()

        def close(self):
            observed["closed"] = True

    monkeypatch.setattr(
        safe_fetch_module,
        "_PinnedHTTPConnection",
        FakeConnection,
    )

    transport = PinnedHTTPTransport()
    with pytest.raises(SafeJobFetchError) as raised:
        transport.request(
            "GET",
            "http://jobs.example/large?source=test",
            pinned_ip=PUBLIC_IP,
            timeout=1.0,
            max_body_bytes=128,
        )

    assert raised.value.code == "response_too_large"
    assert observed["read_size"] == 129
    assert observed["pinned_ip"] == PUBLIC_IP
    assert observed["headers"].get("Authorization") is None
    assert observed["headers"].get("Cookie") is None
    assert observed["closed"] is True


def test_unsafe_request_count_zero():
    resolver = FakeResolver({
        "localhost.example": ["127.0.0.1"],
        "ipv6.example": ["::1"],
        "mixed.example": [PUBLIC_IP, "192.168.1.9"],
    })
    transport = FakeTransport([TransportResponse(200, {})])

    for url in (
        "http://localhost.example/job",
        "https://ipv6.example/job",
        "https://mixed.example/job",
    ):
        result = SafeJobFetcher(resolver=resolver, transport=transport).check(url)
        assert result.failure_reason == "unsafe_destination"

    assert len(transport.calls) == 0


def test_redirect_limit_is_three_and_each_hop_is_revalidated():
    resolver = FakeResolver({
        "one.example": [PUBLIC_IP],
        "two.example": [PUBLIC_IP],
        "three.example": [PUBLIC_IP],
        "four.example": [PUBLIC_IP],
    })
    transport = FakeTransport([
        TransportResponse(302, {"location": "https://two.example/job"}),
        TransportResponse(302, {"location": "https://three.example/job"}),
        TransportResponse(302, {"location": "https://four.example/job"}),
        TransportResponse(302, {"location": "https://one.example/again"}),
    ])

    result = SafeJobFetcher(resolver=resolver, transport=transport).check(
        "https://one.example/job"
    )

    assert result.failure_reason == "redirect_limit"
    assert result.redirect_count == 3
    assert len(transport.calls) == 4


def test_head_falls_back_to_bounded_get_without_credentials():
    resolver = FakeResolver({"jobs.example": [PUBLIC_IP]})
    transport = FakeTransport([
        TransportResponse(405, {}),
        TransportResponse(200, {}),
    ])

    result = SafeJobFetcher(resolver=resolver, transport=transport).check(
        "https://jobs.example/job"
    )

    assert result.http_status == 200
    assert [call["method"] for call in transport.calls] == ["HEAD", "GET"]
    assert all(call["max_body_bytes"] == 128 * 1024 for call in transport.calls)
