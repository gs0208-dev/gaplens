"""The fictional sample SOP from evals/, as Markdown text and as a PDF."""

from pathlib import Path

from tests.pdf_fixtures import text_pdf

DATASETS = Path(__file__).resolve().parents[2] / "evals" / "datasets"
SOP_TEXT = (DATASETS / "sop_refund_escalation.md").read_text()


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
