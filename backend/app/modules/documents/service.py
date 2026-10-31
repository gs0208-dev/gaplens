import hashlib
import re
import unicodedata
import uuid
from pathlib import PurePosixPath

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import FileTooLarge
from app.modules.audit.service import record_audit_event
from app.modules.documents import repository
from app.modules.documents.errors import DocumentNotFound, DuplicateDocument
from app.modules.documents.models import Document
from app.modules.ingestion.validate import InspectedUpload, UploadLimits, inspect_upload

DOCUMENT_UPLOAD = "document.upload"
SHA256_UNIQUE_INDEX = "documents_owner_sha256_uidx"
MAX_TITLE_LENGTH = 200
MAX_FILENAME_LENGTH = 255
FALLBACK_FILENAME = "document"


def clean_filename(raw: str | None) -> str:
    """A safe display name. It is only ever shown, never used as a path.

    Directory parts (from either kind of separator) and control characters are removed, and
    the result is cut to the column limit.
    """
    name = (raw or "").replace("\\", "/")
    name = PurePosixPath(name).name
    name = "".join(char for char in name if unicodedata.category(char) != "Cc").strip()
    if name in {".", ".."}:
        return FALLBACK_FILENAME
    return name[:MAX_FILENAME_LENGTH] or FALLBACK_FILENAME


def default_title(filename: str) -> str:
    stem = PurePosixPath(filename).stem or filename
    return re.sub(r"\s+", " ", stem).strip()[:MAX_TITLE_LENGTH] or FALLBACK_FILENAME


def _inspect_and_hash(
    data: bytes, filename: str, limits: UploadLimits
) -> tuple[InspectedUpload, str]:
    # One worker-thread call for both CPU-bound steps, so neither blocks the event loop.
    return inspect_upload(data, filename, limits), hashlib.sha256(data).hexdigest()


def _violates_sha256_index(error: IntegrityError) -> bool:
    # Same approach as the email index in the auth service: read the index name from the
    # driver's exception instead of matching on message text.
    cause = error.orig.__cause__ if error.orig is not None else None
    return getattr(cause, "constraint_name", None) == SHA256_UNIQUE_INDEX


async def upload_document(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    upload: UploadFile,
    title: str | None,
    ip: str | None,
) -> Document:
    settings = get_settings()
    # Reads one byte more than the cap, so an oversized file is noticed without reading all of it.
    data = await upload.read(settings.upload_max_bytes + 1)
    if len(data) > settings.upload_max_bytes:
        raise FileTooLarge

    filename = clean_filename(upload.filename)
    limits = UploadLimits(
        max_pages=settings.upload_max_pages, max_text_chars=settings.upload_max_text_chars
    )
    inspected, sha256 = await run_in_threadpool(_inspect_and_hash, data, filename, limits)

    try:
        document = await repository.create_document(
            session,
            owner_id=owner_id,
            title=title or default_title(filename),
            filename=filename,
            mime_type=inspected.mime_type,
            size_bytes=len(data),
            sha256=sha256,
            page_count=inspected.page_count,
        )
    except IntegrityError as error:
        # Insert first and let the unique index decide. A "look first" check could let two
        # simultaneous uploads of the same file both succeed.
        if not _violates_sha256_index(error):
            raise
        raise DuplicateDocument from error
    await record_audit_event(
        session,
        action=DOCUMENT_UPLOAD,
        actor_id=owner_id,
        resource_type="document",
        resource_id=document.id,
        ip=ip,
    )
    await session.commit()
    return document


async def get_document(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = await repository.get_document(session, owner_id=owner_id, document_id=document_id)
    if document is None:
        raise DocumentNotFound
    return document
