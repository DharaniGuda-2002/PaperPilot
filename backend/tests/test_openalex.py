"""OpenAlex client tests. The fixture is a real OpenAlex response recorded on
2026-10-22 (OpenAlex data is CC0), trimmed to two works."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.papers.openalex import (
    OpenAlexClient,
    ProviderUnavailableError,
    normalize_work,
    reconstruct_abstract,
)
from app.papers.schemas import PaperSearchParams, SearchSort

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "openalex_search_gnn_fraud.json").read_text()
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr("app.papers.openalex.time.sleep", sleeps.append)
    return sleeps


def client_with(handler: Any) -> OpenAlexClient:
    return OpenAlexClient(transport=httpx2.MockTransport(handler), min_interval_seconds=0)


def test_normalize_work_maps_recorded_response() -> None:
    paper = normalize_work(FIXTURE["results"][0])

    assert paper.provider == "openalex"
    assert paper.provider_id == "W3022945404"
    assert paper.doi == "10.1145/3397271.3401253"
    assert paper.title.startswith("Alleviating the Inconsistency Problem")
    assert paper.authors[:2] == ["Zhiwei Liu", "Yingtong Dou"]
    assert paper.publication_year == 2020
    assert paper.venue is not None and "SIGIR" in paper.venue
    assert paper.is_open_access is True
    assert paper.pdf_url == "https://arxiv.org/pdf/2005.00625"
    assert paper.abstract is not None and len(paper.abstract.split()) > 50


def test_normalize_tolerates_missing_fields() -> None:
    paper = normalize_work({"id": "https://openalex.org/W1", "display_name": "Minimal"})
    assert paper.doi is None
    assert paper.authors == []
    assert paper.is_open_access is False
    assert paper.abstract is None


def test_normalize_drops_non_http_links() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "Untrusted links",
        "best_oa_location": {"pdf_url": "javascript:alert(1)", "landing_page_url": "ftp://x"},
    }
    paper = normalize_work(work)
    assert paper.pdf_url is None
    assert paper.landing_page_url is None


def test_reconstruct_abstract_orders_words_by_position() -> None:
    assert reconstruct_abstract({"world": [1], "hello": [0], "again": [3], "hello,": [2]}) == (
        "hello world hello, again"
    )
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_search_sends_expected_query() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=FIXTURE)

    params = PaperSearchParams(
        q="graph neural network fraud",
        from_year=2019,
        open_access_only=True,
        sort=SearchSort.CITATIONS,
        per_page=2,
    )
    result = client_with(handler).search_works(params)

    query = seen[0].url.params
    assert seen[0].url.path == "/works"
    assert query["search"] == "graph neural network fraud"
    assert query["filter"] == "publication_year:2019-,open_access.is_oa:true"
    assert query["sort"] == "cited_by_count:desc"
    assert query["per_page"] == "2"
    assert "abstract_inverted_index" in query["select"]
    assert result.total == FIXTURE["meta"]["count"]
    assert len(result.hits) == 2
    assert result.hits[0].relevance_score == FIXTURE["results"][0]["relevance_score"]


def test_api_key_sent_as_bearer_header() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"meta": {"count": 0}, "results": []})

    client = OpenAlexClient(
        api_key="test-key", transport=httpx2.MockTransport(handler), min_interval_seconds=0
    )
    client.search_works(PaperSearchParams(q="anything"))
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert "api_key" not in seen[0].url.params  # never put the key in URLs or logs


def test_retries_short_rate_limit_then_succeeds(no_sleep: list[float]) -> None:
    responses = iter(
        [
            httpx2.Response(429, headers={"Retry-After": "1"}),
            httpx2.Response(200, json=FIXTURE),
        ]
    )
    result = client_with(lambda _: next(responses)).search_works(PaperSearchParams(q="gnn"))
    assert len(result.hits) == 2
    assert no_sleep == [1.0]


def test_exhausted_daily_budget_fails_fast(no_sleep: list[float]) -> None:
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429, headers={"Retry-After": "72000"})

    with pytest.raises(ProviderUnavailableError, match="budget"):
        client_with(handler).search_works(PaperSearchParams(q="gnn"))
    assert calls == 1
    assert no_sleep == []


def test_server_errors_retry_with_bounded_backoff(no_sleep: list[float]) -> None:
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503)

    with pytest.raises(ProviderUnavailableError):
        client_with(handler).search_works(PaperSearchParams(q="gnn"))
    assert calls == 3
    assert no_sleep == [0.5, 1.0]


def test_client_errors_are_not_retried() -> None:
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(400)

    with pytest.raises(ProviderUnavailableError, match="rejected"):
        client_with(handler).search_works(PaperSearchParams(q="gnn"))
    assert calls == 1


def test_network_errors_become_provider_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom", request=request)

    with pytest.raises(ProviderUnavailableError, match="reached"):
        client_with(handler).search_works(PaperSearchParams(q="gnn"))
