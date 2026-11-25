import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.client import LLMClient
from app.ai.errors import LLMInvalidOutput, LLMTimeout, LLMUnavailable
from app.ai.gap_report import generate_gap_report
from app.ai.prompts import GAP_REPORT_PROMPT_VERSION, DocumentSection
from app.core.config import get_settings
from app.modules.analysis import repository
from app.modules.analysis.citations import ChunkText, verify_report
from app.modules.analysis.errors import (
    FAILURE_GENERIC,
    FAILURE_INVALID_OUTPUT,
    FAILURE_STUCK,
    FAILURE_TIMEOUT,
    FAILURE_UNAVAILABLE,
    AnalysisAlreadyRunning,
    AnalysisNotFound,
    FindingNotFound,
)
from app.modules.analysis.models import Analysis
from app.modules.analysis.ordering import order_findings
from app.modules.analysis.schemas import CitationOut, FindingDetail
from app.modules.audit.service import record_audit_event
from app.modules.documents import service as documents_service
from app.modules.documents.errors import DocumentNotReady

logger = logging.getLogger(__name__)

ANALYSIS_START = "analysis.start"
ONE_ACTIVE_INDEX = "analyses_one_active_per_document_uidx"

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class Report:
    analysis: Analysis
    findings: list[FindingDetail]


def _violates_one_active_index(error: IntegrityError) -> bool:
    cause = error.orig.__cause__ if error.orig is not None else None
    return getattr(cause, "constraint_name", None) == ONE_ACTIVE_INDEX


async def start_analysis(
    session: AsyncSession,
    llm: LLMClient,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    ip: str | None,
) -> Analysis:
    document = await documents_service.get_document(
        session, owner_id=owner_id, document_id=document_id
    )
    if document.status != "ready":
        raise DocumentNotReady
    try:
        analysis = await repository.create_analysis(
            session,
            owner_id=owner_id,
            document_id=document_id,
            prompt_version=GAP_REPORT_PROMPT_VERSION,
            model=llm.model,
        )
    except IntegrityError as error:
        # Insert first and let the partial unique index decide, so two starts cannot both pass.
        if not _violates_one_active_index(error):
            raise
        raise AnalysisAlreadyRunning from error
    await record_audit_event(
        session,
        action=ANALYSIS_START,
        actor_id=owner_id,
        resource_type="analysis",
        resource_id=analysis.id,
        ip=ip,
    )
    await session.commit()
    return analysis


def _failure_message(error: Exception) -> str:
    if isinstance(error, LLMTimeout):
        return FAILURE_TIMEOUT
    if isinstance(error, LLMUnavailable):
        return FAILURE_UNAVAILABLE
    if isinstance(error, LLMInvalidOutput):
        return FAILURE_INVALID_OUTPUT
    return FAILURE_GENERIC


async def run_analysis(
    session_factory: SessionFactory,
    llm: LLMClient,
    *,
    analysis_id: uuid.UUID,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Generate, verify and store one gap report, then mark it succeeded or failed.

    Runs after the start response has been sent, so it opens its own sessions and must never
    raise: an analysis has to end in succeeded or failed, not stay running.
    """
    started = time.perf_counter()
    try:
        async with session_factory() as session:
            if not await repository.claim_analysis(
                session, owner_id=owner_id, analysis_id=analysis_id
            ):
                logger.info("analysis not claimed analysis_id=%s", analysis_id)
                return
            rows = await documents_service.list_chunks(
                session, owner_id=owner_id, document_id=document_id
            )
            await session.commit()
        chunks = [ChunkText(r.id, r.chunk_index, r.section_label, r.content) for r in rows]
        sections = [DocumentSection(r.section_label, r.heading, r.content) for r in rows]

        # No session is busy during the model call; this one only collects the llm_calls row.
        async with session_factory() as session:
            result = await generate_gap_report(session, llm, owner_id=owner_id, sections=sections)
            verified = verify_report(result.parsed, chunks)
            findings, duplicates = order_findings(verified.findings, chunks)
            # The report, its status and the llm_calls row are committed together.
            finished = await repository.finish_analysis(
                session,
                owner_id=owner_id,
                analysis_id=analysis_id,
                summary=verified.summary,
                findings_count=len(findings),
                dropped_findings_count=verified.counts.findings_dropped,
            )
            if finished:
                await repository.insert_findings(
                    session, analysis_id=analysis_id, findings=findings
                )
            await session.commit()
    except Exception as error:
        # Only the type is logged. The message of an exception can quote the document.
        logger.warning(
            "analysis failed analysis_id=%s error_type=%s", analysis_id, type(error).__name__
        )
        await _mark_failed(session_factory, analysis_id, owner_id, _failure_message(error))
        return

    if not finished:
        logger.warning("analysis no longer running analysis_id=%s", analysis_id)
        return
    logger.info(
        "analysis.finished analysis_id=%s findings=%d dropped=%d duplicates=%d quotes=%d "
        "quotes_verified=%d duration_ms=%d",
        analysis_id,
        len(findings),
        verified.counts.findings_dropped,
        duplicates,
        verified.counts.quotes_total,
        verified.counts.quotes_verified,
        (time.perf_counter() - started) * 1000,
    )


async def _mark_failed(
    session_factory: SessionFactory, analysis_id: uuid.UUID, owner_id: uuid.UUID, message: str
) -> None:
    try:
        async with session_factory() as session:
            await repository.fail_analysis(
                session, owner_id=owner_id, analysis_id=analysis_id, message=message
            )
            await session.commit()
    except Exception as error:
        # If even this fails (the database is down), the sweep will fail the analysis later.
        logger.error(
            "could not mark analysis failed analysis_id=%s error_type=%s",
            analysis_id,
            type(error).__name__,
        )


def _group_findings(rows: list[Row[*tuple[Any, ...]]]) -> list[FindingDetail]:
    """Fold one row per citation into one finding with a list of citations, keeping order."""
    findings: dict[uuid.UUID, FindingDetail] = {}
    for row in rows:
        finding = findings.get(row.id)
        if finding is None:
            finding = FindingDetail(
                id=row.id,
                kind=row.kind,
                severity=row.severity,
                title=row.title,
                description=row.description,
                suggested_question=row.suggested_question,
                review_status=row.review_status,
                citations=[],
            )
            findings[row.id] = finding
        if row.chunk_id is not None:
            finding.citations.append(
                CitationOut(chunk_id=row.chunk_id, section_label=row.section_label, quote=row.quote)
            )
    return list(findings.values())


async def _report(session: AsyncSession, owner_id: uuid.UUID, analysis: Analysis) -> Report:
    rows = await repository.list_findings(session, owner_id=owner_id, analysis_id=analysis.id)
    return Report(analysis=analysis, findings=_group_findings(rows))


async def get_latest_report(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> Report:
    # A deleted or foreign document is a 404 for the document, as on every document route.
    await documents_service.get_document(session, owner_id=owner_id, document_id=document_id)
    analysis = await repository.get_latest_analysis(
        session, owner_id=owner_id, document_id=document_id
    )
    if analysis is None:
        raise AnalysisNotFound
    return await _report(session, owner_id, analysis)


async def get_report(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> Report:
    analysis = await repository.get_analysis(session, owner_id=owner_id, analysis_id=analysis_id)
    if analysis is None:
        raise AnalysisNotFound
    return await _report(session, owner_id, analysis)


async def set_review_status(
    session: AsyncSession, *, owner_id: uuid.UUID, finding_id: uuid.UUID, review_status: str
) -> FindingDetail:
    updated = await repository.update_review_status(
        session, owner_id=owner_id, finding_id=finding_id, review_status=review_status
    )
    if not updated:
        raise FindingNotFound
    await session.commit()
    (finding,) = _group_findings(
        await repository.get_finding(session, owner_id=owner_id, finding_id=finding_id)
    )
    return finding


async def delete_for_document(
    session: AsyncSession, owner_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Remove a document's analyses in the caller's transaction (document delete)."""
    await repository.delete_analyses(session, owner_id=owner_id, document_id=document_id)


async def sweep_stuck_analyses(session_factory: SessionFactory) -> int:
    """Fail analyses abandoned in queued or running, for example by a restart."""
    cutoff = datetime.now(UTC) - timedelta(minutes=get_settings().stuck_after_minutes)
    async with session_factory() as session:
        count = await repository.fail_stuck_analyses(session, cutoff=cutoff, message=FAILURE_STUCK)
        await session.commit()
    if count:
        logger.warning("failed stuck analyses count=%d", count)
    return count
