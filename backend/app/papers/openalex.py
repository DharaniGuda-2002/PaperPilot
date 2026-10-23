"""OpenAlex works-search client and response normalization.

OpenAlex bills by usage: requests without a key share a small daily budget per
IP; a free key has its own budget. Per-second limits return 429 with a short
Retry-After (safe to retry); an exhausted daily budget also returns 429 with a
long Retry-After (not worth retrying in-request).
"""

import logging
import re
import threading
import time
from typing import Any

import httpx2

from app.papers.schemas import (
    NormalizedPaper,
    PaperSearchParams,
    ProviderSearchHit,
    ProviderSearchResult,
    SearchSort,
)

logger = logging.getLogger(__name__)

PROVIDER = "openalex"
MAX_AUTHORS = 25

_SORT = {
    SearchSort.RELEVANCE: "relevance_score:desc",
    SearchSort.CITATIONS: "cited_by_count:desc",
    SearchSort.NEWEST: "publication_date:desc",
}

_SELECT = ",".join(
    [
        "id",
        "doi",
        "display_name",
        "publication_year",
        "type",
        "authorships",
        "primary_location",
        "best_oa_location",
        "open_access",
        "cited_by_count",
        "abstract_inverted_index",
        "relevance_score",
    ]
)


class ProviderUnavailableError(Exception):
    """The provider cannot serve this request now (quota, outage, timeout)."""


class OpenAlexClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.openalex.org",
        api_key: str | None = None,
        contact_email: str | None = None,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        min_interval_seconds: float = 0.2,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        headers = {"User-Agent": "PaperPilot/0.1 (research investigation demo)"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._contact_email = contact_email
        self._max_attempts = max_attempts
        self._min_interval = min_interval_seconds
        self._last_request = 0.0
        self._throttle_lock = threading.Lock()
        self._client = httpx2.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def search_works(self, params: PaperSearchParams) -> ProviderSearchResult:
        query: dict[str, str | int] = {
            "search": search_text(params.q),
            "page": params.page,
            "per_page": params.per_page,
            "sort": _SORT[params.sort],
            "select": _SELECT,
        }
        filters = _filters(params)
        if filters:
            query["filter"] = filters
        if self._contact_email:
            query["mailto"] = self._contact_email

        body = self._get_json("/works", query)
        hits = [
            ProviderSearchHit(
                paper=normalize_work(work), relevance_score=work.get("relevance_score")
            )
            for work in body.get("results", [])
            if work.get("id") and work.get("display_name")
        ]
        return ProviderSearchResult(total=int(body.get("meta", {}).get("count", 0)), hits=hits)

    def _get_json(self, path: str, query: dict[str, str | int]) -> dict[str, Any]:
        for attempt in range(1, self._max_attempts + 1):
            self._throttle()
            try:
                response = self._client.get(path, params=query)
            except httpx2.TransportError as exc:
                logger.warning(
                    "openalex transport error", extra={"attempt": attempt, "error": str(exc)}
                )
                if attempt == self._max_attempts:
                    raise ProviderUnavailableError("OpenAlex could not be reached") from exc
                self._backoff(attempt)
                continue

            if response.status_code == 200:
                body: dict[str, Any] = response.json()
                return body

            retry_after = _retry_after_seconds(response)
            logger.warning(
                "openalex error response",
                extra={
                    "attempt": attempt,
                    "status": response.status_code,
                    "retry_after": retry_after,
                },
            )
            if response.status_code == 429 and retry_after is not None and retry_after > 5:
                raise ProviderUnavailableError("OpenAlex daily usage budget is exhausted")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_attempts:
                    raise ProviderUnavailableError(f"OpenAlex returned {response.status_code}")
                self._backoff(attempt, retry_after)
                continue
            # Other 4xx means our request is wrong; retrying will not help.
            raise ProviderUnavailableError(
                f"OpenAlex rejected the request ({response.status_code})"
            )
        raise AssertionError("unreachable")

    def _throttle(self) -> None:
        """Space requests at least min_interval apart within this process."""
        with self._throttle_lock:
            wait = self._last_request + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    @staticmethod
    def _backoff(attempt: int, retry_after: float | None = None) -> None:
        time.sleep(retry_after if retry_after is not None else 0.5 * 2 ** (attempt - 1))


_WILDCARDS = re.compile(r"[*?]")
_OPERATORS = re.compile(r"\b(AND|OR|NOT)\b")


def search_text(query: str) -> str:
    """Plain-text search for OpenAlex. `*` and `?` are wildcards there (and are
    rejected with stemmed search), and uppercase AND/OR/NOT are boolean
    operators; user text should mean neither."""
    cleaned = _WILDCARDS.sub(" ", query)
    cleaned = _OPERATORS.sub(lambda m: m.group(0).lower(), cleaned)
    return " ".join(cleaned.split())


def _filters(params: PaperSearchParams) -> str:
    parts = []
    if params.from_year or params.to_year:
        parts.append(f"publication_year:{params.from_year or ''}-{params.to_year or ''}")
    if params.open_access_only:
        parts.append("open_access.is_oa:true")
    return ",".join(parts)


def _retry_after_seconds(response: httpx2.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def normalize_work(work: dict[str, Any]) -> NormalizedPaper:
    """Map an OpenAlex work to provider-independent metadata. Missing fields stay None."""
    open_access = work.get("open_access") or {}
    best_oa = work.get("best_oa_location") or {}
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    authors = [
        name
        for authorship in work.get("authorships") or []
        if (name := (authorship.get("author") or {}).get("display_name"))
    ]
    return NormalizedPaper(
        provider=PROVIDER,
        provider_id=_strip_prefix(str(work["id"]), "https://openalex.org/"),
        doi=_normalize_doi(work.get("doi")),
        title=str(work["display_name"]).strip(),
        authors=authors[:MAX_AUTHORS],
        publication_year=work.get("publication_year"),
        venue=source.get("display_name") or best_oa.get("raw_source_name"),
        work_type=work.get("type"),
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        cited_by_count=work.get("cited_by_count"),
        is_open_access=bool(open_access.get("is_oa")),
        oa_status=open_access.get("oa_status"),
        pdf_url=_http_url(best_oa.get("pdf_url")),
        landing_page_url=_http_url(
            best_oa.get("landing_page_url") or primary.get("landing_page_url")
        ),
        license=best_oa.get("license") or primary.get("license"),
    )


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the word order."""
    if not inverted_index:
        return None
    positions = [(pos, word) for word, places in inverted_index.items() for pos in places]
    return " ".join(word for _, word in sorted(positions)) or None


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        value = _strip_prefix(value, prefix)
    return value or None


def _http_url(url: str | None) -> str | None:
    """Keep only http(s) URLs; provider data is untrusted and is rendered as links."""
    if url and url.lower().startswith(("https://", "http://")):
        return url
    return None


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix) :] if value.startswith(prefix) else value
