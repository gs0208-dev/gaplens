from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    # RETURNING gives back the database-generated id and timestamps in the same round trip.
    result = await session.execute(
        insert(User).values(email=email, password_hash=password_hash).returning(User)
    )
    return result.scalar_one()
