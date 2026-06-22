FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy UV from UV image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy application code
COPY . .

# Install dependencies
RUN uv sync --no-dev

# Copy and set entrypoint script permissions
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 --home /home/appuser appuser && \
    mkdir -p /home/appuser/.cache/uv && \
    chown -R appuser:appgroup /home/appuser && \
    chown -R appuser:appgroup /app /entrypoint.sh

# Switch to non-root user
USER appuser

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/home/appuser/.cache/uv

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
