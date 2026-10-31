import uuid
from datetime import UTC, datetime

import pytest

from app.core.pagination import InvalidCursor, decode_cursor, encode_cursor


def test_a_cursor_round_trips() -> None:
    created_at = datetime(2026, 11, 1, 12, 30, 15, 123456, tzinfo=UTC)
    row_id = uuid.uuid4()

    assert decode_cursor(encode_cursor(created_at, row_id)) == (created_at, row_id)


def test_a_cursor_is_url_safe_text() -> None:
    cursor = encode_cursor(datetime.now(UTC), uuid.uuid4())

    assert cursor.replace("-", "").replace("_", "").isalnum()


@pytest.mark.parametrize("cursor", ["", "not-a-cursor", "!!!", "YWJj", "MjAyNnx4"])
def test_a_bad_cursor_is_refused(cursor: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor)
