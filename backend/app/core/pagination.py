import base64
import binascii
import uuid
from datetime import datetime

from app.core.errors import DomainError


class InvalidCursor(DomainError):
    status_code = 422
    code = "invalid_cursor"
    title = "Invalid cursor"
    detail = "The cursor is not valid. Start again without it."


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    """An opaque position in a list: the created_at and id of the last row the client has seen
    (keyset pagination, docs/database.md). Opaque so clients do not build their own."""
    raw = f"{created_at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, _, row_id = raw.partition("|")
        return datetime.fromisoformat(created_at), uuid.UUID(row_id)
    except (ValueError, binascii.Error) as error:
        raise InvalidCursor from error
