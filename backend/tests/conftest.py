import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.core.rate_limit import email_failures, limiter
from app.main import app

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limits() -> Iterator[None]:
    """Rate limit counters live in memory, so one test's requests must not count in the next."""
    limiter.reset()
    email_failures.reset()
    yield
    limiter.reset()
    email_failures.reset()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def empty_database_url() -> AsyncIterator[str]:
    """A brand new database that only this test uses, so the dev database is never touched."""
    admin_url = make_url(get_settings().database_url)
    name = f"gaplens_test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield admin_url.set(database=name).render_as_string(hide_password=False)
    finally:
        async with admin_engine.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin_engine.dispose()


@pytest.fixture
def alembic_config(empty_database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", empty_database_url)
    # Keeps Alembic from reconfiguring logging, which would disturb pytest's log capture.
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture
async def engine(empty_database_url: str) -> AsyncIterator[AsyncEngine]:
    test_engine = create_async_engine(empty_database_url)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def migrated_engine(alembic_config: Config, engine: AsyncEngine) -> AsyncEngine:
    """An engine on a fresh database that already has every migration applied."""
    # Alembic's async env.py starts its own event loop, so it must run outside ours.
    await asyncio.to_thread(command.upgrade, alembic_config, "head")
    return engine
