# Hermes 本地部署

## 概述

Hermes 是智能体框架，支持自定义 Skill 开发，本地部署。
- 仓库: https://github.com/NousResearch/hermes-agent
  (注: PRD 附录原写的 `github.com/modelcontextprotocol/servers` 是错误的，那是通用 MCP servers 仓库)
- 协议: MIT
- 部署方式: Docker

## 目录说明

- `skills/` — Hermes Skill 定义目录
- `config/` — Hermes 配置文件

## 配置

在 `.env` 中设置：
```
HERMES_IMAGE=nousresearch/hermes-agent:latest
HERMES_LLM_BASE_URL=http://your-llm-endpoint:8000
```

## 验证

```bash
curl http://localhost:8081/health
```
