import uuid

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document


async def create_document(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    title: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    page_count: int | None,
) -> Document:
    # RETURNING gives back the database-generated id, status and timestamps in the same round trip.
    result = await session.execute(
        insert(Document)
        .values(
            owner_id=owner_id,
            title=title,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            page_count=page_count,
        )
        .returning(Document)
    )
    return result.scalar_one()


async def get_document(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    """One live document of one owner. Another owner's id and a deleted document give None."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
