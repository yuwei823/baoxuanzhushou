# Stage 1: resolve a Linux runtime lock with hashes inside the build.
FROM python:3.11-slim AS deps
WORKDIR /build
RUN pip install --no-cache-dir pip-tools==7.6.2
COPY requirements-runtime.in .
RUN pip-compile --generate-hashes --output-file requirements-runtime.lock requirements-runtime.in

# Stage 2: runtime image; published corpus snapshot and vector index are baked in.
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_ROOT=/app
WORKDIR /app
COPY --from=deps /build/requirements-runtime.lock .
RUN pip install --require-hashes -r requirements-runtime.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir setuptools==84.0.0 wheel==0.48.0 \
 && pip install --no-build-isolation --no-deps .
COPY data/corpus ./data/corpus
COPY data/indexes ./data/indexes
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "insurance_audit.api:app", "--host", "0.0.0.0", "--port", "8000"]
