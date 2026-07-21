"""本地 Agent (OpenClaw / Hermes) 工具发现服务。对齐 PRD 6.4 / 第 7.3 节。

工具来源:
  1. 本地 Skills 目录扫描 (deploy/openclaw/skills, deploy/hermes/skills) — 读取 skill.json
  2. OpenClaw gateway HTTP API (GET /v1/tools) — 若可用则合并

dev 环境: OpenClaw 不可达时, 调用返回 mock 结构化结果, 保证画布「工具调用」节点可演示。
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
        ))

    return tools


async def discover_tools() -> list[ToolInfo]:
    """发现本地工具: Skills 目录扫描 + OpenClaw HTTP 合并。"""
    root = _project_root()
    tools: list[ToolInfo] = []

    # 1. 扫描本地 Skills 目录
    tools += _scan_skills_dir("openclaw", root / "deploy" / "openclaw" / "skills")
    tools += _scan_skills_dir("hermes", root / "deploy" / "hermes" / "skills")

    # 2. 合并 OpenClaw gateway 在线工具 (若可用)
    try:
        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.openclaw_url}/v1/tools", headers=headers)
            if resp.status_code < 400:
                data = resp.json()
                online = data if isinstance(data, list) else data.get("data", data.get("tools", []))
                for t in online:
                    if isinstance(t, dict):
                        tools.append(ToolInfo(
                            id=t.get("id") or t.get("name", "openclaw_tool"),
                            name=t.get("name") or t.get("id", "openclaw_tool"),
                            description=t.get("description"),
                            source="openclaw",
                            parameters=t.get("parameters") or t.get("input_schema"),
                        ))
    except Exception as e:
        logger.debug("OpenClaw 在线工具发现不可用: %s", e)

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
    """调用本地工具。优先 OpenClaw HTTP; 仅连接异常且 dev 环境时返回 mock。"""
    # 0. 校验 tool_id 存在 (本地 Skills 目录 + OpenClaw 在线工具)
    tools = await discover_tools()
    if tool_id not in {t.id for t in tools}:
        return {
            "tool_id": tool_id,
            "success": False,
            "result": None,
            "error": f"本地工具不存在: {tool_id}",
            "source": "local",
        }

    # 1. 尝试 OpenClaw
    try:
        headers = {"Content-Type": "application/json"}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.openclaw_url}/v1/tools/{tool_id}/call",
                headers=headers,
                json={"parameters": parameters},
            )
            if resp.status_code < 400:
                return {"tool_id": tool_id, "success": True, "result": resp.json(), "source": "openclaw"}
            # 4xx/5xx → 明确失败, 不伪装成功
            logger.warning("OpenClaw 工具调用返回 %s: %s", resp.status_code, resp.text[:200])
            return {
                "tool_id": tool_id,
                "success": False,
                "result": None,
                "error": f"OpenClaw 工具调用失败 (HTTP {resp.status_code}): {resp.text[:200]}",
                "source": "openclaw",
            }
    except Exception as e:
        logger.debug("OpenClaw 工具调用连接失败: %s", e)

    # 2. 仅 dev 环境连接异常时 mock 兜底; 其它环境明确报错
    if settings.environment == "dev":
        return {
            "tool_id": tool_id,
            "success": True,
            "result": {
                "mock": True,
                "message": f"[Mock 工具调用] {tool_id} 已接收参数 (离线兜底)",
                "echo_parameters": parameters,
            },
            "source": "mock",
        }
    return {
        "tool_id": tool_id,
        "success": False,
        "result": None,
        "error": "OpenClaw 网关不可达, 且非 dev 环境不提供 mock 兜底",
        "source": "openclaw",
    }


async def health() -> dict:
    """本地 Agent 健康检查。"""
    from app.core.llm_client import health_check as openclaw_health

    openclaw_ok = await openclaw_health()
    hermes_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.hermes_url}/")
            hermes_ok = resp.status_code < 400
    except Exception:
        hermes_ok = False

    return {
        "openclaw": openclaw_ok,
        "hermes": hermes_ok,
        "openclaw_url": settings.openclaw_url,
        "hermes_url": settings.hermes_url,
    }
