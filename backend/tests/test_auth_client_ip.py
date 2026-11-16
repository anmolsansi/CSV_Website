"""Security regressions for authenticated client identity behind trusted proxies."""
import pytest
from starlette.requests import Request

from app.services.auth_client_ip import resolve_auth_client_ip


def _request(peer="192.0.2.8", forwarded=()):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/email/login",
        "raw_path": b"/auth/email/login",
        "query_string": b"",
        "root_path": "",
        "server": ("example.test", 80),
        "client": (peer, 40001) if peer else None,
        "headers": [(b"x-forwarded-for", value.encode("ascii")) for value in forwarded],
    })


def test_ignores_spoofed_forwarded_for_when_not_opted_in():
    request = _request("192.0.2.8", ["198.51.100.123"])
    assert resolve_auth_client_ip(request, []) == "192.0.2.8"


def test_direct_client_cannot_spoof_when_other_proxies_are_trusted():
    request = _request("192.0.2.8", ["198.51.100.123"])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "192.0.2.8"


def test_one_trusted_ingress_returns_forwarded_client():
    request = _request("10.3.4.5", ["198.51.100.20"])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "198.51.100.20"


def test_trusted_chain_ignores_untrusted_leftmost_spoof():
    request = _request("10.3.4.5", ["198.51.100.123, 203.0.113.20, 10.3.4.6"])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "203.0.113.20"


def test_multiple_forwarded_headers_form_single_chain():
    request = _request("10.3.4.5", [
        "198.51.100.123, 203.0.113.20",
        "10.3.4.6",
    ])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "203.0.113.20"


def test_trusted_ipv6_ingress_and_client():
    request = _request("2001:db8:abcd::1", ["2001:db8:fedc::5, 2001:db8:abcd::2"])
    assert resolve_auth_client_ip(request, ["2001:db8:abcd::/48"]) == "2001:db8:fedc::5"


def test_ipv4_mapped_ipv6_uses_single_ipv4_bucket():
    request = _request("::ffff:192.0.2.8", [])
    assert resolve_auth_client_ip(request, []) == "192.0.2.8"


@pytest.mark.parametrize("headers", [
    [],
    [""],
    ["not-an-ip"],
    ["198.51.100.20, invalid"],
    [", 198.51.100.20"],
    ["198.51.100.20,"],
    ["198.51.100.20" * 150],
    [", ".join(["198.51.100.20"] * 33)],
])
def test_malformed_or_missing_chain_falls_back_to_socket_peer(headers):
    request = _request("10.3.4.5", headers)
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "10.3.4.5"


def test_all_forwarded_hops_trusted_falls_back_to_socket_peer():
    request = _request("10.3.4.5", ["10.3.4.6,10.3.4.7"])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "10.3.4.5"


@pytest.mark.parametrize("cidrs", [["*"], ["0.0.0.0/0"], ["broken"], ["198.51.100.0/24"] * 33])
def test_invalid_trust_config_falls_back_to_socket_peer(cidrs):
    request = _request("10.3.4.5", ["198.51.100.20"])
    assert resolve_auth_client_ip(request, cidrs) == "10.3.4.5"


def test_missing_socket_peer_never_trusts_forwarded_for():
    request = _request(None, ["198.51.100.20"])
    assert resolve_auth_client_ip(request, ["10.3.0.0/16"]) == "unknown"
