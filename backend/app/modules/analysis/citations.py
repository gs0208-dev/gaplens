import re
import unicodedata
import uuid
from dataclasses import dataclass

from app.ai.schemas import FindingOut, GapReportOut

# Distinct chunks a finding must be backed by, per kind (docs/ai-engineering.md, Gap report).
REQUIRED_CHUNKS = {"contradiction": 2, "unclear": 1, "missing": 0}

_WHITESPACE_OR_CHARACTER = re.compile(r"\s+|\S")


@dataclass(frozen=True)
class ChunkText:
    id: uuid.UUID
    chunk_index: int
    section_label: str | None
    content: str


@dataclass(frozen=True)
class VerifiedCitation:
    chunk_id: uuid.UUID
    section_label: str | None
    quote: str


@dataclass(frozen=True)
class VerifiedFinding:
    kind: str
    severity: str
    title: str
    description: str
    suggested_question: str
    citations: list[VerifiedCitation]


@dataclass(frozen=True)
class CitationCounts:
    quotes_total: int
    quotes_verified: int
    findings_dropped: int


@dataclass(frozen=True)
class VerifiedReport:
    summary: str
    findings: list[VerifiedFinding]
    counts: CitationCounts


@dataclass(frozen=True)
class _SearchableChunk:
    chunk: ChunkText
    collapsed: str
    # Where each character of `collapsed` starts and ends in the original content.
    starts: list[int]
    ends: list[int]


def _collapse(text: str) -> tuple[str, list[int], list[int]]:
    """Each run of whitespace becomes one space, with a map back to the original positions."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for match in _WHITESPACE_OR_CHARACTER.finditer(text):
        characters.append(" " if match.group().isspace() else match.group())
        starts.append(match.start())
        ends.append(match.end())
    return "".join(characters), starts, ends


def _normalize_quote(quote: str) -> str:
    # The stored chunks are NFKC-normalized at ingestion, so the quote must be too.
    return _collapse(unicodedata.normalize("NFKC", quote))[0].strip()


def _locate(
    quote: str, searchable: list[_SearchableChunk], section_label: str | None
) -> VerifiedCitation | None:
    """The chunk that contains the quote and the quote as it is written in that chunk."""
    needle = _normalize_quote(quote)
    if not needle:
        return None
    matches = [
        (item, item.collapsed.find(needle)) for item in searchable if needle in item.collapsed
    ]
    if not matches:
        return None
    # A quote in the overlap of two chunks goes to the one the model labeled, else the first.
    item, position = next(
        (m for m in matches if section_label and m[0].chunk.section_label == section_label),
        matches[0],
    )
    original = item.chunk.content[item.starts[position] : item.ends[position + len(needle) - 1]]
    return VerifiedCitation(item.chunk.id, item.chunk.section_label, original)


def _verify_finding(
    finding: FindingOut, searchable: list[_SearchableChunk]
) -> tuple[VerifiedFinding | None, int]:
    citations: list[VerifiedCitation] = []
    verified = 0
    for evidence in finding.evidence:
        citation = _locate(evidence.quote, searchable, evidence.section_label)
        if citation is None:
            continue
        verified += 1
        if citation not in citations:
            citations.append(citation)

    distinct_chunks = len({citation.chunk_id for citation in citations})
    if distinct_chunks < REQUIRED_CHUNKS[finding.kind]:
        return None, verified
    return (
        VerifiedFinding(
            kind=finding.kind,
            severity=finding.severity,
            title=finding.title,
            description=finding.description,
            suggested_question=finding.suggested_question,
            citations=citations,
        ),
        verified,
    )


def verify_report(report: GapReportOut, chunks: list[ChunkText]) -> VerifiedReport:
    """Keep only the findings whose evidence is real text from the document.

    The model proposes, the code verifies. A quote counts only if it is found in one chunk after
    whitespace is collapsed; the section label and the quote that are kept come from the chunk,
    never from the model. A finding that then lacks the evidence its kind needs is dropped.
    """
    ordered = sorted(chunks, key=lambda chunk: chunk.chunk_index)
    searchable = [_SearchableChunk(chunk, *_collapse(chunk.content)) for chunk in ordered]
    kept: list[VerifiedFinding] = []
    quotes_total = quotes_verified = 0
    for finding in report.findings:
        quotes_total += len(finding.evidence)
        verified_finding, verified = _verify_finding(finding, searchable)
        quotes_verified += verified
        if verified_finding is not None:
            kept.append(verified_finding)
    counts = CitationCounts(
        quotes_total=quotes_total,
        quotes_verified=quotes_verified,
        findings_dropped=len(report.findings) - len(kept),
    )
    return VerifiedReport(report.summary, kept, counts)
