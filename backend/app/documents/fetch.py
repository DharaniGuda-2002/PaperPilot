"""Fetch open-access PDFs safely and politely.

Safety (server-side request forgery): document URLs come from third-party
metadata, so every request is checked before and after connecting:
- only http/https on ports 80/443;
- the host must resolve only to public addresses (no private, loopback,
  link-local, multicast, reserved, unspecified, or IPv4-mapped equivalents);
- redirects are followed by hand, at most MAX_REDIRECTS, re-validating each hop;
- after connecting, the actual peer address is checked before any body is
  read, which defeats DNS rebinding between validation and connection;
- bodies are streamed with a byte cap, and must be a PDF ("%PDF" magic bytes).

Politeness: robots.txt is honored per host (disallowed paths are not fetched;
Crawl-delay sets the minimum spacing). Spacing is coordinated through a shared
HostScheduler so many workers together still respect it.
"""

import hashlib
import ipaddress
import logging
import socket
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx2

logger = logging.getLogger(__name__)

USER_AGENT = "PaperPilot/0.1 (research tool; +https://github.com/DharaniGuda-2002/PaperPilot)"
ROBOTS_AGENT = "PaperPilot"
MAX_REDIRECTS = 5
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
DEFAULT_HOST_INTERVAL_SECONDS = 1.0
ROBOTS_CACHE_SECONDS = 24 * 3600
ALLOWED_PORTS = {None, 80, 443}

Resolver = Callable[[str, int], list[str]]


class FetchRejectedError(Exception):
    """The URL must not be fetched (unsafe, disallowed, or not a PDF). Permanent."""


class FetchFailedError(Exception):
    """The fetch failed for a reason that may be temporary (network, 5xx)."""


class FetchDeferredError(Exception):
    """The host's politeness window is not open yet; try again after `wait_seconds`."""

    def __init__(self, host: str, wait_seconds: float) -> None:
        super().__init__(f"{host} rate window opens in {wait_seconds:.0f}s")
        self.host = host
        self.wait_seconds = wait_seconds


class HostScheduler(Protocol):
    def reserve(self, host: str, interval_seconds: float) -> float:
        """Reserve the next request slot for host; return seconds until it."""
        ...


@dataclass(frozen=True)
class FetchedPdf:
    content: bytes
    source_url: str
    final_url: str
    sha256: str


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str, resolver: Resolver) -> tuple[str, int]:
    """Return (host, port) if the URL is safe to request; raise FetchRejectedError otherwise."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchRejectedError(f"scheme not allowed: {parts.scheme or 'none'}")
    if parts.username or parts.password:
        raise FetchRejectedError("credentials in URL not allowed")
    host = parts.hostname
    if not host:
        raise FetchRejectedError("no host")
    try:
        port_value = parts.port
    except ValueError as exc:
        raise FetchRejectedError("invalid port") from exc
    if port_value not in ALLOWED_PORTS:
        raise FetchRejectedError(f"port not allowed: {port_value}")
    port = port_value or (443 if parts.scheme == "https" else 80)
    try:
        addresses = resolver(host, port)
    except OSError as exc:
        raise FetchFailedError(f"cannot resolve {host}") from exc
    if not addresses:
        raise FetchFailedError(f"no addresses for {host}")
    blocked = [a for a in addresses if not is_public_address(a)]
    if blocked:
        raise FetchRejectedError(f"{host} resolves to non-public address {blocked[0]}")
    return host, port


class SafeFetcher:
    def __init__(
        self,
        scheduler: HostScheduler,
        *,
        resolver: Resolver = system_resolver,
        transport: httpx2.BaseTransport | None = None,
        verify_peer: bool = True,
        timeout_seconds: float = 30.0,
        max_wait_seconds: float = 20.0,
    ) -> None:
        self._scheduler = scheduler
        self._resolver = resolver
        self._verify_peer = verify_peer  # off only for in-memory test transports
        self._max_wait = max_wait_seconds
        self._robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}
        self._client = httpx2.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_pdf(self, url: str) -> FetchedPdf:
        content, final_url = self._get(url, MAX_PDF_BYTES, require_pdf=True)
        return FetchedPdf(content, url, final_url, hashlib.sha256(content).hexdigest())

    # -- internals -------------------------------------------------------

    def _get(self, url: str, max_bytes: int, *, require_pdf: bool) -> tuple[bytes, str]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host, _port = validate_url(current, self._resolver)
            if require_pdf:
                self._check_robots_and_wait(current, host)
            try:
                with self._client.stream("GET", current) as response:
                    self._check_peer(response, host)
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchFailedError("redirect without location")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 500 or response.status_code == 429:
                        raise FetchFailedError(f"HTTP {response.status_code}")
                    if response.status_code != 200:
                        raise FetchRejectedError(f"HTTP {response.status_code}")
                    return self._read_capped(response, max_bytes, require_pdf), current
            except httpx2.TransportError as exc:
                raise FetchFailedError(f"network error: {type(exc).__name__}") from exc
        raise FetchRejectedError(f"more than {MAX_REDIRECTS} redirects")

    def _check_peer(self, response: httpx2.Response, host: str) -> None:
        if not self._verify_peer:
            return
        stream = response.extensions.get("network_stream")
        peer = stream.get_extra_info("server_addr") if stream is not None else None
        if not peer:
            raise FetchRejectedError("cannot verify connected address")
        if not is_public_address(str(peer[0])):
            raise FetchRejectedError(f"{host} connected to non-public address {peer[0]}")

    @staticmethod
    def _read_capped(response: httpx2.Response, max_bytes: int, require_pdf: bool) -> bytes:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise FetchRejectedError(f"too large: {declared} bytes")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise FetchRejectedError(f"too large: over {max_bytes} bytes")
            chunks.append(chunk)
        body = b"".join(chunks)
        if require_pdf and not body.lstrip()[:5].startswith(b"%PDF"):
            content_type = response.headers.get("content-type", "unknown")
            raise FetchRejectedError(f"not a PDF (content-type {content_type})")
        return body

    def _check_robots_and_wait(self, url: str, host: str) -> None:
        robots = self._robots_for(url, host)
        if not robots.can_fetch(ROBOTS_AGENT, url):
            raise FetchRejectedError(f"disallowed by {host}/robots.txt")
        delay = robots.crawl_delay(ROBOTS_AGENT)
        interval = max(float(delay) if delay else 0.0, DEFAULT_HOST_INTERVAL_SECONDS)
        wait = self._scheduler.reserve(host, interval)
        if wait > self._max_wait:
            raise FetchDeferredError(host, wait)
        if wait > 0:
            time.sleep(wait)

    def _robots_for(self, url: str, host: str) -> urllib.robotparser.RobotFileParser:
        cached = self._robots.get(host)
        if cached and time.monotonic() - cached[0] < ROBOTS_CACHE_SECONDS:
            return cached[1]
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            body, _ = self._get(robots_url, MAX_ROBOTS_BYTES, require_pdf=False)
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
        except FetchRejectedError:
            parser.parse([])  # no robots.txt (4xx): everything allowed (RFC 9309)
        except FetchFailedError:
            # Unreachable robots.txt: assume disallowed, as RFC 9309 advises for 5xx.
            parser.parse(["User-agent: *", "Disallow: /"])
        self._robots[host] = (time.monotonic(), parser)
        return parser
