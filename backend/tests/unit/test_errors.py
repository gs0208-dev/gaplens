from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import DomainError, register_error_handlers
from app.core.request_id import RequestIdMiddleware


class TeapotError(DomainError):
    status_code = 418
    code = "teapot"
    title = "Short and stout"
    detail = "This server is a teapot."


def build_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)
    register_error_handlers(test_app)

    @test_app.get("/teapot")
    async def teapot() -> None:
        raise TeapotError

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    return test_app


@pytest.fixture
async def error_client() -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False lets the test see the 500 response instead of the exception.
    transport = ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_domain_error_uses_the_problem_format(error_client: AsyncClient) -> None:
    response = await error_client.get("/teapot", headers={"X-Request-ID": "request-id-1234"})

    assert response.status_code == 418
    assert response.json() == {
        "type": "about:blank",
        "title": "Short and stout",
        "status": 418,
        "code": "teapot",
        "detail": "This server is a teapot.",
        "request_id": "request-id-1234",
    }


async def test_unhandled_error_returns_a_generic_500_without_details(
    error_client: AsyncClient,
) -> None:
    response = await error_client.get("/boom")

    assert response.status_code == 500
    problem = response.json()
    assert problem["code"] == "internal_error"
    assert problem["request_id"] == response.headers["X-Request-ID"]
    assert problem["request_id"] != "-"
    assert "internal detail" not in response.text
    assert "Traceback" not in response.text
