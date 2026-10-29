from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import LOGIN_LIMIT, REGISTER_LIMIT, limiter
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.cookies import set_refresh_cookie
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# The user agent is only stored for the owner's later reference, so a long one is cut short.
MAX_USER_AGENT_LENGTH = 255


# slowapi needs the request argument by this exact name to find the client address.
@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_LIMIT)
async def register(
    request: Request,
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    user = await service.register_user(session, body.email, body.password)
    return RegisterResponse(user=UserOut.model_validate(user))


@router.post("/login")
@limiter.limit(LOGIN_LIMIT)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    result = await service.login(
        session,
        body.email,
        body.password,
        user_agent=request.headers.get("user-agent", "")[:MAX_USER_AGENT_LENGTH] or None,
        ip=request.client.host if request.client else None,
    )
    set_refresh_cookie(response, result.refresh_token, result.refresh_token_max_age)
    return LoginResponse(
        access_token=result.access_token,
        expires_in=result.access_token_expires_in,
        user=UserOut.model_validate(result.user),
    )
