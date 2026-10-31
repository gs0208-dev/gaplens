from dataclasses import dataclass
from typing import Any

from app.ai.schemas import ChatAnswerOut
from app.modules.retrieval.repository import RetrievedChunk

# The only text a user sees when the document does not answer. The model's own wording of a
# "no" (or of a guess) is never shown.
NOT_FOUND_ANSWER = "This is not found in the document."
# How much of a chunk is shown as the quote. Cut at the start of the chunk, so it is verbatim.
QUOTE_LENGTH = 300


@dataclass(frozen=True)
class VerifiedAnswer:
    answer: str
    grounded: bool
    citations: list[dict[str, Any]]


def excerpt(content: str, length: int = QUOTE_LENGTH) -> str:
    """The start of a chunk, cut at a word boundary. A prefix of stored text is verbatim by
    construction, which is what a citation promises."""
    if len(content) <= length:
        return content
    cut = content[:length]
    boundary = cut.rfind(" ")
    return (cut[:boundary] if boundary > 0 else cut).rstrip()


def not_found() -> VerifiedAnswer:
    return VerifiedAnswer(NOT_FOUND_ANSWER, grounded=False, citations=[])


def verify_answer(output: ChatAnswerOut, chunks: list[RetrievedChunk]) -> VerifiedAnswer:
    """Keep the model's answer only if it cites at least one source that really exists.

    The model proposes, the code verifies (docs/ai-engineering.md). A cited number outside the
    sources it was shown is dropped. An answer that claims to be grounded but has no valid
    citation, or that is empty, becomes "not found". Quotes and section labels come from the
    stored chunk, never from the model.
    """
    cited_chunks: list[RetrievedChunk] = []
    for number in output.cited_sources:
        if 1 <= number <= len(chunks) and chunks[number - 1] not in cited_chunks:
            cited_chunks.append(chunks[number - 1])

    answer = output.answer.strip()
    if not output.grounded or not cited_chunks or not answer:
        return not_found()
    citations = [
        {
            "chunk_id": str(chunk.id),
            "section_label": chunk.section_label,
            "quote": excerpt(chunk.content),
        }
        for chunk in cited_chunks
    ]
    return VerifiedAnswer(answer, grounded=True, citations=citations)
