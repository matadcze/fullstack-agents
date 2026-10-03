"""Real API/CORS server for Playwright, with isolated SQLite and in-memory Redis."""

import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn

from src.api.app import create_app
from src.api.middleware import RateLimitMiddleware
from src.infrastructure.auth.rate_limiter import AuthRateLimiter
from src.infrastructure.database.session import Base, engine
from src.infrastructure.dependencies import get_rate_limiter
from tests.conftest import FakeRedis


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await engine.dispose()


async def no_global_redis(self):
    raise ConnectionError("Redis is not available in tests")


if __name__ == "__main__":
    limiter = AuthRateLimiter(redis_url="redis://unused")
    limiter._redis_client = FakeRedis()
    with pytest.MonkeyPatch.context() as patches, socket.socket() as listener:
        patches.setattr("src.api.v1.auth.get_auth_rate_limiter", lambda: limiter)
        patches.setattr(RateLimitMiddleware, "get_redis_client", no_global_redis)
        app = create_app()
        app.router.lifespan_context = lifespan
        app.dependency_overrides[get_rate_limiter] = lambda: limiter
        listener.bind(("127.0.0.1", 0))
        print(f"CORS_TEST_API_URL=http://127.0.0.1:{listener.getsockname()[1]}", flush=True)
        uvicorn.Server(uvicorn.Config(app, log_level="error")).run(sockets=[listener])
