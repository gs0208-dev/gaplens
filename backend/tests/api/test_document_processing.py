import asyncio
import logging
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
from app.modules.ingestion import repository, service
from app.modules.ingestion.errors import (
    GENERIC_FAILURE_MESSAGE,
    NO_TEXT_MESSAGE,
    TOO_MANY_SECTIONS_MESSAGE,
)
from tests.api.helpers import DOCUMENTS_URL, Account, audit_rows, upload
from tests.fakes.embedder import FakeEmbedder, vector_for
from tests.pdf_fixtures import text_pdf
from tests.sop_fixtures import SOP_TEXT, sop_as_pdf

SOP_CHUNKS = 8
MARKER = "ZEBRA-CLAUSE-7731-confidential-refund-rule"


def many_clauses(count: int) -> bytes:
    """Each clause is under a different parent, so each becomes its own chunk."""
    return "\n".join(
        f"{n}.1 Clause number {n} says something specific." for n in range(count)
    ).encode()


async def fetch_document(client: AsyncClient, headers: dict[str, str], document_id: str) -> Any:
    response = await client.get(f"{DOCUMENTS_URL}/{document_id}", headers=headers)
    return response.json()["document"]


async def chunk_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT chunk_index, section_label, heading, content, token_count, page_start, "
                "owner_id, document_id, vector_dims(embedding) AS dims "
                "FROM document_chunks ORDER BY chunk_index"
            )
        )
        return list(result)


async def upload_and_fetch(
    client: AsyncClient, headers: dict[str, str], data: bytes, filename: str
) -> Any:
    response = await upload(client, headers, data, filename)
    assert response.status_code == 202
    return await fetch_document(client, headers, response.json()["document"]["id"])


async def test_an_upload_becomes_ready_with_its_chunks_stored(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document = await upload_and_fetch(api_client, headers, SOP_TEXT.encode(), "sop.md")

    assert document["status"] == "ready"
    assert document["chunk_count"] == SOP_CHUNKS
    assert document["error_message"] is None
    rows = await chunk_rows(migrated_engine)
    assert [row.chunk_index for row in rows] == list(range(SOP_CHUNKS))
    assert [row.section_label for row in rows][:4] == [None, "1.1-1.2", "2.1-2.2", "3.1-3.5"]
    assert rows[3].heading == "Refund handling"
    assert rows[3].content.startswith("3.1 L1 agents may approve refunds up to INR 5,000")
    assert all(row.dims == 384 for row in rows)
    assert all(row.token_count > 0 for row in rows)


async def test_every_chunk_belongs_to_the_documents_owner(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")
    async with migrated_engine.connect() as connection:
        mismatched = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM document_chunks c JOIN documents d "
                    "ON d.id = c.document_id WHERE c.owner_id <> d.owner_id"
                )
            )
        ).scalar_one()
        total = (
            await connection.execute(text("SELECT count(*) FROM document_chunks"))
        ).scalar_one()

    assert (mismatched, total) == (0, SOP_CHUNKS)


async def test_the_document_is_ready_with_the_embedding_model_recorded(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")

    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(text("SELECT embedding_model, status FROM documents"))
        ).one()

    assert (row.embedding_model, row.status) == (get_settings().embedding_model, "ready")


async def test_a_pdf_keeps_its_page_numbers_on_the_chunks(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document = await upload_and_fetch(api_client, headers, sop_as_pdf(), "sop.pdf")

    rows = await chunk_rows(migrated_engine)

    assert document["status"] == "ready"
    assert [row.page_start for row in rows if row.section_label] == [1, 1, 2, 2, 3, 3, 3]


async def test_text_without_structure_is_stored_as_unlabeled_chunks(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = b"Refunds are handled by the team.\n\nEscalations go to a manager when needed."

    document = await upload_and_fetch(api_client, headers, data, "notes.txt")

    rows = await chunk_rows(migrated_engine)
    assert document["status"] == "ready"
    assert [(row.section_label, row.heading) for row in rows] == [(None, None)]


async def test_the_stored_vector_is_the_one_the_embedder_returned_for_heading_and_content(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")

    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT heading, content, embedding <=> CAST(:expected AS vector) AS distance "
                    "FROM document_chunks WHERE chunk_index = 3"
                ),
                {"expected": str(vector_for("Refund handling\n" + SOP_CHUNK_3_CONTENT))},
            )
        ).one()

    assert row.heading == "Refund handling"
    assert row.distance == pytest.approx(0, abs=1e-5)


SOP_CHUNK_3_CONTENT = "\n".join(
    [
        "3.1 L1 agents may approve refunds up to INR 5,000 per request without further approval.",
        "3.2 Refunds above INR 5,000 and up to INR 25,000 need approval from a team lead.",
        "3.3 Refunds above INR 25,000 need approval from the finance department.",
        "3.4 Approved refunds are processed promptly and credited to the original payment method.",
        "3.5 Agents must record the refund reason in the CRM before approving.",
    ]
)


async def test_chunks_are_embedded_in_batches_of_32(
    api_client: AsyncClient, headers: dict[str, str], fake_embedder: FakeEmbedder
) -> None:
    document = await upload_and_fetch(api_client, headers, many_clauses(70), "many.txt")

    assert document["chunk_count"] == 70
    assert fake_embedder.passage_batch_sizes == [32, 32, 6]


async def test_chunks_are_inserted_in_batches_in_one_transaction(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[object] = []
    real_insert = repository.insert

    def counting_insert(table: Any) -> Any:
        statements.append(table)
        return real_insert(table)

    monkeypatch.setattr(repository, "INSERT_BATCH_SIZE", 25)
    monkeypatch.setattr(repository, "insert", counting_insert)

    document = await upload_and_fetch(api_client, headers, many_clauses(70), "many.txt")

    assert document["chunk_count"] == 70
    assert len(statements) == 3  # 25 + 25 + 20
    assert len(await chunk_rows(migrated_engine)) == 70


async def test_if_the_embedder_fails_the_document_fails_with_a_fixed_message(
    api_client: AsyncClient,
    headers: dict[str, str],
    fake_embedder: FakeEmbedder,
    migrated_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_embedder.failure = RuntimeError(f"model exploded while reading {MARKER}")

    with caplog.at_level(logging.DEBUG):
        document = await upload_and_fetch(api_client, headers, SOP_TEXT.encode(), "sop.md")

    assert document["status"] == "failed"
    assert document["error_message"] == GENERIC_FAILURE_MESSAGE
    assert document["chunk_count"] == 0
    assert await chunk_rows(migrated_engine) == []
    assert MARKER not in caplog.text
    assert "model exploded" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


async def test_too_many_chunks_fails_the_document_before_any_embedding(
    api_client: AsyncClient,
    headers: dict[str, str],
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "max_chunks_per_document", 5)

    document = await upload_and_fetch(api_client, headers, many_clauses(10), "many.txt")

    assert document["status"] == "failed"
    assert document["error_message"] == TOO_MANY_SECTIONS_MESSAGE
    assert fake_embedder.passage_batch_sizes == []


async def test_a_document_with_no_chunks_fails_with_the_no_text_message(
    api_client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_prepare_chunks", lambda data, mime_type: [])

    document = await upload_and_fetch(api_client, headers, SOP_TEXT.encode(), "sop.md")

    assert (document["status"], document["error_message"]) == ("failed", NO_TEXT_MESSAGE)


async def test_an_extraction_error_fails_the_document_without_leaking_its_message(
    api_client: AsyncClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(data: bytes, mime_type: str) -> list[Any]:
        raise ValueError(f"cannot parse {MARKER}")

    monkeypatch.setattr(service, "_prepare_chunks", broken)

    with caplog.at_level(logging.DEBUG):
        document = await upload_and_fetch(api_client, headers, SOP_TEXT.encode(), "sop.md")

    assert (document["status"], document["error_message"]) == ("failed", GENERIC_FAILURE_MESSAGE)
    assert MARKER not in caplog.text


async def test_processing_logs_never_contain_document_text(
    api_client: AsyncClient, headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await upload(api_client, headers, f"1.1 Rule. {MARKER}".encode(), "sop.txt")
        await upload(api_client, headers, text_pdf([MARKER]), "sop.pdf")

    assert MARKER not in caplog.text
    assert "document ready" in caplog.text


async def insert_uploaded_document(
    engine: AsyncEngine, *, deleted: bool = False
) -> tuple[Any, Any]:
    async with engine.begin() as connection:
        owner_id = (
            await connection.execute(
                text(
                    "INSERT INTO users (email, password_hash) "
                    "VALUES ('o@example.com', 'x') RETURNING id"
                )
            )
        ).scalar_one()
        document_id = (
            await connection.execute(
                text(
                    "INSERT INTO documents (owner_id, title, filename, mime_type, size_bytes, "
                    "sha256, deleted_at) VALUES (:o, 't', 'f.txt', 'text/plain', 10, :h, "
                    "CASE WHEN :deleted THEN now() END) RETURNING id"
                ),
                {"o": owner_id, "h": uuid.uuid4().hex + uuid.uuid4().hex, "deleted": deleted},
            )
        ).scalar_one()
    return owner_id, document_id


async def test_only_one_of_two_simultaneous_tasks_processes_a_document(
    migrated_engine: AsyncEngine, fake_embedder: FakeEmbedder
) -> None:
    owner_id, document_id = await insert_uploaded_document(migrated_engine)
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    data = b"1.1 A clause that is long enough to be one chunk of text."

    await asyncio.gather(
        *(
            service.process_document(
                session_factory,
                fake_embedder,
                document_id=document_id,
                owner_id=owner_id,
                data=data,
                mime_type="text/plain",
            )
            for _ in range(2)
        )
    )

    assert len(await chunk_rows(migrated_engine)) == 1
    assert sum(fake_embedder.passage_batch_sizes) == 1


async def test_a_deleted_document_is_not_processed(
    migrated_engine: AsyncEngine, fake_embedder: FakeEmbedder
) -> None:
    owner_id, document_id = await insert_uploaded_document(migrated_engine, deleted=True)

    await service.process_document(
        async_sessionmaker(migrated_engine, expire_on_commit=False),
        fake_embedder,
        document_id=document_id,
        owner_id=owner_id,
        data=b"1.1 Some clause text that would be stored.",
        mime_type="text/plain",
    )

    assert await chunk_rows(migrated_engine) == []
    assert fake_embedder.passage_batch_sizes == []


async def test_another_owners_id_cannot_claim_a_document(
    migrated_engine: AsyncEngine, fake_embedder: FakeEmbedder
) -> None:
    _, document_id = await insert_uploaded_document(migrated_engine)

    await service.process_document(
        async_sessionmaker(migrated_engine, expire_on_commit=False),
        fake_embedder,
        document_id=document_id,
        owner_id=uuid.uuid4(),
        data=b"1.1 Some clause text that would be stored.",
        mime_type="text/plain",
    )

    assert await chunk_rows(migrated_engine) == []


async def test_nothing_is_stored_if_the_document_stopped_processing_meanwhile(
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, document_id = await insert_uploaded_document(migrated_engine)

    async def lost(*args: Any, **kwargs: Any) -> bool:
        return False  # as if the sweep had failed the document while it was being embedded

    monkeypatch.setattr(repository, "mark_ready", lost)

    await service.process_document(
        async_sessionmaker(migrated_engine, expire_on_commit=False),
        fake_embedder,
        document_id=document_id,
        owner_id=owner_id,
        data=b"1.1 Some clause text that would be stored.",
        mime_type="text/plain",
    )

    assert await chunk_rows(migrated_engine) == []


async def test_the_task_never_raises_even_if_marking_the_failure_fails(
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner_id, document_id = await insert_uploaded_document(migrated_engine)
    fake_embedder.failure = RuntimeError("boom")

    async def database_down(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("database is down")

    monkeypatch.setattr(repository, "mark_failed", database_down)

    with caplog.at_level(logging.DEBUG):
        await service.process_document(
            async_sessionmaker(migrated_engine, expire_on_commit=False),
            fake_embedder,
            document_id=document_id,
            owner_id=owner_id,
            data=b"1.1 Some clause text that would be stored.",
            mime_type="text/plain",
        )

    assert "could not mark document failed" in caplog.text
    assert "database is down" not in caplog.text


async def test_processing_writes_no_audit_event(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")

    assert [row.action for row in await audit_rows(migrated_engine)] == [
        "auth.login",
        "document.upload",
    ]
