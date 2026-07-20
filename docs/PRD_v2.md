# Claw-Native Agent 平台 — PRD v2

> **版本**: v2.0
> **日期**: 2026-07-15
> **状态**: MVP 闭环可用（M1–M4 已交付 + 本轮补全）
> **本文档定位**: 在 v1.1 基础上，**按代码实际实现状态**重生成 PRD，如实标注已实现 / 偏差 / 本轮新增 / 剩余路线图。

---

## 0. 与 v1.1 的关系

v1.1 是设计草案。v2.0 以**已落地代码**为准重新对齐：保留 v1.1 的整体架构与目标，更新各模块实现现状、API 清单与里程碑勾选，并新增“本轮补全”与“剩余路线图”两节。存在三处与 v1.1 设计的**有意偏差**（详见 §3.8）：

1. 编排引擎采用**自研 asyncio DAG 执行器**（Kahn 拓扑排序），而非 LangGraph SDK。
2. PDF 解析使用 DeepDoc `PlainParser`（纯文本），视觉/OCR 解析留待 M5。
3. 短期记忆（Redis）未实现，当前记忆系统仅 PostgreSQL 持久层。

---

## 1. 项目概述

### 1.1 项目背景
构建一个类 RAGFlow 的三模块 Agent 平台，核心差异化在于**以本地部署的 OpenClaw / Hermes 为一等公民**的模型供应商层，实现「知识管理 → 工作流编排 → 全链路自动化执行 → 多平台推送」的闭环。所有执行均在本地/私域完成，数据不出域。

### 1.2 产品定位
- **对标**: RAGFlow（知识库 + Agent 画布 + 模型供应商）
- **差异化**: OpenClaw / Hermes 原生集成；本地工具发现、定时任务、文件工作区、多平台推送均自建
- **目标用户**: 需要 7×24 自动化工作流且数据敏感的技术团队、运营团队、个人超级用户

### 1.3 核心原则
1. DeepDoc 零自研（从 RAGFlow 复制，Apache 2.0）
2. OpenClaw / Hermes 一等公民（本地部署，非云端 API）
3. LangGraph 风格编排（状态机式 DAG，当前为自研等价实现）
4. MVP 优先：P0 六模块缺一不可
5. 数据不出域

---

## 2. 产品目标

### 2.1 MVP 目标（闭环可用）— ✅ 已达成
- ✅ 用户可上传文档，DeepDoc 解析后建立知识库（DeepDoc 已复制入 `backend/deepdoc/`）
- ✅ 用户可在画布上拖拽节点编排工作流（XYFlow）
- ✅ 工作流可调用本地工具（本轮新增 `/api/v1/local-agent/tools` 发现 + 调用）
- ✅ 定时任务通过本地 APScheduler 驱动工作流（PostgreSQL JobStore）
- ✅ 执行结果通过自建推送服务发送至飞书/企微/Telegram（本轮新增渠道持久化配置）
- ✅ 支持 OpenAI 作为 OpenClaw / Hermes 的 fallback
- ✅（本轮新增）dev 环境内置 Mock LLM / 向量兜底，无 API Key 亦可完整演示
- ✅（Kaiweb 适配）OpenClaw 接入自建 OpenAI 兼容网关 https://ai.kaiweb.net，真实 GLM 模型已可用（默认 glm-4.5）

### 2.2 生产级目标（可对外交付）— ⬜ 路线图
- ⬜ 多租户权限隔离（当前为单租户 owner 隔离）
- ⬜ 全链路可观测（LangSmith + 日志聚合）
- ⬜ 定时任务稳定运行（已有 APScheduler + PG 持久化，缺分布式锁加固）
- ⬜ 支持 5+ 模型供应商统一路由（本地 + 云端混合）
- ⬜ 文件工作区版本管理（当前为单版本 MinIO 存储）

---

## 3. 功能模块规格（实现现状）

### 3.1 知识库 — ✅
- **文档上传**：PDF/DOCX/XLSX/PPTX/TXT/MD/HTML/JSON/EPUB；单文件上传；MinIO 存储；100MB 限制。
- **文档解析**：DeepDoc（`backend/deepdoc/`，含 parser + vision）；按类型路由；输出标准化 `{content, content_type, page}`。PDF 用 `PlainParser`（无 OCR，M5 启用 Vision）。
- **分块**：`fixed`（token 窗口）/ `recursive` / `markdown` / `semantic`（降级为 recursive）；表格整块保留；token 计数用 tiktoken。
- **向量化**：默认使用 OpenAI 兼容 Embedding API（要求 1024 维）；TEI sidecar（BGE-M3）作为 `local-embedding` 可选 profile 和 API 失败后的本地回退；TEI 分批 embed（每批 16）避免 413；dev 环境均不可用时回退确定性哈希向量。
- **索引**：Elasticsearch（dense_vector + BM25，IK 分析器）；增量索引。
- **检索**：`POST /api/v1/knowledge-bases/{id}/search`，kNN + BM25 混合；可选 Cross-Encoder（TEI reranker）重排；8GB 默认使用多语言 `mmarco-mMiniLMv2-L12-H384-v1`，高内存环境可通过 `RERANKER_MODEL_ID` 切换 BGE reranker；阈值可调；引用溯源（doc_id + page + chunk）。
- **Chunk 管理**：`GET /{id}/chunks`（本轮已确认实现，支持 doc_id 过滤）。

### 3.2 Agent 画布 — ✅
- **画布引擎**：@xyflow/react；节点拖拽/连线/删除、缩放/平移/minimap、序列化为 DAG JSON。
- **节点类型**（6 类）：`text` / `llm` / `retrieval` / `condition` / `notify` / `memory`。
- **执行引擎**：自研 asyncio DAG（Kahn 拓扑排序，逐节点执行，每步写 `node_states`）；后台任务 + SSE 实时状态推送（`progress`/`complete`）；暂停/恢复/取消（DB 状态轮询）；节点失败即终止。
- **模板与复用**：CRUD 已就绪，预设模板留作路线图。
- **MCP**：二期。

### 3.3 模型供应商 — ✅
- **统一抽象**：`app/core/llm_client.py`，OpenAI 兼容 `chat/completions`；httpx 直调，不引 langchain/openai SDK。
- **供应商与优先级**：**OpenClaw（本地 Agent 网关，默认上游 Kaiweb glm-4.5）** → Kaiweb 直连 fallback → OpenAI（云端 fallback）→ Anthropic → dev Mock 兜底。
- **Kaiweb 适配**：OpenClaw 自定义 `openai-completions` provider 指向 `https://ai.kaiweb.net/v1`；Klaw 的 `_call_openai_compatible` / `_stream_openai_compatible` 保留为 OpenClaw 故障时的直连 fallback；兼容推理模型 content 为空时回退 `reasoning_content`。
- **流式**：`/providers/chat/stream`（SSE）。
- **本地集成**：OpenClaw `/v1/chat/completions`、`/v1/models`、`/health`；本轮新增 `/api/v1/local-agent/tools` 发现（扫描 `deploy/*/skills/skill.json` + OpenClaw 在线工具合并）与 `/tools/{id}/call`（OpenClaw 不可达时 dev mock）。

### 3.4 定时任务 — ✅
- **引擎**：APScheduler AsyncIO + PostgreSQL SQLAlchemyJobStore（持久化，重启不丢）。
- **API**：`/api/v1/schedules` CRUD + 暂停/恢复；5 字段 cron；回调创建 Execution → `run_flow`。
- **本轮前端补全**：支持创建后编辑 name/cron（内联编辑）。

### 3.5 文件工作区 — ✅（本轮新增）
- **存储**：MinIO，路径 `/workspaces/{user_id}/{file_id}/{filename}`。
- **API**：`POST /api/v1/files` 上传 / `GET` 列表 / `GET /{id}` 下载 / `DELETE` / `GET /{id}/share` 预签名 URL（1h）。
- **模型**：`workspace_files` 表（owner 隔离）。

### 3.6 多平台推送 — ✅（本轮补全渠道配置）
- **渠道**：飞书 / 企业微信 / Telegram / Hermes（httpx 直调 Webhook/Bot API）。
- **即时推送**：`POST /api/v1/notifications/send`（内联 `channels` 或按 `channel_ids` 解析已配置渠道）。
- **渠道配置**（本轮新增）：`/api/v1/push/channels` GET/POST/DELETE；敏感字段（webhook_url/bot_token）AES-256-GCM 加密存储，API 返回脱敏 `******`。
- **节点**：画布 `notify` 节点内联多渠道；本轮补 `hermes` 渠道选项。

### 3.7 记忆与用户系统 — ✅
- **记忆**：PostgreSQL 持久层；`preference`/`decision`/`context` 类型；按 (user,key,session) upsert；ilike 关键词搜索；画布 `memory` 节点读写。短期 Redis 记忆留作路线图。
- **用户**：注册/登录/JWT(access+refresh)/RBAC(admin/user/viewer)；首个用户自动 admin；API Key 加密存储；本轮补 API Key 清除能力与前端管理 UI。

### 3.8 与 v1.1 的有意偏差
| 项 | v1.1 设计 | 实际实现 | 说明 |
|---|---|---|---|
| 编排引擎 | LangGraph | 自研 asyncio DAG | 功能等价（拓扑序 + 状态机 + SSE），降低依赖；M5 可迁 LangGraph |
| PDF 解析 | DeepDoc 全量（含 OCR） | PlainParser 纯文本 | 视觉/OCR 需 ONNX 模型，留 M5 |
| 短期记忆 | Redis + PG | 仅 PG | Redis 短期记忆待补 |
| 条件分支 | IF/ELSE 分支 | 简化求值返回 true/false | 当前不裁剪下游边，全部执行；M5 实现真正分支 |

---

## 4. 技术架构（实现现状）

```
前端 React 19 + Vite + Tailwind + shadcn/ui + @xyflow/react
  ↓ (Vite proxy /api → 8000)
API 网关 FastAPI + JWT + RBAC + 全局异常 + 结构化 JSON 日志
  ↓
知识库服务(DeepDoc/ES/TEI/MinIO) · Agent 服务(DAG 执行/SSE) · 模型供应商(OpenClaw/Hermes/OpenAI/Anthropic/Mock)
  ↓
基础设施 PostgreSQL(元数据+记忆+JobStore) · ES(向量+全文) · Redis · MinIO · APScheduler
  ↓
外部 OpenAI/Anthropic · 飞书/企微/Telegram Bot API
```

**技术栈**：FastAPI · SQLAlchemy(async) + asyncpg · Alembic · APScheduler · httpx · elasticsearch[async] · minio · sse-starlette · DeepDoc(parser+vision) · tiktoken · React 19 · @xyflow/react · Zustand。

---

## 5. 数据模型（已实现表）
`users` · `knowledge_bases` · `documents` · `chunks` · `agent_flows` · `executions` · `schedule_jobs` · `memories` · `workspace_files`(本轮新增) · `push_channels`(本轮新增)。

枚举修复：`executionstatus` 本轮补 `paused` 值（v1.1 迁移漏写，PG 上暂停会崩，已修）。

---

## 6. API 设计（实现现状）

| 模块 | 前缀 | 状态 |
|---|---|---|
| 认证 | `/auth` register/login/refresh/me | ✅ |
| 用户 | `/users` (admin 列表/改角色, `/me` 更新含 API Key) | ✅ |
| 知识库 | `/knowledge-bases` CRUD + documents + chunks + search | ✅ |
| Agent 画布 | `/agent-flows` CRUD + execute + executions + pause/resume/cancel + SSE stream | ✅ |
| 模型供应商 | `/providers` + `/models` + `/chat` + `/chat/stream` | ✅ |
| 本地 Agent | `/local-agent/tools` + `/tools/{id}/call` + `/health` | ✅ 本轮新增 |
| 文件工作区 | `/files` CRUD + `/{id}/share` | ✅ 本轮新增 |
| 定时任务 | `/schedules` CRUD + pause/resume | ✅ |
| 推送 | `/notifications/send` + `/push/channels` CRUD | ✅ 本轮补渠道配置 |
| 记忆 | `/memories` CRUD + `/search`(query param) | ✅ 本轮修 search |
| 健康检查 | `/health` | ✅ |

---

## 7. 非功能需求（现状）
- **性能**：检索 P95 目标 <500ms（ES 混合）；单节点 LLM <5s；定时秒级。
- **安全**：AES-256-GCM（API Key、推送渠道密钥）；JWT；RBAC；owner 隔离；SSRF guard（`common/ssrf_guard.py`）。
- **可观测**：结构化 JSON 日志（按 task 关联）；`/health` 多依赖探活。LangSmith 追踪留 M5。
- **部署**：Docker Compose（postgres/redis/minio/es/tei/reranker/openclaw/hermes/backend/frontend）；亦可本地 `uv`+`vite` 开发。

---

## 8. 里程碑（勾选现状）

| 里程碑 | 状态 |
|---|---|
| M1 基础设施（骨架+用户系统+Docker Compose+OpenClaw/Hermes） | ✅ |
| M2 知识库（DeepDoc+解析/分块/索引+混合检索） | ✅ |
| M3 Agent 画布（XYFlow+节点+DAG 执行+SSE） | ✅ |
| M4 全链路（本地工具+定时+记忆+文件工作区+推送+fallback） | ✅ 本轮补全 |
| **本轮补全** | 本地工具发现 / 文件工作区 / 推送渠道配置 / dev Mock 兜底 / paused 枚举修复 / 前端补全（仪表盘统计、API Key 管理、渠道页、定时编辑、KB 分块设置、hermes 渠道） |
| M5 生产级 | ⬜ 见 §9 |

---

## 9. 剩余路线图（M5 生产级）
1. 迁移到 LangGraph SDK（保留当前 DAG 作为 fallback）；条件节点实现真正分支裁剪。
2. PDF 视觉/OCR 解析（DeepDoc VisionParser + ONNX 模型）。
3. Redis 短期记忆（会话上下文 TTL）。
4. LangSmith 全链路追踪 + 日志聚合 + 告警。
5. 多租户权限隔离加固 + 分布式锁（APScheduler 多实例）。
6. Telegram / 邮件推送补全 + 推送失败重试告警。
7. 文件工作区版本管理 + 报告归档。
8. K8s + Helm + Prometheus/Grafana + 压测。

---

## 10. 验证状态（2026-07-15）
- 后端测试：`uv run pytest -q` → **58 passed**（含本轮新增 6 项：本地工具/文件工作区/推送渠道）。
- 端到端（本地运行，轻量基础设施 postgres+redis+minio+es，OpenClaw/Hermes/TEI 可用）：
  - 注册/登录/JWT ✅
  - 知识库：创建→上传 txt→DeepDoc 解析→TEI 向量化→ES 索引→混合检索（3 hits，BM25+kNN 排序）✅
  - 工作流：创建(text→llm)→执行→node_states→success（**真实 GLM via Kaiweb**，非 Mock）✅
  - 本地工具发现（3 Skills）✅ · 推送渠道配置（加密+脱敏）✅ · 文件上传 ✅ · 供应商列表（kaiweb=ok，10 真实模型）✅
- 前端：`tsc -b` 通过；Vite 5173 + 代理 8000 正常。

---

## 11. 版本变更记录
| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-07-14 | 初始版本（云端 Kimi Claw） |
| v1.1 | 2026-07-14 | 模型层改本地 OpenClaw/Hermes；定时/存储/推送/记忆自建 |
| v2.0 | 2026-07-15 | 按实际实现重生成；标注偏差；本轮补全 P0 接口与 UI；新增 Mock 兜底；修复 paused 枚举 |
| v2.1 | 2026-07-16 | OpenClaw 接入 Kaiweb OpenAI 兼容网关（glm-4.5 默认），Kaiweb 直连作为 fallback；兼容 reasoning_content |
