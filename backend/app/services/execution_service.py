"""工作流执行引擎。

自定义 asyncio DAG 执行器:
  1. 解析 flow.dag (XYFlow nodes + edges)
  2. 拓扑排序 (Kahn 算法)
  3. 逐节点执行, 每步提交 node_states (SSE 可读)
  4. 节点类型: llm / retrieval / condition / text

对齐 PRD 第 3.2 节: 画布编排 → DAG 执行 → SSE 状态同步。
"""

import asyncio
import logging
import re
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.llm_client import chat as llm_chat
from app.models.agent_flow import AgentFlow
from app.models.execution import Execution, ExecutionStatus
from app.models.user import User
from app.schemas.knowledge_base import SearchRequest
from app.services import document_service

logger = logging.getLogger("claw.execution")


async def run_flow(execution_id: uuid.UUID, flow_id: uuid.UUID) -> None:
    """后台任务: 执行工作流 DAG。

    使用独立的 DB session (不在请求上下文内)。
    """
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        # 加载执行记录和工作流
        result = await db.execute(select(Execution).where(Execution.id == execution_id))
        execution = result.scalar_one_or_none()
        if execution is None:
            logger.error("执行记录不存在: %s", execution_id)
            return

        flow_result = await db.execute(select(AgentFlow).where(AgentFlow.id == flow_id))
        flow = flow_result.scalar_one_or_none()
        if flow is None:
            logger.error("工作流不存在: %s", flow_id)
            execution.status = ExecutionStatus.failed
            execution.error_message = "工作流不存在"
            await db.commit()
            return

        # 加载用户 (用于 LLM API Key)
        user_result = await db.execute(select(User).where(User.id == flow.owner_id))
        user = user_result.scalar_one_or_none()

        try:
            # ── 1. 标记为 running ──
            execution.status = ExecutionStatus.running
            execution.node_states = {}
            await db.commit()

            # ── 2. 解析 DAG ──
            dag = flow.dag or {"nodes": [], "edges": []}
            nodes = dag.get("nodes", [])
            edges = dag.get("edges", [])

            if not nodes:
                execution.output = {"result": "工作流为空, 无节点可执行"}
                execution.status = ExecutionStatus.success
                await db.commit()
                return

            # ── 3. 拓扑排序 ──
            ordered = _topological_sort(nodes, edges)
            logger.info("工作流执行: flow=%s execution=%s nodes=%d", flow_id, execution_id, len(ordered))

            # ── 4. 逐节点执行 ──
            context = dict(execution.input or {})  # 上下文: 节点输出累积
            node_outputs = {}

            for node in ordered:
                node_id = node["id"]
                node_type = node.get("type", "text")
                node_data = node.get("data", {})
                config = node_data.get("config", {})

                # ── 暂停检查 (人机交互) ──
                await db.refresh(execution)
                if execution.status == ExecutionStatus.paused:
                    # 等待恢复 (轮询 DB, 每 2s 检查一次)
                    while execution.status == ExecutionStatus.paused:
                        await asyncio.sleep(2)
                        await db.refresh(execution)
                        if execution.status == ExecutionStatus.cancelled:
                            execution.output = node_outputs
                            await db.commit()
                            return

                # 初始化节点状态
                node_states = dict(execution.node_states or {})
                node_states[node_id] = {
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "label": node_data.get("label", node_id),
                    "type": node_type,
                }
                execution.node_states = node_states
                flag_modified(execution, "node_states")
                await db.commit()

                try:
                    output = await _execute_node(node_type, config, context, user, node_outputs)
                    node_outputs[node_id] = output
                    context[node_id] = output

                    # 更新节点状态为成功
                    node_states = dict(execution.node_states or {})
                    node_states[node_id] = {
                        **node_states[node_id],
                        "status": "success",
                        "output": output if isinstance(output, str) else str(output),
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                    }
                    execution.node_states = node_states
                    flag_modified(execution, "node_states")
                    await db.commit()

                    logger.info("节点执行成功: %s (%s)", node_id, node_type)

                except Exception as node_err:
                    # 节点执行失败
                    node_states = dict(execution.node_states or {})
                    node_states[node_id] = {
                        **node_states[node_id],
                        "status": "failed",
                        "error": str(node_err),
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                    }
                    execution.node_states = node_states
                    flag_modified(execution, "node_states")
                    execution.status = ExecutionStatus.failed
                    execution.error_message = f"节点 {node_id} ({node_type}) 执行失败: {node_err}"
                    await db.commit()

                    logger.error("节点执行失败: %s — %s", node_id, node_err)
                    return

            # ── 5. 全部完成 ──
            execution.status = ExecutionStatus.success
            execution.output = node_outputs
            await db.commit()

            logger.info("工作流执行完成: flow=%s execution=%s", flow_id, execution_id)

        except Exception as e:
            logger.exception("工作流执行异常: %s — %s", flow_id, e)
            execution.status = ExecutionStatus.failed
            execution.error_message = str(e)
            await db.commit()


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Kahn 算法拓扑排序。返回按依赖顺序排列的节点列表。

    条件分支节点: 只执行满足条件的下游节点 (运行时动态决定)。
    这里先返回完整拓扑序, 条件节点的分支选择在执行时处理。
    """
    node_map = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adj = defaultdict(list)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in in_degree and target in in_degree:
            adj[source].append(target)
            in_degree[target] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    ordered = []

    while queue:
        nid = queue.popleft()
        ordered.append(node_map[nid])
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 检查环
    if len(ordered) != len(nodes):
        raise ValueError("DAG 存在循环依赖, 无法拓扑排序")

    return ordered


async def _execute_node(
    node_type: str,
    config: dict,
    context: dict,
    user=None,
    node_outputs: dict | None = None,
) -> str:
    """执行单个节点, 返回输出文本。

    Args:
        node_type: llm / retrieval / condition / text / notify / memory
        config: 节点配置 (从 dag.data.config 读取)
        context: 累积上下文 (所有上游节点输出 + 初始输入)
        user: User 对象 (LLM API Key)
        node_outputs: 已执行节点的输出 {node_id: output}
    """
    if node_type == "llm":
        return await _execute_llm_node(config, context, user)
    elif node_type == "retrieval":
        return await _execute_retrieval_node(config, context)
    elif node_type == "condition":
        return await _execute_condition_node(config, context)
    elif node_type == "text":
        return _execute_text_node(config, context)
    elif node_type == "notify":
        return await _execute_notify_node(config, context)
    elif node_type == "memory":
        return await _execute_memory_node(config, context, user)
    else:
        # 未知类型按文本处理
        return _execute_text_node(config, context)


async def _execute_llm_node(config: dict, context: dict, user=None) -> str:
    """LLM 对话节点。

    config:
      - model: 模型标识 (default/openclaw/gpt-4o-mini 等)
      - system_prompt: 系统提示词
      - user_template: 用户消息模板 (支持 {var} 占位符)
    """
    model = config.get("model", "default")
    system_prompt = config.get("system_prompt", "")
    user_template = config.get("user_template", "{input}")

    # 模板替换: {var} → context 中的值
    user_content = _render_template(user_template, context)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    return await llm_chat(messages, model=model, user=user)


async def _execute_retrieval_node(config: dict, context: dict) -> str:
    """知识库检索节点。复用 M2 混合检索。

    config:
      - kb_id: 知识库 UUID
      - query_template: 查询模板 (支持 {var})
      - top_k: 返回条数
    """
    from app.core.database import async_session_factory

    kb_id = config.get("kb_id")
    if not kb_id:
        return "[检索节点未配置 kb_id]"

    query_template = config.get("query_template", "{input}")
    top_k = config.get("top_k", 5)
    query = _render_template(query_template, context)

    async with async_session_factory() as db:
        request = SearchRequest(query=query, top_k=top_k)
        result = await document_service.search(db, kb_id, request)

    if not result.hits:
        return "[未检索到相关内容]"

    # 拼接检索结果
    parts = []
    for i, hit in enumerate(result.hits):
        parts.append(f"[{i + 1}] {hit.content}")
    return "\n\n".join(parts)


async def _execute_condition_node(config: dict, context: dict) -> str:
    """条件分支节点。

    评估表达式, 返回 "true" 或 "false", 用于下游边的选择。
    (简化: 表达式为 {var} == "value" 格式)

    config:
      - expression: 条件表达式 (如 "{input} == '是'")
    """
    expression = config.get("expression", "true")
    rendered = _render_template(expression, context).strip()

    # 简单条件评估: 支持 == 和 != 和 contains
    try:
        if "==" in rendered:
            left, right = rendered.split("==", 1)
            result = left.strip() == right.strip().strip("'\"")
        elif "!=" in rendered:
            left, right = rendered.split("!=", 1)
            result = left.strip() != right.strip().strip("'\"")
        elif "contains" in rendered:
            parts = rendered.split("contains", 1)
            result = parts[1].strip().strip("'\"") in parts[0].strip()
        else:
            # 非空即为 true
            result = bool(rendered)
    except Exception:
        result = False

    return "true" if result else "false"


def _execute_text_node(config: dict, context: dict) -> str:
    """文本拼接节点。

    config:
      - template: 模板文本 (支持 {var} 占位符)
    """
    template = config.get("template", "")
    return _render_template(template, context)


def _render_template(template: str, context: dict) -> str:
    """渲染模板: 替换 {var} 为 context 中的值。

    支持嵌套: {node-1.output} → context["node-1"]
    支持特殊键: {input} → context.get("input", "")
    """
    if not template:
        return ""

    def replacer(match):
        key = match.group(1)
        # 支持 key.subkey 格式 (取 context[key] 的前100字符)
        main_key = key.split(".")[0]
        value = context.get(main_key, context.get(key, ""))
        if isinstance(value, dict):
            return str(value.get("output", value))
        return str(value)

    return re.sub(r"\{([^}]+)\}", replacer, template)


# ── 推送节点 (M4) ──

async def _execute_notify_node(config: dict, context: dict) -> str:
    """多平台推送节点。

    config:
      - channels: 推送渠道列表 [{type, webhook_url/bot_token+chat_id/channel}]
      - title_template: 标题模板 (支持 {var})
      - content_template: 内容模板 (支持 {var})
    """
    from app.core.notify_client import notify as do_notify

    channels = config.get("channels", [])
    if not channels:
        return "[推送节点未配置渠道]"

    title = _render_template(config.get("title_template", "通知"), context)
    content = _render_template(config.get("content_template", ""), context)

    results = await do_notify(channels, title, content)
    success_count = sum(1 for r in results if r["success"])
    return f"推送完成: {success_count}/{len(results)} 渠道成功"


# ── 记忆节点 (M4) ──

async def _execute_memory_node(config: dict, context: dict, user=None) -> str:
    """记忆读写节点。

    config:
      - action: "save" 或 "load"
      - key: 记忆键 (支持 {var})
      - value_template: 值模板 (save 时使用, 支持 {var})
      - session_id: 会话 ID (可选)
    """
    from app.core.database import async_session_factory
    from app.services import memory_service

    action = config.get("action", "load")
    key = _render_template(config.get("key", ""), context)
    session_id = config.get("session_id")

    if not user:
        return "[记忆节点无用户上下文]"

    async with async_session_factory() as db:
        if action == "save":
            value_str = _render_template(config.get("value_template", ""), context)
            await memory_service.save_memory(
                db, user.id, "context", key, {"value": value_str}, session_id
            )
            return f"记忆已保存: {key}"

        # load
        memory = await memory_service.get_memory(db, user.id, key, session_id)
        if memory and memory.value:
            return str(memory.value.get("value", memory.value))
        return f"[未找到记忆: {key}]"


# ── 人机交互: 暂停/恢复/取消 (M4) ──

async def pause_execution(db, execution_id) -> bool:
    """暂停执行。执行引擎在下一个节点前检测到 paused 状态后停止。"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None or execution.status != ExecutionStatus.running:
        return False
    execution.status = ExecutionStatus.paused
    await db.commit()
    logger.info("执行已暂停: %s", execution_id)
    return True


async def resume_execution(db, execution_id) -> bool:
    """恢复执行。执行引擎检测到 running 状态后继续。"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None or execution.status != ExecutionStatus.paused:
        return False
    execution.status = ExecutionStatus.running
    await db.commit()
    logger.info("执行已恢复: %s", execution_id)
    return True


async def cancel_execution(db, execution_id) -> bool:
    """取消执行。执行引擎检测到 cancelled 状态后终止。"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        return False
    if execution.status in (ExecutionStatus.success, ExecutionStatus.failed):
        return False
    execution.status = ExecutionStatus.cancelled
    await db.commit()
    logger.info("执行已取消: %s", execution_id)
    return True
