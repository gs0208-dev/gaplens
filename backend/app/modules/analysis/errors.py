from app.core.errors import DomainError

# Stored as analyses.error_message and shown to the user. Fixed text only: the model's output and
# exception messages never reach it.
FAILURE_TIMEOUT = "The analysis took too long. Try again."
FAILURE_UNAVAILABLE = "The analysis service is not available right now. Try again later."
FAILURE_INVALID_OUTPUT = "The analysis did not produce a usable report. Try again."
FAILURE_GENERIC = "The analysis could not be completed. Try again."
FAILURE_STUCK = "The analysis did not finish. Try again."


class AnalysisNotFound(DomainError):
    # The same error for a missing analysis and another user's analysis.
    status_code = 404
    code = "analysis_not_found"
    title = "Analysis not found"
    detail = "No analysis with this id."


class FindingNotFound(DomainError):
    status_code = 404
    code = "finding_not_found"
    title = "Finding not found"
    detail = "No finding with this id."


class AnalysisAlreadyRunning(DomainError):
    status_code = 409
    code = "analysis_already_running"
    title = "Analysis already running"
    detail = "An analysis of this document is already running. Wait for it to finish."
