from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.schemas import RegisterRequest, RegisterResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> RegisterResponse:
    user = await service.register_user(session, body.email, body.password)
    return RegisterResponse(user=UserOut.model_validate(user))
