# STUB: 替换 RAGFlow 原始 settings.py (原始文件在导入时连 Redis/DB/ES)
# DeepDoc parser 只读取 PARALLEL_DEVICES 和 DOC_ENGINE_INFINITY
import os

PARALLEL_DEVICES = int(os.environ.get("PARALLEL_DEVICES", "0"))
DOC_ENGINE_INFINITY = False
DOC_ENGINE = os.environ.get("DOC_ENGINE", "elasticsearch")
