import uuid
from typing import Any

import pytest

from app.ai.schemas import Evidence, FindingOut, GapReportOut
from app.modules.analysis.citations import ChunkText, verify_report


def chunk(index: int, content: str, label: str | None = None) -> ChunkText:
    return ChunkText(uuid.uuid4(), index, label, content)


REFUNDS = chunk(0, "3.1 Agents may approve refunds\nup to 5,000 per case.", "3.1")
ESCALATION = chunk(1, "4.1 The agent escalates it to the relevant manager.", "4.1")
TIMING = chunk(2, "5.2 Escalations are answered within  two days.", "5.2")
CHUNKS = [REFUNDS, ESCALATION, TIMING]


def finding(kind: str = "unclear", *quotes: str, label: str | None = None) -> FindingOut:
    return FindingOut(
        kind=kind,  # type: ignore[arg-type]
        severity="high",
        title="A title",
        description="A description.",
        evidence=[Evidence(section_label=label, quote=quote) for quote in quotes],
        suggested_question="A question?",
    )


def verify(*findings: FindingOut, chunks: list[ChunkText] = CHUNKS) -> Any:
    return verify_report(GapReportOut(summary="s", findings=list(findings)), chunks)


def test_an_exact_quote_is_verified_with_the_chunk_id_and_label() -> None:
    result = verify(finding("unclear", "escalates it to the relevant manager", label="9.9"))

    (kept,) = result.findings
    (citation,) = kept.citations
    assert citation.chunk_id == ESCALATION.id
    assert citation.quote == "escalates it to the relevant manager"
    # The label comes from the chunk, not from the model.
    assert citation.section_label == "4.1"


def test_a_quote_that_differs_only_in_whitespace_is_verified_as_the_original_text() -> None:
    result = verify(
        finding("unclear", "approve refunds up to 5,000 per case."),
        finding("unclear", "answered within two days."),
    )

    refunds, timing = (f.citations[0] for f in result.findings)
    assert refunds.quote == "approve refunds\nup to 5,000 per case."
    assert timing.quote == "answered within  two days."
    assert result.counts.quotes_verified == 2


def test_surrounding_whitespace_in_a_quote_is_not_stored() -> None:
    result = verify(finding("unclear", "  escalates it to the relevant manager \n"))

    assert result.findings[0].citations[0].quote == "escalates it to the relevant manager"


@pytest.mark.parametrize(
    "quote",
    [
        "escalates it to the senior manager",
        "ESCALATES IT TO THE RELEVANT MANAGER",
        "the agent escalates it to the relevant manager",
        "escalates it to the relevant manager within one hour",
        "a sentence that is nowhere in the document",
        "within two days. 4.1 The agent escalates",
        "          ",
    ],
    ids=["changed_word", "case", "case_start", "extended", "fabricated", "across_chunks", "blank"],
)
def test_a_quote_that_is_not_in_one_chunk_verbatim_is_dropped(quote: str) -> None:
    result = verify(finding("unclear", quote))

    assert result.findings == []
    assert (result.counts.quotes_total, result.counts.quotes_verified) == (1, 0)


def test_a_quote_is_compared_in_the_same_unicode_form_as_the_stored_text() -> None:
    stored = chunk(0, "The office closes at noon.", "1.1")

    # The model wrote the "ffi" ligature; ingestion folded it, so the stored text has "ffi".
    result = verify(finding("unclear", "The o\ufb03ce closes at noon."), chunks=[stored])

    assert result.findings[0].citations[0].quote == "The office closes at noon."


def test_unclear_needs_one_verified_quote() -> None:
    result = verify(
        finding("unclear"),
        finding("unclear", "made up text that is not there"),
        finding(
            "unclear", "made up text that is not there", "escalates it to the relevant manager"
        ),
    )

    assert [len(f.citations) for f in result.findings] == [1]
    assert result.counts.findings_dropped == 2


def test_contradiction_needs_quotes_from_two_different_chunks() -> None:
    same_chunk = finding("contradiction", "Agents may approve refunds", "up to 5,000 per case.")
    two_chunks = finding(
        "contradiction", "up to 5,000 per case.", "escalates it to the relevant manager"
    )
    one_fabricated = finding(
        "contradiction", "up to 5,000 per case.", "invented text that is not there"
    )

    result = verify(same_chunk, two_chunks, one_fabricated)

    (kept,) = result.findings
    assert {c.chunk_id for c in kept.citations} == {REFUNDS.id, ESCALATION.id}
    assert result.counts.findings_dropped == 2


def test_missing_is_kept_without_evidence_and_loses_only_the_quotes_that_fail() -> None:
    result = verify(finding("missing"), finding("missing", "invented text that is not there"))

    assert [f.citations for f in result.findings] == [[], []]
    assert result.counts.findings_dropped == 0


def test_a_quote_in_two_chunks_goes_to_the_one_the_model_labeled_else_the_first() -> None:
    first = chunk(0, "A shared sentence in the overlap.", "1.1")
    second = chunk(1, "A shared sentence in the overlap. Then more.", "1.2")

    result = verify(
        finding("unclear", "A shared sentence in the overlap.", label="1.2"),
        finding("unclear", "A shared sentence in the overlap.", label="9.9"),
        finding("unclear", "A shared sentence in the overlap."),
        chunks=[second, first],
    )

    assert [f.citations[0].chunk_id for f in result.findings] == [second.id, first.id, first.id]


def test_the_same_quote_cited_twice_in_one_finding_is_kept_once() -> None:
    result = verify(
        finding(
            "unclear",
            "escalates it to the relevant manager",
            "escalates   it to the relevant manager",
        )
    )

    assert len(result.findings[0].citations) == 1
    assert result.counts.quotes_verified == 2


def test_counts_cover_every_quote_and_every_dropped_finding() -> None:
    result = verify(
        finding("unclear", "escalates it to the relevant manager"),
        finding("unclear", "invented text that is not there"),
        finding("contradiction", "up to 5,000 per case.", "invented text that is not there"),
        finding("missing"),
    )

    assert result.counts.quotes_total == 4
    assert result.counts.quotes_verified == 2
    assert result.counts.findings_dropped == 2
    assert [f.kind for f in result.findings] == ["unclear", "missing"]


def test_an_empty_report_has_zero_counts_and_keeps_the_summary() -> None:
    result = verify_report(GapReportOut(summary="Nothing to report.", findings=[]), CHUNKS)

    assert result.summary == "Nothing to report." and result.findings == []
    assert (
        result.counts.quotes_total,
        result.counts.quotes_verified,
        result.counts.findings_dropped,
    ) == (0, 0, 0)


def test_when_every_finding_is_unverifiable_none_survive_and_the_counts_say_why() -> None:
    result = verify(
        finding("unclear", "invented text that is not there"),
        finding("contradiction", "also invented text", "more invented text"),
    )

    assert result.findings == []
    assert (result.counts.quotes_total, result.counts.findings_dropped) == (3, 2)


def test_no_chunks_means_no_quote_can_be_verified() -> None:
    result = verify(finding("unclear", "escalates it to the relevant manager"), chunks=[])

    assert result.findings == [] and result.counts.quotes_verified == 0
