# STUB: 替换 RAGFlow 原始 rag/prompts/generator.py (39KB, 依赖 jinja2/json_repair)
# DeepDoc pdf_parser 只需要 vision_llm_describe_prompt 函数


def vision_llm_describe_prompt(page=None):
    """STUB: 返回视觉 LLM 描述提示词。

    原始实现在 rag/prompts/generator.py 中用 Jinja2 渲染模板。
    M2 阶段 VisionParser 不是主路径 (PlainParser 和 RAGFlowPdfParser 不调用此函数)，
    仅在 VisionParser 模式下需要。返回简单占位。
    """
    return "Describe the content of this document page in detail."
