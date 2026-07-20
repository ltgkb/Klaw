# OpenClaw 本地部署

## 概述

OpenClaw 是开源的本地 AI 智能体框架，支持 Skills 扩展和 OpenAI 兼容接口。
- 仓库: https://github.com/openclaw/openclaw
- 协议: MIT
- 部署方式: Docker

## 目录说明

- `skills/` — 平台展示的本地工具清单，也挂载到 OpenClaw workspace
- `openclaw.json` — 首次启动的基础配置，显式开启 Chat Completions API

## 配置

在 `.env` 中设置：
```
OPENCLAW_IMAGE=openclaw/openclaw:latest
OPENCLAW_GATEWAY_TOKEN=replace-with-a-random-secret
OPENAI_API_KEY=your-provider-key
```

也可使用 `ANTHROPIC_API_KEY`，或进入 OpenClaw 完成其他模型供应商配置。
Compose 会保留持久卷里的已有配置，并在启动时合并启用
`gateway.http.endpoints.chatCompletions.enabled`。

## 验证

```bash
curl http://localhost:8080/readyz
curl http://localhost:8080/v1/models \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN"
```
