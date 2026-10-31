import math
import re
from dataclasses import dataclass

from app.modules.ingestion.structure import ExtractedDocument, Section

# Sizes are in estimated tokens. They are code, not settings: changing one changes what is stored
# and what retrieval finds, so it needs an eval run (docs/ai-engineering.md), not a redeploy.
SHORT_CLAUSE_TOKENS = 40
MERGE_TARGET_TOKENS = 120
MAX_CHUNK_TOKENS = 400
WINDOW_TOKENS = 300
WINDOW_OVERLAP_TOKENS = 50

# A full stop, question mark or exclamation mark, then a space, then something that can start a
# sentence. Requiring that start keeps "approx. 5 days" and "e.g. a manager" in one piece.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass(frozen=True)
class Chunk:
    """One row of document_chunks, apart from the embedding."""

    chunk_index: int
    section_label: str | None
    heading: str | None
    content: str
    token_count: int
    page_start: int | None


@dataclass(frozen=True)
class _Draft:
    section_label: str | None
    heading: str | None
    content: str
    page_start: int | None


def estimate_tokens(text: str) -> int:
    """About 1.3 tokens per word, rounded up, and never zero (the table requires more than 0).

    Whole-number arithmetic: 10 words must be exactly 13, which 10 * 1.3 does not guarantee.
    This sizes chunks only. Billing numbers come from the LLM API's reported usage.
    """
    words = len(text.split())
    return max(1, (words * 13 + 9) // 10)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]


def _fit_sentence(sentence: str, limit: int) -> list[str]:
    """The sentence itself, or word-by-word pieces if it alone is over the limit."""
    if estimate_tokens(sentence) <= limit:
        return [sentence]
    words = sentence.split()
    words_per_piece = max(1, limit * 10 // 13)
    return [
        " ".join(words[start : start + words_per_piece])
        for start in range(0, len(words), words_per_piece)
    ]


def _split_long_text(text: str) -> list[str]:
    """Cut a text over the limit into similar-sized pieces at sentence ends, with no overlap."""
    sentences = [
        piece
        for sentence in _sentences(text)
        for piece in _fit_sentence(sentence, MAX_CHUNK_TOKENS)
    ]
    sizes = [estimate_tokens(sentence) for sentence in sentences]
    piece_count = math.ceil(sum(sizes) / MAX_CHUNK_TOKENS)
    # Cutting at an even share, not only at the limit, keeps the last piece from being a stub.
    even_share = sum(sizes) / piece_count
    pieces: list[str] = []
    current: list[str] = []
    current_size = 0
    for sentence, size in zip(sentences, sizes, strict=True):
        if current and (current_size + size > MAX_CHUNK_TOKENS or current_size >= even_share):
            pieces.append(" ".join(current))
            current, current_size = [], 0
        current.append(sentence)
        current_size += size
    pieces.append(" ".join(current))
    return pieces


def _depth(label: str) -> int:
    return label.count(".") + 1


def _parent(label: str) -> str:
    return label.rpartition(".")[0]


def _are_siblings(first: Section, other: Section) -> bool:
    """3.1 and 3.2 are siblings under 3. Top-level labels and unlabeled sections never are."""
    if first.label is None or other.label is None:
        return False
    return (
        _depth(first.label) >= 2
        and _depth(first.label) == _depth(other.label)
        and _parent(first.label) == _parent(other.label)
    )


def _merged_draft(group: list[Section]) -> _Draft:
    first, last = group[0], group[-1]
    if len(group) == 1:
        return _Draft(first.label, first.heading, first.text, first.page_start)
    # Each clause keeps its number on its own line, because S2-3 removed it from the text and a
    # reader of the chunk (or the model) must still see which clause says what.
    content = "\n".join(f"{section.label} {section.text}" for section in group)
    return _Draft(f"{first.label}-{last.label}", first.heading, content, first.page_start)


def _structured_drafts(sections: list[Section]) -> list[_Draft]:
    drafts: list[_Draft] = []
    index = 0
    while index < len(sections):
        section = sections[index]
        tokens = estimate_tokens(section.text)
        if tokens > MAX_CHUNK_TOKENS:
            drafts.extend(
                _Draft(section.label, section.heading, piece, section.page_start)
                for piece in _split_long_text(section.text)
            )
            index += 1
            continue

        group = [section]
        # Only a short clause starts a group. A clause of 40 tokens or more is a chunk by itself.
        if tokens < SHORT_CLAUSE_TOKENS:
            while index + len(group) < len(sections):
                candidate = sections[index + len(group)]
                if not _are_siblings(section, candidate):
                    break
                if estimate_tokens(_merged_draft(group).content) >= MERGE_TARGET_TOKENS:
                    break
                if estimate_tokens(_merged_draft([*group, candidate]).content) > MAX_CHUNK_TOKENS:
                    break
                group.append(candidate)
        drafts.append(_merged_draft(group))
        index += len(group)
    return drafts


def _window_drafts(sections: list[Section]) -> list[_Draft]:
    """Overlapping windows of whole sentences, for text with no clause numbers or headings."""
    sentences = [
        (piece, section.page_start)
        for section in sections
        for sentence in _sentences(section.text)
        for piece in _fit_sentence(sentence, WINDOW_TOKENS)
    ]
    sizes = [estimate_tokens(sentence) for sentence, _ in sentences]
    drafts: list[_Draft] = []
    start = 0
    while start < len(sentences):
        end, size = start, 0
        while end < len(sentences) and (end == start or size + sizes[end] <= WINDOW_TOKENS):
            size += sizes[end]
            end += 1
        window = sentences[start:end]
        drafts.append(_Draft(None, None, " ".join(text for text, _ in window), window[0][1]))
        if end >= len(sentences):
            break
        # The next window begins early enough to repeat about 50 tokens, but always moves on by
        # at least one sentence, so the loop ends.
        next_start, overlap = end, 0
        while next_start > start + 1 and overlap < WINDOW_OVERLAP_TOKENS:
            next_start -= 1
            overlap += sizes[next_start]
        start = next_start
    return drafts


def chunk_document(document: ExtractedDocument) -> list[Chunk]:
    """Turn the sections of a document into the chunks that get embedded and stored."""
    if document.structured:
        drafts = _structured_drafts(document.sections)
    else:
        drafts = _window_drafts(document.sections)
    return [
        Chunk(
            chunk_index=index,
            section_label=draft.section_label,
            heading=draft.heading,
            content=draft.content,
            token_count=estimate_tokens(draft.content),
            page_start=draft.page_start,
        )
        for index, draft in enumerate(drafts)
    ]
