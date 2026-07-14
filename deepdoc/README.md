# DeepDoc 集成 (M2)

本目录将在 M2 阶段从 RAGFlow 复制 DeepDoc 文档解析引擎。

## 集成方式

直接导入 `deepdoc.parser` Python 包，获取完整解析能力（文本 + HTML 表格 + 版面坐标）。

## 依赖说明

`deepdoc/parser/` 依赖 RAGFlow 的以下兄弟包（M2 时选择性 vendor）：

| 依赖 | 用到的模块 |
|---|---|
| `common/` | `constants.py` (MAXIMUM_PAGE_NUMBER), `file_utils.py` (get_project_base_directory), `settings.py`, `misc_utils.py` (thread_pool_exec) |
| `rag/nlp/` | `rag_tokenizer.py` |
| `rag/prompts/` | `generator.py` (vision_llm_describe_prompt) |
| `rag/utils/` | `lazy_image.py` |

## 模型文件

需要下载 5 个 ONNX 模型到 `rag/res/deepdoc/`：

| 文件 | 大小 | 用途 |
|---|---|---|
| `layout.onnx` | 75.7 MB | DLA (版面分析) |
| `det.onnx` | 4.7 MB | OCR 文字检测 |
| `rec.onnx` | 10.8 MB | OCR 文字识别 |
| `tsr.onnx` | 12.2 MB | TSR (表格结构识别) |
| `ocr.res` | 26 KB | OCR 字符字典 |

下载方式：`python deepdoc/server/download_deps.py /path/to/models`
HuggingFace 仓库：`InfiniFlow/deepdoc`

## Python 依赖

```
pdfplumber==0.10.4
python-docx>=1.1.2
python-pptx>=1.0.2
xgboost==1.6.0
openpyxl>=3.1.5
onnxruntime>=1.20.0
opencv-python-headless
scikit-learn
huggingface_hub
beartype
```
