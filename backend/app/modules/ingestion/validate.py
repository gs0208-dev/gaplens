import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from pypdf import PdfReader

from app.modules.ingestion.errors import (
    EncryptedPdf,
    NoExtractableText,
    PdfUnreadable,
    TextTooLong,
    TooManyPages,
    UnsupportedFileType,
)

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
PDF_MIME_TYPE = "application/pdf"
TEXT_MIME_TYPE = "text/plain"
MARKDOWN_MIME_TYPE = "text/markdown"
MARKDOWN_EXTENSIONS = {".md", ".markdown"}


@dataclass(frozen=True)
class UploadLimits:
    max_pages: int
    max_text_chars: int


@dataclass(frozen=True)
class InspectedUpload:
    mime_type: str
    # None for text files, which have no pages.
    page_count: int | None


def inspect_upload(data: bytes, filename: str, limits: UploadLimits) -> InspectedUpload:
    """Decide what an uploaded file is and whether it is acceptable, from its bytes alone.

    Blocking and CPU heavy, so callers run it in a worker thread. Raises a DomainError for
    every rejection. The size cap is checked by the caller before the bytes get here.
    """
    if data.startswith(PDF_MAGIC):
        return _inspect_pdf(data, limits)
    return _inspect_text(data, filename, limits)


def _inspect_text(data: bytes, filename: str, limits: UploadLimits) -> InspectedUpload:
    # A NUL byte or invalid UTF-8 means a binary file, whatever its name says.
    if b"\x00" in data:
        raise UnsupportedFileType
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UnsupportedFileType from error
    if len(text) > limits.max_text_chars:
        raise TextTooLong
    if not text.strip():
        raise NoExtractableText
    # Markdown and plain text look the same in bytes, so the extension picks the label only.
    # It never decides whether the file is accepted.
    extension = PurePosixPath(filename.lower()).suffix
    mime_type = MARKDOWN_MIME_TYPE if extension in MARKDOWN_EXTENSIONS else TEXT_MIME_TYPE
    return InspectedUpload(mime_type=mime_type, page_count=None)


def _inspect_pdf(data: bytes, limits: UploadLimits) -> InspectedUpload:
    try:
        reader = PdfReader(BytesIO(data))
        # Any encryption is refused, even one with an empty password, as docs/security.md says.
        if reader.is_encrypted:
            raise EncryptedPdf
        page_count = len(reader.pages)
        # Checked before any text is read, so a huge document costs almost nothing.
        if page_count > limits.max_pages:
            raise TooManyPages
        characters = 0
        has_text = False
        for page in reader.pages:
            page_text = page.extract_text()
            characters += len(page_text)
            # Stops as soon as the cap is passed instead of extracting the rest.
            if characters > limits.max_text_chars:
                raise TextTooLong
            has_text = has_text or bool(page_text.strip())
    except (EncryptedPdf, TooManyPages, TextTooLong):
        raise
    except Exception as error:
        # The parser reads untrusted bytes and can fail in many ways (a bad file, a pypdf bug,
        # deep recursion). Only the exception type is logged: its message may quote the file.
        logger.warning("pdf could not be parsed error_type=%s", type(error).__name__)
        raise PdfUnreadable from error
    if not has_text:
        raise NoExtractableText
    return InspectedUpload(mime_type=PDF_MIME_TYPE, page_count=page_count)
