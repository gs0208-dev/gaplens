import uuid

from app.modules.analysis.citations import ChunkText, VerifiedCitation, VerifiedFinding
from app.modules.analysis.ordering import order_findings

CHUNKS = [ChunkText(uuid.uuid4(), index, None, f"chunk {index}") for index in range(4)]


def finding(
    title: str, severity: str, *chunk_indexes: int, kind: str = "unclear"
) -> VerifiedFinding:
    citations = [VerifiedCitation(CHUNKS[i].id, None, f"quote {i}") for i in chunk_indexes]
    return VerifiedFinding(kind, severity, title, "d", "q?", citations)


def titles(findings: list[VerifiedFinding]) -> list[str]:
    return [f.title for f in findings]


def test_findings_are_sorted_by_severity_then_by_where_their_evidence_starts() -> None:
    ordered, removed = order_findings(
        [
            finding("low first", "low", 0),
            finding("high late", "high", 3),
            finding("medium", "medium", 1),
            finding("high early", "high", 2, 1),
        ],
        CHUNKS,
    )

    assert titles(ordered) == ["high early", "high late", "medium", "low first"]
    assert removed == 0


def test_a_finding_without_citations_goes_after_the_others_of_its_severity() -> None:
    ordered, _ = order_findings(
        [finding("missing", "high", kind="missing"), finding("cited", "high", 3)], CHUNKS
    )

    assert titles(ordered) == ["cited", "missing"]


def test_equal_findings_keep_the_order_the_model_gave() -> None:
    ordered, _ = order_findings(
        [finding("a", "medium", kind="missing"), finding("b", "medium", kind="missing")], CHUNKS
    )

    assert titles(ordered) == ["a", "b"]


def test_a_near_duplicate_is_removed_and_the_more_severe_one_stays() -> None:
    ordered, removed = order_findings(
        [finding("low copy", "low", 1, 2), finding("high copy", "high", 2, 1)], CHUNKS
    )

    assert titles(ordered) == ["high copy"]
    assert removed == 1


def test_same_chunks_but_another_kind_or_other_chunks_are_not_duplicates() -> None:
    ordered, removed = order_findings(
        [
            finding("unclear", "high", 1),
            finding("contradiction", "high", 1, kind="contradiction"),
            finding("other chunk", "high", 2),
            finding("more chunks", "high", 1, 2),
        ],
        CHUNKS,
    )

    assert len(ordered) == 4 and removed == 0


def test_missing_findings_without_citations_are_never_merged() -> None:
    ordered, removed = order_findings(
        [finding("a", "high", kind="missing"), finding("b", "high", kind="missing")], CHUNKS
    )

    assert titles(ordered) == ["a", "b"] and removed == 0
