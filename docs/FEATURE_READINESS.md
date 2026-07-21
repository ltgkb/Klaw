# Klaw 功能就绪矩阵

> 审计批次：2026-07-22（Asia/Shanghai）
> 目标分支：`auto-iter-20260722`
> 证据原则：状态只依据本批次代码、自动化和真实运行结果；SQLite/mock 不替代 PostgreSQL、模型、网关或外部渠道证据。

## 证据摘要

- 后端基线：`uv run pytest -q` 为 **203 passed**；本轮最终全量回归 **219 passed**。
- 前端：`npm run lint` 通过（4 个既有 Fast Refresh warning）；`npm run build` 通过，主 JS 约 631 kB，仍有 code-splitting warning。
- 真实依赖：隔离 PostgreSQL 16、Redis 7、MinIO、Elasticsearch 8.11、OpenClaw 2026.7.1、Hermes 0.18.2、TEI reranker 全部 healthy；OpenClaw/Hermes/reranker 均 0 重启、未 OOM。
- 真实 API：注册、登录、refresh、TXT 上传解析、MinIO 存储、ES 索引/检索、真实 rerank、条件裁剪、Bearer Header SSE、Agent 对话落库、OpenClaw `web_fetch`、APScheduler 触发/重启恢复/暂停均通过。
- 浏览器：Playwright 在 1440x1000 与 390x844 完成登录、设置页真实工具调用和 Agent 对话；SSE URL 无 token query 且请求含 Bearer Header；console 无 error；移动页无横向溢出。
- 环境阻塞：本次没有真实 embedding 服务或 LLM 凭据；知识库使用明确的 dev 哈希向量，LLM 未宣称真实推理。外部飞书/企微/Telegram 推送、OCR 和 TEI BGE-M3 未验证。

## 功能矩阵

| 功能 | 用户入口 | 前端状态 | 后端/API 与真实依赖 | 本次证据 | 状态 | 问题与优先级 |
|---|---|---|---|---|---|---|
| 注册、登录、access JWT | `/register`、`/login` | 可用 | `/auth/register`、`/auth/login` + PG | 自动化；真实 HTTP 201/200 | 可用 | 无 |
| 刷新令牌 | Axios 拦截器 | 可用 | `/auth/refresh` 校验 token 类型和 active 用户 | 自动化；真实 Bearer refresh | 可用 | rotation/revocation 缺失（P2） |
| RBAC 与用户启停 | `/users`（admin） | 可用 | 动态读取 DB 角色/状态，保护最后 admin 和自锁 | auth/negative tests | 可用 | 组织级角色策略缺失（P2） |
| owner 隔离与密钥保护 | 各资源页、设置 | 可用 | owner-scoped 查询；AES-256-GCM 存 API key/channel secret | KB/flow/schedule/file 隔离和 crypto tests | 可用 | 当前是单租户 owner 隔离（P2） |
| 知识库 CRUD | `/kb` | 可用 | PG CRUD，分页上限 100 | 自动化；真实创建/列表 | 可用 | 无 |
| TXT/MD/HTML/JSON/DOCX/XLSX/PPTX/EPUB | KB 详情上传 | 可用 | MinIO + DeepDoc 类型路由 | parser fixtures；真实 TXT 全链路 | 部分可用 | 其它格式缺逐格式 MinIO->ES E2E（P1） |
| PDF 解析/OCR | KB 详情上传 | 文本 PDF 可上传 | pypdf 文本路径；视觉模块未启用 | parser test；未跑扫描 PDF | 部分可用 | OCR/版面/图片表格缺失（P2） |
| 分块、引用、删除 | KB chunks/文档列表 | 可用 | fixed/recursive/markdown；semantic 降级；page/doc metadata | tests；真实 TXT chunk/引用 | 可用 | semantic 不是独立算法（P2） |
| 向量化 | 摄取后台任务、系统配置 | 可配置 API | API -> TEI -> dev hash fallback | 真实 hash fallback，健康为 unhealthy | 部分可用 | 生产 embedding 环境阻塞（P0 部署条件） |
| ES 索引与删除 | 摄取/删除触发 | 间接可见 | dense_vector + BM25；bulk 退避 | 真实索引、检索命中 `ORBIT-20260722` | 可用 | 缺索引备份/生命周期（P2） |
| 混合检索、重排、引用 | KB 详情搜索 | rerank 开关可用 | kNN+BM25 + TEI Cross-Encoder | 真实中文 rerank；相关分 0.9819，天气 0.0003 | 可用 | embedding 仍为 hash，整体质量不可作生产结论（P1 环境） |
| 画布保存/加载/导入导出 | `/flows/:id` | 可用 | DAG JSON 保存 node size 和 sourceHandle | CRUD/画布 tests；build | 可用 | 模板和版本历史缺失（P2） |
| 节点配置 | 画布属性栏 | 10 类节点有入口 | start/end/text/llm/retrieval/condition/loop/http/notify/memory；HTTP 公网 allowlist | execution tests；真实公网 HTTP；内网 SSRF 拦截 | 部分可用 | 本地工具没有画布节点；私网 HTTP 连接策略需确认（P1） |
| 真正条件分支 | condition 多 handle | 可用 | 只推进 matched sourceHandle，未命中标记 skipped | 自动化；真实 yes 命中、错误分支 skipped | 可用 | 复杂多分支汇合仍需扩展测试（P1） |
| 循环节点 | 画布 loop | 可配置 detached body | 1-100 次、失败继续、迭代状态 | 自动化 | 部分可用 | 仅支持单个 detached body，非子图迭代（P1/P2） |
| 执行、SSE、失败恢复 | 画布/执行详情 | 可用 | PG execution + SSE + stale reaper；Nginx 禁用缓冲 | 修复 identity-map 永久 progress；容器 Nginx 实时 progress→complete | 可用 | 无 durable checkpoint/幂等锁（P2） |
| SSE 鉴权与密钥保护 | 画布、Agent 对话 | Header 流客户端 | 仅 Bearer Header；active/owner 校验 | Header/query-reject/disabled/malformed/live-session tests；浏览器无 query token | 可用 | 无 |
| 暂停/恢复/取消 | 执行详情、对话停止键 | UI/API 可用 | 状态轮询；取消终帧同步节点状态且优先于 success | 自动化；真实延迟 HTTP 暂停/恢复/取消 + Header SSE | 部分可用 | 在途 HTTP/LLM 不会被强制中断；下个让出点终止（P1） |
| Agent 对话与历史 | `/agents` | 实时节点进度、停止、错误可见 | conversation/message PG + flow execution | 真实 SSE + 2 消息落库；浏览器回答可见 | 部分可用 | 是执行状态流，不是 LLM token 流；单固定会话（P1） |
| 模型发现/切换 | 设置、LLM 节点 | 仅展示已启用本地模型 | OpenClaw→Hermes→Kaiweb→OpenAI→Anthropic；本地路由有独立开关 | Hermes models/chat 接口真实探测；适配自动化 | 部分可用 | Hermes 无推理供应商、其它无真实 LLM 凭据（P0 部署条件） |
| provider 流式/fallback/错误 | `/providers/chat/stream`、设置 | 设置测试为非流式 | SSE delta；多级 fallback；dev Mock 显式标记 | fallback/stream tests | 部分可用 | UI 未消费 token stream；真实 provider 未验证（P1） |
| OpenClaw/Hermes 发现 | 设置 | 3 个清单可见 | 本地 manifest；网关健康 | OpenClaw/Hermes healthy | 可用 | `send_notification`、`data_analysis` 仍仅清单（P1） |
| 本地工具调用 | 设置工具调用器 | JSON 参数、结果/错误可见 | manifest allowlist 后调用 OpenClaw `/tools/invoke` | 真实 `web_fetch` HTTP 200；未知工具零网关请求 | 部分可用 | 只有 web_fetch 完成真实调用；缺画布 tool node（P1） |
| APScheduler CRUD/控制/触发 | `/schedules` | 创建/编辑/暂停/恢复 | PG SQLAlchemyJobStore | 每分钟任务真实触发 success | 可用 | 多实例无 leader/分布式锁（P1/P2） |
| 调度重启持久化 | `/schedules` | next run 可见 | PG JobStore 恢复 | 后端重启后 next run 恢复并再次触发；暂停清空 next run | 可用 | 多实例重复触发风险（P1） |
| PostgreSQL/Redis 记忆 | `/memories` | PG 记忆 UI 可用 | PG CRUD/search/upsert；Redis 只探活 | memory tests；Redis healthy | 部分可用 | Redis TTL 短期会话记忆缺失（P2） |
| 文件工作区/分享 | `/files` | 上传/下载/删除/分享 | MinIO + owner PG + presigned URL | tests；本次 MinIO 实际存储由 KB 链路覆盖 | 部分可用 | 本次未重跑文件分享浏览器 E2E；无版本/撤销（P1/P2） |
| 推送渠道与失败重试 | 设置、notify 节点 | 配置/测试入口 | 加密渠道；SSRF guard + DNS pin；四种 sender | 自动化失败/脱敏/rebinding 防护 | 部分可用 | 无真实渠道凭据；无持久重试/告警（P1/P2） |
| 系统设置/健康 | `/settings`、`/health` | 依赖状态可见 | PG/Redis/ES/MinIO/OpenClaw/Hermes/reranker 探活 | 前六项真实 ok；embedding error 使 overall degraded | 可用（诚实） | 缺延迟、版本和历史趋势（P2） |
| 导航/空态/错误态/移动端 | 全站 | 响应式主导航和 Agent 选择 | React Router + toast | 1440/390 Playwright，无 console error/横向溢出 | 部分可用 | 多页仍有静默 catch；无 CI 浏览器套件（P1） |
| Compose/迁移/部署 | Compose、Makefile | N/A | backend 启动前 Alembic；health gating；无运行时依赖安装 | backend/frontend 镜像；容器迁移到 head；运行后 alembic check clean；Nginx E2E | 部分可用 | 固定 container_name 阻碍并行；TEI BGE-M3 未启动（P1/P2） |
| 测试/lint/build/CI | Makefile | N/A | pytest/oxlint/tsc/Vite/Compose | 219 tests；lint/build/config 通过 | 部分可用 | 仓库无 CI；bundle 631 kB；无浏览器 CI（P1） |

## 本轮矩阵变化

1. SSE 从“query token + 可能永久 progress”提升为 Header 鉴权、可刷新 token、独立 session 状态可见，画布和 Agent 对话共用安全客户端。
2. Agent 对话从固定 1 秒消息轮询提升为实时节点进度、断线回退、取消和终态错误持久化；明确仍不是 token streaming。
3. 本地工具从“3 个展示清单、调用失败”提升为设置页可调用，`web_fetch` 经 OpenClaw 真实成功；其余两个清单仍标部分可用。
4. 无 Kaiweb Key 的全新 OpenClaw dev 部署从重启循环提升为 gateway/Skills 可启动；不伪造模型可用。
5. 移动设置页从 507px 横向溢出修为 390px；移动对话输入从约 35px 修为约 275px。
6. Compose backend 从覆盖镜像的宿主源码挂载改为确定性镜像，启动前自动迁移并向 frontend 提供 health gate；Docker 构建上下文排除 `.venv`/`node_modules`/缓存。
7. 画布 HTTP 节点新增公网地址校验与 DNS pinning，阻断 loopback/私网/云元数据 SSRF；HTTP 错误不再泄露 URL 查询凭据。
8. 取消操作立即把运行节点写为 cancelled 并记录原因，SSE 终帧不再出现“顶层已取消、节点仍运行”的矛盾状态。
9. Hermes 从“在线即模型可用”的误报改为显式 chat 开关；补齐非流式/SSE fallback 适配，未配置推理供应商时保持未配置状态。
10. 模型发现不再展示未配置的 Kaiweb/OpenAI/Anthropic；无真实凭据时只显示默认路由和显式 dev mock。
11. Alembic autogenerate 排除 APScheduler 自管表，避免运行后错误生成删除 `apscheduler_jobs` 的迁移。

## 对标参考（官方资料，检索日期 2026-07-22）

- [RAGFlow README](https://github.com/infiniflow/ragflow) / [DeepDoc](https://ragflow.io/docs/dev)，latest `v0.26.4`（2026-07-07）：借鉴格式化解析、chunk metadata、引用和可解释检索；Klaw 暂不宣称 OCR/多模态。
- [Dify README](https://github.com/langgenius/dify) / [Workflow](https://docs.dify.ai/guides/workflow)，latest `1.16.0`（2026-07-17）：借鉴分支 handle、变量、工具运行结果和错误可见性；Klaw 保持轻量 DAG，不复制实现。
- [LangChain README](https://github.com/langchain-ai/langchain)，latest `langchain-core==1.5.0`（2026-07-21）：借鉴 provider/tool 抽象和流式契约；当前不为抽象而引入框架依赖。
- [LangGraph persistence](https://langchain-ai.github.io/langgraph/concepts/persistence/)，latest `1.2.9`（2026-07-10）：借鉴 checkpoint、恢复、重试与人机协同验收维度；迁移前必须补持久执行和回退测试。

## 遗留优先级

- P0 部署条件：生产必须配置强 JWT/加密密钥、真实 1024 维 embedding 和至少一个真实 LLM；当前代码无已知未修 P0。
- P1：真实 LLM/token stream UI；OpenClaw 工具画布节点；其它工具真实实现；在途调用强制中断；多实例调度防重；逐格式摄取 E2E；推送成功链路/重试；基础/浏览器 CI；移除静默错误。
- P2：OCR/多模态、语义分块、Redis TTL 记忆、文件版本、索引备份、checkpoint/评测/可观测、K8s/压测。

## 需用户确认

- HTTP 节点现按安全默认值仅允许解析到公网 IP 的 URL。若产品必须访问企业内网 API，应设计管理员域名/CIDR allowlist，不能启用全局绕过。
- Compose 仍保留固定 `container_name` 以兼容现有运维命令；这会阻碍同机多 project 并行，是否移除需同步部署脚本。

## 参考命令

```bash
cd backend && uv run pytest -q
cd frontend && npm run lint && npm run build
docker compose config -q
cd backend && POSTGRES_URL=... uv run alembic upgrade head && uv run alembic check
```
