import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.main as main_module
from app.core.config import get_settings
from app.main import app
from app.modules.ingestion import repository
from app.modules.ingestion.errors import STUCK_MESSAGE
from app.modules.ingestion.service import sweep_stuck_documents

OLD = timedelta(hours=1)
RECENT = timedelta(minutes=1)


async def add_owner(engine: AsyncEngine) -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('o@example.com', 'x') RETURNING id"
            )
        )
        return result.scalar_one()


async def add_document(
    engine: AsyncEngine,
    owner_id: uuid.UUID,
    *,
    status: str,
    age: timedelta,
    deleted: bool = False,
    error_message: str | None = None,
) -> uuid.UUID:
    when = datetime.now(UTC) - age
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO documents (owner_id, title, filename, mime_type, size_bytes, sha256, "
                "status, error_message, updated_at, deleted_at) VALUES (:owner, 't', 'f.txt', "
                "'text/plain', 10, :sha, :status, :message, CAST(:when AS timestamptz), "
                "CASE WHEN :deleted THEN CAST(:when AS timestamptz) END) RETURNING id"
            ),
            {
                "owner": owner_id,
                "sha": uuid.uuid4().hex + uuid.uuid4().hex,
                "status": status,
                "message": error_message,
                "when": when,
                "deleted": deleted,
            },
        )
        return result.scalar_one()


async def state_of(engine: AsyncEngine, document_id: uuid.UUID) -> Any:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT status, error_message, updated_at FROM documents WHERE id = :id"),
            {"id": document_id},
        )
        return result.one()


async def test_old_uploaded_and_processing_documents_are_failed(
    migrated_engine: AsyncEngine,
) -> None:
    owner = await add_owner(migrated_engine)
    uploaded = await add_document(migrated_engine, owner, status="uploaded", age=OLD)
    processing = await add_document(migrated_engine, owner, status="processing", age=OLD)
    before = datetime.now(UTC) - OLD

    count = await sweep_stuck_documents(async_sessionmaker(migrated_engine))

    assert count == 2
    for document_id in (uploaded, processing):
        state = await state_of(migrated_engine, document_id)
        assert (state.status, state.error_message) == ("failed", STUCK_MESSAGE)
        assert state.updated_at > before + timedelta(minutes=30)


@pytest.mark.parametrize(
    ("status", "age", "deleted"),
    [
        ("uploaded", RECENT, False),
        ("processing", RECENT, False),
        ("ready", OLD, False),
        ("failed", OLD, False),
        ("uploaded", OLD, True),
    ],
)
async def test_other_documents_are_left_alone(
    migrated_engine: AsyncEngine, status: str, age: timedelta, deleted: bool
) -> None:
    owner = await add_owner(migrated_engine)
    document_id = await add_document(
        migrated_engine, owner, status=status, age=age, deleted=deleted, error_message=None
    )

    count = await sweep_stuck_documents(async_sessionmaker(migrated_engine))

    state = await state_of(migrated_engine, document_id)
    assert (count, state.status, state.error_message) == (0, status, None)


async def test_a_second_sweep_has_nothing_left_to_do(migrated_engine: AsyncEngine) -> None:
    owner = await add_owner(migrated_engine)
    await add_document(migrated_engine, owner, status="processing", age=OLD)
    session_factory = async_sessionmaker(migrated_engine)

    first = await sweep_stuck_documents(session_factory)
    second = await sweep_stuck_documents(session_factory)

    assert (first, second) == (1, 0)


async def test_claiming_a_document_moves_its_updated_at(migrated_engine: AsyncEngine) -> None:
    owner = await add_owner(migrated_engine)
    document_id = await add_document(migrated_engine, owner, status="uploaded", age=OLD)
    session_factory = async_sessionmaker(migrated_engine)

    async with session_factory() as session:
        claimed = await repository.claim_document(session, document_id=document_id, owner_id=owner)
        await session.commit()

    state = await state_of(migrated_engine, document_id)
    assert claimed is True
    assert state.status == "processing"
    assert state.updated_at > datetime.now(UTC) - timedelta(minutes=5)


async def test_the_app_sweeps_at_start_and_again_while_running_and_stops_cleanly(
    migrated_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await add_owner(migrated_engine)
    left_by_restart = await add_document(migrated_engine, owner, status="processing", age=OLD)
    session_factory = async_sessionmaker(migrated_engine)
    monkeypatch.setattr(main_module, "SessionFactory", session_factory)
    monkeypatch.setattr(get_settings(), "sweep_interval_minutes", 0)

    async with app.router.lifespan_context(app):
        assert (await state_of(migrated_engine, left_by_restart)).status == "failed"
        abandoned_later = await add_document(migrated_engine, owner, status="uploaded", age=OLD)
        for _ in range(50):
            await asyncio.sleep(0.05)
            if (await state_of(migrated_engine, abandoned_later)).status == "failed":
                break
        assert (await state_of(migrated_engine, abandoned_later)).status == "failed"

    leftover = [task for task in asyncio.all_tasks() if "run_sweeper" in repr(task)]
    assert leftover == []


async def test_a_database_error_at_start_does_not_stop_the_app(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing_sweep(*args: Any, **kwargs: Any) -> int:
        raise ConnectionError("database is down")

    monkeypatch.setattr(main_module, "sweep_stuck_documents", failing_sweep)
    monkeypatch.setattr(get_settings(), "sweep_interval_minutes", 60)

    async with app.router.lifespan_context(app):
        pass

    assert "startup sweep failed error_type=ConnectionError" in caplog.text
    assert "database is down" not in caplog.text
