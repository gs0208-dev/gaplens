import hashlib
import logging
from typing import Any

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.core.security import DUMMY_PASSWORD_HASH
from app.modules.auth import service
from tests.api.helpers import (
    LOGIN_URL,
    REGISTER_URL,
    SAMPLE_PHRASE,
    WRONG_PHRASE,
    Account,
    credentials,
    insert_user,
    login_from,
    parse_set_cookie,
    stored_refresh_tokens,
)


async def test_login_returns_the_access_token_and_user(
    api_client: AsyncClient, account: Account
) -> None:
    response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "expires_in", "user"}
    assert body["expires_in"] == 900
    assert set(body["user"]) == {"id", "email", "role", "created_at"}
    assert body["user"]["email"] == account.email


async def test_access_token_carries_the_documented_claims(
    api_client: AsyncClient, account: Account
) -> None:
    response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    settings = get_settings()
    body = response.json()
    claims = jwt.decode(
        body["access_token"],
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert claims["sub"] == body["user"]["id"]
    assert claims["role"] == "user"
    assert claims["exp"] - claims["iat"] == 15 * 60


async def test_refresh_cookie_has_the_required_attributes(
    api_client: AsyncClient, account: Account
) -> None:
    response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    name, value, attributes = parse_set_cookie(response.headers["set-cookie"])
    assert name == "refresh_token"
    assert len(value) >= 43
    assert {
        "httponly",
        "secure",
        "samesite=strict",
        "path=/api/v1/auth",
        f"max-age={7 * 24 * 60 * 60}",
    } <= attributes


async def test_refresh_token_is_only_stored_as_a_hash(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    _, token, _ = parse_set_cookie(response.headers["set-cookie"])
    assert token not in response.text
    (row,) = await stored_refresh_tokens(migrated_engine)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row.token_hash


async def test_login_records_client_details_and_last_login(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    await api_client.post(
        LOGIN_URL,
        json=credentials(account.email, account.phrase),
        headers={"User-Agent": "test-agent/1.0"},
    )

    (row,) = await stored_refresh_tokens(migrated_engine)
    assert row.user_agent == "test-agent/1.0"
    assert str(row.ip) == "127.0.0.1"
    async with migrated_engine.connect() as connection:
        last_login_at = (await connection.execute(text("SELECT last_login_at FROM users"))).scalar()
    assert last_login_at is not None


async def test_each_login_starts_a_new_token_family(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    first = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))
    second = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    assert first.headers["set-cookie"] != second.headers["set-cookie"]
    rows = await stored_refresh_tokens(migrated_engine)
    assert len(rows) == 2
    assert rows[0].family_id != rows[1].family_id


async def test_login_ignores_email_case_and_padding(
    api_client: AsyncClient, account: Account
) -> None:
    response = await api_client.post(
        LOGIN_URL, json=credentials(" ANA@Example.COM ", account.phrase)
    )

    assert response.status_code == 200


async def test_failed_logins_are_indistinguishable_and_set_no_cookie(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    disabled = await insert_user(migrated_engine, "off@example.com", SAMPLE_PHRASE, is_active=False)

    wrong_password = await api_client.post(LOGIN_URL, json=credentials(account.email, WRONG_PHRASE))
    unknown_email = await api_client.post(
        LOGIN_URL, json=credentials("nobody@example.com", WRONG_PHRASE)
    )
    disabled_account = await api_client.post(
        LOGIN_URL, json=credentials(disabled.email, disabled.phrase)
    )

    def without_request_id(response: Response) -> tuple[int, dict[str, Any]]:
        body = response.json()
        body.pop("request_id")
        return response.status_code, body

    assert without_request_id(wrong_password)[0] == 401
    assert without_request_id(wrong_password)[1]["code"] == "invalid_credentials"
    assert (
        without_request_id(wrong_password)
        == without_request_id(unknown_email)
        == without_request_id(disabled_account)
    )
    for response in (wrong_password, unknown_email, disabled_account):
        assert "set-cookie" not in response.headers


async def test_unknown_email_still_verifies_against_the_dummy_hash(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified_hashes: list[str] = []
    real_verify = service.verify_password

    def spy(password_hash: str, password: str) -> bool:
        verified_hashes.append(password_hash)
        return real_verify(password_hash, password)

    monkeypatch.setattr(service, "verify_password", spy)

    await api_client.post(LOGIN_URL, json=credentials("nobody@example.com", WRONG_PHRASE))

    assert verified_hashes == [DUMMY_PASSWORD_HASH]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"email": "not-an-email", "password": WRONG_PHRASE}, id="invalid-email"),
        pytest.param({"email": "ana@example.com", "password": ""}, id="empty-password"),
        pytest.param({"email": "ana@example.com", "password": "a" * 129}, id="password-too-long"),
        pytest.param({"email": "ana@example.com"}, id="missing-password"),
        pytest.param(
            {"email": "ana@example.com", "password": WRONG_PHRASE, "remember": True},
            id="unknown-field",
        ),
    ],
)
async def test_malformed_login_requests_return_422(
    api_client: AsyncClient, payload: dict[str, Any]
) -> None:
    response = await api_client.post(LOGIN_URL, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_login_is_limited_to_five_requests_per_minute_per_ip(
    api_client: AsyncClient,
) -> None:
    responses = [
        await api_client.post(LOGIN_URL, json=credentials(f"user{n}@example.com", WRONG_PHRASE))
        for n in range(6)
    ]

    assert [response.status_code for response in responses] == [401] * 5 + [429]
    assert responses[-1].headers["Retry-After"] == "60"
    problem = responses[-1].json()
    assert problem["code"] == "rate_limited"
    assert problem["request_id"] == responses[-1].headers["X-Request-ID"]


async def test_five_failures_for_one_email_block_it_even_from_other_ips(
    api_client: AsyncClient, account: Account
) -> None:
    responses = [await login_from(f"10.0.0.{n}", account.email, WRONG_PHRASE) for n in range(1, 7)]

    assert [response.status_code for response in responses] == [401] * 5 + [429]
    assert responses[-1].json()["code"] == "rate_limited"
    assert 0 < int(responses[-1].headers["Retry-After"]) <= 15 * 60


async def test_successful_logins_do_not_count_toward_the_email_limit(
    api_client: AsyncClient, account: Account
) -> None:
    attempts = [WRONG_PHRASE] * 4 + [account.phrase] * 3 + [WRONG_PHRASE] * 2
    responses = [
        await login_from(f"10.0.1.{n}", account.email, phrase)
        for n, phrase in enumerate(attempts, start=1)
    ]

    assert [response.status_code for response in responses] == [401] * 4 + [200] * 3 + [401, 429]


async def test_register_is_limited_to_five_requests_per_hour_per_ip(
    api_client: AsyncClient,
) -> None:
    responses = [
        await api_client.post(REGISTER_URL, json=credentials(f"user{n}@example.com", SAMPLE_PHRASE))
        for n in range(6)
    ]

    assert [response.status_code for response in responses] == [201] * 5 + [429]


async def test_login_does_not_log_the_password_or_tokens(
    api_client: AsyncClient, account: Account, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    _, refresh_token, _ = parse_set_cookie(response.headers["set-cookie"])
    assert account.phrase not in caplog.text
    assert response.json()["access_token"] not in caplog.text
    assert refresh_token not in caplog.text
