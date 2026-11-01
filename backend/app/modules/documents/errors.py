from app.core.errors import DomainError


class DuplicateDocument(DomainError):
    status_code = 409
    code = "duplicate_document"
    title = "Document already uploaded"
    detail = "You have already uploaded this file."


class DocumentNotFound(DomainError):
    # The same error for a missing document, another user's document and a deleted one.
    status_code = 404
    code = "document_not_found"
    title = "Document not found"
    detail = "No document with this id."


class DocumentNotReady(DomainError):
    # Asking a question of, or reading the text of, a document that is still being processed (or
    # failed) would find no chunks, and "nothing there" would be the wrong thing to tell the user.
    status_code = 409
    code = "document_not_ready"
    title = "Document not ready"
    detail = "This document is not ready yet. Try again when processing has finished."
