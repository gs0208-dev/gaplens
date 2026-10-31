"""Small PDFs built in memory, so no binary fixture files are committed."""

import secrets
from io import BytesIO

from pypdf import PdfReader, PdfWriter


def text_pdf(pages: list[str]) -> bytes:
    """A valid PDF with one line of Helvetica text per page, written by hand."""
    objects: list[bytes] = []
    page_count = len(pages)
    # Object numbers: 1 catalog, 2 page tree, 3 font, then a page and a content stream per page.
    first_page = 4
    kids = " ".join(f"{first_page + 2 * index} 0 R" for index in range(page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(pages):
        content_number = first_page + 2 * index + 1
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
            ).encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(output)


def blank_pdf(page_count: int = 1) -> bytes:
    """A valid PDF whose pages have no text, like a scan."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf() -> bytes:
    """A PDF with text that is encrypted. An empty user password still counts as encrypted."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(text_pdf(["Secret refund policy"]))))
    writer.encrypt(user_password="", owner_password=secrets.token_hex(8))
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
