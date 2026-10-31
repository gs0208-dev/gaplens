import pytest

from app.modules.ingestion.extract import Page, extract_pages, normalize_text, remove_repeated_lines
from tests.pdf_fixtures import blank_pdf, text_pdf

# Built with chr() so the invisible and look-alike characters stay visible in review.
LIGATURE_FFI = chr(0xFB03)
FULL_WIDTH_5 = chr(0xFF15)
NO_BREAK_SPACE = chr(0x00A0)
ZERO_WIDTH_SPACE = chr(0x200B)
SOFT_HYPHEN = chr(0x00AD)
BYTE_ORDER_MARK = chr(0xFEFF)
LINE_SEPARATOR = chr(0x2028)
PARAGRAPH_SEPARATOR = chr(0x2029)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"o{LIGATURE_FFI}ce", "office"),
        (f"limit {FULL_WIDTH_5}000", "limit 5000"),
        (f"INR{NO_BREAK_SPACE}5,000", "INR 5,000"),
        (f"re{ZERO_WIDTH_SPACE}fund", "refund"),
        (f"refund{SOFT_HYPHEN}able", "refundable"),
        (f"{BYTE_ORDER_MARK}Title", "Title"),
        ("one\r\ntwo\rthree", "one\ntwo\nthree"),
        (f"one{LINE_SEPARATOR}two{PARAGRAPH_SEPARATOR}three", "one\ntwo\nthree"),
        ("a \t  b   c", "a b c"),
        ("  padded line  \n\tnext  ", "padded line\nnext"),
        ("one\n\n\n\n\ntwo", "one\n\ntwo"),
        ("bell\x07 and null\x00 removed", "bell and null removed"),
        ("   \n\n  ", ""),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_a_pdf_gives_one_numbered_page_per_pdf_page() -> None:
    pdf = text_pdf(["First page text", "Second page text", "Third page text"])

    pages = extract_pages(pdf, "application/pdf")

    assert [(page.number, page.text) for page in pages] == [
        (1, "First page text"),
        (2, "Second page text"),
        (3, "Third page text"),
    ]


def test_a_pdf_page_without_text_keeps_its_number() -> None:
    pages = extract_pages(blank_pdf(2), "application/pdf")

    assert [(page.number, page.text) for page in pages] == [(1, ""), (2, "")]


@pytest.mark.parametrize("mime_type", ["text/plain", "text/markdown"])
def test_text_and_markdown_are_one_page_without_a_number(mime_type: str) -> None:
    pages = extract_pages(b"\xef\xbb\xbf1.1 First.\r\n\r\n\r\n\r\n1.2 Second.", mime_type)

    assert pages == [Page(None, "1.1 First.\n\n1.2 Second.")]


BODIES = ["Refunds", "Escalations", "Quality", "Records", "Payments"]


def footer_pages(count: int) -> list[Page]:
    return [
        Page(
            number,
            f"Northwind Telecom - Confidential\n{BODIES[number - 1]}\nPage {number} of {count}",
        )
        for number in range(1, count + 1)
    ]


def test_a_repeated_header_and_a_page_number_footer_are_removed() -> None:
    cleaned = remove_repeated_lines(footer_pages(4))

    assert [page.text for page in cleaned] == BODIES[:4]
    assert [page.number for page in cleaned] == [1, 2, 3, 4]


def test_a_line_on_most_but_not_all_pages_is_still_removed() -> None:
    pages = footer_pages(5)
    pages[2] = Page(3, BODIES[2])  # this page has no header or footer

    cleaned = remove_repeated_lines(pages)

    assert [page.text for page in cleaned] == BODIES


def test_a_repeated_line_in_the_middle_of_pages_is_kept() -> None:
    def body(word: str) -> str:
        return f"Intro {word}\nDetail {word}\nSee the escalation matrix\nMore {word}\nOutro {word}"

    pages = [Page(number, body(BODIES[number - 1])) for number in range(1, 5)]

    cleaned = remove_repeated_lines(pages)

    assert all("See the escalation matrix" in page.text for page in cleaned)


def test_lines_that_differ_only_in_a_digit_are_not_treated_as_a_footer() -> None:
    pages = [Page(number, f"Step {number}\nBody text {number}") for number in range(1, 5)]

    assert remove_repeated_lines(pages) == pages


def test_a_line_on_half_the_pages_or_fewer_is_kept() -> None:
    pages = [
        Page(1, "Confidential\nBody one"),
        Page(2, "Confidential\nBody two"),
        Page(3, "Body three"),
        Page(4, "Body four"),
    ]

    assert remove_repeated_lines(pages) == pages


def test_documents_under_three_pages_are_left_alone() -> None:
    pages = footer_pages(2)

    assert remove_repeated_lines(pages) == pages


def test_removal_works_on_a_real_pdf() -> None:
    pdf = text_pdf([f"Acme Handbook\n{BODIES[n - 1]}\nPage {n} of 3" for n in range(1, 4)])

    pages = extract_pages(pdf, "application/pdf")

    assert [page.text for page in pages] == BODIES[:3]
