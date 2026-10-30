import logging

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.helpers import (
    ALLOWED_ORIGIN,
    Account,
    log_in,
    logout,
    parse_set_cookie,
    refresh,
    token_rows,
)


def assert_cookie_is_cleared(response: Response) -> None:
    name, _, attributes = parse_set_cookie(response.headers["set-cookie"])
    assert name == "refresh_token"
    assert {"max-age=0", "path=/api/v1/auth"} <= attributes


async def test_logout_returns_204_clears_the_cookie_and_revokes_the_login(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    first_token = await log_in(api_client, account)
    rotated = await refresh(api_client, first_token)
    _, current_token, _ = parse_set_cookie(rotated.headers["set-cookie"])

    response = await logout(api_client, current_token)

    assert response.status_code == 204
    assert response.content == b""
    assert_cookie_is_cleared(response)
    assert all(row.revoked_at is not None for row in await token_rows(migrated_engine))
    assert (await refresh(api_client, current_token)).status_code == 401


async def test_logging_out_with_an_older_token_still_ends_the_whole_login(
    api_client: AsyncClient, account: Account
) -> None:
    old_token = await log_in(api_client, account)
    rotated = await refresh(api_client, old_token)
    _, current_token, _ = parse_set_cookie(rotated.headers["set-cookie"])

    response = await logout(api_client, old_token)

    assert response.status_code == 204
    assert (await refresh(api_client, current_token)).status_code == 401


async def test_logout_leaves_other_logins_of_the_same_user_alone(
    api_client: AsyncClient, account: Account
) -> None:
    laptop_token = await log_in(api_client, account)
    phone_token = await log_in(api_client, account)

    await logout(api_client, laptop_token)

    assert (await refresh(api_client, phone_token)).status_code == 200


async def test_logout_is_quiet_when_there_is_nothing_to_revoke(
    api_client: AsyncClient, account: Account
) -> None:
    token = await log_in(api_client, account)
    await logout(api_client, token)

    responses = [
        await logout(api_client, None),
        await logout(api_client, "not-a-real-token"),
        await logout(api_client, token),
    ]

    for response in responses:
        assert response.status_code == 204
        assert_cookie_is_cleared(response)


@pytest.mark.parametrize(
    "bad_origin",
    [
        pytest.param(None, id="missing"),
        pytest.param("null", id="null"),
        pytest.param("https://evil.example", id="not-on-the-list"),
    ],
)
async def test_a_bad_origin_is_rejected_and_the_login_stays_active(
    api_client: AsyncClient, account: Account, bad_origin: str | None
) -> None:
    token = await log_in(api_client, account)

    rejected = await logout(api_client, token, origin=bad_origin)

    assert rejected.status_code == 403
    assert rejected.json()["code"] == "origin_not_allowed"
    assert "set-cookie" not in rejected.headers
    assert (await refresh(api_client, token, origin=ALLOWED_ORIGIN)).status_code == 200


async def test_logout_does_not_log_the_refresh_token(
    api_client: AsyncClient, account: Account, caplog: pytest.LogCaptureFixture
) -> None:
    token = await log_in(api_client, account)

    with caplog.at_level(logging.DEBUG):
        await logout(api_client, token)

    assert token not in caplog.text
