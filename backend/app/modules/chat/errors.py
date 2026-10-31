from app.core.errors import DomainError


class ThreadNotFound(DomainError):
    # The same error for a missing thread, another user's thread and a thread of another
    # document, so the response never says which it was.
    status_code = 404
    code = "thread_not_found"
    title = "Thread not found"
    detail = "No conversation with this id."
