# 后端 Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先拷依赖文件，利用缓存层
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# 拷贝源码
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
