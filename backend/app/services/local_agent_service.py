"""本地 Agent (OpenClaw / Hermes) 工具发现服务。对齐 PRD 6.4 / 第 7.3 节。

工具来源:
  1. 本地 Skills 目录扫描 (deploy/openclaw/skills, deploy/hermes/skills) — 读取 skill.json
  2. OpenClaw gateway HTTP API (POST /tools/invoke) — 直接调用工具

OpenClaw 没有工具列表 HTTP API。本地清单用于展示可配置的工具，调用时由
Gateway 的策略和实际工具注册情况决定是否可执行。
"""

import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas.local_agent import ToolInfo

logger = logging.getLogger("claw.local_agent")


def _project_root() -> Path:
    """项目根目录 (backend/ 的上一级)。"""
    return Path(__file__).resolve().parents[3]


def _scan_skills_dir(source: str, skills_dir: Path) -> list[ToolInfo]:
    """扫描某个 Skills 目录下的 skill.json 清单。

    支持两种布局:
      - skills/<tool_id>/skill.json
      - skills/<tool_id>.json
    """
    tools: list[ToolInfo] = []
    if not skills_dir.exists():
        return tools

    for child in sorted(skills_dir.iterdir()):
        manifest_path: Path | None = None
        tool_id: str | None = None

        if child.is_dir():
            candidate = child / "skill.json"
            if candidate.exists():
                manifest_path = candidate
                tool_id = child.name
        elif child.suffix == ".json":
            manifest_path = child
            tool_id = child.stem

        if manifest_path is None:
            continue

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("解析 skill 清单失败 %s: %s", manifest_path, e)
            continue

        tools.append(ToolInfo(
            id=data.get("id") or tool_id or data.get("name", "unknown"),
            name=data.get("name") or tool_id or "unknown",
            description=data.get("description"),
            source=source,
            parameters=data.get("parameters"),
            executable=source == "openclaw",
        ))

    return tools


async def discover_tools() -> list[ToolInfo]:
    """发现本地工具清单。"""
    root = _project_root()
    tools: list[ToolInfo] = []

    # 1. 扫描本地 Skills 目录
    tools += _scan_skills_dir("openclaw", root / "deploy" / "openclaw" / "skills")
    tools += _scan_skills_dir("hermes", root / "deploy" / "hermes" / "skills")

    # 去重 (按 id, 保留首个)
    seen: set[str] = set()
    unique: list[ToolInfo] = []
    for t in tools:
        if t.id in seen:
            continue
        seen.add(t.id)
        unique.append(t)

    logger.info("本地工具发现: %d 个", len(unique))
    return unique


async def call_tool(tool_id: str, parameters: dict) -> dict:
    """调用本地工具。OpenClaw 网关为权威来源; 网关不可达/报错时明确失败 (不伪装成功)。

    语义:
      - tool_id 必须存在于仓库 manifest allowlist，未知工具不接触网关
      - 网关返回 ok:true → 成功, 取 result
      - 网关返回无效响应 / HTTP 错误 → success=False + error (source=mock)
      - 连接级失败 (网关不可达) → success=False，明确报告网关不可用
    """
    tools_by_id = {tool.id: tool for tool in await discover_tools()}
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return {
            "tool_id": tool_id,
            "success": False,
            "result": None,
            "error": f"本地工具不存在: {tool_id}",
            "source": "local",
        }
    if not tool.executable:
        return {
            "tool_id": tool_id,
            "success": False,
            "result": None,
            "error": f"{tool.source} 工具仅完成清单发现，当前没有可用的调用端点: {tool_id}",
            "source": tool.source,
        }

    headers = {"Content-Type": "application/json"}
    if settings.openclaw_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_token}"

    # 1. 连接 OpenClaw 网关 (连接异常单独捕获, 与响应解析异常区分)
    resp = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.openclaw_url}/tools/invoke",
                headers=headers,
                json={"tool": tool_id, "args": parameters},
            )
    except Exception as e:
        logger.debug("OpenClaw 工具调用连接失败: %s", e)
        error = f"OpenClaw 工具服务不可用 ({e.__class__.__name__})"
        return _tool_failure(tool_id, parameters, error)

    # 2. 已拿到响应: 网关是权威, 校验 ok 信封
    if resp.status_code < 400:
        try:
            data = resp.json()
        except Exception as e:
            logger.warning("OpenClaw 工具调用响应解析失败: %s", e)
            error = f"OpenClaw 工具服务不可用 ({e.__class__.__name__})"
        else:
            if isinstance(data, dict) and data.get("ok") is True:
                return {
                    "tool_id": tool_id,
                    "success": True,
                    "result": data.get("result"),
                    "source": "openclaw",
                }
            logger.warning("OpenClaw 工具调用返回无效响应: %s", resp.text[:200])
            error = "OpenClaw 返回无效的工具调用响应"
    else:
        logger.warning("OpenClaw 工具调用返回 HTTP %s: %s", resp.status_code, resp.text[:200])
        error = f"OpenClaw 工具不可用 (HTTP {resp.status_code})"

    return _tool_failure(tool_id, parameters, error)


def _tool_failure(tool_id: str, parameters: dict, error: str) -> dict:
    """工具调用失败的统一响应: 明确失败 + mock 标记, 不伪装成功。"""
    return {
        "tool_id": tool_id,
        "success": False,
        "result": {
            "mock": True,
            "message": f"{tool_id} 未执行",
            "echo_parameters": parameters,
        },
        "error": error,
        "source": "mock",
    }


async def health() -> dict:
    """本地 Agent 健康检查。"""
    from app.core.llm_client import health_check as openclaw_health

    openclaw_ok = await openclaw_health()
    hermes_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.hermes_url}/health")
            hermes_ok = resp.status_code == 200
    except Exception:
        hermes_ok = False

    return {
        "openclaw": openclaw_ok,
        "hermes": hermes_ok,
        "openclaw_url": settings.openclaw_url,
        "hermes_url": settings.hermes_url,
    }
