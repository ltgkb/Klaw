# Klaw 功能就绪矩阵

> 审计批次：2026-07-21（Asia/Shanghai）  
> 目标分支：`auto-iter-20260721`  
> 证据原则：只记录本批次实际运行结果；SQLite/mock 仅用于自动化隔离测试，不能替代真实依赖证据。

## 证据摘要

- 后端：`uv run pytest -q` → **77 passed**；另行运行 `uv run python -m compileall -q app deepdoc common` 通过。
- 前端：`npm run lint` 通过（3 个既有 Fast Refresh warning）；`npm run build` 通过（Vite 产生约 607 kB 主 JS，存在 code-splitting warning）。
- 浏览器：Playwright 在 1440×1000 与 390×844 视口完成真实登录→设置→用户停用→恢复；用户管理可见，页面/滚动容器无横向溢出，控制台无 error。
- Compose：基础 `docker compose config --quiet` 通过；隔离覆盖配置也通过；后端/前端镜像均构建成功，`.dockerignore` 将最终 build context 限制在约 194 kB / 39 kB（未忽略时曾达 1.12 GB / 132 MB）。
- 真实依赖：隔离 PostgreSQL 16、Redis 7、MinIO、Elasticsearch 8.11 全部 healthy；Alembic 从空库升级到 `4b2e9a1c7d33 (head)`，`alembic check` 无漂移。
- 真实 API：注册/登录/刷新、PG 元数据、管理员用户列表与停用/恢复、MinIO 上传下载分享删除、TXT/HTML DeepDoc 解析、哈希向量 fallback、ES 索引与检索、条件分支、SSE complete、APScheduler 实际触发和重启恢复均已通过；内存生成的 MD/HTML/JSON/DOCX/XLSX/PPTX/PDF parser fixture 也已通过。
- 环境阻塞：本次未启动 TEI BGE-M3、reranker、OpenClaw、Hermes；健康检查如实为 degraded。知识库使用明确标记的 dev 哈希向量 fallback，LLM/工具使用明确标记的 dev Mock，未宣称真实模型或真实本地工具可用。

## 功能矩阵

| 功能 | 用户入口 | 前端状态 | 后端/API 与真实依赖 | 自动化/端到端证据 | 状态 | 问题与优先级 |
|---|---|---|---|---|---|---|
| 注册、登录、access JWT | `/register`、`/login` | 可用 | `/auth/register`、`/auth/login` + PG | `test_auth.py`；真实 HTTP 注册/登录 | 可用 | 无；密码 bcrypt |
| 刷新令牌 | 前端拦截器自动刷新 | 本批补全 | `/auth/refresh`，校验 refresh 类型、用户 active | `test_refresh_token`；真实 HTTP 200 | 可用 | 需后续增加 token rotation/revocation（P2） |
| RBAC 与禁用用户 | 设置/用户管理 | 可用 | `require_roles`；当前用户每次请求检查 `is_active`；管理员状态 API 禁止自锁 | RBAC、普通用户 403、自锁 400 测试；真实 API 与浏览器停用/恢复；旧 token 401 | 可用 | 组织/团队级管理员策略仍缺失（P2） |
| owner 隔离与密钥保护 | 各资源页面 | 可用 | 查询按 owner；AES-256-GCM API key/channel secret | KB/flow/schedule/file 隔离测试；真实 push 配置返回 `******` | 可用 | 单租户 owner 模式，不是团队/组织租户（P2） |
| 知识库 CRUD | `/kb` | 可用 | `/knowledge-bases` + PG；页码最小 1、每页最大 100 | `test_kb.py`、分页 422、真实创建/列表 | 可用 | 无 |
| TXT/MD/HTML/JSON/DOCX/XLSX/PPTX/EPUB 上传解析 | KB 详情上传 | 可用 | MinIO + DeepDoc 格式路由 | parser fixture 覆盖 MD/HTML/JSON/DOCX/XLSX/PPTX/EPUB/PDF；真实 MinIO→解析→ES 管线验证 TXT、HTML | 部分可用 | 仍需逐格式 MinIO→ES E2E 和大文件/损坏文件验证（P1） |
| PDF 纯文本解析 | KB 详情上传 | 可用 | pypdf 轻量路径；视觉 OCR 未启用 | 代码路径和 parser 回归 | 部分可用 | OCR/版面/表格图片仍缺模型（P2） |
| 分块与引用元数据 | KB chunks | 可用 | fixed/recursive/markdown/semantic 降级；page/doc/chunk metadata | `test_kb.py`；真实 1 chunk、page/source metadata | 可用 | semantic 仍是 recursive fallback（P2） |
| 向量化 | 上传后台任务 | 无独立配置入口可感知 fallback | TEI → dev 哈希向量 | 真实 TEI 不可达时明确日志并完成 ES indexing | 部分可用 | TEI 模型 sidecar 未启动；哈希向量不可用于生产（P0/P1 环境） |
| Elasticsearch 索引 | 无独立入口 | 由 KB 流程触发 | dense_vector + BM25 | 真实 ES bulk 1 chunk 成功 | 可用 | 无索引生命周期/备份策略（P2） |
| 混合检索、阈值、引用 | KB 详情检索 | 可用 | `/search` kNN+BM25；可选 rerank | mock rerank 测试；真实 ES 查询命中 `ORBIT-7429` | 部分可用 | reranker 未启动；真实结果未覆盖重排（P1 环境） |
| Agent 画布保存/加载 | `/flows/:id` | 可用 | `/agent-flows` DAG JSON | CRUD/DAG 测试；真实 flow 保存 | 可用 | 模板库/版本历史缺失（P2） |
| 节点配置 | 画布右侧面板 | 可用 | text/llm/retrieval/condition/notify/memory/start/end | execution tests + 真实 text/condition flow | 部分可用 | 本地工具未作为画布节点，仅独立工具 API（P1） |
| 条件分支裁剪 | condition handles | 可用 | 按 `sourceHandle` 只推进匹配路径 | 新增错误分支不执行测试；真实 `approved` 路径成功 | 可用 | 汇合节点复杂拓扑仍需更多回归（P1） |
| 执行、node states、失败终止 | 画布执行/执行详情 | 可用 | asyncio DAG + PG execution | 测试；真实 flow success | 可用 | 多实例执行锁/幂等缺失（P2） |
| SSE 实时执行流 | 执行详情 | 可用 | `/stream` token query 鉴权，刷新 DB row | 新增 complete 测试；真实 SSE `complete` | 可用 | query token 会出现在 URL 日志，宜改短期 SSE ticket（P1） |
| 暂停/恢复/取消 | 执行详情按钮 | 本批补全实时轮询/错误态 | 控制 API 绑定 flow+execution；取消不再复活 | owner 越权、pre-cancel、控制测试 | 部分可用 | 尚未在真实长耗时节点执行暂停/取消；需真实 LLM/人工节点验证（P1） |
| Agent 对话与历史 | `/agents` | 可用 | `/chat` 后台执行 + PG conversations/messages | 真实工作流对话 2 messages、assistant 输出 | 部分可用 | 前端轮询而非流式对话；固定单会话/最近 10 条（P1） |
| 模型发现/切换 | 设置、LLM 节点 | 可用 | `/providers`、`/providers/models`、OpenAI-compatible client | 真实无 key 返回 6 providers/5 models；Mock fallback chat | 部分可用 | Kaiweb/OpenClaw 无 key/服务，未做真实模型切换（环境阻塞） |
| 流式输出/fallback/错误呈现 | provider stream、设置测试 | 部分可用 | `/providers/chat/stream`；Kaiweb→OpenClaw→OpenAI→Anthropic→dev mock | provider chat 真实 fallback；SSE 代码覆盖有限 | 部分可用 | 本轮未接真实 SSE provider；UI 对流式 provider 未直接消费（P1） |
| OpenClaw/Hermes 工具发现与调用 | 设置工具列表/API | 部分可用 | skill.json 扫描 + gateway merge/call | 真实扫描 3 skills；调用返回明确 `mock` | 部分可用 | OpenClaw/Hermes 未启动；生产已禁止伪造 mock success；无画布工具节点（P1） |
| APScheduler 创建/编辑/暂停/恢复/触发 | `/schedules` | 可用 | AsyncIO + PostgreSQL SQLAlchemyJobStore | `test_m4.py`；真实 08:17/08:18 触发 success | 可用 | 多实例无分布式锁；漏触发/并发策略需 P2 加固 |
| 调度重启持久化 | `/schedules` | 可用 | JobStore PG | 后端重启后 next_run 保留并实际再次触发 | 可用 | migration/startup 多实例竞态（P2） |
| PostgreSQL/Redis 记忆 | `/memories` | PG UI/API 可用；Redis 无 UI | PG memory CRUD/search；Redis 仅健康探活 | 真实 PG save/search；mock owner tests | 部分可用 | Redis 短期 TTL/session context 未实现（P2） |
| 文件工作区 | `/files`（本批新增） | 可用 | MinIO + owner-scoped DB；鉴权 blob 下载 | 真实上传/下载 hash/分享/隔离/删除 | 可用 | 无版本、批量、断点续传（P2） |
| 分享链接 | 文件行分享按钮 | 可用 | MinIO presigned URL 1h | 真实返回 1h URL | 部分可用 | 外部客户端访问需可达 MinIO endpoint；无撤销记录（P2） |
| 推送渠道配置 | 设置 | 可用 | channel CRUD + encrypted config | 真实配置脱敏；失败 webhook 返回 success=false/error | 部分可用 | 未验证真实飞书/企微/Telegram 成功；无重试/告警（P1/P2） |
| 系统设置 | 设置 | 可用 | embedding/LLM config admin endpoints；普通用户跳过 admin-only 请求 | 现有 API 测试；真实 startup 读取 PG；管理员用户管理 E2E | 部分可用 | 前端部分错误态仍有静默 catch（P1） |
| 健康检查 | `/health`、设置 | 可用 | PG/Redis/ES/MinIO/TEI/reranker/OpenClaw/Hermes | 真实返回 degraded，四个基础依赖 ok，重型 sidecar error | 可用（诚实） | `/health` 未提供依赖延迟/版本（P2） |
| 前后端导航与空/加载/错误态 | 全局布局 | 部分可用 | React Router + API interceptor | build；文件页/执行页新增错误态；桌面/移动浏览器无溢出 | 部分可用 | 多页面仍有静默 catch（P1） |
| Docker Compose 启动 | 根目录 Compose | 部分可用 | 10 服务；后端镜像启动先迁移 | config 校验；本轮隔离只启动 4 基础依赖 | 部分可用 | TEI/OCR/OpenClaw/Hermes 镜像/模型未在本机验证；固定 container_name 影响并行部署（P1） |
| 迁移 | `make db-migrate` | 可用 | Alembic | 空 PG upgrade + current head + check | 可用 | 首次多实例迁移锁策略未加固（P2） |
| 测试/lint/build | Makefile、GitHub Actions | 可用 | pytest/oxlint/tsc/Vite；后端/前端/Compose 三个 CI job | 77 passed；lint/build、YAML/Compose、手工 Playwright 烟测通过 | 可用 | 浏览器 E2E 尚未纳入 CI（P1） |

## 本轮修复与新增能力

1. 执行控制按 `flow_id + execution_id + owner` 绑定，修复跨工作流越权；取消在启动、节点完成、最终提交前均不会被复活为 success；SSE 每轮刷新独立 session 写入的状态。
2. DeepDoc parser 改为惰性导出和按格式导入；TXT/PDF 轻量路径不再加载 PDF OCR/xgboost；解析和 MinIO 下载移入线程，真实上传从分钟级事件循环阻塞降为约 20ms 返回并后台完成。
3. Alembic 加入 `prepend_sys_path`；Docker 后端启动先迁移再启动 API；修复全新数据库“容器健康但无表”的部署风险。
4. Cron 用 APScheduler 原生校验；暂停清空 next_run；暂停期间编辑 cron/input 会替换并再次暂停真实 job；恢复可重建缺失 job。
5. 健康检查只把 2xx 视为依赖可用；生产环境禁止本地工具 mock 伪造成功。
6. 新增鉴权文件工作区 UI、blob 下载、分享/删除/上传状态；前端 access token 自动 refresh；移动端提供可滚动导航。
7. 新增管理员用户管理纵向切片：用户列表、角色调整、启用/停用入口；后端禁止普通用户操作及管理员自锁；普通用户设置页不再请求 admin-only 配置。
8. 新增 GitHub Actions CI，锁文件安装后并行执行后端测试、前端 lint/build 与 Compose 配置校验，并限制最小只读权限。
9. 知识库、chunk 与 Agent 流列表统一校验分页边界，拒绝负页码、空页和超过 100 条的单页查询。

## 对标参考（官方资料，检索日期 2026-07-21）

- [RAGFlow README](https://github.com/infiniflow/ragflow) / [DeepDoc 文档](https://ragflow.io/docs/dev)（官方 latest `v0.26.4`，2026-07-07）：借鉴按文件类型的深度解析、块级 metadata/citation 和检索可解释性；本仓库保留轻量 DeepDoc 路由，OCR/多模态列入 M5，不复制实现。
- [Dify README](https://github.com/langgenius/dify) / [Workflow 文档](https://docs.dify.ai/guides/workflow)（官方 latest `1.16.0`，2026-07-17）：借鉴变量上下文、条件分支、模型/工具入口和错误可见性；本轮补强真正 handle 分支裁剪和执行状态 UI，尚未扩展迭代节点/评测。
- [LangChain README](https://github.com/langchain-ai/langchain)（`langchain-core==1.4.9`，2026-07-08）/ [LangGraph persistence 文档](https://langchain-ai.github.io/langgraph/concepts/persistence/)（`1.2.9`，2026-07-10）：借鉴 provider/tool 抽象、streaming、checkpoint/持久执行的验收维度；当前保留自研轻量 DAG，待引入 LangGraph 前先补迁移、checkpoint 和回退测试。

## 遗留项

- P0：无代码层遗留；生产启动仍需提供 TEI/OpenClaw/Hermes/Kaiweb 等真实依赖，当前环境阻塞必须在部署前解决。
- P1：真实 provider/工具/推送成功链路未验证；前端对话流式与多数页面错误态；画布工具节点；真实长耗时暂停/取消；浏览器 E2E 自动化；多实例调度锁。
- P2：OCR/多模态、Redis TTL 短期记忆、重排服务、文件版本、推送重试/告警、可观测/评测、K8s/压测。

## 参考命令

```bash
cd backend && uv run pytest -q
cd frontend && npm run lint && npm run build
docker compose config --quiet
cd backend && POSTGRES_URL=... uv run alembic upgrade head && uv run alembic check
```
