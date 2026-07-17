"""系统配置 Pydantic 模型。"""

from pydantic import BaseModel


class EmbeddingConfigRead(BaseModel):
    """Embedding 模型 API 配置 (读取, key 脱敏)。"""

    base_url: str
    model: str
    has_key: bool
    configured: bool  # base_url + key 是否齐备
    source: str  # api / tei / hash


class EmbeddingConfigUpdate(BaseModel):
    """更新 Embedding 模型 API 配置。"""

    base_url: str = ""
    api_key: str = ""  # 空串表示清除
    model: str = ""


class LlmConfigRead(BaseModel):
    """LLM 默认模型配置 (画布新建 LLM 节点的默认模型)。"""

    default_model: str


class LlmConfigUpdate(BaseModel):
    """更新 LLM 默认模型。"""

    default_model: str = ""

