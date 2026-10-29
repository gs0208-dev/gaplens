from collections.abc import AsyncIterator

from httpx import AsyncClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import app


class HealthySession:
    async def execute(self, statement: object) -> None:
        return None


class BrokenSession:
    async def execute(self, statement: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


async def test_live_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ok_when_database_is_reachable(client: AsyncClient) -> None:
    async def override() -> AsyncIterator[HealthySession]:
        yield HealthySession()

    app.dependency_overrides[get_session] = override

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


async def test_ready_returns_503_when_database_is_down(client: AsyncClient) -> None:
    async def override() -> AsyncIterator[BrokenSession]:
        yield BrokenSession()

    app.dependency_overrides[get_session] = override

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "down"}


async def test_response_carries_a_generated_request_id(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert len(response.headers["X-Request-ID"]) >= 8


async def test_valid_incoming_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "abc12345-test"})

    assert response.headers["X-Request-ID"] == "abc12345-test"


async def test_malformed_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "bad id with spaces!"})

    assert response.headers["X-Request-ID"] != "bad id with spaces!"
