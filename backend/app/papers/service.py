"""Paper search use case: serve from cache when fresh, otherwise call the
provider and persist normalized papers.

The provider call happens outside any database transaction so a slow network
never holds a connection or locks.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.papers.models import Paper, SearchCacheEntry
from app.papers.schemas import (
    NormalizedPaper,
    PaperRead,
    PaperSearchParams,
    PaperSearchResponse,
    PaperSearchResultItem,
    ProviderSearchResult,
)


class PaperProvider(Protocol):
    def search_works(self, params: PaperSearchParams) -> ProviderSearchResult: ...


class ProviderQuotaExceededError(Exception):
    """Our own daily cap on provider calls has been reached."""


PROVIDER = "openalex"


def cache_key(params: PaperSearchParams) -> str:
    canonical = json.dumps(
        {**params.model_dump(mode="json"), "q": " ".join(params.q.lower().split())},
        sort_keys=True,
    )
    return hashlib.sha256(f"{PROVIDER}:{canonical}".encode()).hexdigest()


def search_papers(
    session: Session,
    provider: PaperProvider,
    params: PaperSearchParams,
    *,
    cache_ttl: timedelta,
    daily_provider_call_cap: int,
) -> PaperSearchResponse:
    key = cache_key(params)
    cached = session.get(SearchCacheEntry, key)
    if cached and cached.fetched_at > datetime.now(UTC) - cache_ttl:
        return _response_from_cache(session, params, cached, from_cache=True)

    if _provider_calls_last_day(session) >= daily_provider_call_cap:
        raise ProviderQuotaExceededError
    session.rollback()  # end the read transaction before the network call

    result = provider.search_works(params)
    fetched_at = datetime.now(UTC)

    ids = upsert_papers(session, [hit.paper for hit in result.hits], fetched_at)
    entry_values = {
        "provider": PROVIDER,
        "request": params.model_dump(mode="json"),
        "total": result.total,
        "results": [
            {"paper_id": str(paper_id), "relevance_score": hit.relevance_score}
            for paper_id, hit in zip(ids, result.hits, strict=True)
        ],
        "fetched_at": fetched_at,
    }
    session.execute(
        insert(SearchCacheEntry)
        .values(key=key, **entry_values)
        .on_conflict_do_update(index_elements=["key"], set_=entry_values)
    )
    session.commit()
    entry = session.get(SearchCacheEntry, key, populate_existing=True)
    assert entry is not None
    return _response_from_cache(session, params, entry, from_cache=False)


def upsert_papers(
    session: Session, papers: list[NormalizedPaper], fetched_at: datetime
) -> list[uuid.UUID]:
    """Insert or refresh papers by (provider, provider_id); returns ids in input order."""
    ids: list[uuid.UUID] = []
    for paper in papers:
        values = {**paper.model_dump(), "metadata_fetched_at": fetched_at}
        updatable = {k: v for k, v in values.items() if k not in ("provider", "provider_id")}
        statement = (
            insert(Paper)
            .values(id=uuid.uuid4(), **values)
            .on_conflict_do_update(
                constraint="uq_papers_provider_provider_id",
                set_={**updatable, "updated_at": func.now()},
            )
            .returning(Paper.id)
        )
        ids.append(session.execute(statement).scalar_one())
    return ids


def get_paper(session: Session, paper_id: uuid.UUID) -> Paper | None:
    return session.get(Paper, paper_id)


def _provider_calls_last_day(session: Session) -> int:
    """Each cache row written in the last 24h stands for one provider call."""
    return (
        session.scalar(
            select(func.count())
            .select_from(SearchCacheEntry)
            .where(SearchCacheEntry.fetched_at > func.now() - timedelta(days=1))
        )
        or 0
    )


def _response_from_cache(
    session: Session, params: PaperSearchParams, entry: SearchCacheEntry, *, from_cache: bool
) -> PaperSearchResponse:
    ids = [uuid.UUID(item["paper_id"]) for item in entry.results]
    papers = {p.id: p for p in session.scalars(select(Paper).where(Paper.id.in_(ids)))}
    items = [
        PaperSearchResultItem(
            paper=PaperRead.model_validate(papers[uuid.UUID(item["paper_id"])]),
            relevance_score=item["relevance_score"],
        )
        for item in entry.results
        if uuid.UUID(item["paper_id"]) in papers
    ]
    return PaperSearchResponse(
        query=params.q,
        provider=entry.provider,
        total=entry.total,
        page=params.page,
        per_page=params.per_page,
        cached=from_cache,
        fetched_at=entry.fetched_at,
        results=items,
    )
