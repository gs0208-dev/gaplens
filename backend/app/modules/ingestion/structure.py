import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from app.modules.ingestion.extract import Page, extract_pages
from app.modules.ingestion.validate import MARKDOWN_MIME_TYPE

# A clause number: 3, 3.1, 3.1.2, at most three digits per part (so a year is not a number),
# with an optional closing dot or bracket, then the clause text.
_NUMBERED = re.compile(r"^(?P<label>\d{1,3}(?:\.\d{1,3})*)[.)]?\s+(?P<text>\S.*)$")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(?P<text>\S.*)$")
_CODE_FENCE = re.compile(r"^(```|~~~)")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

# A numbered line with no body that is directly followed by a sub-clause is a title if it is
# short and does not read like a sentence.
MAX_TITLE_WORDS = 10
_SENTENCE_ENDINGS = ".;:?!"


@dataclass(frozen=True)
class Section:
    # "3.1" for a numbered clause, None for text with no number.
    label: str | None
    # The title of the section this text sits under, for example "Refund handling".
    heading: str | None
    text: str
    # The page the section starts on. None for text and Markdown.
    page_start: int | None


@dataclass(frozen=True)
class ExtractedDocument:
    sections: list[Section]
    # False when no clause numbers or headings were found and sections are plain paragraphs.
    structured: bool
    page_count: int | None


@dataclass
class _Block:
    """One start line and the lines under it, before headings are told apart from clauses."""

    label: str | None
    start_text: str
    is_markdown_heading: bool
    page: int | None
    body: list[str] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        return "\n".join(self.body).strip()


def _split_label(text: str) -> tuple[str | None, str]:
    match = _NUMBERED.match(text)
    return (match["label"], match["text"]) if match else (None, text)


def _is_descendant(parent_label: str | None, child_label: str | None) -> bool:
    """3.1 and 3.1.2 are under 3. An unlabeled heading (a document title) is over everything."""
    if parent_label is None:
        return True
    return child_label is not None and child_label.startswith(parent_label + ".")


def _ancestors(label: str) -> Iterator[str]:
    """3.1.2 gives 3.1, then 3: the closest enclosing section first."""
    parts = label.split(".")
    for length in range(len(parts) - 1, 0, -1):
        yield ".".join(parts[:length])


def _find_blocks(pages: list[Page], *, markdown: bool) -> list[_Block]:
    # The first block holds any text before the first start line.
    blocks = [_Block(label=None, start_text="", is_markdown_heading=False, page=pages[0].number)]
    in_code_fence = False
    for page in pages:
        for line in page.text.split("\n"):
            # Inside a Markdown code fence a "#" is a comment or a shell prompt, not a heading.
            if markdown and _CODE_FENCE.match(line):
                in_code_fence = not in_code_fence
                blocks[-1].body.append(line)
                continue
            if in_code_fence:
                blocks[-1].body.append(line)
                continue
            heading = _MARKDOWN_HEADING.match(line) if markdown else None
            if heading:
                title = heading["text"].rstrip("#").strip()
                label, title = _split_label(title)
                blocks.append(_Block(label, title, True, page.number))
                continue
            numbered = _NUMBERED.match(line)
            # A lowercase word after the number means a wrapped line ("5 percent of ..." or
            # "1.5 million ..."), not the start of a clause.
            if numbered and numbered["text"][0].isupper():
                blocks.append(_Block(numbered["label"], numbered["text"], False, page.number))
                continue
            blocks[-1].body.append(line)
    return blocks


def _is_title_line(block: _Block, next_block: _Block | None) -> bool:
    return (
        not block.is_markdown_heading
        and not block.body_text
        and len(block.start_text.split()) <= MAX_TITLE_WORDS
        and block.start_text[-1] not in _SENTENCE_ENDINGS
        and next_block is not None
        and _is_descendant(block.label, next_block.label)
    )


def _build_sections(blocks: list[_Block]) -> list[Section]:
    sections: list[Section] = []
    # Titles of the headings seen so far, by clause number, for the "heading" of what follows.
    titles: dict[str, str] = {}
    document_title: str | None = None

    def enclosing_title(label: str | None) -> str | None:
        if label is not None:
            for ancestor in _ancestors(label):
                if ancestor in titles:
                    return titles[ancestor]
        return document_title

    for index, block in enumerate(blocks):
        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        body = block.body_text

        if not block.start_text:
            if body:
                sections.append(Section(None, document_title, body, block.page))
            continue

        is_heading = block.is_markdown_heading or _is_title_line(block, next_block)
        if is_heading:
            has_children = next_block is not None and _is_descendant(block.label, next_block.label)
            if body or has_children:
                if block.label is not None:
                    titles[block.label] = block.start_text
                else:
                    document_title = block.start_text
                if body:
                    sections.append(Section(block.label, block.start_text, body, block.page))
                continue
            # A heading with nothing under it keeps its title as text, so no words are lost.
            sections.append(
                Section(block.label, enclosing_title(block.label), block.start_text, block.page)
            )
            continue

        text = block.start_text + ("\n" + body if body else "")
        sections.append(Section(block.label, enclosing_title(block.label), text, block.page))
    return sections


def _split_paragraphs(pages: list[Page]) -> list[Section]:
    return [
        Section(None, None, paragraph.strip(), page.number)
        for page in pages
        for paragraph in _PARAGRAPH_BREAK.split(page.text)
        if paragraph.strip()
    ]


def detect_sections(pages: list[Page], *, markdown: bool) -> ExtractedDocument:
    page_count = None if pages[0].number is None else len(pages)
    blocks = _find_blocks(pages, markdown=markdown)
    if len(blocks) == 1:
        # No clause numbers and no headings anywhere: fall back to paragraphs.
        return ExtractedDocument(_split_paragraphs(pages), structured=False, page_count=page_count)
    return ExtractedDocument(_build_sections(blocks), structured=True, page_count=page_count)


def extract_document(data: bytes, mime_type: str) -> ExtractedDocument:
    """Bytes of a validated upload to ordered sections with labels, headings and pages."""
    pages = extract_pages(data, mime_type)
    return detect_sections(pages, markdown=mime_type == MARKDOWN_MIME_TYPE)
