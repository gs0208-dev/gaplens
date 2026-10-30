import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from tests.api.helpers import (
    ALLOWED_ORIGIN,
    LOGIN_URL,
    REFRESH_URL,
    Account,
    credentials,
    parse_set_cookie,
)

REQUIRED_COOKIE_ATTRIBUTES = {
    "httponly",
    "secure",
    "samesite=strict",
    "path=/api/v1/auth",
    f"max-age={7 * 24 * 60 * 60}",
}


async def log_in(client: AsyncClient, account: Account) -> str:
    """Log in and return the refresh token from the cookie."""
    response = await client.post(LOGIN_URL, json=credentials(account.email, account.phrase))
    _, token, _ = parse_set_cookie(response.headers["set-cookie"])
    return token


async def refresh(
    client: AsyncClient, token: str | None, *, origin: str | None = ALLOWED_ORIGIN
) -> Response:
    """Send the refresh cookie by hand, because httpx will not send a Secure cookie over http."""
    headers: dict[str, str] = {}
    if token is not None:
        headers["Cookie"] = f"refresh_token={token}"
    if origin is not None:
        headers["Origin"] = origin
    return await client.post(REFRESH_URL, headers=headers)


async def token_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT id, token_hash, family_id, revoked_at, replaced_by, expires_at "
                "FROM refresh_tokens ORDER BY created_at"
            )
        )
        return list(result)


async def expire_all_tokens(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE refresh_tokens SET expires_at = now() - interval '1 day'")
        )


def without_request_id(response: Response) -> tuple[int, dict[str, Any]]:
    body = response.json()
    body.pop("request_id")
    return response.status_code, body


async def test_refresh_returns_a_new_token_pair(api_client: AsyncClient, account: Account) -> None:
    old_token = await log_in(api_client, account)

    response = await refresh(api_client, old_token)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "expires_in", "user"}
    assert body["expires_in"] == 900
    assert body["user"]["email"] == account.email
    settings = get_settings()
    claims = jwt.decode(
        body["access_token"],
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert claims["sub"] == body["user"]["id"]
    name, new_token, attributes = parse_set_cookie(response.headers["set-cookie"])
    assert name == "refresh_token"
    assert new_token != old_token
    assert attributes >= REQUIRED_COOKIE_ATTRIBUTES
    assert new_token not in response.text


async def test_rotation_revokes_the_old_token_and_links_the_new_one(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    old_token = await log_in(api_client, account)

    response = await refresh(api_client, old_token)

    _, new_token, _ = parse_set_cookie(response.headers["set-cookie"])
    old_row, new_row = await token_rows(migrated_engine)
    assert old_row.revoked_at is not None
    assert old_row.replaced_by == new_row.id
    assert new_row.revoked_at is None
    assert new_row.family_id == old_row.family_id
    assert new_row.token_hash == hashlib.sha256(new_token.encode()).hexdigest()
    seven_days_from_now = datetime.now(UTC) + timedelta(days=7)
    assert abs(new_row.expires_at - seven_days_from_now) < timedelta(minutes=1)


async def test_the_new_token_can_be_refreshed_again(
    api_client: AsyncClient, account: Account
) -> None:
    token = await log_in(api_client, account)

    for _ in range(3):
        response = await refresh(api_client, token)
        assert response.status_code == 200
        _, token, _ = parse_set_cookie(response.headers["set-cookie"])


async def test_reusing_a_rotated_token_revokes_the_whole_family(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    old_token = await log_in(api_client, account)
    rotated = await refresh(api_client, old_token)
    _, newer_token, _ = parse_set_cookie(rotated.headers["set-cookie"])
    other_login_token = await log_in(api_client, account)

    reuse = await refresh(api_client, old_token)
    newer_after_reuse = await refresh(api_client, newer_token)
    other_login_after = await refresh(api_client, other_login_token)

    assert reuse.status_code == 401
    assert reuse.json()["code"] == "invalid_refresh_token"
    assert newer_after_reuse.status_code == 401
    assert other_login_after.status_code == 200
    first_family = (await token_rows(migrated_engine))[0].family_id
    rows_of_first_login = [
        row for row in await token_rows(migrated_engine) if row.family_id == first_family
    ]
    assert len(rows_of_first_login) == 2
    assert all(row.revoked_at is not None for row in rows_of_first_login)


async def test_missing_unknown_and_expired_tokens_fail_identically_and_clear_the_cookie(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    expired_token = await log_in(api_client, account)
    await expire_all_tokens(migrated_engine)

    missing = await refresh(api_client, None)
    unknown = await refresh(api_client, "not-a-real-token")
    expired = await refresh(api_client, expired_token)

    assert without_request_id(missing)[0] == 401
    assert without_request_id(missing)[1]["code"] == "invalid_refresh_token"
    assert without_request_id(missing) == without_request_id(unknown)
    assert without_request_id(missing) == without_request_id(expired)
    for response in (missing, unknown, expired):
        name, _, attributes = parse_set_cookie(response.headers["set-cookie"])
        assert name == "refresh_token"
        assert {"max-age=0", "path=/api/v1/auth"} <= attributes


async def test_an_expired_token_is_not_treated_as_reuse(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    expired_token = await log_in(api_client, account)
    await expire_all_tokens(migrated_engine)

    await refresh(api_client, expired_token)

    (row,) = await token_rows(migrated_engine)
    assert row.revoked_at is None


async def test_a_disabled_user_cannot_refresh_and_loses_the_family(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in(api_client, account)
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE users SET is_active = false"))

    response = await refresh(api_client, token)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_refresh_token"
    rows = await token_rows(migrated_engine)
    assert all(row.revoked_at is not None for row in rows)


@pytest.mark.parametrize(
    "bad_origin",
    [
        pytest.param(None, id="missing"),
        pytest.param("null", id="null"),
        pytest.param("https://evil.example", id="not-on-the-list"),
        pytest.param(ALLOWED_ORIGIN + ".evil.example", id="lookalike"),
    ],
)
async def test_a_bad_origin_is_rejected_without_using_up_the_token(
    api_client: AsyncClient, account: Account, bad_origin: str | None
) -> None:
    token = await log_in(api_client, account)

    rejected = await refresh(api_client, token, origin=bad_origin)
    accepted = await refresh(api_client, token)

    assert rejected.status_code == 403
    assert rejected.json()["code"] == "origin_not_allowed"
    assert "set-cookie" not in rejected.headers
    assert accepted.status_code == 200


async def test_simultaneous_refreshes_of_one_token_allow_only_one_and_revoke_the_family(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in(api_client, account)

    responses = await asyncio.gather(refresh(api_client, token), refresh(api_client, token))

    assert sorted(response.status_code for response in responses) == [200, 401]
    rows = await token_rows(migrated_engine)
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)


async def test_refresh_does_not_log_tokens(
    api_client: AsyncClient, account: Account, caplog: pytest.LogCaptureFixture
) -> None:
    old_token = await log_in(api_client, account)

    with caplog.at_level(logging.DEBUG):
        response = await refresh(api_client, old_token)

    _, new_token, _ = parse_set_cookie(response.headers["set-cookie"])
    assert old_token not in caplog.text
    assert new_token not in caplog.text
    assert response.json()["access_token"] not in caplog.text
