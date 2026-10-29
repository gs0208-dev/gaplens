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
from app.modules.auth.errors import EmailAlreadyRegistered, InvalidCredentials
from app.modules.auth.models import User

EMAIL_UNIQUE_INDEX = "users_email_lower_uidx"


@dataclass(frozen=True)
class LoginResult:
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
) -> LoginResult:
    if email_failures.is_blocked(email):
        raise RateLimited(retry_after=email_failures.retry_after(email))

    user = await repository.get_user_by_email(session, email)
    # An unknown email is checked against a dummy hash so it takes as long as a wrong password.
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_matches = await run_in_threadpool(verify_password, password_hash, password)

    if user is None or not password_matches or not user.is_active:
        email_failures.record_failure(email)
        raise InvalidCredentials

    settings = get_settings()
    now = datetime.now(UTC)
    refresh_token = generate_refresh_token()
    refresh_token_max_age = settings.refresh_token_days * 24 * 60 * 60
    await repository.create_refresh_token(
        session,
        user_id=user.id,
        # A new family per login. Refresh rotation (S1-4) keeps every token of one login in it.
        family_id=uuid.uuid4(),
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(seconds=refresh_token_max_age),
        user_agent=user_agent,
        ip=ip,
    )
    await repository.mark_login(session, user.id, now)
    await session.commit()

    return LoginResult(
        user=user,
        access_token=create_access_token(user.id, user.role),
        access_token_expires_in=settings.access_token_minutes * 60,
        refresh_token=refresh_token,
        refresh_token_max_age=refresh_token_max_age,
    )
