import asyncio
import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.documents import repository as documents_repository
from app.modules.ingestion import repository as ingestion_repository
from tests.api.helpers import (
    DOCUMENTS_URL,
    Account,
    audit_rows,
    auth_headers,
    upload,
    without_request_id,
)
from tests.fakes.embedder import FakeEmbedder
from tests.sop_fixtures import SOP_TEXT

SOP = SOP_TEXT.encode()


async def create_document(client: AsyncClient, headers: dict[str, str], data: bytes = SOP) -> str:
    response = await upload(client, headers, data, "sop.md")
    return str(response.json()["document"]["id"])


async def delete(client: AsyncClient, headers: dict[str, str], document_id: str) -> Any:
    return await client.delete(f"{DOCUMENTS_URL}/{document_id}", headers=headers)


async def count(engine: AsyncEngine, sql: str) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(text(sql))).scalar_one()


async def test_the_owner_deletes_a_document_and_it_disappears(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document_id = await create_document(api_client, headers)

    response = await delete(api_client, headers, document_id)

    assert response.status_code == 204
    assert response.content == b""
    after = await api_client.get(f"{DOCUMENTS_URL}/{document_id}", headers=headers)
    assert after.status_code == 404
    assert (
        await count(migrated_engine, "SELECT count(*) FROM documents WHERE deleted_at IS NULL") == 0
    )


async def test_the_row_is_kept_for_retention_but_its_text_is_removed(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await create_document(api_client, headers)
    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 8

    await delete(api_client, headers, await _only_document_id(migrated_engine))

    assert await count(migrated_engine, "SELECT count(*) FROM documents") == 1
    assert (
        await count(migrated_engine, "SELECT count(*) FROM documents WHERE deleted_at IS NOT NULL")
        == 1
    )
    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 0


async def _only_document_id(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        return str((await connection.execute(text("SELECT id FROM documents"))).scalar_one())


async def test_a_delete_writes_one_audit_event(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document_id = await create_document(api_client, headers)

    await delete(api_client, headers, document_id)

    (event,) = await audit_rows(migrated_engine, "document.delete")
    assert str(event.resource_id) == document_id
    assert event.resource_type == "document"
    assert event.metadata == {}
    async with migrated_engine.connect() as connection:
        owner = (await connection.execute(text("SELECT id FROM users"))).scalar_one()
    assert event.actor_id == owner


async def test_a_second_delete_is_a_404_and_writes_no_second_event(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document_id = await create_document(api_client, headers)
    await delete(api_client, headers, document_id)

    again = await delete(api_client, headers, document_id)

    assert again.status_code == 404
    assert again.json()["code"] == "document_not_found"
    assert len(await audit_rows(migrated_engine, "document.delete")) == 1


async def test_another_users_document_looks_missing_and_is_left_untouched(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    document_id = await create_document(api_client, headers)
    other_headers = await auth_headers(api_client, other_account)
    other_document = await create_document(api_client, other_headers, b"1.1 Another users clause.")

    foreign = await delete(api_client, other_headers, document_id)
    missing = await delete(api_client, other_headers, str(uuid.uuid4()))

    assert foreign.status_code == 404
    assert without_request_id(foreign) == without_request_id(missing)
    owner_view = await api_client.get(f"{DOCUMENTS_URL}/{document_id}", headers=headers)
    assert owner_view.status_code == 200
    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 9
    assert await audit_rows(migrated_engine, "document.delete") == []
    assert (
        await api_client.get(f"{DOCUMENTS_URL}/{other_document}", headers=other_headers)
    ).status_code == 200


async def test_deleting_one_document_keeps_the_chunks_of_the_other_documents(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    first = await create_document(api_client, headers)
    await create_document(api_client, headers, b"1.1 A second document with one clause.")

    await delete(api_client, headers, first)

    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 1


async def test_deleting_needs_a_valid_token_and_a_well_formed_id(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    no_token = await api_client.delete(f"{DOCUMENTS_URL}/{uuid.uuid4()}")
    bad_id = await api_client.delete(f"{DOCUMENTS_URL}/not-a-uuid", headers=headers)

    assert (no_token.status_code, bad_id.status_code) == (401, 422)


async def test_the_same_file_can_be_uploaded_again_after_a_delete(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    document_id = await create_document(api_client, headers)
    await delete(api_client, headers, document_id)

    response = await upload(api_client, headers, SOP, "sop.md")

    assert response.status_code == 202
    new_id = response.json()["document"]["id"]
    assert new_id != document_id
    status = (await api_client.get(f"{DOCUMENTS_URL}/{new_id}", headers=headers)).json()
    assert status["document"]["status"] == "ready"


async def test_a_failed_document_can_be_deleted_and_its_file_uploaded_again(
    api_client: AsyncClient, headers: dict[str, str], fake_embedder: FakeEmbedder
) -> None:
    fake_embedder.failure = RuntimeError("model unavailable")
    failed_id = await create_document(api_client, headers)
    failed = (await api_client.get(f"{DOCUMENTS_URL}/{failed_id}", headers=headers)).json()
    assert failed["document"]["status"] == "failed"
    blocked = await upload(api_client, headers, SOP, "sop.md")
    assert blocked.json()["code"] == "duplicate_document"

    fake_embedder.failure = None
    assert (await delete(api_client, headers, failed_id)).status_code == 204
    retry = await upload(api_client, headers, SOP, "sop.md")

    assert retry.status_code == 202
    retried = (
        await api_client.get(f"{DOCUMENTS_URL}/{retry.json()['document']['id']}", headers=headers)
    ).json()
    assert retried["document"]["status"] == "ready"


async def test_a_document_deleted_while_processing_never_gets_its_chunks(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_embedder: FakeEmbedder,
) -> None:
    document_id = await create_document(api_client, headers)
    async with migrated_engine.begin() as connection:
        # Put it back to the state it is in while the background task is working.
        await connection.execute(
            text("UPDATE documents SET status = 'processing', chunk_count = 0")
        )
        await connection.execute(text("DELETE FROM document_chunks"))
    await delete(api_client, headers, document_id)
    owner = await _owner_id(migrated_engine)

    async with async_sessionmaker(migrated_engine)() as session:
        finished = await ingestion_repository.mark_ready(
            session,
            document_id=uuid.UUID(document_id),
            owner_id=owner,
            chunk_count=3,
            embedding_model="m",
        )

    assert finished is False
    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 0


async def _owner_id(engine: AsyncEngine) -> uuid.UUID:
    async with engine.connect() as connection:
        return (await connection.execute(text("SELECT id FROM users"))).scalar_one()


async def test_simultaneous_deletes_succeed_once_and_audit_once(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document_id = await create_document(api_client, headers)

    responses = await asyncio.gather(*(delete(api_client, headers, document_id) for _ in range(5)))

    assert sorted(r.status_code for r in responses) == [204, 404, 404, 404, 404]
    assert len(await audit_rows(migrated_engine, "document.delete")) == 1


async def test_the_repository_will_not_delete_for_the_wrong_owner(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    document_id = await create_document(api_client, headers)

    async with async_sessionmaker(migrated_engine)() as session:
        deleted = await documents_repository.soft_delete_document(
            session, owner_id=uuid.uuid4(), document_id=uuid.UUID(document_id)
        )
        await documents_repository.delete_chunks(
            session, owner_id=uuid.uuid4(), document_id=uuid.UUID(document_id)
        )
        await session.commit()

    assert deleted is False
    assert await count(migrated_engine, "SELECT count(*) FROM document_chunks") == 8
