import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Row, delete, func, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentChunk


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


async def soft_delete_document(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Mark one live document of one owner as deleted. False if there was nothing to delete.

    One UPDATE both checks and deletes, so of two simultaneous deletes only one gets a row back,
    and only that one goes on to write an audit event.
    """
    result = await session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def delete_chunks(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Remove the stored text of a document. Served by document_chunks_doc_index_uidx."""
    await session.execute(
        delete(DocumentChunk)
        .where(DocumentChunk.document_id == document_id, DocumentChunk.owner_id == owner_id)
        .execution_options(synchronize_session=False)
    )


async def list_documents(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[Row[*tuple[Any, ...]]]:
    """An owner's live documents, newest first, after the cursor.

    Served by documents_owner_created_idx, whose order and WHERE clause match this query
    (docs/database.md, "Document list"). Only the columns a table shows are read.
    """
    query = select(
        Document.id,
        Document.title,
        Document.status,
        Document.page_count,
        Document.chunk_count,
        Document.created_at,
    ).where(Document.owner_id == owner_id, Document.deleted_at.is_(None))
    if after is not None:
        query = query.where(tuple_(Document.created_at, Document.id) < tuple_(*after))
    result = await session.execute(
        query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)
    )
    return list(result.all())


async def list_chunks(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> list[Row[*tuple[Any, ...]]]:
    """The stored text of one document in reading order, via document_chunks_doc_index_uidx."""
    result = await session.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.chunk_index,
            DocumentChunk.section_label,
            DocumentChunk.heading,
            DocumentChunk.content,
            DocumentChunk.page_start,
        )
        .where(DocumentChunk.document_id == document_id, DocumentChunk.owner_id == owner_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.all())
