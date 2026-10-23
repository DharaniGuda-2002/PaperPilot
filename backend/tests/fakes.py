import json
from pathlib import Path

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
        self.empty = False

    def search_works(self, params: PaperSearchParams) -> ProviderSearchResult:
        self.calls.append(params)
        if self.fail:
            raise ProviderUnavailableError("simulated outage")
        if self.empty:
            return ProviderSearchResult(total=0, hits=[])
        hits = [
            ProviderSearchHit(paper=normalize_work(work), relevance_score=work["relevance_score"])
            for work in FIXTURE["results"]
        ]
        return ProviderSearchResult(total=FIXTURE["meta"]["count"], hits=hits)
