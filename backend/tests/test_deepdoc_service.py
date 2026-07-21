"""Document parser loading and lightweight format regressions."""

import subprocess
import sys
from io import BytesIO
from pathlib import Path

from app.services.deepdoc_service import parse_document


def test_txt_parse_does_not_load_pdf_or_vision_stack():
    """A TXT upload must not import the heavyweight OCR/PDF dependency graph."""
    script = """
import sys
from app.services.deepdoc_service import parse_document

blocks = parse_document("sample.txt", b"lightweight parser evidence")
assert blocks[0]["content"] == "lightweight parser evidence"
for forbidden in ("deepdoc.parser.pdf_parser", "deepdoc.vision", "xgboost"):
    assert forbidden not in sys.modules, forbidden
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_lightweight_text_formats_parse_real_content():
    samples = {
        "sample.md": (b"# Audit\n\nKlaw markdown evidence.", "Klaw markdown evidence"),
        "sample.html": (b"<html><body><h1>Audit</h1><p>Klaw html evidence.</p></body></html>", "Klaw html evidence"),
        "sample.json": (b'{"audit": "Klaw json evidence"}', "Klaw json evidence"),
    }
    for filename, (data, expected) in samples.items():
        blocks = parse_document(filename, data)
        assert expected in "\n".join(block["content"] for block in blocks)


def test_office_formats_parse_generated_files():
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation

    doc = Document()
    doc.add_paragraph("Klaw docx evidence")
    docx = BytesIO()
    doc.save(docx)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["kind", "value"])
    sheet.append(["audit", "Klaw xlsx evidence"])
    xlsx = BytesIO()
    workbook.save(xlsx)

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Audit"
    slide.placeholders[1].text = "Klaw pptx evidence"
    pptx = BytesIO()
    presentation.save(pptx)

    samples = {
        "sample.docx": (docx.getvalue(), "Klaw docx evidence"),
        "sample.xlsx": (xlsx.getvalue(), "Klaw xlsx evidence"),
        "sample.pptx": (pptx.getvalue(), "Klaw pptx evidence"),
    }
    for filename, (data, expected) in samples.items():
        blocks = parse_document(filename, data)
        assert expected in "\n".join(block["content"] for block in blocks)


def test_plain_pdf_without_text_parses_without_vision_dependencies():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf = BytesIO()
    writer.write(pdf)
    assert parse_document("blank.pdf", pdf.getvalue()) == []
