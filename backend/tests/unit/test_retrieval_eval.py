import json

import pytest
from retrieval_eval import (
    GOLDEN,
    KS,
    first_rank,
    label_covers,
    load_questions,
    rank_chunks,
    score_questions,
)

from app.modules.ingestion.chunker import chunk_document
from app.modules.ingestion.structure import extract_document
from tests.sop_fixtures import SOP_TEXT


@pytest.mark.parametrize(
    ("chunk_label", "section", "expected"),
    [
        ("3.1", "3.1", True),
        ("3.1-3.5", "3.1", True),
        ("3.1-3.5", "3.3", True),
        ("3.1-3.5", "3.5", True),
        ("3.1-3.5", "3.6", False),
        ("3.1-3.5", "4.1", False),
        ("3.1-3.5", "3", False),
        ("3.1-3.5", "3.1.2", False),
        ("3.5-3.1", "3.3", False),
        ("3.1.2-3.1.4", "3.1.3", True),
        ("3.1.2-3.1.4", "3.2.3", False),
        ("3.2-3.10", "3.9", True),
        ("x.1-x.3", "x.2", False),
        ("3.1-3.5", "not-a-label", False),
        (None, "3.1", False),
        ("3", "3.1", False),
    ],
)
def test_label_covers(chunk_label: str | None, section: str, expected: bool) -> None:
    assert label_covers(chunk_label, section) is expected


def test_first_rank_is_one_based_and_none_when_missing() -> None:
    labels = [None, "1.1-1.2", "3.1-3.5"]

    assert first_rank(labels, "3.3") == 3
    assert first_rank(labels, "1.2") == 2
    assert first_rank(labels, "5.3") is None


def test_rank_chunks_orders_by_similarity_and_breaks_ties_by_position() -> None:
    vectors = [[0.0, 1.0], [1.0, 0.0], [1.0, 0.0], [0.6, 0.8]]

    assert rank_chunks([1.0, 0.0], vectors) == [1, 2, 3, 0]


def test_recall_and_reciprocal_rank_on_made_up_rankings() -> None:
    rankings = {
        "A": ["3.1-3.5", "1.1-1.2", None],  # needs 3.2: found at 1
        "B": [None, "2.1-2.2", "3.1-3.5"],  # needs 2.1 (rank 2) and 3.3 (rank 3)
        "C": ["1.1-1.2", None, None],  # needs 5.3: never found
        "D": ["1.1-1.2"],  # unanswerable: ignored
    }
    expected = {"A": ["3.2"], "B": ["2.1", "3.3"], "C": ["5.3"], "D": []}

    metrics = score_questions(rankings, expected)

    assert metrics.ranks == {"A": {"3.2": 1}, "B": {"2.1": 2, "3.3": 3}, "C": {"5.3": None}}
    # Four pairs: found at ranks 1, 2, 3 and not at all.
    assert metrics.recall_at == {1: 0.25, 3: 0.75, 6: 0.75}
    assert metrics.mean_reciprocal_rank == pytest.approx((1 + 1 / 2 + 0) / 3)


def test_the_cutoffs_are_the_documented_ones() -> None:
    assert KS == (1, 3, 6)


def test_every_golden_section_is_covered_by_a_chunk_of_the_sample_sop() -> None:
    chunks = chunk_document(extract_document(SOP_TEXT.encode(), "text/markdown"))
    labels = [chunk.section_label for chunk in chunks]

    for question in load_questions():
        for section in question.expected_sections:
            assert any(label_covers(label, section) for label in labels), (question.id, section)


def test_unanswerable_questions_expect_no_sections_and_the_others_do() -> None:
    questions = load_questions()

    assert [q.id for q in questions if not q.expected_sections] == ["Q8", "Q9", "Q10"]
    assert all(q.type == "unanswerable" for q in questions if not q.expected_sections)
    assert len(questions) == len(GOLDEN.read_text().splitlines()) == 10
    assert all(json.loads(line)["id"] for line in GOLDEN.read_text().splitlines())
