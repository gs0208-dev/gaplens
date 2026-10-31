from app.core.errors import DomainError


class LLMError(DomainError):
    """The model could not give a usable answer. All of these are 503: the request was fine,
    a dependency was not."""

    status_code = 503


class LLMUnavailable(LLMError):
    code = "llm_unavailable"
    title = "Answering is unavailable"
    detail = "The answering service is not available right now. Try again later."


class LLMTimeout(LLMError):
    code = "llm_timeout"
    title = "Answering took too long"
    detail = "The answering service took too long to reply. Try again."


class LLMInvalidOutput(LLMError):
    code = "llm_invalid_output"
    title = "Answer could not be produced"
    detail = "The answering service did not return a usable answer. Try again."
