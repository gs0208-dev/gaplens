import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import RateLimited
from app.core.rate_limit import email_failures
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth import repository
from app.modules.auth.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
)
from app.modules.auth.models import User

EMAIL_UNIQUE_INDEX = "users_email_lower_uidx"


@dataclass(frozen=True)
class SessionResult:
    """What login and refresh both hand back: a new access token and a new refresh token."""

    user: User
    access_token: str
    access_token_expires_in: int
    refresh_token: str
    refresh_token_max_age: int


def _violates_email_index(error: IntegrityError) -> bool:
    # The driver's own exception carries the index name. Matching on message text would break
    # if the database were set to another language.
    cause = error.orig.__cause__ if error.orig is not None else None
    return getattr(cause, "constraint_name", None) == EMAIL_UNIQUE_INDEX


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    # Hashing is CPU heavy, so it runs in a worker thread and does not block other requests.
    password_hash = await run_in_threadpool(hash_password, password)
    try:
        user = await repository.create_user(session, email, password_hash)
    except IntegrityError as error:
        # Insert first and let the unique index decide. A "look first" check could let two
        # simultaneous requests for the same email both succeed.
        if not _violates_email_index(error):
            raise
        raise EmailAlreadyRegistered from error
    await session.commit()
    return user


async def login(
    session: AsyncSession,
    email: str,
    password: str,
    *,
    user_agent: str | None,
    ip: str | None,
) -> SessionResult:
    if email_failures.is_blocked(email):
        raise RateLimited(retry_after=email_failures.retry_after(email))

    user = await repository.get_user_by_email(session, email)
    # An unknown email is checked against a dummy hash so it takes as long as a wrong password.
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_matches = await run_in_threadpool(verify_password, password_hash, password)

    if user is None or not password_matches or not user.is_active:
        email_failures.record_failure(email)
        raise InvalidCredentials

    now = datetime.now(UTC)
    # A new family per login. Every token that refresh rotation hands out stays in it.
    result = await _issue_session(
        session, user, family_id=uuid.uuid4(), replaces=None, user_agent=user_agent, ip=ip, now=now
    )
    await repository.mark_login(session, user.id, now)
    await session.commit()
    return result


async def refresh_session(
    session: AsyncSession,
    refresh_token: str | None,
    *,
    user_agent: str | None,
    ip: str | None,
) -> SessionResult:
    if not refresh_token:
        raise InvalidRefreshToken

    now = datetime.now(UTC)
    token_hash = hash_refresh_token(refresh_token)
    claimed = await repository.claim_refresh_token(session, token_hash, now)

    if claimed is None:
        # Nothing usable. A token that exists but was already revoked is being presented a
        # second time, which means a copy of it exists somewhere it should not. Revoke the
        # whole login. The commit must come before the error, because the error rolls back.
        family_id = await repository.find_revoked_token_family(session, token_hash)
        if family_id is not None:
            await repository.revoke_family(session, family_id, now)
            await session.commit()
        raise InvalidRefreshToken

    user = await repository.get_user_by_id(session, claimed.user_id)
    if user is None or not user.is_active:
        await repository.revoke_family(session, claimed.family_id, now)
        await session.commit()
        raise InvalidRefreshToken

    result = await _issue_session(
        session,
        user,
        family_id=claimed.family_id,
        replaces=claimed.id,
        user_agent=user_agent,
        ip=ip,
        now=now,
    )
    await session.commit()
    return result


async def _issue_session(
    session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID,
    replaces: uuid.UUID | None,
    user_agent: str | None,
    ip: str | None,
    now: datetime,
) -> SessionResult:
    """Create a refresh token in the given family and an access token. The caller commits."""
    settings = get_settings()
    refresh_token = generate_refresh_token()
    refresh_token_max_age = settings.refresh_token_days * 24 * 60 * 60
    new_token_id = await repository.create_refresh_token(
        session,
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(seconds=refresh_token_max_age),
        user_agent=user_agent,
        ip=ip,
    )
    if replaces is not None:
        await repository.link_replacement(session, replaces, new_token_id)
    return SessionResult(
        user=user,
        access_token=create_access_token(user.id, user.role),
        access_token_expires_in=settings.access_token_minutes * 60,
        refresh_token=refresh_token,
        refresh_token_max_age=refresh_token_max_age,
    )
