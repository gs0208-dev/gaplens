import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chat.models import ChatMessage, ChatThread


async def create_thread(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID, title: str
) -> ChatThread:
    result = await session.execute(
        insert(ChatThread)
        .values(owner_id=owner_id, document_id=document_id, title=title)
        .returning(ChatThread)
    )
    return result.scalar_one()


async def get_thread(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    thread_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
) -> ChatThread | None:
    """One thread of one owner, optionally only if it belongs to the given document."""
    query = select(ChatThread).where(ChatThread.id == thread_id, ChatThread.owner_id == owner_id)
    if document_id is not None:
        query = query.where(ChatThread.document_id == document_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def recent_messages(
    session: AsyncSession, *, owner_id: uuid.UUID, thread_id: uuid.UUID, limit: int
) -> list[tuple[str, str]]:
    """The last `limit` messages of a thread as (role, content), oldest first.

    Served by chat_messages_thread_created_idx, read backwards. The join to the thread is there
    so the owner is checked in the same query that reads the messages.
    """
    result = await session.execute(
        select(ChatMessage.role, ChatMessage.content)
        .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
        .where(ChatMessage.thread_id == thread_id, ChatThread.owner_id == owner_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    return [(row.role, row.content) for row in reversed(result.all())]


async def add_messages(session: AsyncSession, messages: list[ChatMessage]) -> None:
    session.add_all(messages)
    # Flush sends the INSERTs now, so the database-generated ids are loaded.
    await session.flush()


async def touch_thread(session: AsyncSession, *, thread_id: uuid.UUID) -> None:
    await session.execute(
        update(ChatThread)
        .where(ChatThread.id == thread_id)
        .values(updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def list_messages(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    thread_id: uuid.UUID,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[ChatMessage]:
    """Messages oldest first, after the cursor. Keyset pagination (docs/database.md)."""
    query = (
        select(ChatMessage)
        .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
        .where(ChatMessage.thread_id == thread_id, ChatThread.owner_id == owner_id)
    )
    if after is not None:
        query = query.where(tuple_(ChatMessage.created_at, ChatMessage.id) > tuple_(*after))
    result = await session.execute(
        query.order_by(ChatMessage.created_at, ChatMessage.id).limit(limit)
    )
    return list(result.scalars())
