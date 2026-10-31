import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.documents import service as documents_service
from app.modules.ingestion.embedder import Embedder, run_in_embedding_thread
from app.modules.retrieval import repository
from app.modules.retrieval.errors import DocumentNotReady
from app.modules.retrieval.repository import RetrievedChunk


async def retrieve(
    session: AsyncSession,
    embedder: Embedder,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    question: str,
) -> list[RetrievedChunk]:
    """The chunks of a document that best match a question, with their scores.

    Raises DocumentNotFound for a document that is missing, deleted or someone else's (the same
    error for all three), and DocumentNotReady for one that is still processing or failed.
    """
    document = await documents_service.get_document(
        session, owner_id=owner_id, document_id=document_id
    )
    if document.status != "ready":
        raise DocumentNotReady

    settings = get_settings()
    query_embedding = await run_in_embedding_thread(embedder.embed_query, question)
    chunks = await repository.search_chunks(
        session,
        owner_id=owner_id,
        document_id=document_id,
        query_embedding=query_embedding,
        limit=settings.retrieval_top_k,
    )
    # 0.0 means "no cutoff", so a chunk is never dropped by a setting that is switched off.
    if settings.retrieval_min_score > 0:
        chunks = [chunk for chunk in chunks if chunk.score >= settings.retrieval_min_score]
    return chunks
