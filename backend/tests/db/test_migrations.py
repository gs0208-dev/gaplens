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
CHAT_TABLES = {"chat_threads", "chat_messages", "llm_calls"}
ANALYSIS_TABLES = {"analyses", "findings", "finding_citations"}
ALL_TABLES = AUTH_TABLES | DOCUMENT_TABLES | CHAT_TABLES | ANALYSIS_TABLES | {"alembic_version"}
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
    "chat_threads_document_updated_idx",
    "chat_messages_thread_created_idx",
    "llm_calls_owner_created_idx",
    "llm_calls_created_idx",
    "analyses_document_created_idx",
    "analyses_one_active_per_document_uidx",
    "findings_analysis_position_uidx",
    "finding_citations_finding_id_idx",
    "finding_citations_chunk_id_idx",
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

    assert await table_names(engine) == ALL_TABLES


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
    assert await table_names(engine) == ALL_TABLES


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


async def test_downgrade_to_0002_removes_only_the_chat_tables(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    await downgrade(alembic_config, "0002")

    assert await table_names(engine) == AUTH_TABLES | DOCUMENT_TABLES | {"alembic_version"}


async def add_thread(engine: AsyncEngine, document_id: uuid.UUID, owner_id: uuid.UUID) -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO chat_threads (document_id, owner_id) "
                "VALUES (:document_id, :owner_id) RETURNING id"
            ),
            {"document_id": document_id, "owner_id": owner_id},
        )
        return result.scalar_one()


async def add_message(engine: AsyncEngine, thread_id: uuid.UUID, role: str = "user") -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO chat_messages (thread_id, role, content) VALUES (:t, :role, 'hello')"
            ),
            {"t": thread_id, "role": role},
        )


async def add_llm_call(
    engine: AsyncEngine,
    owner_id: uuid.UUID | None,
    *,
    purpose: str = "chat",
    status: str = "ok",
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO llm_calls (owner_id, purpose, model, prompt_version, status) "
                "VALUES (:owner_id, :purpose, 'm', 'chat_answer.v1', :status)"
            ),
            {"owner_id": owner_id, "purpose": purpose, "status": status},
        )


async def test_a_message_needs_a_known_role_and_defaults_to_no_citations(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    thread_id = await add_thread(
        migrated_engine, await add_document(migrated_engine, owner_id), owner_id
    )

    await add_message(migrated_engine, thread_id, "assistant")
    with pytest.raises(IntegrityError):
        await add_message(migrated_engine, thread_id, "system")

    async with migrated_engine.connect() as connection:
        citations = (
            await connection.execute(text("SELECT citations FROM chat_messages"))
        ).scalar_one()
    assert citations == []


@pytest.mark.parametrize(("purpose", "status"), [("shopping", "ok"), ("chat", "done")])
async def test_llm_calls_only_accept_known_purposes_and_statuses(
    migrated_engine: AsyncEngine, purpose: str, status: str
) -> None:
    owner_id = await add_user(migrated_engine)

    with pytest.raises(IntegrityError):
        await add_llm_call(migrated_engine, owner_id, purpose=purpose, status=status)


@pytest.mark.parametrize("status", ["ok", "error", "timeout", "invalid_output"])
async def test_llm_calls_accept_every_documented_status(
    migrated_engine: AsyncEngine, status: str
) -> None:
    owner_id = await add_user(migrated_engine)

    await add_llm_call(migrated_engine, owner_id, status=status)

    assert await count_rows(migrated_engine, "llm_calls") == 1


async def test_deleting_a_document_deletes_its_threads_and_messages(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_message(migrated_engine, await add_thread(migrated_engine, document_id, owner_id))

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    assert await count_rows(migrated_engine, "chat_threads") == 0
    assert await count_rows(migrated_engine, "chat_messages") == 0


async def test_deleting_a_user_keeps_their_llm_calls_but_forgets_who_made_them(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    await add_llm_call(migrated_engine, owner_id)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})

    async with migrated_engine.connect() as connection:
        remaining = (await connection.execute(text("SELECT owner_id FROM llm_calls"))).all()
    assert [row.owner_id for row in remaining] == [None]


async def test_downgrade_to_0003_removes_only_the_analysis_tables(
    alembic_config: Config, engine: AsyncEngine
) -> None:
    await upgrade(alembic_config)

    await downgrade(alembic_config, "0003")

    assert await table_names(engine) == (
        AUTH_TABLES | DOCUMENT_TABLES | CHAT_TABLES | {"alembic_version"}
    )


async def add_analysis(
    engine: AsyncEngine,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    status: str | None = None,
) -> uuid.UUID:
    # Leaving the status out is how the default is tested, so it is only bound when given.
    columns = "document_id, owner_id, prompt_version, model" + (", status" if status else "")
    values = ":document_id, :owner_id, 'gap_report.v1', 'm'" + (", :status" if status else "")
    parameters: dict[str, object] = {"document_id": document_id, "owner_id": owner_id}
    if status:
        parameters["status"] = status
    async with engine.begin() as connection:
        result = await connection.execute(
            text(f"INSERT INTO analyses ({columns}) VALUES ({values}) RETURNING id"),  # noqa: S608
            parameters,
        )
        return result.scalar_one()


async def add_finding(
    engine: AsyncEngine,
    analysis_id: uuid.UUID,
    position: int = 0,
    kind: str = "missing",
    severity: str = "high",
    title: str = "No escalation path",
    review_status: str | None = None,
) -> uuid.UUID:
    columns = "analysis_id, position, kind, severity, title, description, suggested_question"
    values = ":analysis_id, :position, :kind, :severity, :title, 'd', 'q'"
    parameters: dict[str, object] = {
        "analysis_id": analysis_id,
        "position": position,
        "kind": kind,
        "severity": severity,
        "title": title,
    }
    if review_status:
        columns += ", review_status"
        values += ", :review_status"
        parameters["review_status"] = review_status
    async with engine.begin() as connection:
        result = await connection.execute(
            text(f"INSERT INTO findings ({columns}) VALUES ({values}) RETURNING id"),  # noqa: S608
            parameters,
        )
        return result.scalar_one()


async def add_citation(engine: AsyncEngine, finding_id: uuid.UUID, chunk_id: uuid.UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO finding_citations (finding_id, chunk_id, section_label, quote) "
                "VALUES (:finding_id, :chunk_id, '3.1', 'Clause text')"
            ),
            {"finding_id": finding_id, "chunk_id": chunk_id},
        )


async def first_chunk_id(engine: AsyncEngine) -> uuid.UUID:
    async with engine.connect() as connection:
        return (await connection.execute(text("SELECT id FROM document_chunks"))).scalar_one()


async def seed_report(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One user with a document, a chunk, an analysis, a finding and a citation.
    Returns the user, document and finding ids."""
    owner_id = await add_user(engine)
    document_id = await add_document(engine, owner_id)
    await add_chunk(engine, document_id, owner_id)
    analysis_id = await add_analysis(engine, document_id, owner_id, "succeeded")
    finding_id = await add_finding(engine, analysis_id)
    await add_citation(engine, finding_id, await first_chunk_id(engine))
    return owner_id, document_id, finding_id


async def test_new_analysis_and_finding_get_the_documented_defaults(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    analysis_id = await add_analysis(migrated_engine, document_id, owner_id)
    await add_finding(migrated_engine, analysis_id)

    async with migrated_engine.connect() as connection:
        analysis = (
            await connection.execute(
                text("SELECT status, findings_count, completed_at, summary FROM analyses")
            )
        ).one()
        review_status = (
            await connection.execute(text("SELECT review_status FROM findings"))
        ).scalar_one()

    assert tuple(analysis) == ("queued", 0, None, None)
    assert review_status == "open"


async def test_analysis_rejects_an_unknown_status(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    with pytest.raises(IntegrityError):
        await add_analysis(migrated_engine, document_id, owner_id, "cancelled")


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed"])
async def test_analysis_accepts_every_documented_status(
    migrated_engine: AsyncEngine, status: str
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    await add_analysis(migrated_engine, document_id, owner_id, status)

    assert await count_rows(migrated_engine, "analyses") == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "wrong"},
        {"severity": "critical"},
        {"review_status": "resolved"},
        {"title": "x" * 161},
    ],
)
async def test_finding_check_constraints_reject_bad_values(
    migrated_engine: AsyncEngine, overrides: dict[str, str]
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    analysis_id = await add_analysis(migrated_engine, document_id, owner_id, "succeeded")

    with pytest.raises(IntegrityError):
        await add_finding(migrated_engine, analysis_id, **overrides)


async def test_finding_title_of_160_characters_is_allowed(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    analysis_id = await add_analysis(migrated_engine, document_id, owner_id, "succeeded")

    await add_finding(migrated_engine, analysis_id, title="x" * 160)

    assert await count_rows(migrated_engine, "findings") == 1


@pytest.mark.parametrize("active", ["queued", "running"])
@pytest.mark.parametrize("other", ["queued", "running"])
async def test_a_second_active_analysis_for_one_document_is_rejected(
    migrated_engine: AsyncEngine, active: str, other: str
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_analysis(migrated_engine, document_id, owner_id, active)

    with pytest.raises(IntegrityError):
        await add_analysis(migrated_engine, document_id, owner_id, other)


@pytest.mark.parametrize("finished", ["succeeded", "failed"])
async def test_a_new_analysis_is_allowed_once_the_earlier_one_has_finished(
    migrated_engine: AsyncEngine, finished: str
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    await add_analysis(migrated_engine, document_id, owner_id, finished)

    await add_analysis(migrated_engine, document_id, owner_id, "queued")

    assert await count_rows(migrated_engine, "analyses") == 2


async def test_finished_analyses_do_not_limit_each_other(migrated_engine: AsyncEngine) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)

    for status in ("succeeded", "succeeded", "failed", "failed"):
        await add_analysis(migrated_engine, document_id, owner_id, status)

    assert await count_rows(migrated_engine, "analyses") == 4


async def test_two_documents_can_each_have_an_active_analysis(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    first = await add_document(migrated_engine, owner_id, sha256="a" * 64)
    second = await add_document(migrated_engine, owner_id, sha256="b" * 64)

    await add_analysis(migrated_engine, first, owner_id, "running")
    await add_analysis(migrated_engine, second, owner_id, "running")

    assert await count_rows(migrated_engine, "analyses") == 2


async def test_an_active_analysis_that_finishes_frees_the_slot(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    analysis_id = await add_analysis(migrated_engine, document_id, owner_id, "running")
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("UPDATE analyses SET status = 'succeeded' WHERE id = :id"), {"id": analysis_id}
        )

    await add_analysis(migrated_engine, document_id, owner_id, "running")

    assert await count_rows(migrated_engine, "analyses") == 2


async def test_finding_position_is_unique_within_an_analysis(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id = await add_user(migrated_engine)
    document_id = await add_document(migrated_engine, owner_id)
    analysis_id = await add_analysis(migrated_engine, document_id, owner_id, "succeeded")
    other_id = await add_analysis(migrated_engine, document_id, owner_id, "succeeded")
    await add_finding(migrated_engine, analysis_id, position=0)

    await add_finding(migrated_engine, other_id, position=0)
    with pytest.raises(IntegrityError):
        await add_finding(migrated_engine, analysis_id, position=0)


async def test_deleting_a_document_deletes_its_analyses_findings_and_citations(
    migrated_engine: AsyncEngine,
) -> None:
    _, document_id, _ = await seed_report(migrated_engine)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    for table in ("analyses", "findings", "finding_citations"):
        assert await count_rows(migrated_engine, table) == 0


async def test_deleting_a_user_deletes_their_analyses_findings_and_citations(
    migrated_engine: AsyncEngine,
) -> None:
    owner_id, _, _ = await seed_report(migrated_engine)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})

    for table in ("analyses", "findings", "finding_citations"):
        assert await count_rows(migrated_engine, table) == 0


async def test_deleting_a_finding_deletes_its_citations_but_not_the_chunk(
    migrated_engine: AsyncEngine,
) -> None:
    _, _, finding_id = await seed_report(migrated_engine)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM findings WHERE id = :id"), {"id": finding_id})

    assert await count_rows(migrated_engine, "finding_citations") == 0
    assert await count_rows(migrated_engine, "document_chunks") == 1


async def test_deleting_a_chunk_deletes_its_citations_but_keeps_the_finding(
    migrated_engine: AsyncEngine,
) -> None:
    # This is what a soft delete of a document does to a report: the quotes go with the chunks,
    # while the finding's own text stays until the delete service removes the analysis (ADR-042).
    await seed_report(migrated_engine)

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM document_chunks"))

    assert await count_rows(migrated_engine, "finding_citations") == 0
    assert await count_rows(migrated_engine, "findings") == 1
