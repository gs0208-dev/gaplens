from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import get_llm_client
from app.db.session import get_session, get_session_factory
from app.main import app
from app.modules.ingestion.embedder import get_embedder
from tests.api.helpers import SAMPLE_PHRASE, Account, auth_headers, insert_user
from tests.fakes.embedder import FakeEmbedder
from tests.fakes.llm import FakeLLM


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
async def api_client(
    migrated_engine: AsyncEngine, fake_embedder: FakeEmbedder, fake_llm: FakeLLM
) -> AsyncIterator[AsyncClient]:
    """HTTP client whose requests run against a fresh, fully migrated database, with a fake
    embedding model. Background processing uses the same database and the same fake."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def account(migrated_engine: AsyncEngine) -> Account:
    return await insert_user(migrated_engine, "ana@example.com", SAMPLE_PHRASE)


@pytest.fixture
async def headers(api_client: AsyncClient, account: Account) -> dict[str, str]:
    return await auth_headers(api_client, account)


@pytest.fixture
async def other_account(migrated_engine: AsyncEngine) -> Account:
    return await insert_user(migrated_engine, "bob@example.com", SAMPLE_PHRASE)
