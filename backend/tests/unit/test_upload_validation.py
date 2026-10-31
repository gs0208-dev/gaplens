from pathlib import Path

import pytest

from app.core.errors import DomainError
from app.modules.ingestion.errors import (
    EncryptedPdf,
    NoExtractableText,
    PdfUnreadable,
    TextTooLong,
    TooManyPages,
    UnsupportedFileType,
)
from app.modules.ingestion.validate import UploadLimits, inspect_upload
from tests.pdf_fixtures import blank_pdf, encrypted_pdf, text_pdf

LIMITS = UploadLimits(max_pages=3, max_text_chars=200)
SAMPLE_SOP = Path(__file__).resolve().parents[3] / "evals/datasets/sop_refund_escalation.md"
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def rejection(data: bytes, filename: str = "file.bin") -> type[DomainError]:
    with pytest.raises(DomainError) as caught:
        inspect_upload(data, filename, LIMITS)
    return type(caught.value)


def test_pdf_is_accepted_with_its_page_count() -> None:
    result = inspect_upload(
        text_pdf(["Refunds over 500 need approval", "Second page"]), "a.pdf", LIMITS
    )

    assert (result.mime_type, result.page_count) == ("application/pdf", 2)


def test_plain_text_is_accepted_without_a_page_count() -> None:
    result = inspect_upload(b"3.1 Refunds are approved by a lead.", "notes.txt", LIMITS)

    assert (result.mime_type, result.page_count) == ("text/plain", None)


@pytest.mark.parametrize("filename", ["sop.md", "SOP.MD", "sop.markdown"])
def test_markdown_extension_picks_the_markdown_label(filename: str) -> None:
    result = inspect_upload(b"# Refunds\n\nApproved by a lead.", filename, LIMITS)

    assert result.mime_type == "text/markdown"


def test_the_sample_sop_is_accepted_as_markdown() -> None:
    big_limits = UploadLimits(max_pages=100, max_text_chars=300_000)

    result = inspect_upload(SAMPLE_SOP.read_bytes(), SAMPLE_SOP.name, big_limits)

    assert result.mime_type == "text/markdown"


def test_a_png_named_pdf_is_rejected_by_its_bytes() -> None:
    assert rejection(PNG_HEADER, "report.pdf") is UnsupportedFileType


def test_a_pdf_named_txt_is_still_treated_as_a_pdf() -> None:
    result = inspect_upload(text_pdf(["Refund policy"]), "report.txt", LIMITS)

    assert (result.mime_type, result.page_count) == ("application/pdf", 1)


def test_a_nul_byte_means_binary() -> None:
    assert rejection(b"looks like text\x00but is not", "notes.txt") is UnsupportedFileType


def test_invalid_utf8_is_rejected() -> None:
    assert rejection(b"caf\xe9 policy", "notes.txt") is UnsupportedFileType


def test_an_encrypted_pdf_is_rejected_even_with_an_empty_user_password() -> None:
    assert rejection(encrypted_pdf()) is EncryptedPdf


def test_too_many_pages_is_rejected() -> None:
    assert rejection(text_pdf(["page"] * 4)) is TooManyPages


def test_pdf_text_over_the_cap_is_rejected() -> None:
    assert rejection(text_pdf(["x" * 150, "y" * 150])) is TextTooLong


def test_text_over_the_cap_is_rejected() -> None:
    assert rejection(b"x" * 201, "notes.txt") is TextTooLong


def test_text_exactly_at_the_cap_is_accepted() -> None:
    result = inspect_upload(b"x" * 200, "notes.txt", LIMITS)

    assert result.mime_type == "text/plain"


def test_a_pdf_without_text_is_rejected() -> None:
    assert rejection(blank_pdf()) is NoExtractableText


@pytest.mark.parametrize("data", [b"", b"   \n\t  "])
def test_empty_or_whitespace_text_is_rejected(data: bytes) -> None:
    assert rejection(data, "notes.txt") is NoExtractableText


def test_a_damaged_pdf_is_rejected() -> None:
    assert rejection(b"%PDF-1.4\nthis is not a real pdf body") is PdfUnreadable
