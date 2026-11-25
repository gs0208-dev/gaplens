import pytest
from httpx import AsyncClient

from tests.api.helpers import (
    DOCUMENTS_URL,
    ME_URL,
    Account,
    auth_headers,
)

# One count per user shared by every /api/v1 route.
API_LIMIT = 120


async def use_up_the_api_limit(
    client: AsyncClient, headers: dict[str, str], count: int = API_LIMIT
) -> None:
    for _ in range(count):
        assert (await client.get(DOCUMENTS_URL, headers=headers)).status_code == 200


async def test_the_121st_request_in_a_minute_on_any_route_is_refused_in_the_usual_format(
    api_client: AsyncClient, headers: dict[str, str]
) -> None:
    await use_up_the_api_limit(api_client, headers)

    response = await api_client.get(ME_URL, headers=headers)

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "rate_limited"
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["retry-after"] == "60"


async def test_the_default_limit_is_counted_per_user(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
) -> None:
    other_headers = await auth_headers(api_client, other_account)
    await use_up_the_api_limit(api_client, headers)

    assert (await api_client.get(DOCUMENTS_URL, headers=headers)).status_code == 429
    assert (await api_client.get(DOCUMENTS_URL, headers=other_headers)).status_code == 200


async def test_requests_without_a_token_are_counted_per_ip_address(
    api_client: AsyncClient,
) -> None:
    for _ in range(API_LIMIT):
        assert (await api_client.get(ME_URL)).status_code == 401

    response = await api_client.get(DOCUMENTS_URL)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
async def test_the_health_probes_are_never_limited(api_client: AsyncClient, path: str) -> None:
    for _ in range(API_LIMIT + 5):
        assert (await api_client.get(path)).status_code == 200
