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


def _problem(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, str]] | None = None,
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
        status_code=status_code, content=content, headers={REQUEST_ID_HEADER: request_id}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(
            request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
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
        return _problem(
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
        return _problem(
            request,
            status_code=500,
            code="internal_error",
            title="Internal error",
            detail="Something went wrong on our side. Quote the request id if you contact us.",
        )
