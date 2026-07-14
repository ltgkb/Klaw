# OpenClaw 本地部署

## 概述

OpenClaw 是开源的本地 AI 智能体框架，支持 Skills 扩展，可配置 Kimi 等模型作为底层 LLM。
- 仓库: https://github.com/openclaw/openclaw
- 协议: MIT
- 部署方式: Docker

## 目录说明

- `skills/` — 本地 Skills 定义目录（OpenClaw 启动时扫描加载）
- `config/` — OpenClaw 配置文件（模型配置、API 路由）

## 配置

在 `.env` 中设置：
```
OPENCLAW_IMAGE=openclaw/openclaw:latest
OPENCLAW_LLM_BASE_URL=http://your-llm-endpoint:8000
```

## 验证

```bash
curl http://localhost:8080/health
```
