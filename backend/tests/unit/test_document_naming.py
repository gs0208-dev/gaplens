import pytest

from app.modules.documents.service import clean_filename, default_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sop.txt", "sop.txt"),
        ("../../etc/passwd", "passwd"),
        ("/abs/path/file.md", "file.md"),
        ("C:\\Users\\ana\\sop.txt", "sop.txt"),
        ("sop\x00\x07.txt", "sop.txt"),
        ("line\nbreak.txt", "linebreak.txt"),
        ("  padded.txt  ", "padded.txt"),
        ("", "document"),
        (None, "document"),
        ("..", "document"),
        ("a" * 300, "a" * 255),
    ],
)
def test_clean_filename_keeps_a_safe_display_name(raw: str | None, expected: str) -> None:
    assert clean_filename(raw) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Refund SOP.pdf", "Refund SOP"),
        ("refund  \t sop.v2.md", "refund sop.v2"),
        ("noextension", "noextension"),
        (".hidden", ".hidden"),
        ("t" * 300 + ".txt", "t" * 200),
    ],
)
def test_default_title_is_the_filename_stem(filename: str, expected: str) -> None:
    assert default_title(filename) == expected
