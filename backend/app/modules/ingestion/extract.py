import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.modules.ingestion.validate import PDF_MIME_TYPE

# Repeated header and footer removal needs enough pages for "appears on most of them" to mean
# something. With two pages, a line on both is just as likely to be real content.
MIN_PAGES_FOR_REPEAT_REMOVAL = 3
# Headers and footers sit at the edge of a page, so only this many non-empty lines are looked at
# from each end. A repeated line in the middle of a page is body text and stays.
EDGE_LINES = 2

_SPACE_RUNS = re.compile(r"[ \t]+")
_BLANK_LINE_RUNS = re.compile(r"\n{3,}")
_DIGIT_RUNS = re.compile(r"\d+")
_PAGE_NUMBER_LINE = re.compile(r"(?i)\bpage\s*\d+|^\W*\d+(?:\s*(?:/|of)\s*\d+)?\W*$")
# Control (Cc) and format (Cf) characters: stray control codes, zero-width spaces, soft hyphens
# and the byte order mark. None of them carry meaning in a process document.
_DROPPED_CATEGORIES = {"Cc", "Cf"}


@dataclass(frozen=True)
class Page:
    # 1-based for a PDF page. None for text and Markdown, which have no pages.
    number: int | None
    text: str


def normalize_text(text: str) -> str:
    """Make text from any source look the same: one Unicode form, one kind of line break, no
    invisible characters, no ragged whitespace."""
    # NFKC folds look-alike characters together (the "fi" ligature, full-width digits, the
    # non-breaking space), so a clause number or a quote compares the way a person reads it.
    text = unicodedata.normalize("NFKC", text)
    # splitlines treats \r\n, \r, form feed and the Unicode line and paragraph separators as
    # line breaks, so every kind becomes a plain newline.
    text = "\n".join(text.splitlines())
    text = "".join(
        char
        for char in text
        if char in "\n\t" or unicodedata.category(char) not in _DROPPED_CATEGORIES
    )
    text = _SPACE_RUNS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINE_RUNS.sub("\n\n", text).strip()


def _line_key(line: str) -> str:
    """What to compare when looking for a repeated line.

    A line that is a page number ("Page 2 of 9", "- 3 -", "4/12") has its digits replaced, so the
    footer on every page is one and the same line. Any other line is compared exactly: folding
    digits everywhere would make "Step 1 ..." and "Step 2 ..." look like the same header.
    """
    line = line.strip()
    return _DIGIT_RUNS.sub("#", line) if _PAGE_NUMBER_LINE.search(line) else line


def _edge_line_indexes(lines: list[str]) -> list[int]:
    non_empty = [index for index, line in enumerate(lines) if line.strip()]
    return sorted({*non_empty[:EDGE_LINES], *non_empty[-EDGE_LINES:]})


def remove_repeated_lines(pages: list[Page]) -> list[Page]:
    """Drop running headers and footers: a line at the edge of more than half the pages."""
    if len(pages) < MIN_PAGES_FOR_REPEAT_REMOVAL:
        return pages

    split_pages = [page.text.split("\n") for page in pages]
    pages_with_key: Counter[str] = Counter()
    for lines in split_pages:
        # A set, so a line repeated twice on one page still counts as one page.
        pages_with_key.update({_line_key(lines[index]) for index in _edge_line_indexes(lines)})
    repeated = {key for key, count in pages_with_key.items() if count * 2 > len(pages)}
    if not repeated:
        return pages

    cleaned: list[Page] = []
    for page, lines in zip(pages, split_pages, strict=True):
        drop = {index for index in _edge_line_indexes(lines) if _line_key(lines[index]) in repeated}
        kept = [line for index, line in enumerate(lines) if index not in drop]
        text = _BLANK_LINE_RUNS.sub("\n\n", "\n".join(kept)).strip()
        cleaned.append(Page(page.number, text))
    return cleaned


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    """Clean text per page. The bytes have already passed `inspect_upload`.

    A parser failure still raises; the pipeline that calls this turns it into a failed document.
    """
    if mime_type == PDF_MIME_TYPE:
        reader = PdfReader(BytesIO(data))
        pages = [
            Page(number, normalize_text(page.extract_text()))
            for number, page in enumerate(reader.pages, start=1)
        ]
        return remove_repeated_lines(pages)
    return [Page(None, normalize_text(data.decode("utf-8")))]
