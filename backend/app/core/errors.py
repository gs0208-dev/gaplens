import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_id import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """An error a service raises on purpose. Subclasses set the four class attributes."""

    status_code: int = 400
    code: str = "bad_request"
    title: str = "Bad request"
    detail: str = "The request could not be processed."

    def response_headers(self) -> dict[str, str]:
        """Extra headers for the error response. Most errors need none."""
        return {}


class RateLimited(DomainError):
    status_code = 429
    code = "rate_limited"
    title = "Too many requests"
    detail = "Too many attempts. Try again later."

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after

    def response_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after)}


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the error body from docs/api.md."""
    # Read from request.state, not the context variable: the unhandled-error handler runs
    # outside the request id middleware, after the context variable has been reset.
    request_id = getattr(request.state, "request_id", "-")
    content: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "code": code,
        "detail": detail,
        "request_id": request_id,
    }
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return problem_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            headers=exc.response_headers(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Only the field and the message are returned. The submitted value is left out on
        # purpose, because it may be a password.
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return problem_response(
            request,
            status_code=422,
            code="validation_error",
            title="Invalid request",
            detail="Some fields are missing or invalid.",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Only the exception type is logged here. The server already prints the traceback, and
        # the exception message can contain request data.
        logger.error("unhandled exception type=%s", type(exc).__name__)
        return problem_response(
            request,
            status_code=500,
            code="internal_error",
            title="Internal error",
            detail="Something went wrong on our side. Quote the request id if you contact us.",
        )
