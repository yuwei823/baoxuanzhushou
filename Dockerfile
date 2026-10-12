# syntax=docker/dockerfile:1

# Stage 1: resolve a Linux runtime lock with hashes inside the build.
FROM python:3.11-slim AS deps
WORKDIR /build

# 复制你的 pip.conf（uv 会自动兼容里面的阿里云镜像源配置）
COPY pip.conf /etc/pip.conf

# 1. 安装新一代极其高效的 uv 包管理工具
RUN pip install --no-cache-dir uv==0.5.21

COPY requirements-runtime.in .

# 2. 挂载专属于 uv 的缓存目录，使用 uv 秒速生成带哈希的锁文件
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip compile --generate-hashes --output-file requirements-runtime.lock requirements-runtime.in

# Stage 2: runtime image; published corpus snapshot and vector index are baked in.
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_ROOT=/app
WORKDIR /app
COPY pip.conf /etc/pip.conf
COPY --from=deps /build/requirements-runtime.lock .
RUN pip install --require-hashes -r requirements-runtime.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir setuptools==84.0.0 wheel==0.48.0 \
 && pip install --no-build-isolation --no-deps .
COPY data/corpus ./data/corpus
COPY data/indexes ./data/indexes
COPY data/sources ./data/sources
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "insurance_audit.api:app", "--host", "0.0.0.0", "--port", "8000"]
