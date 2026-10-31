import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.modules.ingestion import repository
from app.modules.ingestion.chunker import Chunk, chunk_document
from app.modules.ingestion.embedder import Embedder, run_in_embedding_thread
from app.modules.ingestion.errors import (
    GENERIC_FAILURE_MESSAGE,
    STUCK_MESSAGE,
    NothingToStore,
    ProcessingError,
    TooManySections,
)
from app.modules.ingestion.structure import extract_document

logger = logging.getLogger(__name__)

# docs/ai-engineering.md: passages are embedded in batches of 32.
EMBED_BATCH_SIZE = 32

SessionFactory = async_sessionmaker[AsyncSession]


def _prepare_chunks(data: bytes, mime_type: str) -> list[Chunk]:
    return chunk_document(extract_document(data, mime_type))


def text_to_embed(chunk: Chunk) -> str:
    """The heading goes in front so a clause is embedded with the section it belongs to. The
    stored content stays raw, so a quote from it matches the original document."""
    return f"{chunk.heading}\n{chunk.content}" if chunk.heading else chunk.content


async def _embed_all(embedder: Embedder, chunks: list[Chunk]) -> list[list[float]]:
    texts = [text_to_embed(chunk) for chunk in chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(await run_in_embedding_thread(embedder.embed_passages, batch))
    return vectors


async def process_document(
    session_factory: SessionFactory,
    embedder: Embedder,
    *,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: bytes,
    mime_type: str,
) -> None:
    """Extract, chunk, embed and store one uploaded document, then mark it ready or failed.

    Runs after the upload response has been sent, so it opens its own sessions and must never
    raise: a document has to end in ready or failed, not stay in processing.
    """
    started = time.perf_counter()
    async with session_factory() as session:
        if not await repository.claim_document(session, document_id=document_id, owner_id=owner_id):
            logger.info("document not claimed document_id=%s", document_id)
            return
        await session.commit()

    try:
        settings = get_settings()
        chunks = await run_in_threadpool(_prepare_chunks, data, mime_type)
        if not chunks:
            raise NothingToStore
        if len(chunks) > settings.max_chunks_per_document:
            raise TooManySections
        vectors = await _embed_all(embedder, chunks)
        rows = [
            {
                "document_id": document_id,
                "owner_id": owner_id,
                "chunk_index": chunk.chunk_index,
                "section_label": chunk.section_label,
                "heading": chunk.heading,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "page_start": chunk.page_start,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        async with session_factory() as session:
            # One transaction: the chunks and the ready status appear together or not at all.
            finished = await repository.mark_ready(
                session,
                document_id=document_id,
                owner_id=owner_id,
                chunk_count=len(rows),
                embedding_model=settings.embedding_model,
            )
            if finished:
                await repository.insert_chunks(session, rows)
                await session.commit()
        if not finished:
            logger.warning("document no longer processing document_id=%s", document_id)
            return
    except Exception as error:
        # Only the type is logged. The message of an exception can quote the document.
        logger.warning(
            "document processing failed document_id=%s error_type=%s",
            document_id,
            type(error).__name__,
        )
        message = (
            error.safe_message if isinstance(error, ProcessingError) else GENERIC_FAILURE_MESSAGE
        )
        await _mark_failed(session_factory, document_id, owner_id, message)
        return

    logger.info(
        "document ready document_id=%s chunks=%d duration_ms=%d",
        document_id,
        len(rows),
        (time.perf_counter() - started) * 1000,
    )


async def _mark_failed(
    session_factory: SessionFactory, document_id: uuid.UUID, owner_id: uuid.UUID, message: str
) -> None:
    try:
        async with session_factory() as session:
            await repository.mark_failed(
                session, document_id=document_id, owner_id=owner_id, message=message
            )
            await session.commit()
    except Exception as error:
        # If even this fails (the database is down), the sweep will fail the document later.
        logger.error(
            "could not mark document failed document_id=%s error_type=%s",
            document_id,
            type(error).__name__,
        )


async def sweep_stuck_documents(session_factory: SessionFactory) -> int:
    """Fail documents abandoned in uploaded or processing, for example by a restart."""
    cutoff = datetime.now(UTC) - timedelta(minutes=get_settings().stuck_after_minutes)
    async with session_factory() as session:
        count = await repository.fail_stuck_documents(session, cutoff=cutoff, message=STUCK_MESSAGE)
        await session.commit()
    if count:
        logger.warning("failed stuck documents count=%d", count)
    return count


async def run_sweeper(session_factory: SessionFactory) -> None:
    """Sweep now and then until cancelled. An error in one round must not end the loop."""
    interval_seconds = get_settings().sweep_interval_minutes * 60
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sweep_stuck_documents(session_factory)
        except Exception as error:
            logger.error("sweep failed error_type=%s", type(error).__name__)
