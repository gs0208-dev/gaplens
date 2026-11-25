import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Row, Select, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analysis.citations import VerifiedFinding
from app.modules.analysis.models import Analysis, Finding, FindingCitation

# docs/database.md, rule 5: bulk inserts go in batches of 500 inside one transaction.
INSERT_BATCH_SIZE = 500
ACTIVE_STATUSES = ("queued", "running")


async def create_analysis(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
    prompt_version: str,
    model: str,
) -> Analysis:
    result = await session.execute(
        insert(Analysis)
        .values(
            owner_id=owner_id,
            document_id=document_id,
            prompt_version=prompt_version,
            model=model,
        )
        .returning(Analysis)
    )
    return result.scalar_one()


async def claim_analysis(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> bool:
    """Move an analysis from queued to running. One UPDATE, so only one task can win."""
    result = await session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.owner_id == owner_id,
            Analysis.status == "queued",
        )
        .values(status="running")
        .returning(Analysis.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def finish_analysis(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    analysis_id: uuid.UUID,
    summary: str,
    findings_count: int,
    dropped_findings_count: int,
) -> bool:
    """Mark a running analysis succeeded. False if it was deleted or swept meanwhile."""
    result = await session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.owner_id == owner_id,
            Analysis.status == "running",
        )
        .values(
            status="succeeded",
            summary=summary,
            findings_count=findings_count,
            dropped_findings_count=dropped_findings_count,
            completed_at=func.now(),
        )
        .returning(Analysis.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def fail_analysis(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID, message: str
) -> None:
    await session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.owner_id == owner_id,
            Analysis.status.in_(ACTIVE_STATUSES),
        )
        .values(status="failed", error_message=message, completed_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def insert_findings(
    session: AsyncSession, *, analysis_id: uuid.UUID, findings: list[VerifiedFinding]
) -> None:
    """Store findings in the given order (position) and their citations."""
    finding_rows = [
        {
            "analysis_id": analysis_id,
            "position": position,
            "kind": finding.kind,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "suggested_question": finding.suggested_question,
        }
        for position, finding in enumerate(findings)
    ]
    finding_ids: dict[int, uuid.UUID] = {}
    for start in range(0, len(finding_rows), INSERT_BATCH_SIZE):
        result = await session.execute(
            insert(Finding)
            .values(finding_rows[start : start + INSERT_BATCH_SIZE])
            .returning(Finding.position, Finding.id)
        )
        finding_ids.update({row.position: row.id for row in result})

    citation_rows = [
        {
            "finding_id": finding_ids[position],
            "chunk_id": citation.chunk_id,
            "section_label": citation.section_label,
            "quote": citation.quote,
        }
        for position, finding in enumerate(findings)
        for citation in finding.citations
    ]
    for start in range(0, len(citation_rows), INSERT_BATCH_SIZE):
        await session.execute(
            insert(FindingCitation).values(citation_rows[start : start + INSERT_BATCH_SIZE])
        )


async def get_latest_analysis(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> Analysis | None:
    """The newest analysis of a document, any status. Served by analyses_document_created_idx."""
    result = await session.execute(
        select(Analysis)
        .where(Analysis.document_id == document_id, Analysis.owner_id == owner_id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_analysis(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> Analysis | None:
    result = await session.execute(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


def _finding_rows(owner_id: uuid.UUID) -> Select[*tuple[Any, ...]]:
    # Findings have no owner_id, so the owner is checked on their analysis.
    return (
        select(
            Finding.id,
            Finding.kind,
            Finding.severity,
            Finding.title,
            Finding.description,
            Finding.suggested_question,
            Finding.review_status,
            FindingCitation.chunk_id,
            FindingCitation.section_label,
            FindingCitation.quote,
        )
        .join(Analysis, Analysis.id == Finding.analysis_id)
        .outerjoin(FindingCitation, FindingCitation.finding_id == Finding.id)
        .where(Analysis.owner_id == owner_id)
        .order_by(Finding.position, FindingCitation.id)
    )


async def list_findings(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> list[Row[*tuple[Any, ...]]]:
    """One row per citation (or one per finding without any), in report order."""
    result = await session.execute(
        _finding_rows(owner_id).where(Finding.analysis_id == analysis_id)
    )
    return list(result.all())


async def get_finding(
    session: AsyncSession, *, owner_id: uuid.UUID, finding_id: uuid.UUID
) -> list[Row[*tuple[Any, ...]]]:
    result = await session.execute(_finding_rows(owner_id).where(Finding.id == finding_id))
    return list(result.all())


async def update_review_status(
    session: AsyncSession, *, owner_id: uuid.UUID, finding_id: uuid.UUID, review_status: str
) -> bool:
    owned_analyses = select(Analysis.id).where(Analysis.owner_id == owner_id)
    result = await session.execute(
        update(Finding)
        .where(Finding.id == finding_id, Finding.analysis_id.in_(owned_analyses))
        .values(review_status=review_status)
        .returning(Finding.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def delete_analyses(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Remove a document's analyses; findings and citations go by cascade."""
    await session.execute(
        delete(Analysis)
        .where(Analysis.document_id == document_id, Analysis.owner_id == owner_id)
        .execution_options(synchronize_session=False)
    )


async def fail_stuck_analyses(session: AsyncSession, *, cutoff: datetime, message: str) -> int:
    """Fail every analysis queued or running since before the cutoff. A system job, so not
    scoped to an owner; it returns only a count."""
    result = await session.execute(
        update(Analysis)
        .where(Analysis.status.in_(ACTIVE_STATUSES), Analysis.created_at < cutoff)
        .values(status="failed", error_message=message, completed_at=func.now())
        .returning(Analysis.id)
        .execution_options(synchronize_session=False)
    )
    return len(result.all())
