import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuditEvent, RefreshToken, User


@dataclass(frozen=True)
class ClaimedToken:
    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID


@dataclass(frozen=True)
class RevokedToken:
    user_id: uuid.UUID
    family_id: uuid.UUID


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    # RETURNING gives back the database-generated id and timestamps in the same round trip.
    result = await session.execute(
        insert(User).values(email=email, password_hash=password_hash).returning(User)
    )
    return result.scalar_one()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    # Comparing lower(email) is what lets this query use the users_email_lower_uidx index.
    result = await session.execute(select(User).where(func.lower(User.email) == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
    user_agent: str | None,
    ip: str | None,
) -> uuid.UUID:
    result = await session.execute(
        insert(RefreshToken)
        .values(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        .returning(RefreshToken.id)
    )
    return result.scalar_one()


async def claim_refresh_token(
    session: AsyncSession, token_hash: str, now: datetime
) -> ClaimedToken | None:
    """Revoke a usable token and return it, or return None if there is no usable token.

    One UPDATE both checks and revokes. If two requests present the same token at once, the
    database lets only one of them change the row, so a token can never be rotated twice.
    Served by the unique index refresh_tokens_token_hash_uidx.
    """
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken.id, RefreshToken.user_id, RefreshToken.family_id)
        .execution_options(synchronize_session=False)
    )
    row = result.one_or_none()
    return ClaimedToken(id=row.id, user_id=row.user_id, family_id=row.family_id) if row else None


async def find_revoked_token(session: AsyncSession, token_hash: str) -> RevokedToken | None:
    """The owner and family of a token that exists and was already revoked, otherwise None."""
    result = await session.execute(
        select(RefreshToken.user_id, RefreshToken.family_id).where(
            RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_not(None)
        )
    )
    row = result.one_or_none()
    return RevokedToken(user_id=row.user_id, family_id=row.family_id) if row else None


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    """Revoke every still-active token of one login. Served by refresh_tokens_family_id_idx."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )


async def revoke_family_of_token(
    session: AsyncSession, token_hash: str, now: datetime
) -> uuid.UUID | None:
    """Revoke every still-active token of the login that the given token belongs to.

    Returns the owner's user id, or None if nothing was active to revoke (an unknown token, or
    a login that had already ended). It works even if the given token is an old, already-rotated
    one, because it looks the family up first. Served by refresh_tokens_token_hash_uidx for the
    lookup and refresh_tokens_family_id_idx for the update.
    """
    family_of_token = select(RefreshToken.family_id).where(RefreshToken.token_hash == token_hash)
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_of_token.scalar_subquery(),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .returning(RefreshToken.user_id)
        .execution_options(synchronize_session=False)
    )
    return result.scalars().first()


async def link_replacement(
    session: AsyncSession, old_token_id: uuid.UUID, new_token_id: uuid.UUID
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == old_token_id)
        .values(replaced_by=new_token_id)
        .execution_options(synchronize_session=False)
    )


async def add_audit_event(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    ip: str | None,
    request_id: str | None,
    event_metadata: dict[str, Any],
) -> None:
    await session.execute(
        insert(AuditEvent).values(
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            request_id=request_id,
            event_metadata=event_metadata,
        )
    )


async def mark_login(session: AsyncSession, user_id: uuid.UUID, logged_in_at: datetime) -> None:
    await session.execute(update(User).where(User.id == user_id).values(last_login_at=logged_in_at))
