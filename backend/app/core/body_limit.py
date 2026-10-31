from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import FileTooLarge, problem_response

# Multipart framing (boundaries, headers, the title field) adds a little to the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class BodySizeLimitMiddleware:
    """Refuses an oversized upload from its Content-Length header, before the body is read.

    Starlette reads and spools the whole multipart body before the route runs, so a size check
    in the route cannot stop a huge upload from being buffered. Browsers and normal clients
    always send Content-Length for a form upload. A client that streams without it is not
    stopped here; the host's own request limit covers that (Sprint 4, docs/security.md).
    """

    def __init__(self, app: ASGIApp, *, path: str, max_bytes: int) -> None:
        self.app = app
        self.path = path
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == self.path:
            declared = _declared_length(scope)
            if declared is not None and declared > self.max_bytes:
                error = FileTooLarge()
                response = problem_response(
                    Request(scope),
                    status_code=error.status_code,
                    code=error.code,
                    title=error.title,
                    detail=error.detail,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
