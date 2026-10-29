import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken, User


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


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
    user_agent: str | None,
    ip: str | None,
) -> None:
    await session.execute(
        insert(RefreshToken).values(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
    )


async def mark_login(session: AsyncSession, user_id: uuid.UUID, logged_in_at: datetime) -> None:
    await session.execute(update(User).where(User.id == user_id).values(last_login_at=logged_in_at))
