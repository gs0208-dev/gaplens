import uuid

import pytest

from app.ai.schemas import ChatAnswerOut
from app.modules.chat.grounding import NOT_FOUND_ANSWER, QUOTE_LENGTH, excerpt, verify_answer
from app.modules.retrieval.repository import RetrievedChunk


def chunk(content: str, label: str | None = "3.1-3.5") -> RetrievedChunk:
    return RetrievedChunk(
        id=uuid.uuid4(),
        chunk_index=0,
        section_label=label,
        heading="Heading",
        content=content,
        page_start=None,
        score=0.8,
    )


def output(answer: str, cited: list[int], *, grounded: bool = True) -> ChatAnswerOut:
    return ChatAnswerOut(answer=answer, cited_sources=cited, grounded=grounded)


CHUNKS = [chunk("First source text.", "3.1-3.5"), chunk("Second source text.", "5.1-5.4")]


def test_a_valid_citation_gives_the_chunk_id_label_and_stored_text() -> None:
    result = verify_answer(output("The limit is 5,000.", [1]), CHUNKS)

    assert result.grounded is True
    assert result.answer == "The limit is 5,000."
    assert result.citations == [
        {
            "chunk_id": str(CHUNKS[0].id),
            "section_label": "3.1-3.5",
            "quote": "First source text.",
        }
    ]


def test_two_cited_sources_keep_the_order_the_model_gave() -> None:
    result = verify_answer(output("They differ.", [2, 1]), CHUNKS)

    assert [c["section_label"] for c in result.citations] == ["5.1-5.4", "3.1-3.5"]


@pytest.mark.parametrize("cited", [[1, 1, 1], [1, 99], [0, 1], [-1, 1], [3, 1]])
def test_invalid_numbers_and_duplicates_are_dropped_but_valid_ones_stay(cited: list[int]) -> None:
    result = verify_answer(output("Answer.", cited), CHUNKS)

    assert result.grounded is True
    assert [c["chunk_id"] for c in result.citations] == [str(CHUNKS[0].id)]


@pytest.mark.parametrize("cited", [[], [0], [3], [99], [-1]])
def test_a_grounded_answer_without_a_valid_citation_becomes_not_found(cited: list[int]) -> None:
    result = verify_answer(output("The limit is 9,999.", cited), CHUNKS)

    assert (result.answer, result.grounded, result.citations) == (NOT_FOUND_ANSWER, False, [])


def test_an_ungrounded_answer_is_replaced_even_if_it_cites_something() -> None:
    result = verify_answer(output("I think it is 9,999.", [1], grounded=False), CHUNKS)

    assert (result.answer, result.grounded, result.citations) == (NOT_FOUND_ANSWER, False, [])


@pytest.mark.parametrize("answer", ["", "   \n"])
def test_an_empty_answer_becomes_not_found(answer: str) -> None:
    assert verify_answer(output(answer, [1]), CHUNKS).answer == NOT_FOUND_ANSWER


def test_no_chunks_at_all_gives_not_found() -> None:
    assert verify_answer(output("Answer.", [1]), []).grounded is False


def test_a_short_chunk_is_quoted_whole() -> None:
    assert excerpt("short text") == "short text"


def test_a_long_chunk_is_cut_at_a_word_and_stays_a_verbatim_prefix() -> None:
    content = " ".join(f"word{n}" for n in range(200))

    quote = excerpt(content)

    assert len(quote) <= QUOTE_LENGTH
    assert content.startswith(quote)
    assert not quote.endswith(" ")
    assert content[len(quote)] == " "


def test_a_long_chunk_without_spaces_is_cut_at_the_limit() -> None:
    assert excerpt("x" * 1000) == "x" * QUOTE_LENGTH
