from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_allowed_origin
from app.core.rate_limit import LOGIN_LIMIT, REGISTER_LIMIT, limiter
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.cookies import set_refresh_cookie
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# The user agent is only stored for the owner's later reference, so a long one is cut short.
MAX_USER_AGENT_LENGTH = 255


def client_details(request: Request) -> tuple[str | None, str | None]:
    """The user agent and IP address to store with a refresh token."""
    user_agent = request.headers.get("user-agent", "")[:MAX_USER_AGENT_LENGTH] or None
    ip = request.client.host if request.client else None
    return user_agent, ip


def token_response(response: Response, result: service.SessionResult) -> TokenResponse:
    """Set the refresh cookie on the response and build the body shared by login and refresh."""
    set_refresh_cookie(response, result.refresh_token, result.refresh_token_max_age)
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.access_token_expires_in,
        user=UserOut.model_validate(result.user),
    )


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
) -> TokenResponse:
    user_agent, ip = client_details(request)
    result = await service.login(session, body.email, body.password, user_agent=user_agent, ip=ip)
    return token_response(response, result)


# The origin check is a dependency, so it runs before any token is looked at or changed.
@router.post("/refresh", dependencies=[Depends(require_allowed_origin)])
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    user_agent, ip = client_details(request)
    result = await service.refresh_session(session, refresh_token, user_agent=user_agent, ip=ip)
    return token_response(response, result)
