import hashlib
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from app.modules.auth import repository
from tests.api.helpers import (
    LOGIN_URL,
    REGISTER_URL,
    SAMPLE_PHRASE,
    WRONG_PHRASE,
    Account,
    audit_dump,
    audit_rows,
    credentials,
    expire_all_tokens,
    insert_user,
    log_in,
    log_in_for_access_token,
    login_from,
    logout,
    parse_set_cookie,
    refresh,
    token_rows,
)


def digest(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()


async def user_id_of(engine: AsyncEngine, email: str) -> uuid.UUID:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        return result.scalar_one()


COUNT_USERS = text("SELECT count(*) FROM users")
COUNT_REFRESH_TOKENS = text("SELECT count(*) FROM refresh_tokens")


async def count_rows(engine: AsyncEngine, statement: TextClause) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(statement)).scalar_one()


async def test_register_writes_one_audit_event(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    response = await api_client.post(
        REGISTER_URL, json=credentials("ana@example.com", SAMPLE_PHRASE)
    )

    (row,) = await audit_rows(migrated_engine)
    user_id = uuid.UUID(response.json()["user"]["id"])
    assert row.action == "auth.register"
    assert row.actor_id == user_id
    assert row.resource_type == "user"
    assert row.resource_id == user_id
    assert str(row.ip) == "127.0.0.1"
    assert row.request_id == response.headers["X-Request-ID"]
    assert row.metadata == {}


async def test_a_rejected_registration_writes_no_audit_event(
    api_client: AsyncClient, migrated_engine: AsyncEngine
) -> None:
    await api_client.post(REGISTER_URL, json=credentials("ana@example.com", SAMPLE_PHRASE))
    duplicate = await api_client.post(
        REGISTER_URL, json=credentials("ANA@example.com", SAMPLE_PHRASE)
    )
    invalid = await api_client.post(REGISTER_URL, json=credentials("bob@example.com", "short"))

    assert (duplicate.status_code, invalid.status_code) == (409, 422)
    assert len(await audit_rows(migrated_engine)) == 1


async def test_login_writes_one_audit_event(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    response = await api_client.post(LOGIN_URL, json=credentials(account.email, account.phrase))

    (row,) = await audit_rows(migrated_engine)
    assert row.action == "auth.login"
    assert row.actor_id == await user_id_of(migrated_engine, account.email)
    assert str(row.ip) == "127.0.0.1"
    assert row.request_id == response.headers["X-Request-ID"]


async def test_each_kind_of_failed_login_is_recorded_with_its_reason(
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

    assert {r.status_code for r in (wrong_password, unknown_email, disabled_account)} == {401}
    rows = await audit_rows(migrated_engine, "auth.login_failed")
    assert [row.metadata["reason"] for row in rows] == [
        "wrong_password",
        "unknown_email",
        "account_disabled",
    ]
    assert [row.actor_id for row in rows] == [
        await user_id_of(migrated_engine, account.email),
        None,
        await user_id_of(migrated_engine, disabled.email),
    ]
    attempted = [account.email, "nobody@example.com", disabled.email]
    assert [row.metadata["email_sha256"] for row in rows] == [digest(e) for e in attempted]
    dump = await audit_dump(migrated_engine)
    assert not any(email in dump for email in attempted)


async def test_blocked_attempts_write_no_audit_event(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    for number in range(1, 7):
        await login_from(f"10.0.2.{number}", account.email, WRONG_PHRASE)

    assert len(await audit_rows(migrated_engine, "auth.login_failed")) == 5


async def test_logout_is_recorded_once_and_only_when_it_ends_a_login(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in(api_client, account)

    await logout(api_client, token)
    await logout(api_client, token)
    await logout(api_client, None)
    await logout(api_client, "not-a-real-token")

    (row,) = await audit_rows(migrated_engine, "auth.logout")
    assert row.actor_id == await user_id_of(migrated_engine, account.email)
    assert str(row.ip) == "127.0.0.1"


async def test_reusing_a_rotated_token_is_recorded_against_its_family(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    old_token = await log_in(api_client, account)
    await refresh(api_client, old_token)
    family_id = (await token_rows(migrated_engine))[0].family_id

    await refresh(api_client, old_token)

    (row,) = await audit_rows(migrated_engine, "auth.refresh_reuse_detected")
    assert row.actor_id == await user_id_of(migrated_engine, account.email)
    assert row.resource_type == "refresh_token_family"
    assert row.resource_id == family_id
    assert str(row.ip) == "127.0.0.1"


async def test_ordinary_refresh_failures_write_no_reuse_event(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    token = await log_in(api_client, account)
    rotated = await refresh(api_client, token)
    _, current_token, _ = parse_set_cookie(rotated.headers["set-cookie"])
    await refresh(api_client, "not-a-real-token")
    await refresh(api_client, None)
    await expire_all_tokens(migrated_engine)
    await refresh(api_client, current_token)

    assert await audit_rows(migrated_engine, "auth.refresh_reuse_detected") == []


async def test_no_audit_row_contains_a_password_token_or_readable_email(
    api_client: AsyncClient, account: Account, migrated_engine: AsyncEngine
) -> None:
    access_token = await log_in_for_access_token(api_client, account)
    first_token = await log_in(api_client, account)
    rotated = await refresh(api_client, first_token)
    _, second_token, _ = parse_set_cookie(rotated.headers["set-cookie"])
    await api_client.post(LOGIN_URL, json=credentials("nobody@example.com", WRONG_PHRASE))
    await refresh(api_client, first_token)
    await logout(api_client, second_token)

    dump = await audit_dump(migrated_engine)

    # The reuse already ended that login, so the final logout had nothing left to end.
    assert [row.action for row in await audit_rows(migrated_engine)] == [
        "auth.login",
        "auth.login",
        "auth.login_failed",
        "auth.refresh_reuse_detected",
    ]
    for secret in (
        SAMPLE_PHRASE,
        WRONG_PHRASE,
        access_token,
        first_token,
        second_token,
        "nobody@example.com",
        "argon2",
    ):
        assert secret not in dump


@pytest.mark.parametrize(("url", "needs_account"), [(REGISTER_URL, False), (LOGIN_URL, True)])
async def test_the_action_and_its_audit_event_succeed_or_fail_together(
    api_client: AsyncClient,
    migrated_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    needs_account: bool,
) -> None:
    if needs_account:
        await insert_user(migrated_engine, "ana@example.com", SAMPLE_PHRASE)

    async def failing_audit_insert(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(repository, "add_audit_event", failing_audit_insert)

    with pytest.raises(RuntimeError):
        await api_client.post(url, json=credentials("ana@example.com", SAMPLE_PHRASE))

    users = await count_rows(migrated_engine, COUNT_USERS)
    tokens = await count_rows(migrated_engine, COUNT_REFRESH_TOKENS)
    assert (users, tokens) == ((1 if needs_account else 0), 0)
