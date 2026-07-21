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
    api_key: str = ""  # 空串表示保留已有 Key
    model: str = ""
    clear_key: bool = False  # true 时显式清除已保存的 api_key


class LlmConfigRead(BaseModel):
    """LLM 配置 (读取, key 脱敏)。

    default_model: 画布新建 LLM 节点的默认模型;
    has_*_key: 各供应商 API Key 是否已配置 (DB 热更新或 .env)。
    """

    default_model: str
    has_kaiweb_key: bool = False
    has_openai_key: bool = False
    has_anthropic_key: bool = False


class LlmConfigUpdate(BaseModel):
    """更新 LLM 默认模型与供应商 API Key (热更新, Key 加密存储)。

    各 api_key 为空串表示保留已有 Key (不清除), 便于只改默认模型或单个 Key。
    """

    default_model: str = ""
    kaiweb_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

