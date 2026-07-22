"""DeepDoc 解析服务。

封装 RAGFlow DeepDoc parser，按文件类型路由，统一返回标准化的解析结果。
对齐 PRD 第 3.1 节: 文档上传 → DeepDoc 解析 → 分块。

DeepDoc 各 parser 返回结构不一致:
  - TxtParser/HtmlParser/JsonParser: [[text, ""], ...] 或 [text, ...]
  - DocxParser: (sections, tables) — sections=[(text, style)], tables=[html]
  - PlainParser (PDF): ([(line, "")], [])
  - ExcelParser: [text_line, ...]
  - PptParser: [slide_text, ...]
  - MarkdownParser: 无 __call__, 使用 extract_tables_and_remainder

本服务统一输出: list[dict] — 每项 {content, content_type, page}
"""

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger("claw.deepdoc")

# 文件扩展名 → parser 类型
EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".xlsx": "excel",
    ".xls": "excel",
    ".csv": "excel",
    ".pptx": "ppt",
    ".ppt": "ppt",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".epub": "epub",
}


def get_parser_type(filename: str) -> str | None:
    """根据文件名扩展名返回 parser 类型。"""
    ext = Path(filename).suffix.lower()
    return EXTENSION_MAP.get(ext)


def parse_document(filename: str, file_data: bytes, chunk_token_num: int = 128) -> list[dict]:
    """解析文档，返回标准化的内容块列表。

    Args:
        filename: 文件名 (用于判断类型)
        file_data: 文件二进制内容
        chunk_token_num: 分块 token 数 (传给 DeepDoc parser)

    Returns:
        list[dict] — 每项: {"content": str, "content_type": "text"|"table", "page": int}
    """
    parser_type = get_parser_type(filename)
    if parser_type is None:
        raise ValueError(f"不支持的文件类型: {filename}")

    logger.info("开始解析文档: %s (type=%s, %d bytes)", filename, parser_type, len(file_data))

    # 将 binary 写入临时文件 (部分 parser 需要文件路径)
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        blocks = _dispatch_parse(parser_type, tmp_path, file_data, chunk_token_num)
        logger.info("解析完成: %s → %d blocks", filename, len(blocks))
        return blocks
    finally:
        os.unlink(tmp_path)


def _dispatch_parse(parser_type: str, fnm: str, binary: bytes, chunk_token_num: int) -> list[dict]:
    """按 parser 类型路由到对应的 DeepDoc parser。"""
    if parser_type == "txt":
        return _parse_txt(fnm, binary, chunk_token_num)
    elif parser_type == "pdf":
        return _parse_pdf(fnm, binary)
    elif parser_type == "docx":
        return _parse_docx(fnm, binary)
    elif parser_type == "excel":
        return _parse_excel(fnm, binary)
    elif parser_type == "ppt":
        return _parse_ppt(fnm, binary)
    elif parser_type == "markdown":
        return _parse_markdown(binary, chunk_token_num)
    elif parser_type == "html":
        return _parse_html(fnm, binary, chunk_token_num)
    elif parser_type == "json":
        return _parse_json(binary)
    elif parser_type == "epub":
        return _parse_epub(fnm, binary, chunk_token_num)
    else:
        raise ValueError(f"未知 parser 类型: {parser_type}")


def _parse_txt(fnm: str, binary: bytes, chunk_token_num: int) -> list[dict]:
    """TxtParser 返回 [[text, ""], ...]。"""
    from deepdoc.parser import TxtParser

    result = TxtParser()(fnm, binary=binary, chunk_token_num=chunk_token_num)
    return [{"content": c[0], "content_type": "text", "page": 0} for c in result if c[0].strip()]


def _parse_pdf(fnm: str, binary: bytes) -> list[dict]:
    """PlainParser 返回 ([(line, "")], [])。按页分块。

    使用 PlainParser (纯文本提取) 避免 ONNX 模型依赖，
    视觉解析 (VisionParser) 需要模型文件，留 M2.5 启用。
    """
    from deepdoc.parser import PlainParser

    # PlainParser 需要文件路径或 BytesIO
    sections, tables = PlainParser()(binary if binary else fnm)
    blocks = []
    for line, _ in sections:
        if line.strip():
            blocks.append({"content": line, "content_type": "text", "page": 0})
    return blocks


def _parse_docx(fnm: str, binary: bytes) -> list[dict]:
    """DocxParser 返回 (sections, tables)。

    sections=[(paragraph_text, style)], tables=[html_str]
    """
    from deepdoc.parser import DocxParser

    sections, tables = DocxParser()(fnm)
    blocks = []
    for text, _style in sections:
        if text.strip():
            blocks.append({"content": text, "content_type": "text", "page": 0})
    for tbl_html in tables:
        if tbl_html and str(tbl_html).strip():
            blocks.append({"content": str(tbl_html), "content_type": "table", "page": 0})
    return blocks


def _parse_excel(fnm: str, binary: bytes) -> list[dict]:
    """ExcelParser 返回 [text_line, ...]。"""
    from deepdoc.parser import ExcelParser

    result = ExcelParser()(fnm if not binary else binary)
    blocks = []
    for line in result:
        if line and str(line).strip():
            blocks.append({"content": str(line), "content_type": "text", "page": 0})
    return blocks


def _parse_ppt(fnm: str, binary: bytes) -> list[dict]:
    """PptParser 返回按页排列的文本列表。"""
    from deepdoc.parser import PptParser

    sections = PptParser()(binary if binary else fnm, from_page=0, to_page=10000)
    blocks = []
    for page, text in enumerate(sections):
        if text and str(text).strip():
            blocks.append({"content": str(text), "content_type": "text", "page": page})
    return blocks


def _parse_markdown(binary: bytes, chunk_token_num: int) -> list[dict]:
    """MarkdownParser 使用 extract_tables_and_remainder。"""
    from deepdoc.parser import MarkdownParser

    md_text = binary.decode("utf-8", errors="ignore")
    parser = MarkdownParser(chunk_token_num=chunk_token_num)
    tables, remainder = parser.extract_tables_and_remainder(md_text)

    blocks = []
    if remainder and remainder.strip():
        blocks.append({"content": remainder, "content_type": "text", "page": 0})
    for tbl in tables:
        if tbl and str(tbl).strip():
            blocks.append({"content": str(tbl), "content_type": "table", "page": 0})
    return blocks


def _parse_html(fnm: str, binary: bytes, chunk_token_num: int) -> list[dict]:
    """HtmlParser 返回 sections。"""
    from deepdoc.parser import HtmlParser

    result = HtmlParser()(fnm, binary=binary, chunk_token_num=chunk_token_num)
    blocks = []
    if isinstance(result, list):
        for item in result:
            text = item[0] if isinstance(item, (list, tuple)) else str(item)
            if text and str(text).strip():
                blocks.append({"content": str(text), "content_type": "text", "page": 0})
    return blocks


def _parse_json(binary: bytes) -> list[dict]:
    """JsonParser 返回 list[str]。"""
    from deepdoc.parser import JsonParser

    result = JsonParser()(binary)
    blocks = []
    if isinstance(result, list):
        for item in result:
            if item and str(item).strip():
                blocks.append({"content": str(item), "content_type": "text", "page": 0})
    return blocks


def _parse_epub(fnm: str, binary: bytes, chunk_token_num: int) -> list[dict]:
    """EpubParser 返回 [[text, ""], ...]。"""
    from deepdoc.parser import EpubParser

    result = EpubParser()(fnm, binary=binary, chunk_token_num=chunk_token_num)
    blocks = []
    for item in result:
        text = item[0] if isinstance(item, (list, tuple)) else str(item)
        if text and str(text).strip():
            blocks.append({"content": str(text), "content_type": "text", "page": 0})
    return blocks
