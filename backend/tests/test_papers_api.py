import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.main import create_app
from app.papers.openalex import ProviderUnavailableError, normalize_work
from app.papers.schemas import PaperSearchParams, ProviderSearchHit, ProviderSearchResult

# Real OpenAlex response recorded 2026-10-22 (CC0), trimmed to two works.
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "openalex_search_gnn_fraud.json").read_text()
)


class FakeProvider:
    """Stands in for OpenAlex; returns the recorded works and counts calls."""

    def __init__(self) -> None:
        self.calls: list[PaperSearchParams] = []
        self.fail = False

    def search_works(self, params: PaperSearchParams) -> ProviderSearchResult:
        self.calls.append(params)
        if self.fail:
            raise ProviderUnavailableError("simulated outage")
        hits = [
            ProviderSearchHit(paper=normalize_work(work), relevance_score=work["relevance_score"])
            for work in FIXTURE["results"]
        ]
        return ProviderSearchResult(total=FIXTURE["meta"]["count"], hits=hits)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def make_client(database_url: str, provider: FakeProvider, **overrides: int) -> TestClient:
    settings = Settings(database_url=database_url, **overrides)  # type: ignore[arg-type]
    return TestClient(create_app(settings, paper_provider=provider))


@pytest.fixture
def api(migrated_database: str, engine: Engine, provider: FakeProvider) -> Iterator[TestClient]:
    with make_client(migrated_database, provider) as client:
        yield client
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE investigations, papers, paper_search_cache"))


def search(client: TestClient, **params: str | int | bool) -> dict[str, object]:
    response = client.get("/api/v1/papers/search", params={"q": "gnn fraud detection", **params})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_search_returns_and_persists_normalized_papers(api: TestClient) -> None:
    body = search(api)

    assert body["provider"] == "openalex"
    assert body["cached"] is False
    assert body["total"] == FIXTURE["meta"]["count"]
    results = body["results"]
    assert isinstance(results, list) and len(results) == 2
    first = results[0]["paper"]
    assert first["provider_id"] == "W3022945404"
    assert first["full_text_availability"] == "pdf_available"
    assert results[0]["relevance_score"] == FIXTURE["results"][0]["relevance_score"]

    detail = api.get(f"/api/v1/papers/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == first["title"]


def test_repeated_search_is_served_from_cache(api: TestClient, provider: FakeProvider) -> None:
    first = search(api)
    again = search(api, q="  GNN   fraud detection ")  # same query after normalization

    assert again["cached"] is True
    assert len(provider.calls) == 1
    assert again["results"] == first["results"]


def test_different_filters_call_the_provider_again(api: TestClient, provider: FakeProvider) -> None:
    search(api)
    search(api, open_access_only=True)
    assert len(provider.calls) == 2
    assert provider.calls[1].open_access_only is True


def test_refreshing_results_does_not_duplicate_papers(
    api: TestClient, provider: FakeProvider, engine: Engine
) -> None:
    search(api)
    search(api, sort="citations")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM papers")) == 2


@pytest.mark.parametrize(
    "params",
    [{"q": "ab"}, {"q": "x" * 201}, {"from_year": 2024, "to_year": 2020}, {"per_page": 26}],
    ids=["short-query", "long-query", "inverted-years", "page-too-big"],
)
def test_search_rejects_invalid_params(api: TestClient, params: dict[str, str | int]) -> None:
    response = api.get("/api/v1/papers/search", params={"q": "gnn fraud", **params})
    assert response.status_code == 422


def test_provider_outage_returns_503(api: TestClient, provider: FakeProvider) -> None:
    provider.fail = True
    response = api.get("/api/v1/papers/search", params={"q": "gnn fraud"})
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_daily_provider_cap_blocks_new_searches_but_not_cached_ones(
    migrated_database: str, engine: Engine, provider: FakeProvider
) -> None:
    try:
        with make_client(migrated_database, provider, daily_provider_call_cap=1) as client:
            search(client)
            blocked = client.get("/api/v1/papers/search", params={"q": "a different question"})
            assert blocked.status_code == 503
            assert "daily limit" in blocked.json()["detail"]
            assert search(client)["cached"] is True
            assert len(provider.calls) == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE investigations, papers, paper_search_cache"))


def test_search_is_rate_limited_per_client(
    migrated_database: str, engine: Engine, provider: FakeProvider
) -> None:
    try:
        with make_client(
            migrated_database, provider, paper_search_rate_limit_per_minute=2
        ) as client:
            codes = [
                client.get("/api/v1/papers/search", params={"q": "gnn fraud"}).status_code
                for _ in range(3)
            ]
            assert codes == [200, 200, 429]
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE investigations, papers, paper_search_cache"))


def test_unknown_paper_returns_404(api: TestClient) -> None:
    assert api.get(f"/api/v1/papers/{uuid.uuid4()}").status_code == 404
