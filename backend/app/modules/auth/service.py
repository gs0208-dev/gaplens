from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password
from app.modules.auth import repository
from app.modules.auth.errors import EmailAlreadyRegistered
from app.modules.auth.models import User

EMAIL_UNIQUE_INDEX = "users_email_lower_uidx"


def _violates_email_index(error: IntegrityError) -> bool:
    # The driver's own exception carries the index name. Matching on message text would break
    # if the database were set to another language.
    cause = error.orig.__cause__ if error.orig is not None else None
    return getattr(cause, "constraint_name", None) == EMAIL_UNIQUE_INDEX


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    # Hashing is CPU heavy, so it runs in a worker thread and does not block other requests.
    password_hash = await run_in_threadpool(hash_password, password)
    try:
        user = await repository.create_user(session, email, password_hash)
    except IntegrityError as error:
        # Insert first and let the unique index decide. A "look first" check could let two
        # simultaneous requests for the same email both succeed.
        if not _violates_email_index(error):
            raise
        raise EmailAlreadyRegistered from error
    await session.commit()
    return user
