# ============================================================
# Stage 1: 构建前端
# ============================================================
#FROM node:22-slim AS frontend-builder
#
#WORKDIR /build/frontend
#
## 启用 corepack；pnpm 版本由 frontend/package.json 的 packageManager 字段固定
## 关闭交互式下载确认，否则 docker build 这种非 TTY 环境会卡在
## "Corepack is about to download ..." 直到超时
#ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
#RUN corepack enable
#
## 先复制依赖文件，利用缓存（corepack 按 packageManager 字段自动下载对应 pnpm）
#COPY frontend/package.json frontend/pnpm-lock.yaml ./
#RUN pnpm install --frozen-lockfile
#
## 复制前端源码并构建
#COPY frontend/ ./
#RUN pnpm build

# ============================================================
# Stage 2: 生产镜像
# ============================================================
FROM python:3.12-slim AS production

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    bubblewrap \
    socat \
    jq \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 升级基础镜像预装的 pip：依赖全部由 uv 安装、运行时不调用 pip，
# 但 python:3.12-slim 自带的旧 pip 会被镜像扫描器报 CVE，升级以清除这些告警
RUN python -m pip install --no-cache-dir --upgrade pip

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 禁用 Python 输出缓冲，确保日志实时输出到 Docker logs
ENV PYTHONUNBUFFERED=1

# 默认时区，可由 docker-compose / 运行时 -e TZ=... 覆盖
ENV TZ=Asia/Shanghai

ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ENV UV_EXTRA_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 先复制依赖和包元数据文件，利用缓存
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --no-install-project

# 复制应用代码
COPY lib/ lib/
COPY server/ server/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
COPY agent_runtime_profile/ agent_runtime_profile/
COPY public/ public/

# 复制前端构建产物
#COPY --from=frontend-builder /build/frontend/dist/ frontend/dist/

# 创建运行时目录
RUN mkdir -p projects vertex_keys

# 暴露端口
EXPOSE 1241

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:1241/health || exit 1

# 启动命令：先跑 alembic 迁移(自动对齐 schema),再起 uvicorn。
# 用 sh -c 串起来: 迁移失败时输出错误但仍尝试起 uvicorn,避免迁移 bug 把整个容器拉黑。
CMD ["sh", "-c", "echo '[entrypoint] running alembic upgrade head' && uv run alembic upgrade head || echo '[entrypoint] WARNING: alembic upgrade head failed, continuing'; echo '[entrypoint] starting uvicorn'; uv run uvicorn server.app:app --host 0.0.0.0 --port 1241"]
