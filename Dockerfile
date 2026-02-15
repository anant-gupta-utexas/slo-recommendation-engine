FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv sync

# Copy application code
COPY . .

# Activate virtual environment and set as default
ENV PATH="/app/.venv/bin:$PATH"

# Expose API port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "src.infrastructure.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
