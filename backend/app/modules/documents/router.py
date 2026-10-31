import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import CurrentUser
from app.core.rate_limit import UPLOAD_LIMIT, limiter, user_key
from app.db.session import get_session, get_session_factory
from app.modules.documents import service
from app.modules.documents.schemas import DocumentOut, DocumentResponse
from app.modules.ingestion import service as ingestion_service
from app.modules.ingestion.embedder import Embedder, get_embedder

router = APIRouter(prefix="/documents", tags=["documents"])


# slowapi needs the request argument by this exact name to find the client address.
@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(UPLOAD_LIMIT, key_func=user_key)
async def upload_document(
    request: Request,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=service.MAX_TITLE_LENGTH)] = None,
) -> DocumentResponse:
    ip = request.client.host if request.client else None
    stored = await service.upload_document(
        session,
        owner_id=current_user.id,
        upload=file,
        title=(title or "").strip() or None,
        ip=ip,
    )
    # Runs after the response is sent. The response is built first, so it says "uploaded".
    response = DocumentResponse(document=DocumentOut.model_validate(stored.document))
    background_tasks.add_task(
        ingestion_service.process_document,
        session_factory,
        embedder,
        document_id=stored.document.id,
        owner_id=current_user.id,
        data=stored.data,
        mime_type=stored.document.mime_type,
    )
    return response


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    document = await service.get_document(
        session, owner_id=current_user.id, document_id=document_id
    )
    return DocumentResponse(document=DocumentOut.model_validate(document))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    request: Request,
    document_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    ip = request.client.host if request.client else None
    await service.delete_document(session, owner_id=current_user.id, document_id=document_id, ip=ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
