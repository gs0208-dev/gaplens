import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import DailyBudgetExceeded
from app.ai.models import LlmCall
from app.core.config import get_settings


def start_of_utc_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def tokens_used_since(session: AsyncSession, *, owner_id: uuid.UUID, since: datetime) -> int:
    """Input plus output tokens of every call the user made since a moment, failed ones too.

    Served by llm_calls_owner_created_idx. A row without counts (a timeout) adds nothing.
    """
    tokens = func.coalesce(LlmCall.input_tokens, 0) + func.coalesce(LlmCall.output_tokens, 0)
    result = await session.execute(
        select(func.coalesce(func.sum(tokens), 0)).where(
            LlmCall.owner_id == owner_id, LlmCall.created_at >= since
        )
    )
    return int(result.scalar_one())


async def ensure_within_budget(
    session: AsyncSession, *, owner_id: uuid.UUID, now: datetime | None = None
) -> None:
    """Refuse a model call once the user's tokens for today (UTC) reach the daily budget.

    Calls already running are not seen, so a user can go over by those; the endpoint limits
    and one active analysis per document keep that small.
    """
    now = now or datetime.now(UTC)
    day_start = start_of_utc_day(now)
    used = await tokens_used_since(session, owner_id=owner_id, since=day_start)
    if used >= get_settings().daily_token_budget:
        seconds_left = (day_start + timedelta(days=1) - now).total_seconds()
        raise DailyBudgetExceeded(retry_after=max(1, math.ceil(seconds_left)))
