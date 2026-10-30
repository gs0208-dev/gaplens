import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import request_id_var
from app.modules.auth import repository

# The names are listed in docs/security.md. Keep the two in step.
REGISTER = "auth.register"
LOGIN = "auth.login"
LOGIN_FAILED = "auth.login_failed"
LOGOUT = "auth.logout"
REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"


def email_digest(email: str) -> str:
    """A fingerprint of an email address, so repeated attempts on one address can be matched
    without storing the address itself, or a password typed into the email box by mistake."""
    return hashlib.sha256(email.encode()).hexdigest()


async def record_audit_event(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    ip: str | None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the caller's transaction. The caller commits.

    Sharing the transaction means the row exists if and only if the action it describes
    happened. Never put a password, a token or a readable email address in `metadata`.
    """
    request_id = request_id_var.get()
    await repository.add_audit_event(
        session,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        # "-" is the logging placeholder for "no request", not a real id.
        request_id=None if request_id == "-" else request_id,
        event_metadata=metadata or {},
    )
