from app.core.errors import DomainError


class DocumentNotReady(DomainError):
    # Asking a question of a document that is still being processed (or failed) would find no
    # chunks, and "no answer" would be the wrong thing to tell the user.
    status_code = 409
    code = "document_not_ready"
    title = "Document not ready"
    detail = "This document is not ready yet. Try again when processing has finished."
