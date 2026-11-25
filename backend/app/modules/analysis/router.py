import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.client import LLMClient, get_llm_client
from app.api.deps import CurrentUser
from app.core.rate_limit import ANALYSIS_LIMIT, limiter, user_key
from app.db.session import get_session, get_session_factory
from app.modules.analysis import service
from app.modules.analysis.schemas import (
    AnalysisOut,
    AnalysisResponse,
    FindingResponse,
    ReviewStatusUpdate,
)

router = APIRouter(tags=["analyses"])


def _response(report: service.Report) -> AnalysisResponse:
    analysis = AnalysisOut.model_validate(report.analysis)
    return AnalysisResponse(analysis=analysis.model_copy(update={"findings": report.findings}))


# slowapi needs the request argument by this exact name to find the client address.
@router.post("/documents/{document_id}/analyses", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(ANALYSIS_LIMIT, key_func=user_key)
async def start_analysis(
    request: Request,
    document_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    background_tasks: BackgroundTasks,
) -> AnalysisResponse:
    ip = request.client.host if request.client else None
    analysis = await service.start_analysis(
        session, llm, owner_id=current_user.id, document_id=document_id, ip=ip
    )
    # Built before the task runs, so it says "queued".
    response = _response(service.Report(analysis=analysis, findings=[]))
    background_tasks.add_task(
        service.run_analysis,
        session_factory,
        llm,
        analysis_id=analysis.id,
        owner_id=current_user.id,
        document_id=document_id,
    )
    return response


@router.get("/documents/{document_id}/analyses/latest")
async def get_latest_analysis(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisResponse:
    report = await service.get_latest_report(
        session, owner_id=current_user.id, document_id=document_id
    )
    return _response(report)


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisResponse:
    report = await service.get_report(session, owner_id=current_user.id, analysis_id=analysis_id)
    return _response(report)


@router.patch("/findings/{finding_id}")
async def update_finding(
    finding_id: uuid.UUID,
    body: ReviewStatusUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FindingResponse:
    finding = await service.set_review_status(
        session, owner_id=current_user.id, finding_id=finding_id, review_status=body.review_status
    )
    return FindingResponse(finding=finding)
