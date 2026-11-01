import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.api.deps import CurrentUser
from app.core.rate_limit import CHAT_LIMIT, limiter, user_key
from app.db.session import get_session
from app.modules.chat import service
from app.modules.chat.schemas import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    MessagePage,
    ThreadOut,
    ThreadPage,
)
from app.modules.ingestion.embedder import Embedder, get_embedder

router = APIRouter(tags=["chat"])


# slowapi needs the request argument by this exact name to find the client address.
@router.post("/documents/{document_id}/chat")
@limiter.limit(CHAT_LIMIT, key_func=user_key)
async def chat(
    request: Request,
    document_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> ChatResponse:
    reply = await service.answer_question(
        session,
        embedder,
        llm,
        owner_id=current_user.id,
        document_id=document_id,
        question=body.question,
        thread_id=body.thread_id,
    )
    return ChatResponse(thread_id=reply.thread_id, message=MessageOut.model_validate(reply.message))


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MessagePage:
    page = await service.list_messages(
        session, owner_id=current_user.id, thread_id=thread_id, cursor=cursor, limit=limit
    )
    return MessagePage(
        items=[MessageOut.model_validate(message) for message in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/documents/{document_id}/threads")
async def list_threads(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ThreadPage:
    page = await service.list_threads(
        session, owner_id=current_user.id, document_id=document_id, cursor=cursor, limit=limit
    )
    return ThreadPage(
        items=[ThreadOut.model_validate(row) for row in page.items], next_cursor=page.next_cursor
    )
