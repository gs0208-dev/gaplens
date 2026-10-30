from dataclasses import dataclass
from typing import Any

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import app

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
SAMPLE_PHRASE = "correct horse battery"
WRONG_PHRASE = "wrong horse battery"
# An origin the app trusts, so requests that need the Origin header can send it.
ALLOWED_ORIGIN = get_settings().cors_origins[0]


@dataclass(frozen=True)
class Account:
    email: str
    phrase: str


async def insert_user(
    engine: AsyncEngine, email: str, phrase: str, *, is_active: bool = True
) -> Account:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (email, password_hash, is_active) "
                "VALUES (:email, :password_hash, :is_active)"
            ),
            {"email": email, "password_hash": hash_password(phrase), "is_active": is_active},
        )
    return Account(email, phrase)


def credentials(email: str, phrase: str) -> dict[str, str]:
    return {"email": email, "password": phrase}


async def login_from(ip: str, email: str, phrase: str) -> Response:
    """Send one login request that appears to come from the given IP address."""
    transport = ASGITransport(app=app, client=(ip, 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(LOGIN_URL, json=credentials(email, phrase))


def parse_set_cookie(header: str) -> tuple[str, str, set[str]]:
    name_and_value, *attributes = [part.strip() for part in header.split(";")]
    name, value = name_and_value.split("=", 1)
    return name, value, {attribute.lower() for attribute in attributes}


async def log_in(client: AsyncClient, account: Account) -> str:
    """Log in and return the refresh token from the cookie."""
    response = await client.post(LOGIN_URL, json=credentials(account.email, account.phrase))
    _, token, _ = parse_set_cookie(response.headers["set-cookie"])
    return token


async def log_in_for_access_token(client: AsyncClient, account: Account) -> str:
    response = await client.post(LOGIN_URL, json=credentials(account.email, account.phrase))
    return str(response.json()["access_token"])


def cookie_headers(token: str | None, origin: str | None) -> dict[str, str]:
    """Send the refresh cookie by hand, because httpx will not send a Secure cookie over http."""
    headers: dict[str, str] = {}
    if token is not None:
        headers["Cookie"] = f"refresh_token={token}"
    if origin is not None:
        headers["Origin"] = origin
    return headers


async def refresh(
    client: AsyncClient, token: str | None, *, origin: str | None = ALLOWED_ORIGIN
) -> Response:
    return await client.post(REFRESH_URL, headers=cookie_headers(token, origin))


async def logout(
    client: AsyncClient, token: str | None, *, origin: str | None = ALLOWED_ORIGIN
) -> Response:
    return await client.post(LOGOUT_URL, headers=cookie_headers(token, origin))


async def token_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT id, token_hash, family_id, revoked_at, replaced_by, expires_at "
                "FROM refresh_tokens ORDER BY created_at"
            )
        )
        return list(result)


def without_request_id(response: Response) -> tuple[int, dict[str, Any]]:
    body = response.json()
    body.pop("request_id")
    return response.status_code, body


async def stored_refresh_tokens(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT token_hash, family_id, expires_at, user_agent, ip FROM refresh_tokens")
        )
        return list(result)
