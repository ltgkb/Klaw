# OpenClaw 本地部署

## 概述

OpenClaw 是开源的本地 AI 智能体框架，支持 Skills 扩展和 OpenAI 兼容接口。
- 仓库: https://github.com/openclaw/openclaw
- 协议: MIT
- 部署方式: Docker

## 目录说明

- `skills/` — 平台展示的本地工具清单，也挂载到 OpenClaw workspace
- `openclaw.json` — 启动时合并的基础配置，开启 Chat Completions，并把 Kaiweb GLM-4.5 配为默认聊天模型

## 配置

在 `.env` 中设置：
```
OPENCLAW_IMAGE=openclaw/openclaw:latest
OPENCLAW_GATEWAY_TOKEN=replace-with-a-random-secret
KAIWEB_API_KEY=your-kaiweb-key
KAIWEB_MODEL=glm-4.5
```

`Klaw -> OpenClaw -> Kaiweb GLM-4.5` 是默认聊天链路；Klaw 仅在 OpenClaw
不可用时直连 Kaiweb fallback。Compose 会保留持久卷里的已有配置，并在启动时
合并仓库配置，不覆盖已有渠道和其他用户配置。

## 验证

```bash
curl http://localhost:8080/readyz
curl http://localhost:8080/v1/models \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN"

curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"openclaw/default","messages":[{"role":"user","content":"Reply with OK"}]}'
```
