import uuid
from datetime import UTC, datetime

import pytest

from app.core.pagination import InvalidCursor, decode_cursor, encode_cursor, split_page


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


def row(n: int) -> tuple[datetime, uuid.UUID]:
    return datetime(2026, 1, 1, 0, 0, n, tzinfo=UTC), uuid.UUID(int=n)


def test_split_page_returns_everything_and_no_cursor_when_the_rows_fit() -> None:
    rows = [row(1), row(2)]

    items, cursor = split_page(rows, 2, lambda r: r)

    assert (items, cursor) == (rows, None)


def test_split_page_cuts_the_extra_row_and_points_the_cursor_at_the_last_kept_one() -> None:
    rows = [row(1), row(2), row(3)]  # limit + 1 rows were fetched

    items, cursor = split_page(rows, 2, lambda r: r)

    assert items == rows[:2]
    assert cursor is not None
    assert decode_cursor(cursor) == row(2)


def test_split_page_of_nothing_is_empty() -> None:
    assert split_page([], 5, lambda r: r) == ([], None)
