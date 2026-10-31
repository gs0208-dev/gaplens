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
