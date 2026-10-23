import json
import logging
from pathlib import Path

from app.core.config import Settings
from app.papers.openalex import OpenAlexClient, normalize_work
from app.papers.schemas import PaperSearchParams, ProviderSearchHit, ProviderSearchResult
from app.papers.service import PaperProvider

logger = logging.getLogger(__name__)

SAMPLE_PATH = Path(__file__).parent / "fixtures" / "openalex_sample.json"


class RecordedSampleProvider:
    """Returns one real OpenAlex response recorded on 2026-10-22 (CC0) for every
    query. For automated end-to-end tests only: results do not depend on the
    question, so never enable it for real use."""

    def __init__(self) -> None:
        self._sample = json.loads(SAMPLE_PATH.read_text())

    def search_works(self, params: PaperSearchParams) -> ProviderSearchResult:
        hits = [
            ProviderSearchHit(
                paper=normalize_work(work), relevance_score=work.get("relevance_score")
            )
            for work in self._sample["results"]
        ]
        return ProviderSearchResult(total=int(self._sample["meta"]["count"]), hits=hits)

    def close(self) -> None:
        pass


def make_provider(settings: Settings) -> OpenAlexClient | RecordedSampleProvider:
    if settings.paper_provider == "fixture":
        logger.warning("PAPER_PROVIDER=fixture: search returns a recorded sample for any query")
        return RecordedSampleProvider()
    return OpenAlexClient(
        base_url=settings.openalex_base_url,
        api_key=settings.openalex_api_key,
        contact_email=settings.openalex_contact_email,
    )


_: type[PaperProvider] = RecordedSampleProvider
