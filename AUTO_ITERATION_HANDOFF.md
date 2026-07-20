# Klaw 设备迁移与全流程验收交接

> 最后更新：2026-07-20（Asia/Shanghai）  
> 仓库：<https://github.com/ltgkb/Klaw>  
> 工作分支：`codex/full-flow-hardening-20260720`  
> 核心加固提交：`91ec12b3825363647ea740282ce7af57a873bc05`

## 新设备上的第一条指令

在新设备打开本仓库后，把下面这句话发给 Codex：

```text
请完整阅读 AUTO_ITERATION_HANDOFF.md，从“继续执行顺序”开始接手。先检查当前分支和提交，不要修改 main；完成重排模型、整套 Compose、后端健康检查和浏览器全流程验收，发现问题直接修复、测试、提交并推送到当前分支。
```

## 目标与边界

目标是把 Klaw 的认证、知识库、Agent Flow、定时任务、通知、OpenClaw、Hermes、Embedding 和 Reranker 全流程验证到可用状态。

- 所有后续修改继续放在 `codex/full-flow-hardening-20260720`。
- 不直接修改或推送 `main`，不使用 force push。
- 不提交 `.env`、真实 API Key、Token、数据库数据或模型缓存。
- 当前分支可以提交和推送；最终通过后再创建或更新 Pull Request。

## 新设备准备

推荐环境：

- Docker Desktop，分配内存建议 `>= 12 GB`，磁盘可用空间建议 `>= 25 GB`。
- Apple Silicon 需要启用 amd64/x86_64 容器模拟；Compose 已为 TEI 指定 `linux/amd64`。
- Git、Node.js、npm、Python 3.12、`uv`、`curl`、`jq`。
- 首次启动需要下载约 2GB 的 BGE-M3 和约 500MB 的多语言 reranker，慢网下可能超过 30 分钟。

```bash
git clone https://github.com/ltgkb/Klaw.git
cd Klaw
git fetch origin
git switch --track origin/codex/full-flow-hardening-20260720
git status --short --branch
git log -2 --oneline --decorate
```

如果仓库已经存在：

```bash
git fetch origin
git switch codex/full-flow-hardening-20260720
git pull --ff-only
```

工作树应为空，历史中应包含 `91ec12b`。不要把其他设备上的未提交 WIP 带进此分支。

## 环境变量

```bash
cp .env.example .env
openssl rand -hex 32  # JWT_SECRET_KEY
openssl rand -hex 32  # ENCRYPTION_KEY
openssl rand -hex 24  # OPENCLAW_GATEWAY_TOKEN
openssl rand -hex 24  # HERMES_API_SERVER_KEY
```

把生成值写进 `.env`，并补充以下配置。生产或联网验收时不要使用示例值：

```dotenv
JWT_SECRET_KEY=<随机值>
ENCRYPTION_KEY=<64位十六进制随机值>
OPENCLAW_GATEWAY_TOKEN=<随机值>
HERMES_API_SERVER_KEY=<随机值>

TEI_MODEL_ID=BAAI/bge-m3
TEI_MAX_BATCH_TOKENS=512
RERANKER_MODEL_ID=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
RERANKER_DTYPE=float32
RERANKER_MAX_BATCH_TOKENS=512

# 至少配置一个真实 LLM 供应商，才能验收真实对话和 LLM 节点。
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
KAIWEB_API_KEY=
```

CPU 版 TEI 的 ONNX 后端不支持 `RERANKER_DTYPE=float16`，不要在当前部署中改成 float16。

## 已完成改动

核心加固提交 `91ec12b` 包含：

- 修复 Flow 执行和 SSE 流的跨用户越权访问。
- 修复长任务取消后被覆盖成成功状态的问题。
- DeepDoc、MinIO、tokenizer、文件和知识库删除等阻塞工作移出事件循环。
- DeepDoc 解析器改为懒加载，TXT 冷解析从约 2.58 秒降到约 0.37 秒。
- 修复 Alembic 在未设置 `PYTHONPATH` 时的导入。
- 加固 cron 校验、重新调度、暂停/恢复、下一次执行时间和回调异常处理。
- 修复通知成功判定、错误信息和密钥泄漏风险。
- 修复空 LLM 流、流式失败后的重复输出、Kaiweb 超时和 OpenClaw 模型路由。
- OpenClaw 改用 `/v1/models`、`/tools/invoke`、`/readyz`，修正数据目录权限和 Chat Completions。
- Hermes API Server 使用容器端口 `8642`、宿主机端口 `8081`。
- 健康检查要求真实 HTTP 200；基础设施宿主端口限制到 `127.0.0.1`。
- TEI 升级到 `cpu-1.9`，模型缓存改为持久卷，并加入 8GB 环境的批量和内存限制。
- 新增针对权限、取消、调度、知识库、DeepDoc 和 LLM 回退的回归测试。

## 已完成验证

在旧设备上已经通过：

- 后端：`70 passed`。
- 前端 lint：成功，仅有 3 条原有 Fast Refresh warning。
- 前端 build：成功，仅有 bundle 大于 500kB 的 warning。
- Alembic：`4b2e9a1c7d33 (head)`，只有一个 head。
- `docker compose config -q`：成功。
- `git diff --check`：成功。
- 跨用户访问执行记录返回 404。
- 35 秒底层调用结束后，取消状态仍保持 `cancelled`。
- 定时 Flow 能执行并保存下一次时间，暂停后清空下一次时间。
- OpenClaw 模型列表和工具调用返回真实 JSON。
- Hermes `/health` 和带认证的 `/v1/models` 可访问。
- BGE-M3 返回 1024 维向量。
- 文件上传、解析、Embedding、Elasticsearch 搜索和旧 reranker 的链路曾完整跑通。
- TXT 懒加载解析低于 1 秒，同时请求延迟约 3ms。

## 当前唯一未完成的基础设施验收

旧设备只有约 7.75GB Docker 内存，测试发现：

1. `BAAI/bge-reranker-v2-m3` 会引发整套环境 OOM。
2. `BAAI/bge-reranker-base` 的 1.1GB ONNX 在 4GB 容器上限内加载失败。
3. CPU TEI 指定 float16 会先拒绝 ONNX，再回退下载 safetensors，不能作为默认配置。
4. 默认模型已改为 TEI 官方兼容的多语言 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`，覆盖中文和英文，ONNX 约 471MB。
5. 该默认模型尚未完成首次健康与真实 `/rerank` 验证。旧设备当时访问 Hugging Face 只有约 8-16KB/s，因此主动停止下载并迁移设备；这不是已知代码错误。

新设备第一优先级是完成这一项，不要再次切回 BGE reranker，除非 Docker 内存充足并同步提高 `reranker.mem_limit`。

## 继续执行顺序

### 1. 静态与单元检查

```bash
cd backend
uv sync --dev
uv run pytest -q
uv run alembic heads

cd ../frontend
npm ci
npm run lint
npm run build

cd ..
docker compose config -q
git diff --check
```

预期：70 项后端测试通过；前端只有已知 warning；Alembic 只有 `4b2e9a1c7d33 (head)`。

### 2. 分阶段启动基础设施和模型

```bash
docker compose up -d postgres redis elasticsearch minio openclaw hermes
docker compose up -d tei reranker
docker compose ps
```

持续观察模型首次下载和加载：

```bash
docker compose logs -f tei reranker
```

另开终端观察资源和重启：

```bash
docker stats --no-stream claw-tei claw-reranker claw-es claw-openclaw claw-hermes
docker inspect claw-reranker --format '{{.State.Health.Status}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}'
```

通过标准：`claw-tei` 和 `claw-reranker` 均为 `healthy`，`RestartCount=0`，`OOMKilled=false`。首次下载慢时继续等，不要因健康状态仍是 `starting` 就删除持久卷。

### 3. 验证模型真实推理

```bash
curl -fsS http://127.0.0.1:8082/health
curl -fsS http://127.0.0.1:8083/health

curl -fsS http://127.0.0.1:8082/embed \
  -H 'Content-Type: application/json' \
  -d '{"inputs":"Klaw knowledge base"}' \
  | jq '.[0] | length'

curl -fsS http://127.0.0.1:8083/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"如何创建知识库？","texts":["创建知识库后上传文档并等待解析。","今天天气很好。","Create a knowledge base and upload documents."],"return_text":true}' \
  | jq .
```

通过标准：Embedding 维度为 `1024`；rerank 返回 3 项、包含 `index` 和 `score`，知识库相关文本排在天气文本之前。

### 4. 启动应用层并检查整套健康

```bash
docker compose up -d --build backend frontend
docker compose ps
curl -fsS http://127.0.0.1:8000/api/v1/health | jq .
```

通过标准：返回 `status: healthy`，`postgres`、`redis`、`elasticsearch`、`minio`、`openclaw`、`hermes`、`tei`、`reranker` 全部为 `ok`。

额外检查：

```bash
curl -fsS http://127.0.0.1:8080/readyz
curl -fsS http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" | jq .
curl -fsS http://127.0.0.1:8081/health | jq .
curl -fsS http://127.0.0.1:8081/v1/models \
  -H "Authorization: Bearer $HERMES_API_SERVER_KEY" | jq .
```

如果 shell 中没有导出 `.env` 的变量，先执行 `set -a; source .env; set +a`。

### 5. 浏览器全流程

打开 <http://127.0.0.1:3000>，至少完成：

- 注册、登录、刷新页面后保持登录。
- 创建知识库，上传 TXT 和 PDF，等待解析完成，查看 chunks。
- 使用中文和英文查询，分别测试关闭和开启 rerank 的搜索结果。
- 创建 Agent Flow，保存、执行、查看 SSE 日志、取消长任务。
- 创建下一分钟触发的 cron，确认执行记录和下一次时间，再暂停、恢复、删除。
- 查看供应商、OpenClaw/Hermes 健康和本地工具列表。
- 配置真实 LLM Key 后，验证普通聊天、流式聊天和 Flow 中的 LLM 节点。
- 配置一个真实通知渠道后，验证成功和失败提示，确认页面及日志不显示密钥。

旧设备的浏览器自动化插件报过 `Cannot redefine property: process`，因此浏览器点击验收未完成。新设备优先使用正常浏览器手测；如果 Playwright 可用，再补自动化截图和 console/network error 检查。

### 6. 最终收尾

```bash
git status --short --branch
git diff --check
cd backend && uv run pytest -q
cd ../frontend && npm run lint && npm run build
cd ..
docker compose ps
curl -fsS http://127.0.0.1:8000/api/v1/health | jq .
```

修复中新增的行为必须补回归测试。全部通过后提交并推送：

```bash
git add <相关文件>
git commit -m "fix: complete full-stack runtime verification"
git push origin codex/full-flow-hardening-20260720
```

Pull Request：<https://github.com/ltgkb/Klaw/pull/new/codex/full-flow-hardening-20260720>

## 外部条件与非代码故障

以下功能没有相应外部配置时不能宣称“真实可用”：

- OpenAI、Anthropic、Kaiweb 或其他本地模型的有效凭据。
- Hermes 的 Telegram、Discord、Slack 等消息渠道凭据与 allowlist。
- 生产环境强随机 JWT、Encryption、OpenClaw 和 Hermes 密钥。
- 扫描 PDF 的 OCR/视觉模型资产。

没有凭据时仍应验证错误提示、超时、回退和密钥脱敏，不能把外部鉴权失败当作平台代码通过。

## 定时自动迭代

Codex 中已有每日任务 `2-claw-platform`，计划时间为北京时间每天 `02:03`。换设备后先在 Codex Automations 中确认它是否同步并处于启用状态；不要直接重复创建同名任务。若未同步，再根据用户要求重建。

## 旧设备状态

- 原仓库 `/Users/kunkundawang/ZCodeProject/claw-platform` 中用户自己的 WIP 未被修改或提交。
- 加固工作树为 `/Users/kunkundawang/ZCodeProject/claw-platform-hardening`。
- 旧设备上的 reranker 已主动停止，避免继续慢速下载；其他容器可能仍在运行。
- 本交接以远端分支为准，新设备不需要旧设备的 Docker volumes 或数据库测试数据。
