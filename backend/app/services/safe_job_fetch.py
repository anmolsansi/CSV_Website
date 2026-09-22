from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from time import monotonic
from typing import Mapping, Protocol, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..availability_schemas import validate_job_url


MAX_REDIRECTS = 3
MAX_TOTAL_SECONDS = 10.0
MAX_RESPONSE_BYTES = 128 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_GET_FALLBACK_STATUSES = frozenset({405, 501})


class SafeJobFetchError(ValueError):
    """A bounded checker failure safe to persist as a short outcome code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    headers: Mapping[str, str]


@dataclass(frozen=True)
class SafeFetchResult:
    http_status: int | None = None
    failure_reason: str | None = None
    redirect_count: int = 0


class AddressResolver(Protocol):
    def resolve(self, hostname: str, port: int, *, timeout: float) -> Sequence[str]:
        ...


class PinnedTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        pinned_ip: str,
        timeout: float,
        max_body_bytes: int,
    ) -> TransportResponse:
        ...


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise SafeJobFetchError("timeout", "The link check exceeded its time budget.")
    return remaining


def validate_public_addresses(addresses: Sequence[str]) -> tuple[str, ...]:
    """Require every DNS answer to be globally routable.

    Rejecting the complete answer set on one unsafe address prevents mixed-answer
    hosts from turning resolver selection into an SSRF bypass.
    """

    if not addresses:
        raise SafeJobFetchError("dns_no_answers", "The hostname did not resolve.")

    normalized: list[str] = []
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise SafeJobFetchError("dns_invalid_answer", "DNS returned an invalid address.") from exc
        if not address.is_global:
            raise SafeJobFetchError(
                "unsafe_destination",
                "The hostname resolved to a non-public network address.",
            )
        canonical = str(address)
        if canonical not in normalized:
            normalized.append(canonical)

    if not normalized:
        raise SafeJobFetchError("dns_no_answers", "The hostname did not resolve.")
    return tuple(normalized)


class SystemAddressResolver:
    """Resolve through the host resolver with a caller-visible timeout boundary."""

    def resolve(self, hostname: str, port: int, *, timeout: float) -> Sequence[str]:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jobgrid-dns")
        future = executor.submit(
            socket.getaddrinfo,
            hostname,
            port,
            0,
            socket.SOCK_STREAM,
        )
        try:
            rows = future.result(timeout=max(0.001, timeout))
        except FutureTimeoutError as exc:
            future.cancel()
            raise SafeJobFetchError("timeout", "DNS resolution exceeded the time budget.") from exc
        except socket.gaierror as exc:
            raise SafeJobFetchError("dns_error", "The hostname could not be resolved.") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return [row[4][0] for row in rows if row and row[4]]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, *, pinned_ip: str, timeout: float) -> None:
        self._pinned_ip = pinned_ip
        super().__init__(host=host, port=port, timeout=timeout)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        pinned_ip: str,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        self._pinned_ip = pinned_ip
        super().__init__(host=host, port=port, timeout=timeout, context=context)

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class PinnedHTTPTransport:
    """Dial only the validated IP while retaining the original TLS/Host identity."""

    def __init__(self, *, ssl_context: ssl.SSLContext | None = None) -> None:
        self.ssl_context = ssl_context or ssl.create_default_context()

    def request(
        self,
        method: str,
        url: str,
        *,
        pinned_ip: str,
        timeout: float,
        max_body_bytes: int,
    ) -> TransportResponse:
        parsed = urlsplit(validate_job_url(url))
        hostname = parsed.hostname
        if hostname is None:
            raise SafeJobFetchError("invalid_job_url", "Job URL is missing a hostname.")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme == "https":
            connection: http.client.HTTPConnection = _PinnedHTTPSConnection(
                hostname,
                port,
                pinned_ip=pinned_ip,
                timeout=timeout,
                context=self.ssl_context,
            )
        else:
            connection = _PinnedHTTPConnection(
                hostname,
                port,
                pinned_ip=pinned_ip,
                timeout=timeout,
            )

        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        headers = {
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Connection": "close",
            "User-Agent": "JobGrid-LinkCheck/1.0",
        }
        try:
            connection.request(method.upper(), path, headers=headers)
            response = connection.getresponse()
            if method.upper() != "HEAD":
                body = response.read(max_body_bytes + 1)
                if len(body) > max_body_bytes:
                    raise SafeJobFetchError(
                        "response_too_large",
                        "The response exceeded the link-check byte limit.",
                    )
            return TransportResponse(
                status_code=int(response.status),
                headers={key.lower(): value for key, value in response.getheaders()},
            )
        except SafeJobFetchError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise SafeJobFetchError("timeout", "The link check timed out.") from exc
        except (ssl.SSLError, OSError, http.client.HTTPException) as exc:
            raise SafeJobFetchError("transport_error", "The link check transport failed.") from exc
        finally:
            connection.close()


class SafeJobFetcher:
    """Conservative URL checker with validation at every network hop."""

    def __init__(
        self,
        *,
        resolver: AddressResolver | None = None,
        transport: PinnedTransport | None = None,
        max_redirects: int = MAX_REDIRECTS,
        max_total_seconds: float = MAX_TOTAL_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        if max_redirects < 0 or max_redirects > MAX_REDIRECTS:
            raise ValueError("max_redirects must be between 0 and 3.")
        if max_total_seconds <= 0 or max_total_seconds > MAX_TOTAL_SECONDS:
            raise ValueError("max_total_seconds must be between 0 and 10 seconds.")
        if max_response_bytes <= 0 or max_response_bytes > MAX_RESPONSE_BYTES:
            raise ValueError("max_response_bytes must be between 1 and 131072.")
        self.resolver = resolver or SystemAddressResolver()
        self.transport = transport or PinnedHTTPTransport()
        self.max_redirects = max_redirects
        self.max_total_seconds = max_total_seconds
        self.max_response_bytes = max_response_bytes

    def _resolve_target(self, url: str, *, deadline: float) -> str:
        parsed = urlsplit(validate_job_url(url))
        hostname = parsed.hostname
        if hostname is None:
            raise SafeJobFetchError("invalid_job_url", "Job URL is missing a hostname.")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            answers = self.resolver.resolve(
                hostname,
                port,
                timeout=_remaining(deadline),
            )
        else:
            answers = [str(literal)]

        public = validate_public_addresses(answers)
        return public[0]

    def check(self, url: str) -> SafeFetchResult:
        current_url = validate_job_url(url)
        deadline = monotonic() + self.max_total_seconds
        redirects = 0

        while True:
            try:
                pinned_ip = self._resolve_target(current_url, deadline=deadline)
                response = self.transport.request(
                    "HEAD",
                    current_url,
                    pinned_ip=pinned_ip,
                    timeout=_remaining(deadline),
                    max_body_bytes=self.max_response_bytes,
                )
                if response.status_code in _GET_FALLBACK_STATUSES:
                    response = self.transport.request(
                        "GET",
                        current_url,
                        pinned_ip=pinned_ip,
                        timeout=_remaining(deadline),
                        max_body_bytes=self.max_response_bytes,
                    )
            except SafeJobFetchError as exc:
                return SafeFetchResult(
                    failure_reason=exc.code,
                    redirect_count=redirects,
                )

            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    return SafeFetchResult(
                        failure_reason="redirect_missing_location",
                        redirect_count=redirects,
                    )
                if redirects >= self.max_redirects:
                    return SafeFetchResult(
                        failure_reason="redirect_limit",
                        redirect_count=redirects,
                    )
                try:
                    next_url = validate_job_url(urljoin(current_url, location))
                except ValueError:
                    return SafeFetchResult(
                        failure_reason="invalid_redirect",
                        redirect_count=redirects,
                    )
                current_url = next_url
                redirects += 1
                continue

            return SafeFetchResult(
                http_status=response.status_code,
                redirect_count=redirects,
            )
