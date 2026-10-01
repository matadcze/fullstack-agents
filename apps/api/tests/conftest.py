"""Shared fixtures for HTTP-level API tests.

Each test gets an isolated SQLite database, an in-memory stand-in for Redis that backs the
real ``AuthRateLimiter`` (so lockout and per-route limits are exercised), and an async HTTP
client bound to a fresh app instance.
"""

import os
import time
from dataclasses import dataclass
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "changeme-in-tests")

import httpx2  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.api.app import create_app  # noqa: E402
from src.api.middleware import RateLimitMiddleware  # noqa: E402
from src.infrastructure.auth.rate_limiter import AuthRateLimiter  # noqa: E402
from src.infrastructure.database.session import Base, get_db  # noqa: E402
from src.infrastructure.dependencies import get_rate_limiter  # noqa: E402

DEFAULT_PASSWORD = "CorrectHorse1!"


class FakeRedis:
    """Implements the subset of redis.asyncio used by AuthRateLimiter."""

    def __init__(self):
        self.values: dict[str, object] = {}
        self.expiries: dict[str, float] = {}

    def _purge(self, key):
        if key in self.expiries and self.expiries[key] <= time.time():
            self.values.pop(key, None)
            self.expiries.pop(key, None)

    async def incr(self, key):
        self._purge(key)
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    async def expire(self, key, seconds):
        if key in self.values:
            self.expiries[key] = time.time() + seconds

    async def setex(self, key, seconds, value):
        self.values[key] = value
        self.expiries[key] = time.time() + seconds

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expiries.pop(key, None)

    async def ttl(self, key):
        self._purge(key)
        if key not in self.values:
            return -2
        if key not in self.expiries:
            return -1
        return max(0, int(self.expiries[key] - time.time()))

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.ops = []

    def zremrangebyscore(self, key, low, high):
        self.ops.append(("zrem", key, low, high))

    def zcard(self, key):
        self.ops.append(("zcard", key))

    def zadd(self, key, mapping):
        self.ops.append(("zadd", key, mapping))

    def expire(self, key, seconds):
        self.ops.append(("expire", key, seconds))

    async def execute(self):
        results = []
        for op, key, *args in self.ops:
            members = self.redis.values.setdefault(key, {})
            if op == "zrem":
                low, high = args
                for member, score in list(members.items()):
                    if low <= score <= high:
                        del members[member]
                results.append(None)
            elif op == "zcard":
                results.append(len(members))
            elif op == "zadd":
                members.update(args[0])
                results.append(len(args[0]))
            elif op == "expire":
                await self.redis.expire(key, args[0])
                results.append(True)
        return results


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    import bcrypt

    gensalt = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda *args, **kwargs: gensalt(rounds=4))


@pytest.fixture
async def db_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


@pytest.fixture
def rate_limiter():
    limiter = AuthRateLimiter(redis_url="redis://unused")
    limiter._redis_client = FakeRedis()
    return limiter


@pytest.fixture
def app(db_sessions, rate_limiter, monkeypatch):
    async def override_get_db():
        async with db_sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def no_global_redis(self):
        raise ConnectionError("Redis is not available in tests")

    # get_current_user and the auth routes bypass FastAPI DI for these collaborators.
    monkeypatch.setattr("src.infrastructure.auth.dependencies.AsyncSessionLocal", db_sessions)
    monkeypatch.setattr("src.api.v1.auth.get_auth_rate_limiter", lambda: rate_limiter)
    monkeypatch.setattr(RateLimitMiddleware, "get_redis_client", no_global_redis)

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    return application


@pytest.fixture
async def client(app):
    transport = httpx2.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@dataclass
class RegisteredUser:
    id: UUID
    email: str
    password: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture
def register_user(client):
    async def _register(email: str, password: str = DEFAULT_PASSWORD, full_name="Test User"):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": full_name},
        )
        assert response.status_code == 201, response.text
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        tokens = login.json()
        return RegisteredUser(
            id=UUID(response.json()["id"]),
            email=email,
            password=password,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
        )

    return _register
