"""Document parser loading and lightweight format regressions."""

import subprocess
import sys
from pathlib import Path


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
