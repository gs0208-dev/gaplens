import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent


async def add_audit_event(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    ip: str | None,
    request_id: str | None,
    event_metadata: dict[str, Any],
) -> None:
    await session.execute(
        insert(AuditEvent).values(
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            request_id=request_id,
            event_metadata=event_metadata,
        )
    )
