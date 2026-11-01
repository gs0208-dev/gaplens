import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.chat import repository as chat_repository
from app.modules.documents import repository as documents_repository
from tests.api.helpers import DOCUMENTS_URL, Account, auth_headers, upload, without_request_id
from tests.fakes.llm import FakeLLM
from tests.sop_fixtures import SOP_TEXT

SUMMARY_FIELDS = {"id", "title", "status", "page_count", "chunk_count", "created_at"}
CHUNK_FIELDS = {"id", "chunk_index", "section_label", "heading", "content", "page_start"}
THREAD_FIELDS = {"id", "title", "created_at", "updated_at"}


async def make_document(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    data = f"1.1 A clause that belongs to {name}.".encode()
    response = await upload(client, headers, data, f"{name}.txt")
    return str(response.json()["document"]["id"])


async def list_all(
    client: AsyncClient, url: str, headers: dict[str, str], limit: int
) -> list[list[dict[str, Any]]]:
    """Follow next_cursor to the end and return the pages."""
    pages: list[list[dict[str, Any]]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": limit, **({"cursor": cursor} if cursor else {})}
        body = (await client.get(url, headers=headers, params=params)).json()
        pages.append(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


async def ask(client: AsyncClient, headers: dict[str, str], document_id: str, text: str, **kw: Any):
    body = {"question": text, **kw}
    return await client.post(f"{DOCUMENTS_URL}/{document_id}/chat", headers=headers, json=body)


# ---- GET /documents --------------------------------------------------------------------------


async def test_a_new_user_has_an_empty_list(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await api_client.get(DOCUMENTS_URL, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_the_list_shows_only_the_fields_a_table_needs_newest_first(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    first = await make_document(api_client, headers, "first")
    second = await make_document(api_client, headers, "second")
    third = await make_document(api_client, headers, "third")

    body = (await api_client.get(DOCUMENTS_URL, headers=headers)).json()

    assert [item["id"] for item in body["items"]] == [third, second, first]
    assert all(set(item) == SUMMARY_FIELDS for item in body["items"])
    assert body["items"][0]["title"] == "third"
    assert body["items"][0]["status"] == "ready"
    assert body["items"][0]["chunk_count"] == 1
    assert body["next_cursor"] is None


async def test_pages_follow_the_cursor_without_gaps_or_repeats(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    ids = [await make_document(api_client, headers, f"doc{n}") for n in range(5)]

    pages = await list_all(api_client, DOCUMENTS_URL, headers, limit=2)

    assert [len(page) for page in pages] == [2, 2, 1]
    assert [item["id"] for page in pages for item in page] == list(reversed(ids))


async def test_documents_created_at_the_same_instant_are_not_skipped_or_repeated(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await make_document(api_client, headers, "seed")
    async with migrated_engine.begin() as connection:
        owner = (await connection.execute(text("SELECT id FROM users"))).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO documents (owner_id, title, filename, mime_type, size_bytes, sha256, "
                "status, created_at) SELECT :owner, 't' || g, 'f.txt', 'text/plain', 10, "
                "md5(g::text) || md5((g + 100)::text), 'ready', '2026-01-01T00:00:00Z' "
                "FROM generate_series(1, 5) g"
            ),
            {"owner": owner},
        )

    pages = await list_all(api_client, DOCUMENTS_URL, headers, limit=2)

    ids = [item["id"] for page in pages for item in page]
    assert len(ids) == len(set(ids)) == 6


async def test_deleted_documents_and_other_users_documents_are_never_listed(
    api_client: AsyncClient, headers: dict[str, str], other_account: Account
) -> None:
    kept = await make_document(api_client, headers, "kept")
    removed = await make_document(api_client, headers, "removed")
    await api_client.delete(f"{DOCUMENTS_URL}/{removed}", headers=headers)
    other_headers = await auth_headers(api_client, other_account)
    theirs = await make_document(api_client, other_headers, "theirs")

    mine = (await api_client.get(DOCUMENTS_URL, headers=headers)).json()["items"]
    their_list = (await api_client.get(DOCUMENTS_URL, headers=other_headers)).json()["items"]

    assert [item["id"] for item in mine] == [kept]
    assert [item["id"] for item in their_list] == [theirs]


async def test_the_list_shows_documents_that_are_still_processing_or_failed(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    await make_document(api_client, headers, "a")
    await make_document(api_client, headers, "b")
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("UPDATE documents SET status = 'processing' WHERE title = 'a'")
        )
        await connection.execute(text("UPDATE documents SET status = 'failed' WHERE title = 'b'"))

    items = (await api_client.get(DOCUMENTS_URL, headers=headers)).json()["items"]

    assert {item["title"]: item["status"] for item in items} == {
        "a": "processing",
        "b": "failed",
    }


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": "x"}])
async def test_a_bad_limit_is_a_validation_error(
    api_client: AsyncClient, headers: dict[str, str], params: dict[str, Any]
) -> None:
    response = await api_client.get(DOCUMENTS_URL, headers=headers, params=params)

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")


async def test_a_bad_cursor_is_refused_and_listing_needs_a_token(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    bad = await api_client.get(DOCUMENTS_URL, headers=headers, params={"cursor": "nonsense"})
    anonymous = await api_client.get(DOCUMENTS_URL)

    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_cursor")
    assert anonymous.status_code == 401


# ---- GET /documents/{id}/chunks --------------------------------------------------------------


async def test_the_chunks_of_a_ready_document_come_back_in_reading_order(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    response = await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")
    document_id = response.json()["document"]["id"]

    body = (await api_client.get(f"{DOCUMENTS_URL}/{document_id}/chunks", headers=headers)).json()

    items = body["items"]
    assert set(body) == {"items"}
    assert all(set(item) == CHUNK_FIELDS for item in items)
    assert [item["chunk_index"] for item in items] == list(range(8))
    assert [item["section_label"] for item in items][:4] == [None, "1.1-1.2", "2.1-2.2", "3.1-3.5"]
    assert items[3]["heading"] == "Refund handling"
    assert items[3]["content"].startswith("3.1 L1 agents may approve refunds up to INR 5,000")
    async with migrated_engine.connect() as connection:
        stored = {
            str(row.id) for row in await connection.execute(text("SELECT id FROM document_chunks"))
        }
    assert {item["id"] for item in items} == stored


async def test_chunks_are_never_mixed_between_documents(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    await upload(api_client, headers, SOP_TEXT.encode(), "sop.md")
    small = await make_document(api_client, headers, "small")

    items = (await api_client.get(f"{DOCUMENTS_URL}/{small}/chunks", headers=headers)).json()[
        "items"
    ]

    assert len(items) == 1
    assert "small" in items[0]["content"]


@pytest.mark.parametrize("status", ["uploaded", "processing", "failed"])
async def test_a_document_that_is_not_ready_has_no_text_to_show(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine, status: str
) -> None:
    document_id = await make_document(api_client, headers, "x")
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET status = :s"), {"s": status})

    response = await api_client.get(f"{DOCUMENTS_URL}/{document_id}/chunks", headers=headers)

    assert (response.status_code, response.json()["code"]) == (409, "document_not_ready")


async def test_chunks_of_foreign_missing_and_deleted_documents_look_the_same(
    api_client: AsyncClient, headers: dict[str, str], other_account: Account
) -> None:
    mine = await make_document(api_client, headers, "mine")
    gone = await make_document(api_client, headers, "gone")
    await api_client.delete(f"{DOCUMENTS_URL}/{gone}", headers=headers)
    other_headers = await auth_headers(api_client, other_account)

    foreign = await api_client.get(f"{DOCUMENTS_URL}/{mine}/chunks", headers=other_headers)
    missing = await api_client.get(f"{DOCUMENTS_URL}/{uuid.uuid4()}/chunks", headers=other_headers)
    deleted = await api_client.get(f"{DOCUMENTS_URL}/{gone}/chunks", headers=headers)

    assert (foreign.status_code, deleted.status_code) == (404, 404)
    assert without_request_id(foreign) == without_request_id(missing)
    assert deleted.json()["code"] == "document_not_found"


async def test_reading_chunks_needs_a_token(api_client: AsyncClient) -> None:
    response = await api_client.get(f"{DOCUMENTS_URL}/{uuid.uuid4()}/chunks")

    assert response.status_code == 401


# ---- GET /documents/{id}/threads -------------------------------------------------------------


async def test_a_document_without_conversations_has_an_empty_thread_list(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    document_id = await make_document(api_client, headers, "quiet")

    response = await api_client.get(f"{DOCUMENTS_URL}/{document_id}/threads", headers=headers)

    assert response.json() == {"items": [], "next_cursor": None}


async def test_threads_are_listed_with_the_most_recently_used_first(
    api_client: AsyncClient, headers: dict[str, str], fake_llm: FakeLLM
) -> None:
    document_id = await make_document(api_client, headers, "busy")
    older = (await ask(api_client, headers, document_id, "older question")).json()["thread_id"]
    newer = (await ask(api_client, headers, document_id, "newer question")).json()["thread_id"]
    url = f"{DOCUMENTS_URL}/{document_id}/threads"

    before = (await api_client.get(url, headers=headers)).json()["items"]
    await ask(api_client, headers, document_id, "back to the first", thread_id=older)
    after = (await api_client.get(url, headers=headers)).json()["items"]

    assert [t["id"] for t in before] == [newer, older]
    assert [t["id"] for t in after] == [older, newer]
    assert all(set(t) == THREAD_FIELDS for t in after)
    assert after[0]["title"] == "older question"


async def test_thread_pages_follow_the_cursor(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    document_id = await make_document(api_client, headers, "many")
    ids = [
        (await ask(api_client, headers, document_id, f"question {n}")).json()["thread_id"]
        for n in range(3)
    ]

    pages = await list_all(api_client, f"{DOCUMENTS_URL}/{document_id}/threads", headers, limit=1)

    assert [len(page) for page in pages] == [1, 1, 1]
    assert [t["id"] for page in pages for t in page] == list(reversed(ids))


async def test_only_the_threads_of_that_document_and_that_user_are_listed(
    api_client: AsyncClient, headers: dict[str, str], other_account: Account
) -> None:
    first = await make_document(api_client, headers, "first")
    second = await make_document(api_client, headers, "second")
    mine = (await ask(api_client, headers, first, "about the first")).json()["thread_id"]
    await ask(api_client, headers, second, "about the second")
    other_headers = await auth_headers(api_client, other_account)
    theirs = await make_document(api_client, other_headers, "theirs")
    await ask(api_client, other_headers, theirs, "their question")

    listed = (await api_client.get(f"{DOCUMENTS_URL}/{first}/threads", headers=headers)).json()

    assert [t["id"] for t in listed["items"]] == [mine]


async def test_threads_of_foreign_missing_and_deleted_documents_look_the_same(
    api_client: AsyncClient, headers: dict[str, str], other_account: Account
) -> None:
    mine = await make_document(api_client, headers, "mine")
    gone = await make_document(api_client, headers, "gone")
    await api_client.delete(f"{DOCUMENTS_URL}/{gone}", headers=headers)
    other_headers = await auth_headers(api_client, other_account)

    foreign = await api_client.get(f"{DOCUMENTS_URL}/{mine}/threads", headers=other_headers)
    missing = await api_client.get(f"{DOCUMENTS_URL}/{uuid.uuid4()}/threads", headers=other_headers)
    deleted = await api_client.get(f"{DOCUMENTS_URL}/{gone}/threads", headers=headers)

    assert (foreign.status_code, deleted.status_code) == (404, 404)
    assert without_request_id(foreign) == without_request_id(missing)


async def test_thread_listing_validates_input_and_needs_a_token(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    document_id = await make_document(api_client, headers, "x")
    url = f"{DOCUMENTS_URL}/{document_id}/threads"

    bad_cursor = await api_client.get(url, headers=headers, params={"cursor": "nonsense"})
    bad_limit = await api_client.get(url, headers=headers, params={"limit": 101})
    anonymous = await api_client.get(url)

    assert (bad_cursor.status_code, bad_cursor.json()["code"]) == (422, "invalid_cursor")
    assert (bad_limit.status_code, anonymous.status_code) == (422, 401)


# ---- the queries themselves ------------------------------------------------------------------


async def test_the_queries_return_nothing_for_the_wrong_owner_even_with_a_right_document_id(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
) -> None:
    document_id = uuid.UUID(await make_document(api_client, headers, "guarded"))
    await ask(api_client, headers, str(document_id), "a question")
    intruder = uuid.uuid4()

    async with async_sessionmaker(migrated_engine)() as session:
        threads = await chat_repository.list_threads(
            session, owner_id=intruder, document_id=document_id, after=None, limit=10
        )
        chunks = await documents_repository.list_chunks(
            session, owner_id=intruder, document_id=document_id
        )
        documents = await documents_repository.list_documents(
            session, owner_id=intruder, after=None, limit=10
        )

    assert (threads, chunks, documents) == ([], [], [])
