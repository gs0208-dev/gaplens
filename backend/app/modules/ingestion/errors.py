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
