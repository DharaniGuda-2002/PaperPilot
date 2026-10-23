import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class SearchSort(StrEnum):
    RELEVANCE = "relevance"
    CITATIONS = "citations"
    NEWEST = "newest"


class FullTextAvailability(StrEnum):
    PDF_AVAILABLE = "pdf_available"  # provider lists an open-access PDF URL
    OPEN_ACCESS = "open_access"  # open access, but no direct PDF URL listed
    NOT_OPEN_ACCESS = "not_open_access"


class PaperSearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    q: str = Field(min_length=3, max_length=200)
    from_year: int | None = Field(default=None, ge=1900, le=2100)
    to_year: int | None = Field(default=None, ge=1900, le=2100)
    open_access_only: bool = False
    sort: SearchSort = SearchSort.RELEVANCE
    page: int = Field(default=1, ge=1, le=50)
    per_page: int = Field(default=10, ge=1, le=25)

    @model_validator(mode="after")
    def check_year_range(self) -> "PaperSearchParams":
        if self.from_year and self.to_year and self.from_year > self.to_year:
            raise ValueError("from_year must not be after to_year")
        return self


class NormalizedPaper(BaseModel):
    """Provider-independent paper metadata, before persistence."""

    provider: str
    provider_id: str
    doi: str | None
    title: str
    authors: list[str]
    publication_year: int | None
    venue: str | None
    work_type: str | None
    abstract: str | None
    cited_by_count: int | None
    is_open_access: bool
    oa_status: str | None
    pdf_url: str | None
    landing_page_url: str | None
    license: str | None


class ProviderSearchHit(BaseModel):
    paper: NormalizedPaper
    relevance_score: float | None


class ProviderSearchResult(BaseModel):
    total: int
    hits: list[ProviderSearchHit]


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    provider_id: str
    doi: str | None
    title: str
    authors: list[str]
    publication_year: int | None
    venue: str | None
    work_type: str | None
    abstract: str | None
    cited_by_count: int | None
    is_open_access: bool
    oa_status: str | None
    pdf_url: str | None
    landing_page_url: str | None
    license: str | None
    metadata_fetched_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def full_text_availability(self) -> FullTextAvailability:
        if self.pdf_url:
            return FullTextAvailability.PDF_AVAILABLE
        if self.is_open_access:
            return FullTextAvailability.OPEN_ACCESS
        return FullTextAvailability.NOT_OPEN_ACCESS


class PaperSearchResultItem(BaseModel):
    paper: PaperRead
    relevance_score: float | None


class PaperSearchResponse(BaseModel):
    query: str
    provider: str
    total: int
    page: int
    per_page: int
    cached: bool
    fetched_at: datetime
    results: list[PaperSearchResultItem]
