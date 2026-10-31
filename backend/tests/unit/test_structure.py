import re
import time
from pathlib import Path

from app.modules.ingestion.extract import Page
from app.modules.ingestion.structure import Section, detect_sections, extract_document
from tests.pdf_fixtures import text_pdf

DATASETS = Path(__file__).resolve().parents[3] / "evals" / "datasets"
SOP_TEXT = (DATASETS / "sop_refund_escalation.md").read_text()
INJECTION_BYTES = (DATASETS / "injection_sample.md").read_bytes()
SOP_LABELS = [
    None,
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2", "3.3", "3.4", "3.5",
    "4.1", "4.2", "4.3",
    "5.1", "5.2", "5.3", "5.4",
    "6.1", "6.2",
    "7.1",
]  # fmt: skip
SOP_HEADINGS = {
    "1": "Purpose and scope",
    "2": "Support hours and channels",
    "3": "Refund handling",
    "4": "Escalations",
    "5": "Quality and review",
    "6": "Records and urgent cases",
    "7": "Payments",
}
# Page of each top-level section in the PDF rendering below.
SOP_PDF_PAGE = {"1": 1, "2": 1, "3": 2, "4": 2, "5": 3, "6": 3, "7": 3}


def markdown_sections(text: str) -> list[Section]:
    return extract_document(text.encode(), "text/markdown").sections


def plain_sections(text: str) -> list[Section]:
    return extract_document(text.encode(), "text/plain").sections


def as_tuples(sections: list[Section]) -> list[tuple[str | None, str | None, str]]:
    return [(section.label, section.heading, section.text) for section in sections]


def sop_as_pdf() -> bytes:
    """The sample SOP as a 3-page PDF: Markdown marks removed, a running header and a footer."""
    lines = [
        line.lstrip("#").strip() if line.startswith("#") else line for line in SOP_TEXT.splitlines()
    ]
    starts = [lines.index("3. Refund handling"), lines.index("5. Quality and review")]
    chunks = [lines[: starts[0]], lines[starts[0] : starts[1]], lines[starts[1] :]]
    return text_pdf(
        [
            "Northwind Telecom - Confidential\n" + "\n".join(chunk) + f"\nPage {number} of 3"
            for number, chunk in enumerate(chunks, start=1)
        ]
    )


def test_the_sample_sop_gives_the_expected_sections() -> None:
    document = extract_document(SOP_TEXT.encode(), "text/markdown")

    assert document.structured is True
    assert document.page_count is None
    assert [section.label for section in document.sections] == SOP_LABELS
    assert all(section.page_start is None for section in document.sections)


def test_clauses_sit_under_the_title_of_their_section() -> None:
    sections = markdown_sections(SOP_TEXT)

    for section in sections[1:]:
        assert section.label is not None
        assert section.heading == SOP_HEADINGS[section.label.split(".")[0]]


def test_the_preamble_is_a_section_under_the_document_title() -> None:
    preamble = markdown_sections(SOP_TEXT)[0]

    assert preamble.label is None
    assert preamble.heading == "Refund and Escalation Handling SOP"
    assert preamble.text.startswith("Company: Northwind Telecom (fictional).")


def test_the_two_contradicting_limits_are_in_their_own_sections() -> None:
    by_label = {section.label: section for section in markdown_sections(SOP_TEXT)}

    assert "INR 5,000" in by_label["3.1"].text
    assert "INR 2,500" in by_label["5.3"].text
    assert by_label["3.1"].text.startswith("L1 agents may approve refunds")


def test_every_word_of_the_sop_survives_extraction() -> None:
    sections = markdown_sections(SOP_TEXT)
    kept = " ".join(f"{s.label or ''} {s.heading or ''} {s.text}" for s in sections)

    words = set(re.findall(r"[A-Za-z0-9,]+", SOP_TEXT))

    assert words <= set(re.findall(r"[A-Za-z0-9,]+", kept))


def test_the_sop_as_a_pdf_gives_the_same_clauses_as_the_markdown() -> None:
    from_markdown = [
        s for s in extract_document(SOP_TEXT.encode(), "text/markdown").sections if s.label
    ]
    pdf_document = extract_document(sop_as_pdf(), "application/pdf")
    from_pdf = [s for s in pdf_document.sections if s.label]

    assert as_tuples(from_pdf) == as_tuples(from_markdown)
    assert pdf_document.page_count == 3
    assert pdf_document.structured is True


def test_pdf_sections_know_their_page_and_the_running_header_is_gone() -> None:
    pdf_document = extract_document(sop_as_pdf(), "application/pdf")

    for section in pdf_document.sections:
        if section.label:
            assert section.page_start == SOP_PDF_PAGE[section.label.split(".")[0]]
        assert "Confidential" not in section.text
        assert "Page" not in section.text.split("\n")[-1]
    assert pdf_document.sections[0].page_start == 1


def test_a_numbered_pdf_title_becomes_the_heading_of_its_clauses() -> None:
    pdf_document = extract_document(sop_as_pdf(), "application/pdf")

    by_label = {section.label: section for section in pdf_document.sections}

    assert by_label["3.2"].heading == "Refund handling"
    assert "3" not in by_label


def test_a_clause_that_runs_onto_the_next_page_keeps_its_first_page() -> None:
    pages = [
        Page(1, "1.1 Refunds are approved\nby the lead"),
        Page(2, "after review.\n1.2 Next clause."),
    ]

    sections = detect_sections(pages, markdown=False).sections

    assert [(s.label, s.page_start) for s in sections] == [("1.1", 1), ("1.2", 2)]
    assert sections[0].text == "Refunds are approved\nby the lead\nafter review."


def test_text_without_any_structure_falls_back_to_paragraphs() -> None:
    document = extract_document(
        b"First paragraph about refunds.\nIt wraps onto a second line.\n\nSecond paragraph.",
        "text/plain",
    )

    assert document.structured is False
    assert as_tuples(document.sections) == [
        (None, None, "First paragraph about refunds.\nIt wraps onto a second line."),
        (None, None, "Second paragraph."),
    ]


def test_unstructured_pdf_paragraphs_keep_their_page() -> None:
    document = extract_document(text_pdf(["Alpha text", "Beta text"]), "application/pdf")

    assert document.structured is False
    assert [(s.text, s.page_start) for s in document.sections] == [
        ("Alpha text", 1),
        ("Beta text", 2),
    ]


def test_an_empty_document_has_no_sections() -> None:
    document = extract_document(b"", "text/plain")

    assert (document.sections, document.structured) == ([], False)


def test_wrapped_lines_that_start_with_a_number_are_not_clauses() -> None:
    text = (
        "3.2 Refunds above INR 5,000 need approval from a team lead once\n"
        "25,000 customers were reviewed and\n"
        "5 percent of tickets are audited, while\n"
        "1.5 million users exist. The year was\n"
        "2024. Contact 3.1.2024 for details."
    )

    sections = plain_sections(text)

    assert [section.label for section in sections] == ["3.2"]
    assert "5 percent of tickets" in sections[0].text


def test_a_hash_inside_a_code_fence_is_not_a_heading() -> None:
    text = (
        "# Guide\n\n## 1. Setup\n\n1.1 Run the installer.\n\n"
        "```\n# not a heading\n2.5 Not a clause\n```\n"
    )

    sections = markdown_sections(text)

    assert [s.label for s in sections] == ["1.1"]
    assert "# not a heading" in sections[0].text
    assert "2.5 Not a clause" in sections[0].text


def test_a_hash_line_is_only_a_heading_in_markdown() -> None:
    sections = plain_sections("# Not a heading\n1.1 A clause.")

    assert as_tuples(sections) == [
        (None, None, "# Not a heading"),
        ("1.1", None, "A clause."),
    ]


def test_deep_labels_find_the_closest_title_and_a_childless_title_is_kept() -> None:
    text = "3 Escalation\n3.1 Level one\n3.1.2 Detail text here.\n3.2 Other"

    sections = plain_sections(text)

    assert as_tuples(sections) == [
        ("3.1.2", "Level one", "Detail text here."),
        ("3.2", "Escalation", "Other"),
    ]


def test_a_heading_with_nothing_under_it_is_kept_as_text() -> None:
    text = "# Title\n\n## 1. Alpha\n\n## 2. Beta\n\n2.1 Clause body."

    sections = markdown_sections(text)

    assert as_tuples(sections) == [
        ("1", "Title", "Alpha"),
        ("2.1", "Beta", "Clause body."),
    ]


def test_a_markdown_heading_with_its_own_text_keeps_that_text() -> None:
    sections = markdown_sections("## 4. Quality\nOverall text here.\n\n4.1 A clause.")

    assert as_tuples(sections) == [
        ("4", "Quality", "Overall text here."),
        ("4.1", "Quality", "A clause."),
    ]


def test_a_numbered_title_with_a_closing_bracket_is_recognised() -> None:
    sections = plain_sections("1) Scope\n1.1) Who it covers.")

    assert as_tuples(sections) == [("1.1", "Scope", "Who it covers.")]


def test_instructions_inside_a_document_are_kept_as_plain_text() -> None:
    sections = extract_document(INJECTION_BYTES, "text/markdown").sections

    by_label = {section.label: section for section in sections}

    assert "ignore all previous instructions" in by_label["2.1"].text
    assert by_label["2.1"].heading == "Review"
    assert by_label["2.2"].heading == "Review"


def test_a_very_long_line_of_digits_and_dots_is_handled_quickly() -> None:
    hostile = "1" + ".1" * 50_000 + " tail\n" + "9" * 100_000 + " tail"
    started = time.perf_counter()

    sections = plain_sections(hostile)

    assert time.perf_counter() - started < 2
    assert len(sections) == 1
