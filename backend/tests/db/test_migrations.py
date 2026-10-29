import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
AUTH_TABLES = {"users", "refresh_tokens", "audit_events"}
DOCUMENTED_INDEXES = {
    "users_email_lower_uidx",
    "refresh_tokens_token_hash_uidx",
    "refresh_tokens_user_id_idx",
    "refresh_tokens_family_id_idx",
    "refresh_tokens_expires_at_idx",
    "audit_events_actor_created_idx",
    "audit_events_resource_idx",
}


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


async def upgrade(config: Config, revision: str = "head") -> None:
    # Alembic's async env.py starts its own event loop, so it must run outside ours.
    await asyncio.to_thread(command.upgrade, config, revision)


async def downgrade(config: Config, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, config, revision)


async def table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return {row[0] for row in result}


async def index_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        )
        return {row[0] for row in result}


async def test_upgrade_from_empty_creates_the_auth_tables(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    assert await table_names(engine) == AUTH_TABLES | {"alembic_version"}


async def test_upgrade_creates_the_documented_indexes(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    indexes = await index_names(engine)

    assert indexes >= DOCUMENTED_INDEXES


async def test_email_is_unique_ignoring_case(alembic_config: Config, engine: AsyncEngine) -> None:
    await upgrade(alembic_config)
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (email, password_hash) VALUES ('a@example.com', 'x')")
        )

    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO users (email, password_hash) VALUES ('A@Example.com', 'x')")
            )


async def test_role_must_be_user_or_admin(alembic_config: Config, engine: AsyncEngine) -> None:
    await upgrade(alembic_config)

    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) "
                    "VALUES ('a@example.com', 'x', 'owner')"
                )
            )


async def test_downgrade_removes_the_tables_and_upgrade_restores_them(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    await downgrade(alembic_config, "base")
    assert await table_names(engine) == {"alembic_version"}

    await upgrade(alembic_config)
    assert await table_names(engine) == AUTH_TABLES | {"alembic_version"}
