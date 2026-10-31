from app.core.errors import DomainError


class UnsupportedFileType(DomainError):
    status_code = 415
    code = "unsupported_file_type"
    title = "Unsupported file type"
    detail = "Upload a PDF, a plain text file or a Markdown file."


class EncryptedPdf(DomainError):
    status_code = 422
    code = "encrypted_pdf"
    title = "Encrypted PDF"
    detail = "This PDF is password protected. Remove the protection and upload it again."


class PdfUnreadable(DomainError):
    status_code = 422
    code = "pdf_unreadable"
    title = "PDF could not be read"
    detail = "This PDF is damaged or uses a format we cannot read."


class TooManyPages(DomainError):
    status_code = 422
    code = "too_many_pages"
    title = "Too many pages"
    detail = "This document has more pages than the limit allows."


class TextTooLong(DomainError):
    status_code = 422
    code = "text_too_long"
    title = "Document text too long"
    detail = "This document has more text than the limit allows."


class NoExtractableText(DomainError):
    status_code = 422
    code = "no_extractable_text"
    title = "No readable text"
    detail = "No text could be read from this file. Scanned documents are not supported."


# The only texts ever stored in documents.error_message. They are fixed on purpose: an exception
# message could quote the document, so it is never copied into the database or a response.
GENERIC_FAILURE_MESSAGE = "This document could not be processed. Upload it again."
TOO_MANY_SECTIONS_MESSAGE = (
    "This document has too many sections to process. Split it into smaller documents."
)
NO_TEXT_MESSAGE = "No text could be read from this document."
STUCK_MESSAGE = "Processing did not finish. Upload the document again."


class ProcessingError(Exception):
    """A failure whose message is safe to show to the user."""

    safe_message = GENERIC_FAILURE_MESSAGE


class TooManySections(ProcessingError):
    safe_message = TOO_MANY_SECTIONS_MESSAGE


class NothingToStore(ProcessingError):
    safe_message = NO_TEXT_MESSAGE
