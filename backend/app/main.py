import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.body_limit import MULTIPART_OVERHEAD_BYTES, BodySizeLimitMiddleware
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import register_rate_limiting
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.db.session import SessionFactory
from app.modules.analysis.service import sweep_stuck_analyses
from app.modules.ingestion.service import sweep_stuck_documents

logger = logging.getLogger(__name__)


async def sweep_stuck_work(session_factory: async_sessionmaker[AsyncSession], when: str) -> None:
    """Fail documents and analyses abandoned by a restart. One failing sweep does not skip the
    other, and an error is logged by type only."""
    for sweep in (sweep_stuck_documents, sweep_stuck_analyses):
        try:
            await sweep(session_factory)
        except Exception as error:
            logger.error("%s sweep failed error_type=%s", when, type(error).__name__)


async def run_sweeper(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Sweep now and then until cancelled."""
    interval_seconds = get_settings().sweep_interval_minutes * 60
    while True:
        await asyncio.sleep(interval_seconds)
        await sweep_stuck_work(session_factory, "periodic")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Work left unfinished by a restart is failed at start, then every few minutes. A database
    # that is down at start must not stop the app: /health/ready reports it.
    await sweep_stuck_work(SessionFactory, "startup")
    sweeper = asyncio.create_task(run_sweeper(SessionFactory))
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="GapLens API",
        lifespan=lifespan,
        version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Added first, so it sits inside CORS and request id: its 413 still carries both.
    app.add_middleware(
        BodySizeLimitMiddleware,
        path="/api/v1/documents",
        max_bytes=settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_rate_limiting(app)

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
