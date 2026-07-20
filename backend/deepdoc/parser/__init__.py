#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from importlib import import_module


_LAZY_IMPORTS = {
    "PdfParser": (".pdf_parser", "RAGFlowPdfParser"),
    "PlainParser": (".pdf_parser", "PlainParser"),
    "DocxParser": (".docx_parser", "RAGFlowDocxParser"),
    "EpubParser": (".epub_parser", "RAGFlowEpubParser"),
    "ExcelParser": (".excel_parser", "RAGFlowExcelParser"),
    "PptParser": (".ppt_parser", "RAGFlowPptParser"),
    "HtmlParser": (".html_parser", "RAGFlowHtmlParser"),
    "JsonParser": (".json_parser", "RAGFlowJsonParser"),
    "MarkdownParser": (".markdown_parser", "RAGFlowMarkdownParser"),
    "MarkdownElementExtractor": (".markdown_parser", "MarkdownElementExtractor"),
    "TxtParser": (".txt_parser", "RAGFlowTxtParser"),
}


def __getattr__(name):
    """Load only the parser needed for the current document type."""
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

__all__ = [
    "PdfParser",
    "PlainParser",
    "DocxParser",
    "EpubParser",
    "ExcelParser",
    "PptParser",
    "HtmlParser",
    "JsonParser",
    "MarkdownParser",
    "TxtParser",
    "MarkdownElementExtractor",
]
