import asyncio
import hashlib
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "changeme-in-tests")

from src.core.time import utc_now  # noqa: E402
from src.domain.entities import RefreshToken, User  # noqa: E402
from src.domain.exceptions import AuthenticationError  # noqa: E402
from src.domain.repositories import RefreshTokenRepository, UserRepository  # noqa: E402
from src.domain.services.auth_service import AuthService, AuthTokens  # noqa: E402
from src.infrastructure.auth.jwt_provider import JWTProvider  # noqa: E402
from src.infrastructure.database.models import RefreshTokenModel, UserModel  # noqa: E402
from src.infrastructure.database.session import Base  # noqa: E402
from src.infrastructure.repositories.refresh_token_repository import (  # noqa: E402
    RefreshTokenRepositoryImpl,
)


def make_service(user, repo, jwt_provider=JWTProvider):
    user_repo = AsyncMock(spec=UserRepository)
    user_repo.get_by_id.return_value = user
    return AuthService(
        user_repo=user_repo,
        refresh_token_repo=repo,
        metrics=Mock(),
        jwt_provider=jwt_provider,
        password_utils=Mock(),
        settings=SimpleNamespace(refresh_token_expire_days=7, access_token_expire_minutes=15),
    )


@pytest.mark.parametrize(
    "state", ["missing", "revoked", "expired", "expires_now", "wrong_user", "deleted", "inactive"]
)
async def test_refresh_rejects_invalid_stored_token_or_user(state, monkeypatch):
    now = utc_now()
    monkeypatch.setattr(AuthService, "_utcnow", staticmethod(lambda: now))
    user = User(email="test@example.com", password_hash="unused")
    token = RefreshToken(user_id=user.id, token_hash="hash", expires_at=now + timedelta(days=1))
    if state == "revoked":
        token.revoked = True
    elif state in ("expired", "expires_now"):
        token.expires_at = now - timedelta(seconds=1) if state == "expired" else now
    elif state == "wrong_user":
        token.user_id = uuid4()
    elif state == "inactive":
        user.is_active = False

    repo = AsyncMock(spec=RefreshTokenRepository)
    repo.get_by_token_hash.return_value = None if state == "missing" else token
    jwt_provider = Mock()
    jwt_provider.verify_token.return_value = {"sub": str(user.id)}
    jwt_provider.create_refresh_token.return_value = "replacement"
    service = make_service(None if state == "deleted" else user, repo, jwt_provider)

    with pytest.raises(AuthenticationError):
        await service.refresh_access_token("original")

    repo.create.assert_not_awaited()
    repo.revoke_by_token_hash.assert_not_awaited()
    repo.rotate.assert_not_awaited()
    jwt_provider.create_access_token.assert_not_called()
    service.metrics.track_auth_operation.assert_called_once_with(
        "refresh", "error", duration=pytest.approx(0, abs=1)
    )


def test_refresh_jwts_are_unique_even_in_the_same_second(monkeypatch):
    now = utc_now()
    monkeypatch.setattr("src.infrastructure.auth.jwt_provider.utc_now", lambda: now)
    user_id = uuid4()
    first = JWTProvider.create_refresh_token(user_id)
    second = JWTProvider.create_refresh_token(user_id)
    assert first != second
    assert JWTProvider.verify_token(first, token_type="refresh")["sub"] == str(user_id)


async def test_refresh_rejects_malformed_subject():
    repo = AsyncMock(spec=RefreshTokenRepository)
    jwt_provider = Mock()
    jwt_provider.verify_token.return_value = {"sub": "not-a-uuid"}
    service = make_service(None, repo, jwt_provider)
    with pytest.raises(AuthenticationError, match="Invalid user ID"):
        await service.refresh_access_token("original")
    repo.get_by_token_hash.assert_not_awaited()


@pytest.fixture
async def token_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'refresh.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user = User(email="test@example.com", password_hash="unused")
    raw_token = JWTProvider.create_refresh_token(user.id)
    token = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=utc_now() + timedelta(days=1),
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions.begin() as session:
            session.add(UserModel(**user.model_dump()))
            await session.flush()
            await RefreshTokenRepositoryImpl(session).create(token)
        yield sessions, user, raw_token, token
    finally:
        await engine.dispose()


async def test_refresh_rotates_once_and_rejects_reuse(token_database):
    sessions, user, raw_token, token = token_database
    async with sessions.begin() as session:
        service = make_service(user, RefreshTokenRepositoryImpl(session))
        result = await service.refresh_access_token(raw_token)
        assert result.token_type == "Bearer"
        assert result.expires_in == 900
        assert JWTProvider.verify_token(result.access_token)["sub"] == str(user.id)

    async with sessions.begin() as session:
        repo = RefreshTokenRepositoryImpl(session)
        assert await repo.get_by_token_hash(token.token_hash) is None
        assert await repo.get_by_token_hash(
            hashlib.sha256(result.refresh_token.encode()).hexdigest()
        )
        with pytest.raises(AuthenticationError):
            await make_service(user, repo).refresh_access_token(raw_token)
        replacement = await make_service(user, repo).refresh_access_token(result.refresh_token)
        assert replacement.refresh_token != result.refresh_token


async def test_concurrent_refresh_has_exactly_one_winner(token_database):
    sessions, user, raw_token, token = token_database
    barrier = asyncio.Barrier(2)

    async def refresh():
        async with sessions.begin() as session:
            repo = RefreshTokenRepositoryImpl(session)
            lookup = repo.get_by_token_hash

            async def synchronized_lookup(token_hash):
                stored = await lookup(token_hash)
                await barrier.wait()
                return stored

            repo.get_by_token_hash = synchronized_lookup
            try:
                return await make_service(user, repo).refresh_access_token(raw_token)
            except AuthenticationError as error:
                return error

    results = await asyncio.wait_for(asyncio.gather(refresh(), refresh()), timeout=10)
    assert sum(isinstance(result, AuthTokens) for result in results) == 1
    assert sum(isinstance(result, AuthenticationError) for result in results) == 1
    async with sessions() as session:
        tokens = (await session.execute(select(RefreshTokenModel))).scalars().all()
        assert len(tokens) == 2
        assert sum(not stored.revoked for stored in tokens) == 1


async def test_failed_rotation_keeps_original_token_active(token_database, monkeypatch):
    sessions, user, raw_token, token = token_database
    with pytest.raises(RuntimeError, match="insert failed"):
        async with sessions.begin() as session:
            repo = RefreshTokenRepositoryImpl(session)
            monkeypatch.setattr(
                repo, "create", AsyncMock(side_effect=RuntimeError("insert failed"))
            )
            await make_service(user, repo).refresh_access_token(raw_token)

    async with sessions() as session:
        assert await RefreshTokenRepositoryImpl(session).get_by_token_hash(token.token_hash)
        assert len((await session.execute(select(RefreshTokenModel))).scalars().all()) == 1


async def test_insert_constraint_failure_rolls_back_consumption(token_database):
    sessions, user, raw_token, token = token_database
    jwt_provider = Mock(wraps=JWTProvider)
    jwt_provider.create_refresh_token.return_value = raw_token
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            await make_service(
                user, RefreshTokenRepositoryImpl(session), jwt_provider
            ).refresh_access_token(raw_token)

    async with sessions() as session:
        assert await RefreshTokenRepositoryImpl(session).get_by_token_hash(token.token_hash)
        assert len((await session.execute(select(RefreshTokenModel))).scalars().all()) == 1


@pytest.mark.parametrize("state", ["missing", "revoked", "expired", "wrong_user"])
async def test_rotation_rechecks_token_state_before_consumption(token_database, state):
    sessions, user, raw_token, token = token_database
    async with sessions.begin() as session:
        if state == "revoked":
            await session.execute(
                update(RefreshTokenModel)
                .where(RefreshTokenModel.id == token.id)
                .values(revoked=True)
            )
        elif state == "expired":
            await session.execute(
                update(RefreshTokenModel)
                .where(RefreshTokenModel.id == token.id)
                .values(expires_at=utc_now() - timedelta(seconds=1))
            )
        replacement = RefreshToken(
            user_id=uuid4() if state == "wrong_user" else user.id,
            token_hash="replacement",
            expires_at=utc_now() + timedelta(days=1),
        )
        repo = RefreshTokenRepositoryImpl(session)
        assert not await repo.rotate(
            "missing" if state == "missing" else token.token_hash, replacement
        )
        tokens = (await session.execute(select(RefreshTokenModel))).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].revoked == (state == "revoked")
