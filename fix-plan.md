# claw-platform 审计修复分工方案（10 个工作包）

## 全局规则
- 基线：`pytest` 58 passed / `tsc` 通过。修完只能多不能少；每个包附带新测试文件（文件名唯一）。
- **冻结文件（任何人不得改）**：`backend/app/main.py`、`backend/app/api/v1/router.py`、`backend/tests/conftest.py`、`backend/tests/test_m4.py`、`backend/app/schemas/__init__.py`（若必须改，归 WP1）。
- 禁区：不改 `.env`/凭据；不 git 操作；不改 docker-compose 端口；`config.py`、`api.ts` 有 WIP，只做追加式保守改动。
- 独占范围 = 编辑权；import/调用他包模块允许，按下方「跨包契约」对接。
- 清理仓库根垃圾文件 `backend/9b5ad71b2ce5302211f9c61530b329a4922fc6a4` 归 WP10（rm，非 git 操作）。

## 跨包契约（先约定，并行开发依据）
1. **config.py（WP1 独占）新增**：`scheduler_timezone: str = "Asia/Shanghai"`、`minio_public_url: str | None = None`、prod 下默认 jwt/encryption 密钥启动校验。其它包用 `getattr(settings, "minio_public_url", None) or settings.minio_url` 读取，不依赖 WP1 先完成。
2. **HTTP 节点（WP3 后端 / WP8 前端）**：节点 type `"http"`，config = `{method, url, headers: dict, body, timeout_s}`，输出存 context；`node_states` 每条新增 `duration_ms`，被裁剪分支节点补 `{"status": "skipped"}`。
3. **删除 flow 级联（WP3 改 agent_flow_service.py）**：删除前查 ScheduleJob 并逐个调 `scheduler_module.unschedule_flow(str(job.id))`（WP5 保证该函数签名不变）。
4. **api.ts（WP9 独占）新增导出**：`usersApi.list()`、`usersApi.updateRole(id, role)`、`kbApi.listChunks(kbId, page)`、`kbApi.search` 增加 `rerank?: boolean` 参数、轻量 toast 工具 `lib/toast.ts`。WP8 不改 api.ts。

---

## WP1 — 修复_Auth安全基线
- 问题：Auth P1-1（deps.py:41 补 is_active 校验）、P1-2（config.py prod 默认密钥启动拒绝，追加 model_validator，保守不重写）、P1-4（deps.py:38/auth.py:50 畸形 sub→401）、P2-6（user_service IntegrityError→409）、P2-7（security.py bcrypt 72 字节上限）、P2-9（users.py 最后 admin 不可降级）；删 crypto.py:35-54 死代码 EncryptedString；新建 `backend/.env.example`（含 ENCRYPTION_KEY 生成说明）。
- 独占：`app/core/deps.py`、`app/core/security.py`、`app/core/config.py`、`app/utils/crypto.py`、`app/api/v1/endpoints/auth.py`、`app/api/v1/endpoints/users.py`、`app/services/user_service.py`、`app/schemas/auth.py`、`app/schemas/user.py`、`tests/test_auth.py`（仅追加）、`backend/.env.example`（新）、`tests/test_crypto.py`（新）。
- 验收：新增禁用用户 401、畸形 token 401、最后 admin 保护、encrypt/decrypt 往返测试；全套 pytest ≥ 58+新增。

## WP2 — 修复_推送SSRF与误判
- 问题：Push P0-1（push_channels.py:53 只加密敏感字段，chat_id/channel 明文回显）、P0-3（notify_client 分发前接 `common/ssrf_guard.assert_url_is_safe`，创建渠道按 type 校验 host 白名单）、P1-4（飞书/企微成功判定改显式存在性判断 :27/:40）、P1-5（schemas/push_channel.py model_validator 按 type 校验必填）、P2-6（删 get_channel_config_plain 死 stub）、P2-7（Telegram Markdown 失败降级纯文本重发）；notifications.py:42 解密失败→记 warning 跳过该渠道，不当明文发。
- 独占：`app/core/notify_client.py`、`app/api/v1/endpoints/notifications.py`、`app/api/v1/endpoints/push_channels.py`、`app/schemas/push_channel.py`、`app/schemas/notification.py`、`tests/test_notify_client.py`（新）。
- 验收：新增四渠道 payload/成功判定/SSRF 拦截/缺字段 422 测试（mock httpx）；pytest 通过。

## WP3 — 修复_执行引擎与HTTP节点
- 问题：Engine P0-1（:113 节点边界查 cancelled；:199 仅 running 才置 success）、P0-2（:62 启动前查 cancelled）、P1-1（agent_flows.py:230 SSE 校验 execution.flow_id）、P1-2（list/get 执行时惰性 reaper：running/paused 且 updated_at 超 30 分钟置 failed「服务重启中断」，不改 main.py）、P1-3（节点 config `retry`/`retry_interval` 指数退避）、P1-4（retrieval 节点校验 KB.owner==flow.owner）、P2-2（暂停超 24h 自动 cancelled）、P2-6（裁剪分支补 skipped）、附带（agent_chat.py:138 持任务引用+logger.exception）；契约2 HTTP 节点 + duration_ms；契约3 删 flow 级联 unschedule。
- 独占：`app/services/execution_service.py`、`app/services/agent_flow_service.py`、`app/api/v1/endpoints/agent_flows.py`、`app/api/v1/endpoints/agent_chat.py`、`tests/test_agent_flows.py`（仅追加）、`tests/test_execution_engine.py`（新）、`tests/test_execution_control.py`（新）、`tests/test_agent_chat.py`（新）。
- 验收：cancel-while-running、pending 期 cancel、SSE 越权 403、节点重试、环检测、多 case 裁剪、HTTP 节点（mock httpx）测试；pytest 通过。

## WP4 — 修复_LLM供应商层
- 问题：LLM P1-1（流式 started 标志，已 yield 后失败不降级）、P1-2（流式补 reasoning_content + 0 字节视为失败继续降级）、P1-3（新增 `app/core/llm_config.py` 仿 embedding_config 做 Key DB 热更新，chat() 先读缓存回落 settings；system_settings.py 加 PUT/GET llm-config）、P2-4（每级 5xx/连接错 1 次 0.5s 退避重试）、P2-6（embedding-config 加 `clear_key` 字段）、P2-3（docstring 优先级注释同步）；Auth P1-3（system_settings 两个 PUT 加 require_roles("admin")）、Auth 附带（providers.py:25/:97 的 GET /providers、/models 补 CurrentUser）；llm_client.py:120 解密失败按未配置处理+日志。
- 独占：`app/core/llm_client.py`、`app/core/embedding_config.py`、`app/core/llm_config.py`（新）、`app/api/v1/endpoints/providers.py`、`app/api/v1/endpoints/system_settings.py`、`app/schemas/provider.py`、`app/schemas/system.py`、`tests/test_llm_fallback.py`（新）、`tests/test_system_settings.py`（新）。
- 验收：降级顺序/流式去重/热更新/admin 403/解密失败兜底测试；pytest 通过。

## WP5 — 修复_定时任务
- 问题：Cron P1-1（schemas/schedule.py cron field_validator 5 段+CronTrigger 试解析→422；schedule_flow 失败回滚已建行）、P1-2（schedules.py:111 补 changed=True）、P1-3（恢复分支改用 schedule_flow 重建 job）、P1-5（init_scheduler 加 job_defaults misfire_grace_time=3600/coalesce=True/max_instances=1）、P2-6（列表/详情用 get_next_run_time 实时覆盖）、P2-7（next_run 为 None 返回 503）、P2-8（时区读契约1 的 settings.scheduler_timezone）；保证 unschedule_flow 签名不变（契约3）。
- 独占：`app/core/scheduler.py`、`app/api/v1/endpoints/schedules.py`、`app/schemas/schedule.py`、`tests/test_scheduler_callback.py`（新）。
- 验收：非法 cron 422 无孤儿行、改 input 生效、paused 改 cron 恢复用新 cron、回调创建 Execution 测试（mock run_flow）；pytest 通过。

## WP6 — 修复_文件记忆与本地工具
- 问题：MemFile P0-1（files.py:82 Content-Disposition 改 RFC5987 quote 编码）、P1-2（minio_client 带缓存 ensure_bucket 请求时重试；端点 S3Error→503）、P1-3（tool call 4xx/5xx 返回 success=False+error；仅连接异常且 dev 才 mock；call 前校验 tool_id 存在）、P1-4（share URL 按契约1 替换 public host）、P2-5（memory 表加 UniqueConstraint + alembic 迁移 + IntegrityError 转 update）、P2-6（ilike 转义 %_）、P2-7（删文件失败 logger.warning）、P2-8（MinIO 同步调用 to_thread 包装）、P2-11（hermes 健康 <400）；删 SKILLS_DIRS 死代码。
- 独占：`app/api/v1/endpoints/files.py`、`app/api/v1/endpoints/memories.py`、`app/api/v1/endpoints/local_agent.py`、`app/core/minio_client.py`、`app/services/memory_service.py`、`app/services/local_agent_service.py`、`app/models/memory.py`、`app/schemas/memory.py`、`app/schemas/file.py`、`app/schemas/local_agent.py`、`backend/alembic/`（迁移目录）、`tests/test_new_apis.py`（仅追加）。
- 验收：中文文件名下载、MinIO 故障 503、工具失败不伪装成功、记忆 upsert 并发测试；pytest 通过。

## WP7 — 修复_知识库检索链路
- 问题：KB P1-1（tei_client embed 校验维度==settings.embedding_dim 不符即 raise；es_client bulk 解析 error 并 raise；parse_and_index 数不符置 failed 存 error）、P1-2（index_chunks_bulk 开头 ensure_kb_index；hybrid_search 捕获 NotFound 补偿重试一次；search 包 try→503）、P1-3（download/parse/upload 同步调用 to_thread 包装）、P2-4（_embed_via_api 分批 64 + 数量不符 raise 降级）、P2-5（kb.py 加 POST /documents/{id}/reparse；失败原因写 parse_result）、P2-8（上传校验扩展名→415）、附带3（num_candidates=max(200, top_k*10)）、P2-6（_split_and_append 改 token 切片，common/token_utils.py 加 slice_tokens）。
- 独占：`app/services/document_service.py`、`app/services/kb_service.py`、`app/services/deepdoc_service.py`、`app/core/es_client.py`、`app/core/tei_client.py`、`app/core/reranker_client.py`、`app/api/v1/endpoints/kb.py`、`app/schemas/knowledge_base.py`、`backend/common/token_utils.py`（无则新建）、`tests/test_kb.py`（仅追加）、`tests/test_retrieval_unit.py`（新）。
- 验收：维度不符置 failed、索引缺失自愈、tei fallback 链、reparse 端点、非法扩展名 415 测试；pytest 通过。

## WP8 — 修复_前端画布与对话
- 问题：FE P0-1（FlowCanvas.tsx:268/:380 三处 edge 序列化补 sourceHandle/targetHandle；edge id 改 `e-{source}:{sourceHandle}-{target}`）、P1-2（AgentChat.tsx selectedId 变化 clearTimeout+setThinking(false)，poll 内校验 flowId）、P1-4（AgentChat 选中态头部加返回 /flows Link）、P2-6（FlowCanvas/AgentChat 改 h-screen）、P2-8（ExecutionDetail running 态 3s 轮询）、P2-9（pollExecution 加 mounted ref）；契约2：NodeToolbox/NodeConfigPanel 加 http 节点表单项（method/url/headers/body/timeout）、节点状态渲染 duration_ms 与 skipped。
- 独占：`frontend/src/pages/FlowCanvas.tsx`、`frontend/src/pages/AgentChat.tsx`、`frontend/src/pages/ExecutionDetail.tsx`、`frontend/src/pages/FlowList.tsx`、`frontend/src/components/flow/`（3 个文件）。
- 验收：`npx tsc --noEmit` 通过；保存→重载画布 sourceHandle 保留；切换 Agent 不串台（人工验证步骤写明）。

## WP9 — 修复_前端补全与错误处理
- 问题：FE P1-3（新建 `lib/toast.ts` 轻量提示，api.ts 拦截器非 401 统一报错 toast，保守改 WIP 文件）、P1-5（新建 pages/Files.tsx 列表/上传/下载/删除/复制 share 链接；App.tsx 加路由、AppLayout 加入口）、Auth P2-5（api.ts:78 续期失败逐个 reject 队列）、Auth 功能缺失（新建 pages/UserManagement.tsx 用契约4 usersApi）、KB P2-9（KBDetail 加 chunk 分页面板 + rerank checkbox，SearchHit 补 rerank_score）、Settings（notify 测试发送 + local-agent 健康 UI、Promise.allSettled、删除渠道 confirm）；Login 错误区分（P2-12）、KBDetail hasSearched（P2-11）、flow 列表 pageSize=100（P2-13）、Register 二次密码确认。
- 独占：`frontend/src/lib/api.ts`、`frontend/src/lib/toast.ts`（新）、`frontend/src/App.tsx`、`frontend/src/components/layout/AppLayout.tsx`、`frontend/src/pages/Files.tsx`（新）、`frontend/src/pages/UserManagement.tsx`（新）、`frontend/src/pages/Settings.tsx`、`frontend/src/pages/KBDetail.tsx`、`frontend/src/pages/Login.tsx`、`frontend/src/pages/Register.tsx`、`frontend/src/pages/Dashboard.tsx`、`frontend/src/pages/ScheduleList.tsx`、`frontend/src/pages/MemoryList.tsx`、`frontend/src/pages/KnowledgeBase.tsx`、`frontend/src/store/auth.ts`。
- 验收：`npx tsc --noEmit` 通过；新页面可路由可达；请求失败有可见提示。

## WP10 — 修复_测试脚本与仓库卫生
- 问题：Test P1-9（pyproject.toml 加 `[dependency-groups] eval = ["sentence-transformers>=2.2"]`，eval_real_vector.py docstring 改 `uv run --group eval`）、P1-10（eval_retrieval.py 删 :193-194 死分支、凭据改 EVAL_EMAIL/EVAL_PWD 环境变量、检索异常计数非零 exit 1）、P2-11（新增 test_negative_cases.py：非 admin 查他人 403、空/超大文件、坏 refresh 401、下载他人文件 404）、P2-12（新增 test_health.py：单点故障→degraded）；删除仓库根垃圾文件 `backend/9b5ad71b2ce5302211f9c61530b329a4922fc6a4`（rm，非 git）。
- 独占：`backend/scripts/eval_retrieval.py`、`backend/scripts/eval_real_vector.py`、`backend/pyproject.toml`、`tests/test_negative_cases.py`（新）、`tests/test_health.py`（新）。
- 验收：全套 pytest ≥ 58+新增；eval 脚本 dry-run 可启动（无 NameError）。

## 依赖与排序建议
- 无硬依赖，10 包可全并行；WP8/WP9 的 tsc 建议最后各跑一次全量。
- 集成关口：全部合并后跑 `cd backend && uv run pytest -q`（≥58+新增）与 `cd frontend && npx tsc --noEmit`。
- 冲突兜底：若两包同改一个未列出文件，以本方案独占表仲裁，违规改动回退。
