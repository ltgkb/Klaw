# Klaw 功能就绪矩阵

> 审计批次：2026-07-23（Asia/Shanghai）
> 目标分支：`auto-iter-20260723`
> 证据原则：状态只依据本批次代码、自动化和真实运行结果；SQLite/mock 不替代 PostgreSQL、模型、网关或外部渠道证据。

## 证据摘要

- 后端基线：承接分支后全量回归 **249 passed**；本次补多会话 CRUD/owner 隔离测试，最终 **251 passed**（2 个上游 sqlglot 弃用警告）。
- 前端：`npm run lint` 通过（4 个既有 Fast Refresh warning）；`npm run build` 通过，主 JS 约 637 kB，仍有 code-splitting warning。
- 真实依赖：独立 PostgreSQL 数据库 `claw_auto_20260723`、Redis、MinIO、Elasticsearch 8.11、OpenClaw 2026.7.1、Hermes 0.18.2 healthy；迁移到 head 且 `alembic check` 无漂移。
- 真实 API：注册/登录、TXT/MD/HTML/JSON/CSV/PDF/DOCX/XLSX/PPTX/EPUB→MinIO→解析→hash embedding→ES 检索引用、OpenClaw `web_fetch`、画布 tool 节点、加密通知渠道/owner 拦截、APScheduler 实际触发及暂停后重启保持均通过；本次再验证 MD 标记检索、工作流元数据更新与会话创建/删除。
- 浏览器：前端 dev server 可用，但 in-app Browser 运行时初始化被 `Cannot redefine property: process` 阻塞；本批次不沿用昨日截图宣称浏览器通过。
- 环境阻塞：reranker 因 Hugging Face 工件下载连接失败退出，镜像构建因 Docker Hub metadata 超时失败；TEI BGE-M3/真实 LLM/外部推送凭据均不可用。哈希向量与自动化 mock 不作为生产能力证据。

## 功能矩阵

| 功能 | 用户入口 | 前端状态 | 后端/API 与真实依赖 | 本次证据 | 状态 | 问题与优先级 |
|---|---|---|---|---|---|---|
| 注册、登录、access JWT | `/register`、`/login` | 可用 | PG advisory lock 串行首用户角色；bcrypt-SHA256 完整密码哈希 | 自动化；真实并发恰好 1 admin/1 user；旧哈希升级；超长碰撞 401 | 可用 | 无 |
| 刷新令牌 | Axios 拦截器 | 可用 | `/auth/refresh` 校验 token 类型和 active 用户 | 自动化；真实 Bearer refresh | 可用 | rotation/revocation 缺失（P2） |
| RBAC 与用户启停 | `/users`（admin） | 可用 | 动态读取 DB 角色/状态，保护最后 admin 和自锁 | auth/negative tests | 可用 | 组织级角色策略缺失（P2） |
| owner 隔离与密钥保护 | 各资源页、设置、通知节点 | 持久化渠道选择并脱敏 | owner-scoped 查询；AES-256-GCM；新 DAG 禁止内联渠道 | 自动化；真实密文落库、跨 owner 执行失败、内联写入 422 | 可用 | 旧 DAG 仍兼容读取，需用户主动迁移；单租户 owner 隔离（P2） |
| 知识库 CRUD/批量导入 | `/kb` | 新增“导入知识库”，可选多文件或文件夹并自动创建、逐文件上传、报告部分失败 | PG CRUD，分页上限 100；复用真实 documents 摄取 API | lint/build；真实 API 创建后 MD 摄取与检索命中 | 可用 | 浏览器视觉烟测受工具环境阻塞（P1 验证） |
| TXT/MD/HTML/JSON/CSV/DOCX/XLSX/PPTX/EPUB | KB 详情上传 | 可用；失败原因与重试入口 | MinIO + DeepDoc 类型路由；旧 DOC/XLS/PPT 前置 415；修复 MD/PPTX 契约与离线 tokenizer | 生成文件 parser tests；9 种格式真实全链路并分别检索 marker；failed→reparse→parsed | 可用 | 复杂版式/损坏文件样本仍需扩展（P2） |
| PDF 解析/OCR | KB 详情上传 | 文本 PDF 可上传 | pypdf 文本路径；视觉模块未启用 | 真实单页文本 PDF 全链路并检索 marker；未跑扫描 PDF | 部分可用 | OCR/版面/图片表格缺失（P2） |
| 分块、引用、删除 | KB chunks/文档列表 | 可用；创建参数前端约束 | fixed/recursive/markdown；semantic 降级；强制 overlap < size；page/doc metadata | tests；危险窗口 422；真实 TXT chunk/引用 | 可用 | semantic 不是独立算法（P2） |
| 向量化 | 摄取后台任务、系统配置 | 可配置 API | API -> TEI -> dev hash fallback | 真实 hash fallback，健康为 unhealthy | 部分可用 | 生产 embedding 环境阻塞（P0 部署条件） |
| ES 索引与删除 | 摄取/删除触发 | 间接可见 | dense_vector + BM25；bulk 退避 | 真实索引、检索命中 `ORBIT-20260723` | 可用 | 缺索引备份/生命周期（P2） |
| 混合检索、重排、引用 | KB 详情搜索 | rerank 开关可用 | kNN+BM25 + TEI Cross-Encoder | 真实 ES 混合检索和引用；reranker 本次启动失败 | 部分可用 | embedding 为 hash 且本次无重排，质量不可作生产结论（P1 环境） |
| 画布保存/加载/元数据编辑/导入导出 | `/flows`、`/flows/:id` | 列表新增名称/描述编辑入口 | PUT 保存名称、描述、DAG JSON、node size 和 sourceHandle | build；真实 API `Original Flow`→`Renamed Flow` 且描述更新 | 可用 | 模板和版本历史缺失（P2） |
| 节点配置 | 画布属性栏 | 11 类节点有入口 | 新增 tool；其余 start/end/text/llm/retrieval/condition/loop/http/notify/memory | execution/API tests；真实 OpenClaw tool DAG success | 可用 | 私网 HTTP 连接策略需确认（产品决策） |
| 真正条件分支 | condition 多 handle | 可用 | 只推进 matched sourceHandle，未命中标记 skipped | 自动化；真实 yes 命中、错误分支 skipped | 可用 | 复杂多分支汇合仍需扩展测试（P1） |
| 循环节点 | 画布 loop | 可配置 detached body | 1-100 次、失败继续、迭代状态 | 自动化 | 部分可用 | 仅支持单个 detached body，非子图迭代（P1/P2） |
| 执行、SSE、失败恢复 | 画布/执行详情 | 可用 | PG execution + SSE + stale reaper；Nginx 禁用缓冲 | 修复 identity-map 永久 progress；容器 Nginx 实时 progress→complete | 可用 | 无 durable checkpoint/幂等锁（P2） |
| SSE 鉴权与密钥保护 | 画布、Agent 对话 | Header 流客户端 | 仅 Bearer Header；active/owner 校验 | Header/query-reject/disabled/malformed/live-session tests；浏览器无 query token | 可用 | 无 |
| 暂停/恢复/取消 | 执行详情、对话停止键 | UI/API 可用 | 状态轮询；取消终帧同步节点状态且优先于 success | 自动化；真实延迟 HTTP 暂停/恢复/取消 + Header SSE | 部分可用 | 在途 HTTP/LLM 不会被强制中断；下个让出点终止（P1） |
| Agent 对话与历史 | `/agents` | 会话选择、新建、删除；实时节点进度、停止、错误可见 | conversation/message PG + flow execution；会话 CRUD 与可选 `conversation_id`，旧客户端回退最新会话 | 6 个定向测试；真实 PG API 创建 2 个会话并 204 删除；owner 404 | 可用 | 是执行状态流，不是 LLM token 流（P1） |
| 模型发现/切换 | 设置、LLM 节点 | `default` 按 ID 去重；自动路由/Mock 文案准确；加载失败区别于空列表并可重试 | OpenClaw→Hermes→Kaiweb→OpenAI→Anthropic；本地路由默认关闭、需显式启用 | 真实 API 仅 default/mock 且无重复 ID；lint/build | 部分可用 | Hermes/OpenClaw 均无推理供应商、其它无真实 LLM 凭据（P0 部署条件） |
| provider 流式/fallback/错误 | `/providers/chat/stream`、设置 | 设置测试为非流式 | SSE delta；多级 fallback；dev Mock 显式标记 | fallback/stream tests | 部分可用 | UI 未消费 token stream；真实 provider 未验证（P1） |
| OpenClaw/Hermes 发现 | 设置、tool 节点 | 清单标记“可调用/仅发现” | manifest + executable 契约；双网关健康 | 3 个清单；Hermes 0.18.2 无工具调用端点 | 可用（诚实） | `data_analysis` 仅发现（P1） |
| 本地工具调用 | 设置工具调用器、画布 tool 节点 | JSON 参数、变量、结果/错误可见 | allowlist + web_fetch SSRF guard 后调用 OpenClaw；仅发现工具不接触网关 | 真实公网接口/工作流 success；loopback 在网关前拒绝 | 部分可用 | 仅 web_fetch 完成真实调用；Hermes 工具待稳定端点（P1） |
| APScheduler CRUD/控制/触发 | `/schedules` | 创建/编辑/暂停/恢复 | PG SQLAlchemyJobStore；暂停失败 503 且不提交假状态 | 自动化错误态；每分钟任务真实触发 success | 可用 | 多实例无 leader/分布式锁（P1/P2） |
| 调度重启持久化 | `/schedules` | next run 可见 | PG JobStore 恢复 | 后端重启后 next run 恢复并再次触发；暂停清空 next run | 可用 | 多实例重复触发风险（P1） |
| PostgreSQL/Redis 记忆 | `/memories` | PG 记忆 UI 可用 | PG CRUD/search/upsert；Redis 只探活 | memory tests；Redis healthy | 部分可用 | Redis TTL 短期会话记忆缺失（P2） |
| 文件工作区/分享 | `/files` | 上传/下载/删除/分享 | MinIO + owner PG + presigned URL | tests；本次 MinIO 实际存储由 KB 链路覆盖 | 部分可用 | 本次未重跑文件分享浏览器 E2E；无版本/撤销（P1/P2） |
| 推送渠道与失败重试 | 设置、notify 节点 | 创建/原地编辑/测试；节点选择渠道；旧配置可清除 | owner-scoped `channel_ids` 解密；PUT 保持 ID；SSRF/DNS pin | 249 tests；真实密文保留/轮换且 flow 引用不变；跨 owner 拦截 | 部分可用 | 无真实外部推送凭据；无持久重试（P1/P2） |
| 系统设置/健康 | `/settings`、`/health` | 依赖状态可见 | PG/Redis/ES/MinIO/OpenClaw/Hermes/reranker 探活 | 前六项真实 ok；embedding error 使 overall degraded | 可用（诚实） | 缺延迟、版本和历史趋势（P2） |
| 导航/空态/错误态/移动端 | 全站 | 响应式主导航和 Agent 选择 | React Router + toast | lint/build；本批次浏览器工具环境阻塞 | 部分可用 | 多页仍有静默 catch；无浏览器 CI（P1） |
| Compose/迁移/部署 | Compose、Makefile | N/A | 透传 environment/debug；prod 拒绝弱 JWT/加密密钥；启动前 Alembic；health gating | config 通过；prod 默认值拒绝测试；真实迁移/head/check；六项依赖健康 | 部分可用 | reranker 下载和镜像 metadata 超时；固定 container_name 阻碍并行（P1/P2） |
| 测试/lint/build/CI | Makefile、GitHub Actions | N/A | pytest/oxlint/tsc/Vite/Compose jobs；health tests 隔离本机服务 | 251 tests；lint/build/Compose config/Alembic check 通过 | 部分可用 | OAuth 缺 `workflow` scope，CI 尚未推送运行；bundle 645 kB；无浏览器 CI（P1） |

## 本轮矩阵变化

1. notify 节点从 DAG 明文凭据改为选择 owner-scoped 加密渠道 ID；新写入拒绝内联配置，旧流程保留可回退兼容。
2. 画布新增 tool 节点，支持清单选择、JSON 变量参数、结构化输出、重试与明确失败；真实 OpenClaw `web_fetch` 工作流通过。
3. 工具清单新增 executable 契约，Hermes `data_analysis` 明确标为“仅发现”，不会误发给 OpenClaw。
4. 新增 GitHub Actions 基线，覆盖后端、前端和 Compose；OAuth token 缺少 `workflow` scope，远端首次运行仍待授权后 push 确认。
5. 今日真实重跑知识库摄取/检索、调度触发/暂停重启和迁移漂移检查；降级依赖均如实标记。
6. 密码哈希从静默截断 72 字节改为版本化 bcrypt-SHA256，保留 legacy 校验并对普通长度旧哈希惰性升级。
7. 推送渠道支持原地编辑和密钥轮换，敏感字段留空保留旧密文，工作流引用 ID 不变。
8. PostgreSQL 注册事务新增 advisory lock，修复不同邮箱并发注册都成为首个 admin 的竞态；健康端点测试不再连接工作站真实服务。
9. OpenClaw 聊天改为默认关闭并在环境示例中显式配置；无上游凭据时不再把合成 agent 别名展示成可用模型，也不会让默认聊天等待失效上游。
10. 修复 PPTX parser 返回值误解包；真实单页 PPTX 先复现 failed，再经同一文档 reparse 恢复并从 ES 命中，DOCX/XLSX 同批全链路通过。
11. 修复 Markdown 返回值顺序和 HTML/EPUB 对未打包 NLTK 数据的硬依赖；三条 failed 记录原地恢复，最终 9 种文档与文本 PDF 全部从 ES 命中独立 marker。
12. 文档列表返回 owner 可见的解析错误摘要，失败项新增原地重试入口并继续状态轮询，不再要求用户删除后重新上传。
13. 统一前后端分块大小边界并拒绝 `chunk_overlap >= chunk_size`，避免步长退化为 1 导致 chunk 数量爆炸。
14. CSV 纳入明确支持并完成真实摄取；无可靠解析器的旧 `.doc/.xls/.ppt` 改为上传阶段 415，不再先返回 201 再后台失败。
15. Compose 透传 `ENVIRONMENT/DEBUG`，生产启动校验覆盖 Compose 的弱 JWT 占位值，避免部署者设置 prod 后应用仍静默运行在 dev。
16. APScheduler 暂停失败不再被吞掉；API 返回 503 并回滚状态，避免 UI 显示 paused 但任务仍继续触发。
17. 知识库列表新增多文件/文件夹导入入口，自动创建知识库、过滤支持格式、逐文件摄取并呈现部分失败；MD 再次通过真实 MinIO→解析→ES 标记检索。
18. 工作流列表新增名称和描述编辑入口，复用 owner-scoped PUT；真实 PostgreSQL API 更新回读一致。
19. Agent 对话从每工作流固定单会话升级为 owner 隔离的多会话列表/创建/切换/删除，首条消息自动命名，并保持旧 API 调用兼容。
20. 模型选择器统一按 ID 去重，修正自动路由文案，并将接口加载失败与真正空模型库区分且支持重试。

## 对标参考（官方资料，检索日期 2026-07-23）

- [RAGFlow README](https://github.com/infiniflow/ragflow) / [DeepDoc](https://ragflow.io/docs/dev)，latest `v0.26.4`（2026-07-07）：借鉴格式化解析、chunk metadata、引用和可解释检索；Klaw 暂不宣称 OCR/多模态。
- [Dify README](https://github.com/langgenius/dify) / [Workflow](https://docs.dify.ai/guides/workflow)，latest `1.16.0`（2026-07-17）：借鉴分支 handle、变量、工具运行结果和错误可见性；Klaw 保持轻量 DAG，不复制实现。
- [LangChain README](https://github.com/langchain-ai/langchain)，latest `langchain-core==1.5.0`（2026-07-21）：借鉴 provider/tool 抽象和流式契约；当前不为抽象而引入框架依赖。
- [LangGraph persistence](https://langchain-ai.github.io/langgraph/concepts/persistence/)，latest `1.2.9`（2026-07-10）：借鉴 checkpoint、恢复、重试与人机协同验收维度；迁移前必须补持久执行和回退测试。

## 遗留优先级

- P0 部署条件：生产必须配置强 JWT/加密密钥、覆盖 MinIO/OpenClaw 开发凭据、真实 1024 维 embedding 和至少一个真实 LLM；当前代码无已知未修 P0。
- P1：真实 LLM/token stream UI；Hermes/其它工具真实调用；在途调用强制中断；多实例调度防重；推送成功链路/重试；浏览器 CI；其余静默错误。
- P2：OCR/多模态、语义分块、Redis TTL 记忆、文件版本、索引备份、checkpoint/评测/可观测、K8s/压测。

## 需用户确认

- HTTP 节点现按安全默认值仅允许解析到公网 IP 的 URL。若产品必须访问企业内网 API，应设计管理员域名/CIDR allowlist，不能启用全局绕过。
- Compose 仍保留固定 `container_name` 以兼容现有运维命令；这会阻碍同机多 project 并行，是否移除需同步部署脚本。
- 旧 notify DAG 目前可继续执行，但再次保存前必须在画布选择已保存渠道或清除旧配置。是否提供管理员批量迁移工具需用户确认；本轮不自动创建渠道或删除旧凭据。

## 参考命令

```bash
cd backend && uv run pytest -q
cd frontend && npm run lint && npm run build
docker compose config -q
cd backend && POSTGRES_URL=... uv run alembic upgrade head && uv run alembic check
```
