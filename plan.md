# 全功能可用性检查 + 补全迭代计划

> 日期：2026-07-21 · 参考：ragflow / dify / langchain
> 基线：backend 58 tests passed；frontend tsc 通过；git main @ c962cb7（有用户 WIP：config.py / api.ts / .gitignore，不得覆盖）

## Stage 1 — 可用性体检（explore 只读子代理 ×10，并行）
按模块分区审查，输出：每功能状态（可用/部分/缺失/BUG）+ 证据（file:line）+ 修复建议优先级。
1. Auth_审计：认证/用户/RBAC/refresh token
2. KB_审计：知识库全链路（上传→DeepDoc解析→分块→向量化→ES索引→混合检索→rerank）
3. Engine_审计：DAG 执行引擎/SSE/暂停恢复取消/条件分支/变量注入
4. LLM_审计：模型供应商层（Kaiweb/OpenAI/Anthropic/Mock、流式、embedding、reranker）
5. Cron_审计：APScheduler 定时任务
6. Push_审计：推送渠道/通知/加密脱敏
7. MemFile_审计：记忆/文件工作区/本地工具发现
8. FE_审计：前端页面与后端 API 对接完整性（含 agent_chat、死按钮、缺页面）
9. Test_审计：测试覆盖缺口（58 项测试 vs 全部端点/服务）
10. Benchmark_对标：ragflow/dify/langchain 功能对标差距清单（联网）

## Stage 2 — 修复补全（coder 子代理，按文件范围分区避免冲突）
汇总 Stage 1 结果后按优先级分派；禁区：不提交 git、不动 .env/凭据、不改用户 WIP 语义。

## Stage 3 — 验证
pytest 全量 + tsc 全量 + 抽样端点冒烟；输出报告。
