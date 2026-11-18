import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.calls import StructuredResult, call_structured
from app.ai.client import LLMClient
from app.ai.prompts import (
    GAP_REPORT_PROMPT_VERSION,
    DocumentSection,
    build_gap_report_messages,
    load_prompt,
)
from app.ai.schemas import GapReportOut
from app.core.config import get_settings


async def generate_gap_report(
    session: AsyncSession,
    llm: LLMClient,
    *,
    owner_id: uuid.UUID,
    sections: list[DocumentSection],
) -> StructuredResult[GapReportOut]:
    """Send the whole document in one call and return the validated reply, unverified."""
    settings = get_settings()
    return await call_structured(
        session,
        llm,
        owner_id=owner_id,
        purpose="gap_report",
        prompt_version=GAP_REPORT_PROMPT_VERSION,
        system=load_prompt(GAP_REPORT_PROMPT_VERSION),
        messages=build_gap_report_messages(sections),
        output_model=GapReportOut,
        max_tokens=settings.gap_report_max_tokens,
        timeout_seconds=settings.gap_report_timeout_seconds,
    )
