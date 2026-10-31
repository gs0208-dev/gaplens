import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.rate_limit import UPLOAD_LIMIT, limiter, user_key
from app.db.session import get_session
from app.modules.documents import service
from app.modules.documents.schemas import DocumentOut, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


# slowapi needs the request argument by this exact name to find the client address.
@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(UPLOAD_LIMIT, key_func=user_key)
async def upload_document(
    request: Request,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=service.MAX_TITLE_LENGTH)] = None,
) -> DocumentResponse:
    ip = request.client.host if request.client else None
    document = await service.upload_document(
        session,
        owner_id=current_user.id,
        upload=file,
        title=(title or "").strip() or None,
        ip=ip,
    )
    return DocumentResponse(document=DocumentOut.model_validate(document))


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
