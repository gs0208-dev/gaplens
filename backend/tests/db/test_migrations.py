import asyncio
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.documents import models as document_models

AUTH_TABLES = {"users", "refresh_tokens", "audit_events"}
DOCUMENT_TABLES = {"documents", "document_chunks"}
DOCUMENTED_INDEXES = {
    "users_email_lower_uidx",
    "refresh_tokens_token_hash_uidx",
    "refresh_tokens_user_id_idx",
    "refresh_tokens_family_id_idx",
    "refresh_tokens_expires_at_idx",
    "audit_events_actor_created_idx",
    "audit_events_resource_idx",
    "documents_owner_sha256_uidx",
    "documents_owner_created_idx",
    "document_chunks_doc_index_uidx",
}


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


async def test_upgrade_from_empty_creates_the_auth_and_document_tables(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    assert await table_names(engine) == AUTH_TABLES | DOCUMENT_TABLES | {"alembic_version"}


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
    assert await table_names(engine) == AUTH_TABLES | DOCUMENT_TABLES | {"alembic_version"}


async def test_downgrade_one_step_removes_only_the_document_tables(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    await downgrade(alembic_config, "0001")

    assert await table_names(engine) == AUTH_TABLES | {"alembic_version"}


async def test_models_and_migrations_describe_the_same_schema(
    migrated_engine: AsyncEngine,
) -> None:
    def differences(connection: Connection) -> list[object]:
        context = MigrationContext.configure(connection)
        return compare_metadata(context, document_models.Base.metadata)

    async with migrated_engine.connect() as connection:
        assert await connection.run_sync(differences) == []


async def add_user(engine: AsyncEngine, email: str = "a@example.com") -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:email, 'x') RETURNING id"),
            {"email": email},
        )
        return result.scalar_one()


async def add_document(
    engine: AsyncEngine,
    owner_id: uuid.UUID,
    sha256: str = "a" * 64,
    title: str = "Onboarding SOP",
    size_bytes: int = 1000,
    status: str = "uploaded",
) -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO documents (owner_id, title, filename, mime_type, size_bytes, sha256, "
                "status) VALUES (:owner_id, :title, 'sop.pdf', 'application/pdf', :size_bytes, "
                ":sha256, :status) RETURNING id"
            ),
            {
                "owner_id": owner_id,
                "title": title,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "status": status,
            },
        )
        return result.scalar_one()


async def add_chunk(
    engine: AsyncEngine,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    chunk_index: int = 0,
    dimensions: int = 384,
) -> None:
    embedding = "[" + ",".join(["0.1"] * dimensions) + "]"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO document_chunks (document_id, owner_id, chunk_index, content, "
                "token_count, embedding) VALUES (:document_id, :owner_id, :chunk_index, "
                "'Clause text', 3, CAST(:embedding AS vector))"
            ),
            {
                "document_id": document_id,
                "owner_id": owner_id,
                "chunk_index": chunk_index,
                "embedding": embedding,
            },
        )


async def count_rows(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        result = await connection.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        return result.scalar_one()


async def test_new_document_gets_the_documented_defaults(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    await add_document(migrated_engine, owner_id)

    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(text("SELECT status, chunk_count, deleted_at FROM documents"))
        ).one()

    assert (row.status, row.chunk_count, row.deleted_at) == ("uploaded", 0, None)


async def test_same_file_twice_for_one_owner_is_rejected(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    await add_document(migrated_engine, owner_id)

    with pytest.raises(IntegrityError):
        await add_document(migrated_engine, owner_id)


async def test_same_file_for_two_owners_is_allowed(migrated_engine: AsyncEngine) -> None:
    first = await add_user(migrated_engine, "a@example.com")
    second = await add_user(migrated_engine, "b@example.com")

    await add_document(migrated_engine, first)
    await add_document(migrated_engine, second)

    assert await count_rows(migrated_engine, "documents") == 2


async def test_same_file_is_allowed_again_after_the_first_is_soft_deleted(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("UPDATE documents SET deleted_at = now() WHERE id = :id"), {"id": document_id}
        )

    await add_document(migrated_engine, owner_id)

    assert await count_rows(migrated_engine, "documents") == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "archived"},
        {"size_bytes": 0},
        {"title": ""},
        {"title": "x" * 201},
    ],
)
async def test_document_check_constraints_reject_bad_values(
    migrated_engine: AsyncEngine, overrides: dict[str, object]
) -> None:
    owner_id = await add_user(migrated_engine)

    with pytest.raises(IntegrityError):
        await add_document(migrated_engine, owner_id, **overrides)  # type: ignore[arg-type]


async def test_chunk_stores_a_384_dimension_vector(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    await add_chunk(migrated_engine, document_id, owner_id)

    assert await count_rows(migrated_engine, "document_chunks") == 1


async def test_chunk_rejects_a_vector_of_the_wrong_size(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    with pytest.raises(DBAPIError):
        await add_chunk(migrated_engine, document_id, owner_id, dimensions=383)


async def test_chunk_index_is_unique_within_a_document(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_chunk(migrated_engine, document_id, owner_id, chunk_index=0)

    with pytest.raises(IntegrityError):
        await add_chunk(migrated_engine, document_id, owner_id, chunk_index=0)


async def test_chunk_index_cannot_be_negative(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    with pytest.raises(IntegrityError):
        await add_chunk(migrated_engine, document_id, owner_id, chunk_index=-1)


async def test_deleting_a_document_deletes_its_chunks(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_chunk(migrated_engine, document_id, owner_id)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    assert await count_rows(migrated_engine, "document_chunks") == 0


async def test_deleting_a_user_deletes_their_documents_and_chunks(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_chunk(migrated_engine, document_id, owner_id)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})

    assert await count_rows(migrated_engine, "documents") == 0
    assert await count_rows(migrated_engine, "document_chunks") == 0
