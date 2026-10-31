import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    chunk_index: int
    section_label: str | None
    heading: str | None
    content: str
    page_start: int | None
    # Cosine similarity: 1.0 is the same direction, 0.0 unrelated.
    score: float


async def search_chunks(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
) -> list[RetrievedChunk]:
    """The chunks of one document that are closest to the question, best first.

    Both ids are in the WHERE clause. document_id alone would be enough to find the rows, since
    it is unique, but with owner_id too a wrong or forged document id can never return another
    user's text, whatever the caller forgot to check. The filter on document_id narrows the
    search to a few hundred rows through document_chunks_doc_index_uidx, which Postgres then
    sorts exactly, so no vector index is needed (ADR-009).
    """
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    result = await session.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.chunk_index,
            DocumentChunk.section_label,
            DocumentChunk.heading,
            DocumentChunk.content,
            DocumentChunk.page_start,
            distance,
        )
        .where(DocumentChunk.document_id == document_id, DocumentChunk.owner_id == owner_id)
        # chunk_index breaks ties, so equal scores always come back in the same order.
        .order_by(distance, DocumentChunk.chunk_index)
        .limit(limit)
    )
    return [
        RetrievedChunk(
            id=row.id,
            chunk_index=row.chunk_index,
            section_label=row.section_label,
            heading=row.heading,
            content=row.content,
            page_start=row.page_start,
            score=1.0 - float(row.distance),
        )
        for row in result
    ]
