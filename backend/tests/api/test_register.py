import asyncio
import logging
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

REGISTER_URL = "/api/v1/auth/register"
SAMPLE_PHRASE = "correct horse battery"
PROBLEM_FIELDS = {"type", "title", "status", "code", "detail", "request_id"}
# Well-formed (labels of 61 characters, domain under 253) but 312 characters in total.
LONG_EMAIL = "a" * 60 + "@" + ".".join(["b" * 61] * 4) + ".com"


def register_body(email: str = "ana@example.com", phrase: str = SAMPLE_PHRASE) -> dict[str, Any]:
    return {"email": email, "password": phrase}


async def user_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT email, password_hash, role FROM users"))
        return list(result)


async def test_register_returns_the_new_user(api_client: AsyncClient) -> None:
    response = await api_client.post(REGISTER_URL, json=register_body())

    assert response.status_code == 201
    user = response.json()["user"]
    assert set(user) == {"id", "email", "role", "created_at"}
    assert user["email"] == "ana@example.com"
    assert user["role"] == "user"
    uuid.UUID(user["id"])


async def test_register_response_never_contains_the_password_or_hash(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(REGISTER_URL, json=register_body())

    assert SAMPLE_PHRASE not in response.text
    assert "argon2" not in response.text


async def test_email_is_trimmed_and_lowercased(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    response = await api_client.post(REGISTER_URL, json=register_body(email=" Ana@Example.COM "))

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "ana@example.com"
    assert [row.email for row in await user_rows(migrated_engine)] == ["ana@example.com"]


async def test_stored_password_is_an_argon2id_hash(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    await api_client.post(REGISTER_URL, json=register_body())

    (row,) = await user_rows(migrated_engine)
    assert row.password_hash.startswith("$argon2id$")
    assert SAMPLE_PHRASE not in row.password_hash


async def test_duplicate_email_returns_409_even_when_the_case_differs(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    await api_client.post(REGISTER_URL, json=register_body(email="ana@example.com"))

    response = await api_client.post(
        REGISTER_URL,
        json=register_body(email="ANA@example.com"),
        headers={"X-Request-ID": "request-id-1234"},
    )

    assert response.status_code == 409
    problem = response.json()
    assert set(problem) == PROBLEM_FIELDS
    assert problem["type"] == "about:blank"
    assert problem["status"] == 409
    assert problem["code"] == "email_already_registered"
    assert problem["request_id"] == "request-id-1234"
    assert response.headers["X-Request-ID"] == "request-id-1234"
    assert len(await user_rows(migrated_engine)) == 1


async def test_simultaneous_registrations_of_one_email_create_exactly_one_user(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    responses = await asyncio.gather(
        *(api_client.post(REGISTER_URL, json=register_body()) for _ in range(5))
    )

    assert sorted(response.status_code for response in responses) == [201, 409, 409, 409, 409]
    assert len(await user_rows(migrated_engine)) == 1


@pytest.mark.parametrize(
    ("length", "expected_status"),
    [(11, 422), (12, 201), (128, 201), (129, 422)],
)
async def test_password_length_limits(
    api_client: AsyncClient, length: int, expected_status: int
) -> None:
    response = await api_client.post(REGISTER_URL, json=register_body(phrase="a" * length))

    assert response.status_code == expected_status


async def test_short_password_error_names_the_field_and_does_not_echo_it(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(REGISTER_URL, json=register_body(phrase="xq7vz9kw2rt"))

    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "validation_error"
    assert set(problem) == PROBLEM_FIELDS | {"errors"}
    assert [error["field"] for error in problem["errors"]] == ["password"]
    assert "xq7vz9kw2rt" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(register_body(email="not-an-email"), id="invalid-email"),
        pytest.param(register_body(email=LONG_EMAIL), id="email-over-254-characters"),
        pytest.param({"email": "ana@example.com"}, id="missing-password"),
        pytest.param({**register_body(), "role": "admin"}, id="unknown-field"),
    ],
)
async def test_invalid_requests_return_422_and_create_no_user(
    api_client: AsyncClient, migrated_engine: AsyncEngine, payload: dict[str, Any]
) -> None:
    response = await api_client.post(REGISTER_URL, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert await user_rows(migrated_engine) == []


async def test_register_does_not_log_the_password_or_hash(
    api_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await api_client.post(REGISTER_URL, json=register_body())

    assert SAMPLE_PHRASE not in caplog.text
    assert "$argon2" not in caplog.text
