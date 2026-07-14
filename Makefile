# Makefile — 常用命令快捷入口

.PHONY: help install dev test build up down logs ps backend-frontend

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装前后端依赖
	cd backend && uv sync
	cd frontend && npm install

dev: ## 本地开发模式 (前后端分别启动, 需先启动基础设施)
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
	cd frontend && npm run dev

test: ## 运行后端测试
	cd backend && uv run pytest -v

build: ## 构建前端
	cd frontend && npm run build

up: ## 启动全栈 (Docker Compose)
	docker compose up -d

down: ## 停止全栈
	docker compose down

logs: ## 查看日志
	docker compose logs -f

ps: ## 查看服务状态
	docker compose ps

db-migrate: ## 执行数据库迁移
	cd backend && uv run alembic upgrade head

db-revision: ## 生成迁移脚本 (用法: make db-revision m="message")
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
