"""SSRF protection, robots.txt politeness, and limits for document fetching.
All network traffic is simulated; resolvers map test hostnames to addresses."""

from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.documents.fetch import (
    MAX_PDF_BYTES,
    FetchDeferredError,
    FetchFailedError,
    FetchRejectedError,
    SafeFetcher,
    is_public_address,
    validate_url,
)
from app.documents.host_schedule import PostgresHostScheduler

PDF = b"%PDF-1.7\n% test fixture, not a real paper\n"
ADDRESSES = {
    "papers.example": ["93.184.216.34"],
    "evil.example": ["10.0.0.5"],
    "rebind.example": ["93.184.216.34", "127.0.0.1"],
    "metadata.example": ["169.254.169.254"],
}


def resolver(host: str, port: int) -> list[str]:
    return ADDRESSES.get(host, ["93.184.216.34"])


class RecordingScheduler:
    def __init__(self, wait: float = 0.0) -> None:
        self.calls: list[tuple[str, float]] = []
        self.wait = wait

    def reserve(self, host: str, interval_seconds: float) -> float:
        self.calls.append((host, interval_seconds))
        return self.wait


def fetcher(
    handler: Callable[[httpx2.Request], httpx2.Response], scheduler: Any = None
) -> SafeFetcher:
    return SafeFetcher(
        scheduler or RecordingScheduler(),
        resolver=resolver,
        transport=httpx2.MockTransport(handler),
        verify_peer=False,
    )


def site(
    routes: dict[str, httpx2.Response], robots: httpx2.Response | None = None
) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/robots.txt":
            return robots or httpx2.Response(404)
        return routes.get(str(request.url), httpx2.Response(404))

    return handler


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud instance metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",
    ],
)
def test_non_public_addresses_are_rejected(address: str) -> None:
    assert not is_public_address(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "151.101.67.42", "2606:4700::6810:85e5"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_public_address(address)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "scheme"),
        ("ftp://papers.example/a.pdf", "scheme"),
        ("gopher://papers.example/", "scheme"),
        ("http://user:pw@papers.example/a.pdf", "credentials"),
        ("http://papers.example:8080/a.pdf", "port"),
        ("http://evil.example/a.pdf", "non-public"),
        ("http://metadata.example/latest/meta-data", "non-public"),
        ("http://rebind.example/a.pdf", "non-public"),  # any bad address rejects the host
        ("http://127.0.0.1/a.pdf", "non-public"),
        ("http://[::1]/a.pdf", "non-public"),
    ],
)
def test_unsafe_urls_are_rejected(url: str, reason: str) -> None:
    def literal_aware(host: str, port: int) -> list[str]:
        return [host] if host[0].isdigit() or ":" in host else resolver(host, port)

    with pytest.raises(FetchRejectedError, match=reason):
        validate_url(url, literal_aware)


def test_fetches_pdf_and_respects_crawl_delay() -> None:
    scheduler = RecordingScheduler()
    handler = site(
        {"https://papers.example/a.pdf": httpx2.Response(200, content=PDF)},
        robots=httpx2.Response(200, text="User-agent: *\nCrawl-delay: 15\nAllow: /\n"),
    )
    result = fetcher(handler, scheduler).fetch_pdf("https://papers.example/a.pdf")
    assert result.content == PDF
    assert result.final_url == "https://papers.example/a.pdf"
    assert len(result.sha256) == 64
    assert scheduler.calls == [("papers.example", 15.0)]


def test_follows_safe_redirects() -> None:
    handler = site(
        {
            "https://papers.example/a": httpx2.Response(
                302, headers={"location": "https://cdn.example/a.pdf"}
            ),
            "https://cdn.example/a.pdf": httpx2.Response(200, content=PDF),
        }
    )
    result = fetcher(handler).fetch_pdf("https://papers.example/a")
    assert result.final_url == "https://cdn.example/a.pdf"


def test_redirect_to_internal_address_is_blocked() -> None:
    handler = site(
        {
            "https://papers.example/a.pdf": httpx2.Response(
                302, headers={"location": "http://evil.example/admin"}
            )
        }
    )
    with pytest.raises(FetchRejectedError, match="non-public"):
        fetcher(handler).fetch_pdf("https://papers.example/a.pdf")


def test_redirect_loop_is_bounded() -> None:
    handler = site(
        {
            "https://papers.example/a": httpx2.Response(
                302, headers={"location": "https://papers.example/a"}
            )
        }
    )
    with pytest.raises(FetchRejectedError, match="redirects"):
        fetcher(handler).fetch_pdf("https://papers.example/a")


def test_non_pdf_content_is_rejected() -> None:
    handler = site(
        {"https://papers.example/a.pdf": httpx2.Response(200, text="<html>login</html>")}
    )
    with pytest.raises(FetchRejectedError, match="not a PDF"):
        fetcher(handler).fetch_pdf("https://papers.example/a.pdf")


def test_declared_oversize_is_rejected() -> None:
    big = httpx2.Response(200, headers={"content-length": str(MAX_PDF_BYTES + 1)}, content=PDF)
    with pytest.raises(FetchRejectedError, match="too large"):
        fetcher(site({"https://papers.example/a.pdf": big})).fetch_pdf(
            "https://papers.example/a.pdf"
        )


def test_streamed_oversize_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.documents.fetch.MAX_PDF_BYTES", 100)
    handler = site({"https://papers.example/a.pdf": httpx2.Response(200, content=PDF * 10)})
    with pytest.raises(FetchRejectedError, match="too large"):
        fetcher(handler).fetch_pdf("https://papers.example/a.pdf")


def test_robots_disallow_is_respected() -> None:
    handler = site(
        {"https://papers.example/private/a.pdf": httpx2.Response(200, content=PDF)},
        robots=httpx2.Response(200, text="User-agent: *\nDisallow: /private/\n"),
    )
    with pytest.raises(FetchRejectedError, match="robots"):
        fetcher(handler).fetch_pdf("https://papers.example/private/a.pdf")


def test_unreachable_robots_means_disallow() -> None:
    handler = site(
        {"https://papers.example/a.pdf": httpx2.Response(200, content=PDF)},
        robots=httpx2.Response(503),
    )
    with pytest.raises(FetchRejectedError, match="robots"):
        fetcher(handler).fetch_pdf("https://papers.example/a.pdf")


def test_long_politeness_wait_is_deferred_not_slept() -> None:
    handler = site({"https://papers.example/a.pdf": httpx2.Response(200, content=PDF)})
    with pytest.raises(FetchDeferredError) as info:
        fetcher(handler, RecordingScheduler(wait=120)).fetch_pdf("https://papers.example/a.pdf")
    assert info.value.wait_seconds == 120


def test_server_errors_are_temporary_failures() -> None:
    handler = site({"https://papers.example/a.pdf": httpx2.Response(503)})
    with pytest.raises(FetchFailedError):
        fetcher(handler).fetch_pdf("https://papers.example/a.pdf")


class FakeStream:
    def __init__(self, address: str) -> None:
        self.address = address

    def get_extra_info(self, name: str) -> Any:
        return (self.address, 443) if name == "server_addr" else None


def test_peer_address_is_checked_after_connecting() -> None:
    """DNS rebinding: the name validated as public, but the connection landed on
    an internal address. The body must not be read."""
    safe = SafeFetcher(RecordingScheduler(), resolver=resolver)
    response = httpx2.Response(200, extensions={"network_stream": FakeStream("10.0.0.7")})
    with pytest.raises(FetchRejectedError, match="non-public"):
        safe._check_peer(response, "papers.example")
    safe._check_peer(
        httpx2.Response(200, extensions={"network_stream": FakeStream("93.184.216.34")}),
        "papers.example",
    )


def test_postgres_scheduler_spaces_requests_across_workers(engine: Engine) -> None:
    scheduler = PostgresHostScheduler(sessionmaker(bind=engine))
    first = scheduler.reserve("arxiv.org", 15)
    second = scheduler.reserve("arxiv.org", 15)
    third = scheduler.reserve("arxiv.org", 15)
    other_host = scheduler.reserve("example.org", 15)
    assert first == 0
    assert 14 <= second <= 15
    assert 29 <= third <= 30
    assert other_host == 0
