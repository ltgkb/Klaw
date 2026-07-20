"""DeepDoc routing regressions."""

from app.services.deepdoc_service import parse_document


def test_text_parser_remains_available_with_lazy_parser_exports():
    blocks = parse_document("notes.txt", "第一段\nsecond section".encode())

    assert blocks
    assert all(block["content_type"] == "text" for block in blocks)
    assert "第一段" in "\n".join(block["content"] for block in blocks)


def test_parser_package_public_contract():
    from deepdoc.parser import JsonParser, MarkdownParser, TxtParser

    assert TxtParser.__name__ == "RAGFlowTxtParser"
    assert JsonParser.__name__ == "RAGFlowJsonParser"
    assert MarkdownParser.__name__ == "RAGFlowMarkdownParser"
