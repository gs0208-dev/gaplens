import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.calls import call_structured
from app.ai.client import LLMClient
from app.ai.prompts import CHAT_PROMPT_VERSION, PromptSource, build_chat_messages, load_prompt
from app.ai.schemas import ChatAnswerOut, Turn
from app.core.config import get_settings
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.chat import repository
from app.modules.chat.errors import ThreadNotFound
from app.modules.chat.grounding import VerifiedAnswer, not_found, verify_answer
from app.modules.chat.models import ChatMessage
from app.modules.ingestion.embedder import Embedder
from app.modules.retrieval import service as retrieval_service

logger = logging.getLogger(__name__)

# docs/ai-engineering.md: a follow-up question sees the last 4 messages of its thread.
HISTORY_MESSAGES = 4
MAX_TITLE_LENGTH = 80


@dataclass(frozen=True)
class ChatReply:
    thread_id: uuid.UUID
    message: ChatMessage


@dataclass(frozen=True)
class MessageList:
    items: list[ChatMessage]
    next_cursor: str | None


def _history_turns(rows: list[tuple[str, str]]) -> list[Turn]:
    return [
        Turn(role="assistant" if role == "assistant" else "user", content=content)
        for role, content in rows
    ]


async def answer_question(
    session: AsyncSession,
    embedder: Embedder,
    llm: LLMClient,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    question: str,
    thread_id: uuid.UUID | None,
) -> ChatReply:
    # Raises DocumentNotFound (404) or DocumentNotReady (409) before anything else happens.
    chunks = await retrieval_service.retrieve(
        session, embedder, owner_id=owner_id, document_id=document_id, question=question
    )

    history: list[Turn] = []
    if thread_id is not None:
        thread = await repository.get_thread(
            session, owner_id=owner_id, thread_id=thread_id, document_id=document_id
        )
        if thread is None:
            raise ThreadNotFound
        history = _history_turns(
            await repository.recent_messages(
                session, owner_id=owner_id, thread_id=thread_id, limit=HISTORY_MESSAGES
            )
        )

    verified: VerifiedAnswer = not_found()
    if chunks:
        sources = [
            PromptSource(number, chunk.section_label, chunk.heading, chunk.content)
            for number, chunk in enumerate(chunks, start=1)
        ]
        result = await call_structured(
            session,
            llm,
            owner_id=owner_id,
            purpose="chat",
            prompt_version=CHAT_PROMPT_VERSION,
            system=load_prompt(CHAT_PROMPT_VERSION),
            messages=build_chat_messages(question, sources, history),
            output_model=ChatAnswerOut,
            max_tokens=get_settings().chat_max_tokens,
        )
        verified = verify_answer(result.parsed, chunks)

    if thread_id is None:
        # The thread is made only now, so a failed model call leaves no empty thread behind.
        thread = await repository.create_thread(
            session, owner_id=owner_id, document_id=document_id, title=question[:MAX_TITLE_LENGTH]
        )
        thread_id = thread.id

    # Two timestamps taken in order, because both rows are written in one transaction where
    # now() would be identical and the order of question and answer would be undefined.
    asked_at = datetime.now(UTC)
    question_message = ChatMessage(
        thread_id=thread_id,
        role="user",
        content=question,
        grounded=None,
        citations=[],
        created_at=asked_at,
    )
    answer_message = ChatMessage(
        thread_id=thread_id,
        role="assistant",
        content=verified.answer,
        grounded=verified.grounded,
        citations=verified.citations,
        created_at=asked_at + timedelta(microseconds=1),
    )
    await repository.add_messages(session, [question_message, answer_message])
    await repository.touch_thread(session, thread_id=thread_id)
    await session.commit()

    # Event names and counts only, never the question or the answer.
    logger.info(
        "chat answered document_id=%s grounded=%s best_score=%s sources=%d",
        document_id,
        verified.grounded,
        f"{chunks[0].score:.3f}" if chunks else "none",
        len(chunks),
    )
    return ChatReply(thread_id=thread_id, message=answer_message)


async def list_messages(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    thread_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> MessageList:
    thread = await repository.get_thread(session, owner_id=owner_id, thread_id=thread_id)
    if thread is None:
        raise ThreadNotFound
    after = decode_cursor(cursor) if cursor else None
    # One extra row tells whether another page exists (docs/database.md, rule 4).
    rows = await repository.list_messages(
        session, owner_id=owner_id, thread_id=thread_id, after=after, limit=limit + 1
    )
    items = rows[:limit]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id) if len(rows) > limit and items else None
    )
    return MessageList(items=items, next_cursor=next_cursor)
