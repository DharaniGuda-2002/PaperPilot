import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import evidence, health, investigations, papers, reports, system
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.http import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.logging import configure_logging, correlation_id_var
from app.core.rate_limit import SlidingWindowLimiter
from app.papers.providers import make_provider
from app.papers.service import PaperProvider

logger = logging.getLogger("app.request")

CORRELATION_HEADER = "X-Request-ID"


def create_app(
    settings: Settings | None = None, paper_provider: PaperProvider | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings)
    owned_provider = None if paper_provider else make_provider(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()
        if owned_provider:
            owned_provider.close()

    app = FastAPI(title="PaperPilot API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.create_limiter = SlidingWindowLimiter(settings.create_rate_limit_per_minute)
    app.state.search_limiter = SlidingWindowLimiter(settings.paper_search_rate_limit_per_minute)
    app.state.paper_provider = paper_provider or owned_provider

    # Added last runs first: size limit, then security headers, then CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", CORRELATION_HEADER],
        expose_headers=["Location", CORRELATION_HEADER],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Accept a caller-supplied ID only if it is a UUID; never log raw header input.
        incoming = request.headers.get(CORRELATION_HEADER, "")
        try:
            correlation_id = str(uuid.UUID(incoming))
        except ValueError:
            correlation_id = str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        logger.info(
            "request",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)

    app.include_router(health.router)
    app.include_router(investigations.router)
    app.include_router(papers.router)
    app.include_router(system.router)
    app.include_router(evidence.router)
    app.include_router(reports.router)
    return app
