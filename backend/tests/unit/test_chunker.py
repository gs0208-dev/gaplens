import itertools
import time

import pytest

from app.modules.ingestion.chunker import (
    MAX_CHUNK_TOKENS,
    WINDOW_TOKENS,
    Chunk,
    chunk_document,
    estimate_tokens,
)
from app.modules.ingestion.structure import ExtractedDocument, Section, extract_document
from tests.sop_fixtures import SOP_TEXT, sop_as_pdf

SOP_CHUNK_LABELS = [None, "1.1-1.2", "2.1-2.2", "3.1-3.5", "4.1-4.3", "5.1-5.4", "6.1-6.2", "7.1"]


def words(count: int, prefix: str = "Word") -> str:
    """A one-sentence text of exactly `count` words."""
    return " ".join([prefix, *["word"] * (count - 1)]) + "."


def clause(
    label: str | None, word_count: int, *, heading: str | None = "Heading", page: int | None = None
) -> Section:
    return Section(label, heading, words(word_count), page)


def structured(*sections: Section) -> ExtractedDocument:
    return ExtractedDocument(list(sections), structured=True, page_count=None)


def unstructured(*paragraphs: tuple[str, int | None]) -> ExtractedDocument:
    sections = [Section(None, None, text, page) for text, page in paragraphs]
    return ExtractedDocument(sections, structured=False, page_count=None)


def sentence_list(count: int, word_count: int = 20) -> list[str]:
    """Sentences that start with a capital and are not substrings of one another."""
    return [words(word_count, prefix=f"Item{index}") for index in range(count)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("one", 2),
        ("", 1),
        ("   ", 1),
        ("one two three", 4),
        (" ".join(["w"] * 10), 13),
        (" ".join(["w"] * 11), 15),
        (" ".join(["w"] * 100), 130),
    ],
)
def test_estimate_tokens_is_words_times_1_3_rounded_up_and_never_zero(
    text: str, expected: int
) -> None:
    assert estimate_tokens(text) == expected


def test_a_clause_of_normal_size_is_one_chunk_with_its_details() -> None:
    section = clause("3.2", 60, heading="Refund handling", page=2)

    (chunk,) = chunk_document(structured(section))

    assert chunk == Chunk(
        chunk_index=0,
        section_label="3.2",
        heading="Refund handling",
        content=section.text,
        token_count=estimate_tokens(section.text),
        page_start=2,
    )


def test_chunk_indexes_run_from_zero_without_gaps() -> None:
    document = structured(*[clause(f"{n}.1", 60) for n in range(1, 8)])

    chunks = chunk_document(document)

    assert [chunk.chunk_index for chunk in chunks] == list(range(7))


def test_short_siblings_merge_into_a_range_with_labels_kept_in_the_text() -> None:
    sections = [clause("3.1", 10, page=4), clause("3.2", 12), clause("3.3", 8)]

    (chunk,) = chunk_document(structured(*sections))

    assert chunk.section_label == "3.1-3.3"
    assert chunk.content == "\n".join(f"{s.label} {s.text}" for s in sections)
    assert chunk.heading == "Heading"
    assert chunk.page_start == 4
    assert chunk.token_count == estimate_tokens(chunk.content)


def test_merging_stops_once_a_group_reaches_120_tokens() -> None:
    # 23 words is 30 tokens, so four clauses with their labels reach 120.
    sections = [clause(f"2.{n}", 23) for n in range(1, 11)]

    chunks = chunk_document(structured(*sections))

    assert [chunk.section_label for chunk in chunks] == ["2.1-2.4", "2.5-2.8", "2.9-2.10"]


def test_a_clause_that_stands_alone_is_not_given_a_range_or_prefix() -> None:
    sections = [clause("3.1", 10), clause("4.1", 10)]

    chunks = chunk_document(structured(*sections))

    assert [(c.section_label, c.content) for c in chunks] == [
        ("3.1", sections[0].text),
        ("4.1", sections[1].text),
    ]


def test_siblings_under_different_parents_are_not_merged() -> None:
    chunks = chunk_document(structured(clause("3.5", 10), clause("4.1", 10), clause("4.2", 10)))

    assert [chunk.section_label for chunk in chunks] == ["3.5", "4.1-4.2"]


def test_clauses_of_different_depth_are_not_merged() -> None:
    chunks = chunk_document(structured(clause("3.1", 10), clause("3.1.1", 10), clause("3.2", 10)))

    assert [chunk.section_label for chunk in chunks] == ["3.1", "3.1.1", "3.2"]


def test_top_level_and_unlabeled_sections_are_never_merged() -> None:
    sections = [clause(None, 10), clause(None, 10), clause("4", 10), clause("5", 10)]

    chunks = chunk_document(structured(*sections))

    assert [chunk.section_label for chunk in chunks] == [None, None, "4", "5"]


def test_a_bigger_clause_that_follows_a_short_one_is_merged_until_the_target_is_reached() -> None:
    # 31 words is 41 tokens: not short, but it follows a short clause, so it is part of the group.
    sections = [clause("3.1", 10), clause("3.2", 31), clause("3.3", 10), clause("3.4", 10)]

    chunks = chunk_document(structured(*sections))

    assert [chunk.section_label for chunk in chunks] == ["3.1-3.4"]


def test_a_clause_of_40_tokens_or_more_never_starts_a_group() -> None:
    sections = [clause("3.1", 31), clause("3.2", 10), clause("3.3", 10)]

    chunks = chunk_document(structured(*sections))

    assert [chunk.section_label for chunk in chunks] == ["3.1", "3.2-3.3"]


def test_a_sibling_that_would_push_a_group_over_400_tokens_is_left_out() -> None:
    # 300 words is 390 tokens. With the short clause and the label lines the merged text would
    # be about 405 tokens, so the two stay separate and neither chunk is over the limit.
    sections = [clause("3.1", 10), clause("3.2", 300)]

    chunks = chunk_document(structured(*sections))

    assert [chunk.section_label for chunk in chunks] == ["3.1", "3.2"]
    assert all(chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_a_long_clause_is_split_at_sentence_ends_with_nothing_lost_or_repeated() -> None:
    sentences = sentence_list(40)  # 40 * 26 = 1040 tokens
    section = Section("6.2", "Records", " ".join(sentences), 5)

    chunks = chunk_document(structured(section))

    assert len(chunks) == 3
    assert all(chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)
    assert min(chunk.token_count for chunk in chunks) > 300
    assert {(c.section_label, c.heading, c.page_start) for c in chunks} == {("6.2", "Records", 5)}
    assert " ".join(chunk.content for chunk in chunks) == " ".join(sentences)
    for chunk in chunks:
        assert chunk.content.endswith(".")


def test_one_enormous_sentence_is_cut_at_words_with_nothing_lost() -> None:
    text = " ".join(f"w{n}" for n in range(1000))  # no full stop at all

    chunks = chunk_document(structured(Section("1", None, text, None)))

    assert len(chunks) >= 4
    assert all(chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)
    assert " ".join(chunk.content for chunk in chunks).split() == text.split()


def test_abbreviations_do_not_end_a_sentence() -> None:
    sentences = ["Refunds take approx. five days, e.g. by card. " + words(15)]
    text = " ".join(sentences * 40)

    chunks = chunk_document(structured(Section("1", None, text, None)))

    assert all("approx. five" in chunk.content for chunk in chunks)
    assert all(not chunk.content.endswith("approx.") for chunk in chunks)


def test_unstructured_text_becomes_overlapping_windows_of_whole_sentences() -> None:
    sentences = sentence_list(60)
    paragraphs = [(" ".join(sentences[i : i + 12]), 1 + i // 12) for i in range(0, 60, 12)]

    chunks = chunk_document(unstructured(*paragraphs))

    assert len(chunks) > 1
    assert all(chunk.section_label is None and chunk.heading is None for chunk in chunks)
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    covered = [{i for i, s in enumerate(sentences) if s in chunk.content} for chunk in chunks]
    assert set().union(*covered) == set(range(60))
    for before, after in itertools.pairwise(covered):
        shared = before & after
        assert (
            sum(estimate_tokens(sentences[i]) for i in shared) >= 50
        )  # the documented overlap, not the module constant
        assert max(before) < max(after)
    for chunk, indexes in zip(chunks, covered, strict=True):
        assert chunk.page_start == 1 + min(indexes) // 12


def test_a_short_unstructured_text_is_one_chunk() -> None:
    (chunk,) = chunk_document(unstructured(("First point. Second point. Third point.", 1)))

    assert chunk == Chunk(0, None, None, "First point. Second point. Third point.", 8, 1)


def test_an_overlong_sentence_in_unstructured_text_is_cut_at_words() -> None:
    text = " ".join(f"w{n}" for n in range(700))

    chunks = chunk_document(unstructured((text, None)))

    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    assert set(" ".join(chunk.content for chunk in chunks).split()) == set(text.split())


def test_a_document_with_no_sections_has_no_chunks() -> None:
    assert chunk_document(unstructured()) == []
    assert chunk_document(structured()) == []


def test_the_sample_sop_is_chunked_by_section() -> None:
    document = extract_document(SOP_TEXT.encode(), "text/markdown")

    chunks = chunk_document(document)

    assert [chunk.section_label for chunk in chunks] == SOP_CHUNK_LABELS
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.heading for chunk in chunks][1:4] == [
        "Purpose and scope",
        "Support hours and channels",
        "Refund handling",
    ]


def test_the_two_contradicting_refund_limits_land_in_different_chunks() -> None:
    chunks = {
        c.section_label: c
        for c in chunk_document(extract_document(SOP_TEXT.encode(), "text/markdown"))
    }

    assert "3.1 L1 agents may approve refunds up to INR 5,000" in chunks["3.1-3.5"].content
    assert "5.3 To limit fraud exposure" in chunks["5.1-5.4"].content
    assert "INR 2,500" not in chunks["3.1-3.5"].content


def test_every_clause_of_the_sample_sop_is_in_exactly_one_chunk() -> None:
    document = extract_document(SOP_TEXT.encode(), "text/markdown")

    chunks = chunk_document(document)

    for section in document.sections:
        holders = [chunk for chunk in chunks if section.text in chunk.content]
        assert len(holders) == 1


def test_the_sample_sop_as_a_pdf_gives_the_same_clause_chunks() -> None:
    from_markdown = chunk_document(extract_document(SOP_TEXT.encode(), "text/markdown"))
    from_pdf = chunk_document(extract_document(sop_as_pdf(), "application/pdf"))

    def clause_chunks(chunks: list[Chunk]) -> list[tuple[str | None, str | None, str]]:
        return [(c.section_label, c.heading, c.content) for c in chunks if c.section_label]

    assert clause_chunks(from_pdf) == clause_chunks(from_markdown)
    assert [c.page_start for c in from_pdf if c.section_label] == [1, 1, 2, 2, 3, 3, 3]


@pytest.mark.parametrize("same_parent", [True, False])
def test_a_hundred_thousand_short_sections_chunk_quickly(same_parent: bool) -> None:
    sections = [
        clause(f"1.{n}" if same_parent else f"{n}.1", 5, heading=None) for n in range(100_000)
    ]
    started = time.perf_counter()

    chunks = chunk_document(structured(*sections))

    assert time.perf_counter() - started < 5
    assert chunks
