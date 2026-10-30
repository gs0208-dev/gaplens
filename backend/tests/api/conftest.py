from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.session import get_session
from app.main import app
from tests.api.helpers import SAMPLE_PHRASE, Account, insert_user


@pytest.fixture
async def api_client(migrated_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """HTTP client whose requests run against a fresh, fully migrated database."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def account(migrated_engine: AsyncEngine) -> Account:
    return await insert_user(migrated_engine, "ana@example.com", SAMPLE_PHRASE)
