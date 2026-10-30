from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import InvalidAccessTokenError, verify_access_token
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.models import User

# auto_error is off so a missing or wrong-scheme header gets our error format, not FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False)


class OriginNotAllowed(DomainError):
    status_code = 403
    code = "origin_not_allowed"
    title = "Origin not allowed"
    detail = "This request did not come from an allowed origin."


class InvalidAccessToken(DomainError):
    # One error for a missing, expired, forged and unknown-user token, so the response never
    # says which it was.
    status_code = 401
    code = "invalid_access_token"
    title = "Invalid access token"
    detail = "The access token is missing, invalid or expired."

    def response_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": "Bearer"}


def require_allowed_origin(request: Request) -> None:
    """Reject cookie-authenticated requests that do not come from one of our own pages.

    SameSite=Strict already keeps browsers from sending the cookie cross-site. This is the
    second layer. Browsers always send Origin on a POST, so a missing header means a script,
    and it is rejected too. The comparison is exact: scheme, host and port must all match.
    """
    origin = request.headers.get("origin")
    if origin is None or origin not in get_settings().cors_origins:
        raise OriginNotAllowed


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """The signed-in user, from the access token in the Authorization header.

    The token is only trusted to say who the user is. The user is loaded on every request, so a
    deleted or disabled account stops working at once, and the role always comes from the
    database, never from the token.
    """
    if credentials is None:
        raise InvalidAccessToken
    try:
        user_id = verify_access_token(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise InvalidAccessToken from error
    user = await service.get_active_user(session, user_id)
    if user is None:
        raise InvalidAccessToken
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
