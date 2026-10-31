import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentChunk

# docs/database.md, rule 5: bulk inserts go in batches of 500 inside one transaction.
INSERT_BATCH_SIZE = 500


async def claim_document(
    session: AsyncSession, *, document_id: uuid.UUID, owner_id: uuid.UUID
) -> bool:
    """Move a document from uploaded to processing. False if it is not there to be claimed.

    One UPDATE checks and changes the status, so if two tasks ever start for one document the
    database lets only one win (the same idea as the refresh token claim, ADR-022).
    """
    result = await session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.status == "uploaded",
            Document.deleted_at.is_(None),
        )
        .values(status="processing")
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def mark_ready(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    chunk_count: int,
    embedding_model: str,
) -> bool:
    """Finish a document that is still processing. False if it was failed or deleted meanwhile."""
    result = await session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.status == "processing",
            Document.deleted_at.is_(None),
        )
        .values(
            status="ready",
            chunk_count=chunk_count,
            embedding_model=embedding_model,
            error_message=None,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def mark_failed(
    session: AsyncSession, *, document_id: uuid.UUID, owner_id: uuid.UUID, message: str
) -> None:
    await session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.status == "processing",
        )
        .values(status="failed", error_message=message)
        .execution_options(synchronize_session=False)
    )


async def insert_chunks(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        await session.execute(insert(DocumentChunk).values(rows[start : start + INSERT_BATCH_SIZE]))


async def fail_stuck_documents(session: AsyncSession, *, cutoff: datetime, message: str) -> int:
    """Fail every document that has sat in uploaded or processing since before the cutoff.

    A system job, not a user request, so it is not scoped to an owner and returns only a count.
    """
    result = await session.execute(
        update(Document)
        .where(
            Document.status.in_(("uploaded", "processing")),
            Document.updated_at < cutoff,
            Document.deleted_at.is_(None),
        )
        .values(status="failed", error_message=message)
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )
    return len(result.all())
