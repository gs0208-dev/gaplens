import asyncio
import logging
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from tests.api.helpers import (
    DOCUMENTS_URL,
    Account,
    audit_rows,
    auth_headers,
    upload,
    without_request_id,
)
from tests.pdf_fixtures import blank_pdf, encrypted_pdf, text_pdf

POLICY = "Refunds above 500 dollars need approval from a team lead."
DOCUMENT_FIELDS = {
    "id",
    "title",
    "filename",
    "mime_type",
    "size_bytes",
    "status",
    "error_message",
    "page_count",
    "chunk_count",
    "created_at",
}


def distinct_text(label: str) -> bytes:
    return f"3.1 {label}. {POLICY}".encode()


async def document_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT owner_id, title, filename, mime_type, size_bytes, sha256, status, "
                "page_count, chunk_count FROM documents ORDER BY created_at"
            )
        )
        return list(result)


async def test_upload_returns_202_with_the_document(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), "sop.txt")

    assert response.status_code == 202
    document = response.json()["document"]
    assert set(document) == DOCUMENT_FIELDS
    assert document["status"] == "uploaded"
    assert document["title"] == "sop"
    assert document["filename"] == "sop.txt"
    assert document["mime_type"] == "text/plain"
    assert document["chunk_count"] == 0
    assert document["error_message"] is None
    uuid.UUID(document["id"])


async def test_upload_stores_metadata_and_hash_only(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    import hashlib

    data = distinct_text("a")

    await upload(api_client, headers, data)

    (row,) = await document_rows(migrated_engine)
    assert row.sha256 == hashlib.sha256(data).hexdigest()
    assert row.size_bytes == len(data)
    # The response says "uploaded"; by the time the test reads the row, the background task
    # that runs after the response has finished.
    assert row.status == "ready"
    assert row.page_count is None


async def test_pdf_upload_records_page_count_and_mime_type(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(
        api_client, headers, text_pdf([POLICY, "Second page text"]), "policy.pdf"
    )

    document = response.json()["document"]
    assert (document["mime_type"], document["page_count"]) == ("application/pdf", 2)


async def test_upload_needs_a_valid_access_token(api_client: AsyncClient) -> None:
    response = await api_client.post(DOCUMENTS_URL, files={"file": ("a.txt", POLICY.encode())})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_access_token"


async def test_upload_without_a_file_is_a_validation_error(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await api_client.post(DOCUMENTS_URL, headers=headers, data={"title": "x"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_a_file_over_the_size_cap_is_rejected_with_413(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = b"x" * (get_settings().upload_max_bytes + 1)

    response = await upload(api_client, headers, data)

    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"
    assert await document_rows(migrated_engine) == []


async def test_a_huge_body_is_refused_from_its_content_length(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    data = b"x" * (get_settings().upload_max_bytes + 200_000)

    response = await upload(api_client, headers, data)

    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "file_too_large"
    assert body["request_id"] == response.headers["x-request-id"]


async def test_an_image_named_pdf_is_rejected_with_415(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    response = await upload(api_client, headers, png, "report.pdf")

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file_type"
    assert await document_rows(migrated_engine) == []


@pytest.mark.parametrize(
    ("data", "filename", "code"),
    [
        (encrypted_pdf(), "locked.pdf", "encrypted_pdf"),
        (blank_pdf(), "scan.pdf", "no_extractable_text"),
        (b"%PDF-1.4\nnot a real pdf", "broken.pdf", "pdf_unreadable"),
        (b"   \n", "empty.txt", "no_extractable_text"),
    ],
)
async def test_unusable_files_are_rejected_with_422(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    data: bytes,
    filename: str,
    code: str,
) -> None:
    response = await upload(api_client, headers, data, filename)

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert await document_rows(migrated_engine) == []


async def test_a_pdf_with_too_many_pages_is_rejected(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    pdf = blank_pdf(get_settings().upload_max_pages + 1)

    response = await upload(api_client, headers, pdf, "long.pdf")

    assert response.status_code == 422
    assert response.json()["code"] == "too_many_pages"


async def test_text_over_the_character_cap_is_rejected(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    data = b"x" * (get_settings().upload_max_text_chars + 1)

    response = await upload(api_client, headers, data)

    assert response.status_code == 422
    assert response.json()["code"] == "text_too_long"


async def test_the_same_file_twice_is_a_conflict(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = distinct_text("a")
    await upload(api_client, headers, data)

    response = await upload(api_client, headers, data, "renamed.txt")

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_document"
    assert len(await document_rows(migrated_engine)) == 1


async def test_simultaneous_uploads_of_one_file_create_one_document(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = distinct_text("a")

    responses = await asyncio.gather(*(upload(api_client, headers, data) for _ in range(5)))

    assert sorted(response.status_code for response in responses) == [202, 409, 409, 409, 409]
    assert len(await document_rows(migrated_engine)) == 1


async def test_two_users_can_upload_the_same_file(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    data = distinct_text("a")
    other_headers = await auth_headers(api_client, other_account)

    first = await upload(api_client, headers, data)
    second = await upload(api_client, other_headers, data)

    assert (first.status_code, second.status_code) == (202, 202)
    assert len(await document_rows(migrated_engine)) == 2


async def test_the_same_file_can_be_uploaded_again_after_the_first_is_deleted(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = distinct_text("a")
    await upload(api_client, headers, data)
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET deleted_at = now()"))

    response = await upload(api_client, headers, data)

    assert response.status_code == 202


async def test_a_rejected_upload_does_not_use_up_the_duplicate_check(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    await upload(api_client, headers, b"   ", "empty.txt")

    response = await upload(api_client, headers, distinct_text("a"))

    assert response.status_code == 202


async def test_title_defaults_to_the_filename_without_extension(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), "Refund  SOP v2.md")

    document = response.json()["document"]
    assert document["title"] == "Refund SOP v2"
    assert document["mime_type"] == "text/markdown"


async def test_a_given_title_is_trimmed_and_used(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), title="  Refund SOP  ")

    assert response.json()["document"]["title"] == "Refund SOP"


async def test_a_blank_title_falls_back_to_the_filename(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), "sop.txt", title="   ")

    assert response.json()["document"]["title"] == "sop"


async def test_a_title_over_200_characters_is_rejected(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), title="t" * 201)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "title"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\ana\\sop.txt", "sop.txt"),
        ("a" * 300 + ".txt", ("a" * 300 + ".txt")[:255]),
    ],
)
async def test_the_stored_filename_is_a_safe_display_name(
    api_client: AsyncClient, headers: dict[str, str], raw: str, expected: str
) -> None:
    response = await upload(api_client, headers, distinct_text("a"), raw)

    assert response.status_code == 202
    assert response.json()["document"]["filename"] == expected


async def test_upload_writes_one_audit_event(
    api_client: AsyncClient,
    headers: dict[str, str],
    account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    response = await upload(api_client, headers, distinct_text("a"))

    (event,) = await audit_rows(migrated_engine, "document.upload")
    assert str(event.resource_id) == response.json()["document"]["id"]
    assert event.resource_type == "document"
    assert event.metadata == {}
    async with migrated_engine.connect() as connection:
        owner = (await connection.execute(text("SELECT id FROM users"))).scalar_one()
    assert event.actor_id == owner


async def test_rejected_and_duplicate_uploads_write_no_audit_event(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    data = distinct_text("a")
    await upload(api_client, headers, data)
    await upload(api_client, headers, data)
    await upload(api_client, headers, b"\x00\x01", "bad.bin")

    assert len(await audit_rows(migrated_engine, "document.upload")) == 1


async def test_the_eleventh_upload_in_an_hour_is_rate_limited(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    for index in range(10):
        response = await upload(api_client, headers, distinct_text(str(index)))
        assert response.status_code == 202

    response = await upload(api_client, headers, distinct_text("eleven"))

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "retry-after" in response.headers


async def test_the_upload_limit_is_counted_per_user(
    api_client: AsyncClient, headers: dict[str, str], other_account: Account
) -> None:
    for index in range(10):
        await upload(api_client, headers, distinct_text(str(index)))
    other_headers = await auth_headers(api_client, other_account)

    response = await upload(api_client, other_headers, distinct_text("bob"))

    assert response.status_code == 202


async def test_upload_never_logs_document_text(
    api_client: AsyncClient, headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    marker = "ZEBRA-CLAUSE-7731-confidential-refund-rule"
    with caplog.at_level(logging.DEBUG):
        await upload(api_client, headers, f"1.1 {marker}".encode(), "sop.txt")
        await upload(api_client, headers, text_pdf([marker]), "sop.pdf")
        await upload(api_client, headers, f"{marker} \x00".encode(), "binary.txt")

    assert marker not in caplog.text


async def test_the_owner_can_read_their_document(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    created = (await upload(api_client, headers, distinct_text("a"))).json()["document"]

    response = await api_client.get(f"{DOCUMENTS_URL}/{created['id']}", headers=headers)

    assert response.status_code == 200
    # Only the processing result differs from the upload response, which was built before the
    # background task ran.
    processed = {"status": "ready", "chunk_count": 1}
    assert response.json() == {"document": {**created, **processed}}


async def test_another_users_document_looks_like_a_missing_one(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    created = (await upload(api_client, headers, distinct_text("a"))).json()["document"]
    other_headers = await auth_headers(api_client, other_account)

    foreign = await api_client.get(f"{DOCUMENTS_URL}/{created['id']}", headers=other_headers)
    missing = await api_client.get(f"{DOCUMENTS_URL}/{uuid.uuid4()}", headers=other_headers)

    assert foreign.status_code == 404
    assert without_request_id(foreign) == without_request_id(missing)
    assert foreign.json()["code"] == "document_not_found"


async def test_a_deleted_document_looks_like_a_missing_one(
    api_client: AsyncClient, headers: dict[str, str], migrated_engine: AsyncEngine
) -> None:
    created = (await upload(api_client, headers, distinct_text("a"))).json()["document"]
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET deleted_at = now()"))

    response = await api_client.get(f"{DOCUMENTS_URL}/{created['id']}", headers=headers)

    assert response.status_code == 404


async def test_reading_a_document_needs_a_valid_access_token(api_client: AsyncClient) -> None:
    response = await api_client.get(f"{DOCUMENTS_URL}/{uuid.uuid4()}")

    assert response.status_code == 401


async def test_a_malformed_document_id_is_a_validation_error(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await api_client.get(f"{DOCUMENTS_URL}/not-a-uuid", headers=headers)

    assert response.status_code == 422
