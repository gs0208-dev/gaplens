import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.ai.budget import ensure_within_budget, start_of_utc_day, tokens_used_since
from app.ai.errors import DailyBudgetExceeded
from app.core.config import get_settings

NOW = datetime(2026, 11, 26, 18, 30, 15, tzinfo=UTC)


async def add_user(engine: AsyncEngine, email: str) -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"),
            {"e": email},
        )
        return result.scalar_one()


async def add_call(
    engine: AsyncEngine,
    owner_id: uuid.UUID | None,
    *,
    at: datetime,
    input_tokens: int | None,
    output_tokens: int | None,
    status: str = "ok",
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO llm_calls (owner_id, purpose, model, prompt_version, input_tokens, "
                "output_tokens, status, created_at) VALUES (:owner, 'chat', 'm', 'v', :i, :o, "
                ":status, :at)"
            ),
            {"owner": owner_id, "i": input_tokens, "o": output_tokens, "status": status, "at": at},
        )


async def used(engine: AsyncEngine, owner_id: uuid.UUID) -> int:
    async with async_sessionmaker(engine)() as session:
        return await tokens_used_since(session, owner_id=owner_id, since=start_of_utc_day(NOW))


async def check(engine: AsyncEngine, owner_id: uuid.UUID, now: datetime = NOW) -> None:
    async with async_sessionmaker(engine)() as session:
        await ensure_within_budget(session, owner_id=owner_id, now=now)


def test_the_day_starts_at_midnight_utc_whatever_the_time_zone_of_the_clock() -> None:
    india = datetime(2026, 11, 27, 2, 0, tzinfo=UTC).astimezone(ZoneInfo("Asia/Kolkata"))

    assert start_of_utc_day(india) == datetime(2026, 11, 27, tzinfo=UTC)


async def test_only_todays_calls_of_this_user_are_counted(migrated_engine: AsyncEngine) -> None:
    owner = await add_user(migrated_engine, "a@example.com")
    other = await add_user(migrated_engine, "b@example.com")
    midnight = start_of_utc_day(NOW)
    await add_call(migrated_engine, owner, at=midnight, input_tokens=100, output_tokens=20)
    await add_call(migrated_engine, owner, at=NOW, input_tokens=1000, output_tokens=300)
    await add_call(
        migrated_engine,
        owner,
        at=midnight - timedelta(seconds=1),
        input_tokens=50_000,
        output_tokens=0,
    )
    await add_call(migrated_engine, other, at=NOW, input_tokens=70_000, output_tokens=0)
    await add_call(migrated_engine, None, at=NOW, input_tokens=90_000, output_tokens=0)

    assert await used(migrated_engine, owner) == 1420


async def test_failed_attempts_count_and_missing_counts_add_nothing(
    migrated_engine: AsyncEngine,
) -> None:
    owner = await add_user(migrated_engine, "a@example.com")
    await add_call(
        migrated_engine, owner, at=NOW, input_tokens=800, output_tokens=200, status="invalid_output"
    )
    await add_call(
        migrated_engine, owner, at=NOW, input_tokens=None, output_tokens=None, status="timeout"
    )
    await add_call(migrated_engine, owner, at=NOW, input_tokens=40, output_tokens=None)

    assert await used(migrated_engine, owner) == 1040


async def test_a_user_with_no_calls_has_used_nothing(migrated_engine: AsyncEngine) -> None:
    owner = await add_user(migrated_engine, "a@example.com")

    assert await used(migrated_engine, owner) == 0


async def test_a_call_is_allowed_below_the_budget_and_refused_at_it(
    migrated_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "daily_token_budget", 1000)
    owner = await add_user(migrated_engine, "a@example.com")
    await add_call(migrated_engine, owner, at=NOW, input_tokens=999, output_tokens=0)

    await check(migrated_engine, owner)

    await add_call(migrated_engine, owner, at=NOW, input_tokens=1, output_tokens=0)
    with pytest.raises(DailyBudgetExceeded) as refused:
        await check(migrated_engine, owner)

    # 18:30:15 UTC to midnight is 5 h 29 min 45 s.
    assert refused.value.retry_after == 5 * 3600 + 29 * 60 + 45
    assert refused.value.response_headers() == {"Retry-After": str(refused.value.retry_after)}
    assert (refused.value.status_code, refused.value.code) == (429, "daily_budget_exceeded")


async def test_the_budget_is_fresh_the_next_day(
    migrated_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "daily_token_budget", 1000)
    owner = await add_user(migrated_engine, "a@example.com")
    await add_call(migrated_engine, owner, at=NOW, input_tokens=5000, output_tokens=0)

    await check(migrated_engine, owner, now=start_of_utc_day(NOW) + timedelta(days=1))
