from fastapi import Request

from app.core.config import get_settings
from app.core.errors import DomainError


class OriginNotAllowed(DomainError):
    status_code = 403
    code = "origin_not_allowed"
    title = "Origin not allowed"
    detail = "This request did not come from an allowed origin."


def require_allowed_origin(request: Request) -> None:
    """Reject cookie-authenticated requests that do not come from one of our own pages.

    SameSite=Strict already keeps browsers from sending the cookie cross-site. This is the
    second layer. Browsers always send Origin on a POST, so a missing header means a script,
    and it is rejected too. The comparison is exact: scheme, host and port must all match.
    """
    origin = request.headers.get("origin")
    if origin is None or origin not in get_settings().cors_origins:
        raise OriginNotAllowed
