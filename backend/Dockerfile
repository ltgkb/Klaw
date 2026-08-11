# 后端 Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖 (gcc 用于编译 C 扩展, libgompang/openblas 用于 numpy/xgboost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先拷依赖文件，利用缓存层
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# 拷贝源码
COPY . .

EXPOSE 8000

# Apply committed migrations before accepting traffic. A migration failure keeps
# the container unhealthy instead of serving requests against a stale schema.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
