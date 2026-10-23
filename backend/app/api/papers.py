import logging
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_session
from app.core.rate_limit import SlidingWindowLimiter, client_address
from app.papers import service
from app.papers.openalex import ProviderUnavailableError
from app.papers.schemas import PaperRead, PaperSearchParams, PaperSearchResponse

router = APIRouter(prefix="/api/v1/papers", tags=["papers"])
logger = logging.getLogger(__name__)

SessionDep = Annotated[Session, Depends(get_session)]


def enforce_search_limit(request: Request) -> None:
    limiter: SlidingWindowLimiter = request.app.state.search_limiter
    settings: Settings = request.app.state.settings
    client_ip = client_address(request, settings.trusted_proxy_hops, settings.client_ip_header)
    if not limiter.allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many searches from this address. Try again in a minute.",
            headers={"Retry-After": "60"},
        )


@router.get("/search", dependencies=[Depends(enforce_search_limit)])
def search_papers(
    request: Request, session: SessionDep, params: Annotated[PaperSearchParams, Query()]
) -> PaperSearchResponse:
    settings: Settings = request.app.state.settings
    try:
        return service.search_papers(
            session,
            request.app.state.paper_provider,
            params,
            cache_ttl=timedelta(hours=settings.paper_search_cache_hours),
            daily_provider_call_cap=settings.daily_provider_call_cap,
        )
    except service.ProviderQuotaExceededError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Paper search has reached its daily limit. Previously searched queries still work."
            ),
            headers={"Retry-After": "3600"},
        ) from None
    except ProviderUnavailableError as exc:
        logger.warning("paper provider unavailable", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The paper search provider is unavailable right now. Try again shortly.",
            headers={"Retry-After": "60"},
        ) from None


@router.get("/{paper_id}")
def get_paper(paper_id: uuid.UUID, session: SessionDep) -> PaperRead:
    paper = service.get_paper(session, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return PaperRead.model_validate(paper)
