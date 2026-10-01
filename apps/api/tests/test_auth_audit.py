import hashlib
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "changeme-in-tests")

from src.api.v1 import audit, auth  # noqa: E402
from src.core.metrics import audit_events_total  # noqa: E402
from src.core.time import utc_now  # noqa: E402
from src.domain.entities import RefreshToken, User  # noqa: E402
from src.domain.exceptions import AuthenticationError, ValidationError  # noqa: E402
from src.domain.repositories import (  # noqa: E402
    AuditEventRepository,
    RefreshTokenRepository,
    UserRepository,
)
from src.domain.services.auth_service import AuthService  # noqa: E402
from src.domain.value_objects import EventType  # noqa: E402
from src.infrastructure.auth.jwt_provider import JWTProvider  # noqa: E402
from src.infrastructure.auth.password import PasswordUtils  # noqa: E402
from src.infrastructure.auth.rate_limiter import AuthRateLimiter  # noqa: E402
from src.infrastructure.database import session as database_session  # noqa: E402
from src.infrastructure.database.models import (  # noqa: E402
    RefreshTokenModel,
    UserModel,
)
from src.infrastructure.database.session import Base  # noqa: E402
from src.infrastructure.dependencies import get_rate_limiter  # noqa: E402
from src.infrastructure.metrics.transactional_provider import (  # noqa: E402
    TransactionalMetricsProvider,
)
from src.infrastructure.repositories import (  # noqa: E402
    AuditEventRepositoryImpl,
    RefreshTokenRepositoryImpl,
    UserRepositoryImpl,
)

PASSWORD = "OriginalPassword123!"
NEW_PASSWORD = "ReplacementPassword456!"
OPERATIONS = [
    ("register", EventType.USER_REGISTERED, {}),
    ("login", EventType.USER_LOGGED_IN, {"ip": "203.0.113.4"}),
    ("change_password", EventType.PASSWORD_CHANGED, {}),
    ("update_profile", EventType.USER_UPDATED, {"changed_fields": ["full_name"]}),
    ("delete_account", EventType.USER_DELETED, {}),
]


async def perform_operation(service, user, operation):
    if operation == "register":
        return await service.register("new@example.com", PASSWORD, "New User")
    if operation == "login":
        return await service.login(user.email, PASSWORD, client_ip="203.0.113.4")
    if operation == "change_password":
        return await service.change_password(user.id, PASSWORD, NEW_PASSWORD)
    if operation == "update_profile":
        return await service.update_profile(user.id, " Updated Name ")
    if operation == "delete_account":
        return await service.delete_account(user.id)
    raise AssertionError(f"Unexpected operation: {operation}")


@pytest.fixture
def service_and_user():
    user = User(email="test@example.com", password_hash="stored-password-hash", full_name="User")
    user_repo = AsyncMock(spec=UserRepository)
    user_repo.get_by_id.return_value = user
    user_repo.get_by_email.return_value = user
    user_repo.create.side_effect = lambda created: created
    user_repo.update.side_effect = lambda updated: updated
    jwt_provider = Mock()
    jwt_provider.create_access_token.return_value = "private-access-token"
    jwt_provider.create_refresh_token.return_value = "private-refresh-token"
    password_utils = Mock()
    password_utils.hash_password.return_value = "new-password-hash"
    password_utils.verify_password.return_value = True
    service = AuthService(
        user_repo=user_repo,
        refresh_token_repo=AsyncMock(spec=RefreshTokenRepository),
        audit_repo=AsyncMock(spec=AuditEventRepository),
        metrics=Mock(),
        jwt_provider=jwt_provider,
        password_utils=password_utils,
        settings=SimpleNamespace(refresh_token_expire_days=7, access_token_expire_minutes=15),
    )
    return service, user


@pytest.mark.parametrize("operation,event_type,details", OPERATIONS)
async def test_success_creates_one_safe_audit_event(
    service_and_user, operation, event_type, details
):
    service, user = service_and_user
    if operation == "register":
        service.user_repo.get_by_email.return_value = None

    result = await perform_operation(service, user, operation)

    service.audit_repo.create.assert_awaited_once()
    created = service.audit_repo.create.await_args.args[0]
    expected_user_id = result.id if operation == "register" else user.id
    assert created.event_type == event_type
    assert created.user_id == created.resource_id == expected_user_id
    assert created.details == details
    service.metrics.track_audit_event.assert_called_once_with(event_type.value)
    serialized = created.model_dump_json()
    for secret in (
        PASSWORD,
        NEW_PASSWORD,
        "stored-password-hash",
        "new-password-hash",
        "private-access-token",
        "private-refresh-token",
        hashlib.sha256(b"private-refresh-token").hexdigest(),
    ):
        assert secret not in serialized


async def test_login_without_client_ip_has_empty_details(service_and_user):
    service, user = service_and_user
    await service.login(user.email, PASSWORD)
    assert service.audit_repo.create.await_args.args[0].details == {}


async def test_unchanged_profile_does_not_write_or_audit(service_and_user):
    service, user = service_and_user
    assert await service.update_profile(user.id, " User ") == user
    service.user_repo.update.assert_not_awaited()
    service.audit_repo.create.assert_not_awaited()
    service.metrics.track_audit_event.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_registration",
        "unknown_login",
        "wrong_password",
        "inactive_login",
        "locked_login",
        "missing_profile",
        "empty_profile",
        "wrong_current_password",
        "weak_new_password",
        "missing_account",
    ],
)
async def test_rejected_operations_do_not_create_success_events(service_and_user, failure):
    service, user = service_and_user
    with pytest.raises((AuthenticationError, ValidationError)):
        if failure == "duplicate_registration":
            await service.register(user.email, PASSWORD, "User")
        elif failure in ("unknown_login", "wrong_password", "inactive_login", "locked_login"):
            if failure == "unknown_login":
                service.user_repo.get_by_email.return_value = None
            elif failure == "wrong_password":
                service.password_utils.verify_password.return_value = False
            elif failure == "inactive_login":
                user.is_active = False
            else:
                service.rate_limiter = AsyncMock(spec=AuthRateLimiter)
                service.rate_limiter.is_account_locked.return_value = (True, 60)
            await service.login(user.email, PASSWORD)
        elif failure in ("missing_profile", "empty_profile"):
            if failure == "missing_profile":
                service.user_repo.get_by_id.return_value = None
            await service.update_profile(user.id, "" if failure == "empty_profile" else "Name")
        elif failure in ("wrong_current_password", "weak_new_password"):
            if failure == "wrong_current_password":
                service.password_utils.verify_password.return_value = False
            await service.change_password(
                user.id, PASSWORD, "short" if failure == "weak_new_password" else NEW_PASSWORD
            )
        else:
            service.user_repo.get_by_id.return_value = None
            await service.delete_account(user.id)

    service.audit_repo.create.assert_not_awaited()
    service.metrics.track_audit_event.assert_not_called()


@pytest.fixture
async def audit_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield sessions
    finally:
        await engine.dispose()


def database_service(session, metrics=None):
    return AuthService(
        user_repo=UserRepositoryImpl(session),
        refresh_token_repo=RefreshTokenRepositoryImpl(session),
        audit_repo=AuditEventRepositoryImpl(session),
        metrics=TransactionalMetricsProvider(session, metrics if metrics is not None else Mock()),
        jwt_provider=JWTProvider,
        password_utils=PasswordUtils,
        settings=SimpleNamespace(refresh_token_expire_days=7, access_token_expire_minutes=15),
    )


@pytest.fixture
async def stored_account(audit_database):
    user = User(
        email="test@example.com",
        password_hash=PasswordUtils.hash_password(PASSWORD),
        full_name="User",
    )
    token = RefreshToken(
        user_id=user.id,
        token_hash="stored-token-hash",
        expires_at=utc_now() + timedelta(days=1),
    )
    async with audit_database.begin() as session:
        await UserRepositoryImpl(session).create(user)
        await RefreshTokenRepositoryImpl(session).create(token)
    return user, token


@pytest.mark.parametrize("operation,event_type,details", OPERATIONS)
async def test_event_and_operation_commit_together(
    audit_database, stored_account, operation, event_type, details
):
    user, token = stored_account
    metrics = Mock()
    async with audit_database.begin() as session:
        result = await perform_operation(database_service(session, metrics), user, operation)
        metrics.track_audit_event.assert_not_called()
        metrics.track_auth_operation.assert_called_once_with(
            operation, "success", duration=pytest.approx(0, abs=2)
        )

    metrics.track_audit_event.assert_called_once_with(event_type.value)

    async with audit_database() as session:
        expected_user_id = result.id if operation == "register" else user.id
        events, total = await AuditEventRepositoryImpl(session).list(resource_id=expected_user_id)
        assert total == len(events) == 1
        assert events[0].event_type == event_type
        assert events[0].details == details
        assert events[0].user_id == (None if operation == "delete_account" else expected_user_id)
        stored_user = await UserRepositoryImpl(session).get_by_id(expected_user_id)
        if operation == "delete_account":
            assert stored_user is None
            assert await session.get(RefreshTokenModel, token.id) is None
        elif operation == "update_profile":
            assert stored_user.full_name == "Updated Name"
        elif operation == "change_password":
            assert PasswordUtils.verify_password(NEW_PASSWORD, stored_user.password_hash)
            assert (await session.get(RefreshTokenModel, token.id)).revoked
        elif operation == "login":
            tokens = (await session.execute(select(RefreshTokenModel))).scalars().all()
            assert len(tokens) == 2
            assert not any(stored.revoked for stored in tokens)
        else:
            assert stored_user.email == "new@example.com"


@pytest.mark.parametrize("operation,event_type,details", OPERATIONS)
async def test_audit_failure_rolls_back_operation(
    audit_database, stored_account, monkeypatch, operation, event_type, details
):
    user, token = stored_account
    metrics = Mock()
    with pytest.raises(RuntimeError, match="audit write failed"):
        async with audit_database.begin() as session:
            service = database_service(session, metrics)
            monkeypatch.setattr(
                service.audit_repo,
                "create",
                AsyncMock(side_effect=RuntimeError("audit write failed")),
            )
            await perform_operation(service, user, operation)

    metrics.track_audit_event.assert_not_called()
    metrics.track_auth_operation.assert_called_once_with(
        operation, "error", duration=pytest.approx(0, abs=2)
    )
    async with audit_database() as session:
        assert (await UserRepositoryImpl(session).get_by_id(user.id)) == user
        assert await UserRepositoryImpl(session).get_by_email("new@example.com") is None
        tokens = (await session.execute(select(RefreshTokenModel))).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].id == token.id
        assert not tokens[0].revoked
        assert (await AuditEventRepositoryImpl(session).list())[1] == 0


async def test_later_failure_rolls_back_audit_and_account_deletion(
    audit_database, stored_account, monkeypatch
):
    user, token = stored_account
    metrics = Mock()
    with pytest.raises(RuntimeError, match="delete failed"):
        async with audit_database.begin() as session:
            service = database_service(session, metrics)
            monkeypatch.setattr(
                service.user_repo, "delete", AsyncMock(side_effect=RuntimeError("delete failed"))
            )
            await service.delete_account(user.id)

    async with audit_database() as session:
        assert await UserRepositoryImpl(session).get_by_id(user.id) == user
        assert not (await session.get(RefreshTokenModel, token.id)).revoked
        assert (await AuditEventRepositoryImpl(session).list())[1] == 0
    metrics.track_audit_event.assert_not_called()


async def test_later_request_failure_does_not_increment_audit_counter(
    audit_database, stored_account, audit_client, monkeypatch
):
    user, token = stored_account
    counter = audit_events_total.labels(event_type=EventType.USER_DELETED.value)
    before = counter._value.get()
    monkeypatch.setattr(
        UserRepositoryImpl, "delete", AsyncMock(side_effect=RuntimeError("delete failed"))
    )

    response = await audit_client.delete(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {JWTProvider.create_access_token(user.id)}"},
    )

    assert response.status_code == 500
    async with audit_database() as session:
        assert await UserRepositoryImpl(session).get_by_id(user.id) == user
        assert not (await session.get(RefreshTokenModel, token.id)).revoked
        assert (await AuditEventRepositoryImpl(session).list())[1] == 0
    assert counter._value.get() == before


@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("savepoint_commits", [False, True])
@pytest.mark.parametrize("outer_commits", [False, True])
async def test_audit_counts_follow_outer_commit_and_savepoint_outcome(
    audit_database, stored_account, depth, savepoint_commits, outer_commits
):
    user, _ = stored_account
    metrics = Mock()
    async with audit_database() as session:
        service = database_service(session, metrics)
        await service.update_profile(user.id, "Outer Update")
        savepoint = await session.begin_nested()
        inner = await session.begin_nested() if depth == 2 else None
        await service.change_password(user.id, PASSWORD, NEW_PASSWORD)
        if inner is not None:
            await inner.commit()
            metrics.track_audit_event.assert_not_called()
        if savepoint_commits:
            await savepoint.commit()
        else:
            await savepoint.rollback()
        metrics.track_audit_event.assert_not_called()
        if outer_commits:
            await session.commit()
        else:
            await session.rollback()

    expected = [EventType.USER_UPDATED] if outer_commits else []
    if outer_commits and savepoint_commits:
        expected.append(EventType.PASSWORD_CHANGED)
    assert metrics.track_audit_event.call_args_list == [call(kind.value) for kind in expected]
    async with audit_database() as session:
        events, total = await AuditEventRepositoryImpl(session).list(resource_id=user.id)
        assert total == len(expected)
        assert {item.event_type for item in events} == set(expected)


@pytest.mark.parametrize("discard", ["rollback", "close"])
async def test_reused_session_does_not_republish_committed_or_discarded_counts(
    audit_database, stored_account, discard
):
    user, _ = stored_account
    metrics = Mock()
    async with audit_database() as session:
        service = database_service(session, metrics)
        await service.update_profile(user.id, "First Update")
        await session.commit()
        metrics.track_audit_event.assert_called_once_with(EventType.USER_UPDATED.value)

        await service.update_profile(user.id, "Discarded Update")
        await getattr(session, discard)()
        await session.commit()
        metrics.track_audit_event.assert_called_once_with(EventType.USER_UPDATED.value)

        await service.update_profile(user.id, "Final Update")
        await session.commit()
        assert metrics.track_audit_event.call_args_list == [
            call(EventType.USER_UPDATED.value),
            call(EventType.USER_UPDATED.value),
        ]

    async with audit_database() as session:
        assert (await AuditEventRepositoryImpl(session).list(resource_id=user.id))[1] == 2
        assert (await UserRepositoryImpl(session).get_by_id(user.id)).full_name == "Final Update"


async def test_failed_database_commit_does_not_publish_or_leak_audit_count(
    audit_database, stored_account
):
    user, _ = stored_account
    metrics = Mock()
    async with audit_database() as session:
        service = database_service(session, metrics)
        await service.update_profile(user.id, "Uncommitted Update")
        await session.execute(text("PRAGMA defer_foreign_keys=ON"))
        await RefreshTokenRepositoryImpl(session).create(
            RefreshToken(
                user_id=uuid4(),
                token_hash="invalid-user-token",
                expires_at=utc_now() + timedelta(days=1),
            )
        )
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            await session.commit()
        metrics.track_audit_event.assert_not_called()
        await session.rollback()
        await session.commit()
        metrics.track_audit_event.assert_not_called()

        await service.update_profile(user.id, "Committed Update")
        await session.commit()
        metrics.track_audit_event.assert_called_once_with(EventType.USER_UPDATED.value)

    async with audit_database() as session:
        assert (await AuditEventRepositoryImpl(session).list(resource_id=user.id))[1] == 1
        assert (
            await UserRepositoryImpl(session).get_by_id(user.id)
        ).full_name == "Committed Update"


@pytest.fixture
async def audit_client(audit_database, monkeypatch):
    monkeypatch.setattr(database_session, "AsyncSessionLocal", audit_database)
    limiter = AsyncMock(spec=AuthRateLimiter)
    limiter.is_account_locked.return_value = (False, 0)
    limiter.check_register_rate_limit.return_value = (True, 2, 0)
    limiter.check_password_change_rate_limit.return_value = (True, 4, 0)
    monkeypatch.setattr(auth, "get_auth_rate_limiter", lambda: limiter)
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.dependency_overrides[get_rate_limiter] = lambda: limiter

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.parametrize("password_method", ["POST", "PUT"])
async def test_auth_endpoints_generate_listable_private_audit_history(
    audit_database, audit_client, password_method
):
    client = audit_client
    counts_before = {
        kind: audit_events_total.labels(event_type=kind.value)._value.get()
        for _, kind, _ in OPERATIONS
    }
    registration = {"email": "new@example.com", "password": PASSWORD, "full_name": "User"}
    response = await client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201
    user_id = response.json()["id"]
    response = await client.post(
        "/api/v1/auth/login", json={"email": registration["email"], "password": PASSWORD}
    )
    assert response.status_code == 200
    tokens = response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = await client.put(
        "/api/v1/auth/profile", json={"full_name": "Updated Name"}, headers=headers
    )
    assert response.status_code == 200
    response = await client.put(
        "/api/v1/auth/profile", json={"full_name": " Updated Name "}, headers=headers
    )
    assert response.status_code == 200
    response = await client.request(
        password_method,
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert response.status_code == 204
    response = await client.get("/api/v1/audit", headers=headers)
    assert response.status_code == 200
    history = response.json()
    assert history["total"] == len(history["items"]) == 4
    assert {item["event_type"] for item in history["items"]} == {
        "USER_REGISTERED",
        "USER_LOGGED_IN",
        "USER_UPDATED",
        "PASSWORD_CHANGED",
    }
    assert all(item["user_id"] == item["resource_id"] == user_id for item in history["items"])
    for secret in (PASSWORD, NEW_PASSWORD, tokens["access_token"], tokens["refresh_token"]):
        assert secret not in json.dumps(history)
    response = await client.get(
        "/api/v1/audit", params={"event_type": "USER_UPDATED"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    other_headers = {"Authorization": f"Bearer {JWTProvider.create_access_token(UUID(int=1))}"}
    response = await client.get("/api/v1/audit", headers=other_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    response = await client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 204

    async with audit_database() as session:
        history, total = await AuditEventRepositoryImpl(session).list(resource_id=UUID(user_id))
        assert total == 5
        assert all(item.user_id is None for item in history)
        assert sum(item.event_type == EventType.USER_DELETED for item in history) == 1
        assert await session.get(UserModel, UUID(user_id)) is None
        assert (await session.execute(select(RefreshTokenModel))).scalars().all() == []
    for kind, before in counts_before.items():
        assert audit_events_total.labels(event_type=kind.value)._value.get() == before + 1


@pytest.mark.parametrize("operation,event_type,details", OPERATIONS)
async def test_audit_failure_returns_server_error_and_rolls_back_request(
    audit_database, stored_account, audit_client, monkeypatch, operation, event_type, details
):
    user, token = stored_account
    monkeypatch.setattr(
        AuditEventRepositoryImpl,
        "create",
        AsyncMock(side_effect=RuntimeError("audit write failed")),
    )
    headers = {"Authorization": f"Bearer {JWTProvider.create_access_token(user.id)}"}
    if operation == "register":
        registration = {"email": "new@example.com", "password": PASSWORD, "full_name": "User"}
        response = await audit_client.post("/api/v1/auth/register", json=registration)
    elif operation == "login":
        response = await audit_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        )
    elif operation == "update_profile":
        response = await audit_client.put(
            "/api/v1/auth/profile", json={"full_name": "Updated Name"}, headers=headers
        )
    elif operation == "change_password":
        response = await audit_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
    else:
        response = await audit_client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 500

    async with audit_database() as session:
        assert (await UserRepositoryImpl(session).get_by_id(user.id)) == user
        assert await UserRepositoryImpl(session).get_by_email("new@example.com") is None
        tokens = (await session.execute(select(RefreshTokenModel))).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].id == token.id
        assert not tokens[0].revoked
        assert (await AuditEventRepositoryImpl(session).list())[1] == 0
