import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.helpers import ME_URL, Account, log_in_for_access_token, without_request_id
from tests.tokens import make_token, make_unsigned_token


async def get_me(client: AsyncClient, token: str | None, *, scheme: str = "Bearer") -> Response:
    headers = {} if token is None else {"Authorization": f"{scheme} {token}"}
    return await client.get(ME_URL, headers=headers)


async def test_me_returns_the_signed_in_user(api_client: AsyncClient, account: Account) -> None:
    token = await log_in_for_access_token(api_client, account)

    response = await get_me(api_client, token)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"user"}
    assert set(body["user"]) == {"id", "email", "role", "created_at"}
    assert body["user"]["email"] == account.email
    assert body["user"]["role"] == "user"
    assert "argon2" not in response.text


async def test_every_kind_of_bad_token_gets_the_same_401(
    api_client: AsyncClient, account: Account
) -> None:
    valid_token = await log_in_for_access_token(api_client, account)
    # The forged tokens name a real user, so only a failure of token verification can reject them.
    real_user = (await get_me(api_client, valid_token)).json()["user"]["id"]
    bad_requests: dict[str, Response] = {
        "no header": await get_me(api_client, None),
        "wrong scheme": await get_me(api_client, valid_token, scheme="Basic"),
        "expired": await get_me(
            api_client, make_token(sub=real_user, exp=datetime.now(UTC) - timedelta(minutes=1))
        ),
        "wrong signature": await get_me(
            api_client, make_token(sub=real_user, key="a-different-key-" * 3)
        ),
        "alg none": await get_me(api_client, make_unsigned_token(sub=real_user)),
        "wrong audience": await get_me(api_client, make_token(sub=real_user, aud="someone-else")),
        "garbage": await get_me(api_client, "not-a-token"),
        "unknown user": await get_me(api_client, make_token(sub=str(uuid.uuid4()))),
    }

    baseline = without_request_id(bad_requests["no header"])
    assert baseline[0] == 401
    assert baseline[1]["code"] == "invalid_access_token"
    for name, response in bad_requests.items():
        assert without_request_id(response) == baseline, name
        assert response.headers["WWW-Authenticate"] == "Bearer", name


async def test_a_valid_token_stops_working_when_the_user_is_deleted(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in_for_access_token(api_client, account)
    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users"))

    response = await get_me(api_client, token)

    assert response.status_code == 401


async def test_a_valid_token_stops_working_when_the_user_is_disabled(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in_for_access_token(api_client, account)
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE users SET is_active = false"))

    response = await get_me(api_client, token)

    assert response.status_code == 401


async def test_the_role_comes_from_the_database_not_from_the_token(
    api_client: AsyncClient, account: Account
) -> None:
    login_token = await log_in_for_access_token(api_client, account)
    user_id = (await get_me(api_client, login_token)).json()["user"]["id"]
    forged_role_token = make_token(sub=user_id, role="admin")

    response = await get_me(api_client, forged_role_token)

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"


async def test_me_does_not_log_the_token(
    api_client: AsyncClient, account: Account, caplog: pytest.LogCaptureFixture
) -> None:
    token = await log_in_for_access_token(api_client, account)

    with caplog.at_level(logging.DEBUG):
        await get_me(api_client, token)
        await get_me(api_client, make_token(sub=str(uuid.uuid4()), aud="someone-else"))

    assert token not in caplog.text
