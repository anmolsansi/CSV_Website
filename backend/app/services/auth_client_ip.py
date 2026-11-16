"""Resolve a rate-limit peer only across explicitly trusted reverse-proxy hops.

Uvicorn must run with --no-proxy-headers so request.client remains the socket
peer. The default Render Python FORWARDED_ALLOW_IPS=* is NOT safe for this use.
"""
from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from fastapi import Request


def _ip(value: str):
    """Normalize IPv4-mapped IPv6 as IPv4 to avoid duplicate peer identities."""
    address = ipaddress.ip_address(value.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _trusted_networks(cidrs: Sequence[str]):
    networks = []
    if len(cidrs) > 32:
        raise ValueError("Too many trusted proxy networks")
    for cidr in cidrs:
        network = ipaddress.ip_network(cidr, strict=True)
        # Trusting the entire Internet is equivalent to blindly accepting XFF.
        if network.prefixlen == 0:
            raise ValueError("Trusted proxy networks must not include the entire Internet")
        networks.append(network)
    return networks


def resolve_auth_client_ip(request: Request, trusted_proxy_cidrs: Sequence[str]) -> str:
    """Return a stable peer key, ignoring attacker-controlled XFF prefixes.

    If the socket peer is not on the explicit trusted-proxy list, ignore all
    forwarded headers. Otherwise, walk the complete XFF list right-to-left and
    select the first address not in the trusted proxy set. Unknown or malformed
    input falls back to the socket peer, never to an unverified header value.
    """
    peer = request.client.host if request.client else "unknown"
    try:
        socket_address = _ip(peer)
    except ValueError:
        return peer

    normalized_peer = socket_address.compressed
    networks = _trusted_networks(trusted_proxy_cidrs)
    is_trusted = lambda addr: any(addr in net for net in networks)

    if not is_trusted(socket_address):
        return normalized_peer

    # A client can set arbitrary header text before an ingress adds its own hop.
    # Cap parsing work and never accept the leftmost address by default.
    raw_headers = request.headers.getlist("x-forwarded-for")
    if not raw_headers or sum(len(v) for v in raw_headers) > 2048:
        return normalized_peer

    hops = []
    try:
        for header in raw_headers:
            for value in header.split(","):
                if not value.strip() or len(hops) >= 32:
                    return normalized_peer
                hops.append(_ip(value))
    except ValueError:
        return normalized_peer

    for hop in reversed(hops):
        if not is_trusted(hop):
            return hop.compressed
    return normalized_peer
