#!/bin/sh
set -e

# Only run migrations if this is the main API server (not celery worker/beat)
if echo "$@" | grep -q "uvicorn"; then
    echo "Running database migrations..."
    uv run alembic upgrade head
fi

echo "Starting application..."
exec "$@"
