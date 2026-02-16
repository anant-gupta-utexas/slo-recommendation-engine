# Multi-stage build for SLO Recommendation Engine
# Stage 1: Base image with dependencies
FROM python:3.13-slim AS base

WORKDIR /app

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv sync --no-dev

# Activate virtual environment and set as default
ENV PATH="/app/.venv/bin:$PATH"

# Stage 2: API service (FastAPI)
FROM base AS api

# Copy application code
COPY . .

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health')"

# Run API server
CMD ["python", "-m", "uvicorn", "src.infrastructure.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: Worker service (Background tasks - future use)
# Note: Current implementation runs scheduler in API process
# Uncomment and customize if splitting into separate worker process
# FROM base AS worker
# COPY . .
# CMD ["python", "-m", "src.infrastructure.tasks.worker"]
