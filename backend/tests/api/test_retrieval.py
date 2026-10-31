import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
from app.modules.documents.errors import DocumentNotFound
from app.modules.retrieval import repository
from app.modules.retrieval.errors import DocumentNotReady
from app.modules.retrieval.service import retrieve
from tests.api.helpers import Account, upload
from tests.fakes.embedder import FakeEmbedder, vector_for
from tests.sop_fixtures import SOP_TEXT

SOP = SOP_TEXT.encode()


async def create_document(
    client: AsyncClient, headers: dict[str, str], data: bytes = SOP
) -> uuid.UUID:
    response = await upload(client, headers, data, "sop.md")
    return uuid.UUID(response.json()["document"]["id"])


async def user_id(engine: AsyncEngine, email: str) -> uuid.UUID:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        return result.scalar_one()


async def embedded_text_of_chunk(engine: AsyncEngine, document_id: uuid.UUID, index: int) -> str:
    """Exactly what the pipeline embedded for a chunk: the heading, a newline, the content."""
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT heading, content FROM document_chunks "
                    "WHERE document_id = :id AND chunk_index = :index"
                ),
                {"id": document_id, "index": index},
            )
        ).one()
    return f"{row.heading}\n{row.content}" if row.heading else str(row.content)


async def ask(
    engine: AsyncEngine,
    embedder: FakeEmbedder,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    question: str,
) -> list[Any]:
    async with async_sessionmaker(engine)() as session:
        return await retrieve(
            session, embedder, owner_id=owner_id, document_id=document_id, question=question
        )


@pytest.fixture
async def owner_id(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> uuid.UUID:
    return await user_id(migrated_engine, account.email)


async def test_a_chunks_own_text_finds_that_chunk_first_with_a_score_of_one(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    document_id = await create_document(api_client, headers)
    question = await embedded_text_of_chunk(migrated_engine, document_id, 3)

    results = await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question=question,
    )

    assert results[0].chunk_index == 3
    assert results[0].section_label == "3.1-3.5"
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


async def test_results_are_best_first_at_most_k_and_carry_what_chat_needs(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    document_id = await create_document(api_client, headers)

    results = await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question="What is the refund limit?",
    )

    assert len(results) == get_settings().retrieval_top_k == 6
    scores = [chunk.score for chunk in results]
    assert scores == sorted(scores, reverse=True)
    first = results[0]
    assert isinstance(first.id, uuid.UUID)
    assert first.content and first.chunk_index >= 0
    assert {chunk.chunk_index for chunk in results} <= set(range(8))


async def test_k_comes_from_the_settings(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "retrieval_top_k", 3)
    document_id = await create_document(api_client, headers)

    results = await ask(
        migrated_engine, fake_embedder, owner_id=owner_id, document_id=document_id, question="x"
    )

    assert len(results) == 3


async def test_the_score_is_one_minus_the_cosine_distance(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    document_id = await create_document(api_client, headers)
    question = "What are the support hours?"

    results = await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question=question,
    )

    async with migrated_engine.connect() as connection:
        for chunk in results:
            expected = (
                await connection.execute(
                    text(
                        "SELECT 1 - (embedding <=> CAST(:q AS vector)) "
                        "FROM document_chunks WHERE id = :id"
                    ),
                    {"q": str(vector_for(question)), "id": chunk.id},
                )
            ).scalar_one()
            assert chunk.score == pytest.approx(float(expected), abs=1e-6)


async def test_another_document_of_the_same_owner_is_never_searched(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    first = await create_document(api_client, headers)
    second = await create_document(api_client, headers, b"1.1 A completely different document.")

    results = await ask(
        migrated_engine, fake_embedder, owner_id=owner_id, document_id=second, question="refund"
    )

    async with migrated_engine.connect() as connection:
        first_ids = {
            row[0]
            for row in await connection.execute(
                text("SELECT id FROM document_chunks WHERE document_id = :id"), {"id": first}
            )
        }
    assert len(results) == 1
    assert {chunk.id for chunk in results}.isdisjoint(first_ids)


async def test_the_query_returns_nothing_for_another_users_document(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    document_id = await create_document(api_client, headers)
    intruder = await user_id(migrated_engine, other_account.email)

    async with async_sessionmaker(migrated_engine)() as session:
        stolen = await repository.search_chunks(
            session,
            owner_id=intruder,
            document_id=document_id,
            query_embedding=vector_for("refund limit"),
            limit=10,
        )

    assert stolen == []


async def test_another_users_missing_and_deleted_documents_all_look_the_same(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    document_id = await create_document(api_client, headers)
    intruder = await user_id(migrated_engine, other_account.email)
    deleted = await create_document(api_client, headers, b"1.1 A document that is then deleted.")
    await api_client.delete(f"/api/v1/documents/{deleted}", headers=headers)

    for asker, target in ((intruder, document_id), (owner_id, uuid.uuid4()), (owner_id, deleted)):
        with pytest.raises(DocumentNotFound):
            await ask(
                migrated_engine, fake_embedder, owner_id=asker, document_id=target, question="x"
            )
    assert fake_embedder.queries == []


@pytest.mark.parametrize("status", ["uploaded", "processing", "failed"])
async def test_a_document_that_is_not_ready_cannot_be_searched(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
    status: str,
) -> None:
    document_id = await create_document(api_client, headers)
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET status = :status"), {"status": status})

    with pytest.raises(DocumentNotReady):
        await ask(
            migrated_engine, fake_embedder, owner_id=owner_id, document_id=document_id, question="x"
        )
    assert fake_embedder.queries == []


async def test_a_minimum_score_keeps_only_close_chunks_and_zero_keeps_all(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = await create_document(api_client, headers)
    question = await embedded_text_of_chunk(migrated_engine, document_id, 3)
    everything = await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question=question,
    )
    monkeypatch.setattr(get_settings(), "retrieval_min_score", 0.9)

    close_only = await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question=question,
    )

    assert len(everything) == 6
    assert [chunk.chunk_index for chunk in close_only] == [3]


async def test_the_question_is_embedded_once_on_the_embedding_thread(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
    owner_id: uuid.UUID,
) -> None:
    document_id = await create_document(api_client, headers)

    await ask(
        migrated_engine,
        fake_embedder,
        owner_id=owner_id,
        document_id=document_id,
        question="Who approves large refunds?",
    )

    assert fake_embedder.queries == ["Who approves large refunds?"]
    assert fake_embedder.query_thread_names[0].startswith("embedding")
