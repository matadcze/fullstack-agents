"""HTTP-level tests for registration, login, token rotation, deletion and authorization."""

from datetime import timedelta
from uuid import uuid4

import pytest
from jose import jwt
from sqlalchemy import func, select, update

from src.core.config import settings
from src.domain.entities import AuditEvent
from src.domain.value_objects import EventType
from src.infrastructure.auth.jwt_provider import JWTProvider
from src.infrastructure.database.models import AuditEventModel, RefreshTokenModel, UserModel
from src.infrastructure.repositories import AuditEventRepositoryImpl
from tests.conftest import DEFAULT_PASSWORD

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"
PROFILE = "/api/v1/auth/profile"
CHANGE_PASSWORD = "/api/v1/auth/change-password"


async def count_rows(db_sessions, model, *where):
    async with db_sessions() as session:
        return (
            await session.execute(select(func.count()).select_from(model).where(*where))
        ).scalar()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Registration -----------------------------------------------------------------------------


async def test_register_creates_user_without_leaking_password_hash(client, db_sessions):
    response = await client.post(
        REGISTER,
        json={"email": "new@example.com", "password": DEFAULT_PASSWORD, "full_name": "  Ada  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["full_name"] == "Ada"
    assert set(body) == {"id", "email", "full_name", "created_at"}

    async with db_sessions() as session:
        stored = (await session.execute(select(UserModel))).scalar_one()
    assert str(stored.id) == body["id"]
    assert stored.password_hash != DEFAULT_PASSWORD
    assert stored.is_active is True


async def test_register_then_login_round_trip(client):
    await client.post(
        REGISTER, json={"email": "rt@example.com", "password": DEFAULT_PASSWORD, "full_name": "R"}
    )

    login = await client.post(LOGIN, json={"email": "rt@example.com", "password": DEFAULT_PASSWORD})

    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] == settings.access_token_expire_minutes * 60
    me = await client.get(ME, headers=bearer(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "rt@example.com"


async def test_register_rejects_duplicate_email(client, db_sessions):
    payload = {"email": "dup@example.com", "password": DEFAULT_PASSWORD, "full_name": "A"}
    assert (await client.post(REGISTER, json=payload)).status_code == 201

    response = await client.post(REGISTER, json={**payload, "password": "AnotherPass1!"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"
    assert await count_rows(db_sessions, UserModel) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": DEFAULT_PASSWORD, "full_name": "A"},
        {"email": "short@example.com", "password": "short", "full_name": "A"},
        {"email": "long@example.com", "password": "x" * 73, "full_name": "A"},
        {"password": DEFAULT_PASSWORD, "full_name": "A"},
    ],
    ids=["invalid-email", "short-password", "password-over-bcrypt-limit", "missing-email"],
)
async def test_register_rejects_invalid_payload(client, db_sessions, payload):
    response = await client.post(REGISTER, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ValidationError"
    assert await count_rows(db_sessions, UserModel) == 0


async def test_register_without_full_name(client):
    # The web form treats full name as optional and omits it when blank.
    response = await client.post(
        REGISTER, json={"email": "anon@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 201
    assert response.json()["full_name"] is None
    login = await client.post(
        LOGIN, json={"email": "anon@example.com", "password": DEFAULT_PASSWORD}
    )
    assert (await client.get(ME, headers=bearer(login.json()["access_token"]))).status_code == 200


async def test_register_rejects_blank_full_name(client, db_sessions):
    response = await client.post(
        REGISTER,
        json={"email": "blank@example.com", "password": DEFAULT_PASSWORD, "full_name": "  "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Full name cannot be empty"
    assert await count_rows(db_sessions, UserModel) == 0


async def test_register_is_rate_limited_per_client(client):
    statuses = []
    for i in range(4):
        response = await client.post(
            REGISTER,
            json={"email": f"user{i}@example.com", "password": DEFAULT_PASSWORD, "full_name": "A"},
        )
        statuses.append(response.status_code)

    assert statuses == [201, 201, 201, 429]
    assert int(response.headers["Retry-After"]) > 0


# --- Failed login -----------------------------------------------------------------------------


async def test_login_with_wrong_password_is_rejected_without_issuing_tokens(
    client, register_user, db_sessions
):
    user = await register_user("victim@example.com")
    tokens_before = await count_rows(db_sessions, RefreshTokenModel)

    response = await client.post(LOGIN, json={"email": user.email, "password": "WrongPass123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert await count_rows(db_sessions, RefreshTokenModel) == tokens_before


async def test_login_unknown_email_is_indistinguishable_from_wrong_password(client, register_user):
    user = await register_user("known@example.com")

    unknown = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    )
    wrong = await client.post(LOGIN, json={"email": user.email, "password": "WrongPass123"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_repeated_failed_logins_lock_the_account(client, register_user):
    user = await register_user("locked@example.com")

    for _ in range(4):
        response = await client.post(LOGIN, json={"email": user.email, "password": "WrongPass123"})
        assert response.json()["detail"] == "Invalid email or password"

    fifth = await client.post(LOGIN, json={"email": user.email, "password": "WrongPass123"})
    assert fifth.status_code == 401
    assert "Account locked" in fifth.json()["detail"]

    correct = await client.post(LOGIN, json={"email": user.email, "password": user.password})
    assert correct.status_code == 401
    assert "Account locked" in correct.json()["detail"]


async def test_successful_login_resets_failed_attempt_counter(client, register_user):
    user = await register_user("reset@example.com")

    for _ in range(2):
        for _ in range(4):
            await client.post(LOGIN, json={"email": user.email, "password": "WrongPass123"})
        response = await client.post(LOGIN, json={"email": user.email, "password": user.password})
        assert response.status_code == 200


async def test_inactive_user_cannot_log_in_or_use_existing_access_token(
    client, register_user, db_sessions
):
    user = await register_user("inactive@example.com")
    async with db_sessions.begin() as session:
        await session.execute(
            update(UserModel).where(UserModel.id == user.id).values(is_active=False)
        )

    login = await client.post(LOGIN, json={"email": user.email, "password": user.password})
    assert login.status_code == 401
    assert login.json()["detail"] == "Account is not active"

    me = await client.get(ME, headers=user.headers)
    assert me.status_code == 403

    refresh = await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401


# --- Token rotation and reuse -----------------------------------------------------------------


async def test_refresh_rotates_tokens_and_rejects_reuse_of_the_old_one(client, register_user):
    user = await register_user("rotate@example.com")

    first = await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    assert first.status_code == 200
    rotated = first.json()
    assert rotated["refresh_token"] != user.refresh_token
    assert (await client.get(ME, headers=bearer(rotated["access_token"]))).status_code == 200

    reuse = await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    assert reuse.status_code == 401
    assert reuse.json()["detail"] == "Invalid or expired refresh token"

    second = await client.post(REFRESH, json={"refresh_token": rotated["refresh_token"]})
    assert second.status_code == 200
    assert second.json()["refresh_token"] not in {user.refresh_token, rotated["refresh_token"]}


async def test_refresh_leaves_exactly_one_active_token_per_session(
    client, register_user, db_sessions
):
    user = await register_user("chain@example.com")
    token = user.refresh_token
    for _ in range(3):
        token = (await client.post(REFRESH, json={"refresh_token": token})).json()["refresh_token"]

    assert (
        await count_rows(
            db_sessions,
            RefreshTokenModel,
            RefreshTokenModel.user_id == user.id,
            RefreshTokenModel.revoked.is_(False),
        )
        == 1
    )


async def test_refresh_rejects_access_token_and_garbage(client, register_user):
    user = await register_user("types@example.com")

    for candidate in (user.access_token, "not-a-jwt", ""):
        response = await client.post(REFRESH, json={"refresh_token": candidate})
        assert response.status_code == 401, candidate


async def test_refresh_rejects_validly_signed_token_that_was_never_issued(client, register_user):
    user = await register_user("forged@example.com")

    response = await client.post(
        REFRESH, json={"refresh_token": JWTProvider.create_refresh_token(user.id)}
    )

    assert response.status_code == 401


async def test_change_password_revokes_existing_refresh_tokens(client, register_user):
    user = await register_user("pw@example.com")

    response = await client.post(
        CHANGE_PASSWORD,
        headers=user.headers,
        json={"current_password": user.password, "new_password": "BrandNewPass9!"},
    )
    assert response.status_code == 204

    assert (
        await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    ).status_code == 401
    old = await client.post(LOGIN, json={"email": user.email, "password": user.password})
    assert old.status_code == 401
    new = await client.post(LOGIN, json={"email": user.email, "password": "BrandNewPass9!"})
    assert new.status_code == 200


async def test_change_password_requires_correct_current_password(client, register_user):
    user = await register_user("pw2@example.com")

    response = await client.post(
        CHANGE_PASSWORD,
        headers=user.headers,
        json={"current_password": "WrongPass123", "new_password": "BrandNewPass9!"},
    )

    assert response.status_code == 401
    assert (
        await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    ).status_code == 200


# --- Account deletion -------------------------------------------------------------------------


async def test_delete_account_removes_user_and_invalidates_credentials(
    client, register_user, db_sessions
):
    user = await register_user("bye@example.com")

    response = await client.delete(ME, headers=user.headers)
    assert response.status_code == 204

    assert await count_rows(db_sessions, UserModel, UserModel.id == user.id) == 0
    assert (
        await count_rows(db_sessions, RefreshTokenModel, RefreshTokenModel.user_id == user.id) == 0
    )

    me = await client.get(ME, headers=user.headers)
    assert me.status_code == 401
    assert (
        await client.post(REFRESH, json={"refresh_token": user.refresh_token})
    ).status_code == 401
    login = await client.post(LOGIN, json={"email": user.email, "password": user.password})
    assert login.status_code == 401


async def test_deleted_account_cannot_mutate_state_with_lingering_access_token(
    client, register_user
):
    user = await register_user("ghost@example.com")
    delete_response = await client.delete(ME, headers=user.headers)
    assert delete_response.status_code == 204

    again = await client.delete(ME, headers=user.headers)
    profile = await client.put(PROFILE, headers=user.headers, json={"full_name": "Ghost"})

    assert again.status_code >= 400
    assert profile.status_code >= 400


async def test_deleted_email_can_be_registered_again(client, register_user):
    user = await register_user("again@example.com")
    await client.delete(ME, headers=user.headers)

    response = await client.post(
        REGISTER, json={"email": user.email, "password": "FreshPass123", "full_name": "B"}
    )

    assert response.status_code == 201
    assert response.json()["id"] != str(user.id)


async def test_delete_account_preserves_audit_trail_detached_from_user(
    client, register_user, db_sessions
):
    user = await register_user("trail@example.com")
    async with db_sessions.begin() as session:
        await AuditEventRepositoryImpl(session).create(
            AuditEvent(user_id=user.id, event_type=EventType.USER_LOGGED_IN)
        )

    assert (await client.delete(ME, headers=user.headers)).status_code == 204

    async with db_sessions() as session:
        events = (await session.execute(select(AuditEventModel))).scalars().all()
    assert len(events) == 1
    assert events[0].user_id is None


async def test_delete_account_only_affects_the_caller(client, register_user):
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")

    assert (await client.delete(ME, headers=alice.headers)).status_code == 204

    me = await client.get(ME, headers=bob.headers)
    assert me.status_code == 200
    assert me.json()["email"] == bob.email
    assert (
        await client.post(REFRESH, json={"refresh_token": bob.refresh_token})
    ).status_code == 200


# --- Authorization ----------------------------------------------------------------------------

PROTECTED = [
    ("GET", ME, None),
    ("DELETE", ME, None),
    ("PUT", PROFILE, {"full_name": "X"}),
    ("POST", CHANGE_PASSWORD, {"current_password": "a" * 8, "new_password": "b" * 8}),
    ("GET", "/api/v1/audit", None),
]


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
async def test_protected_endpoints_require_bearer_token(client, method, path, body):
    response = await client.request(method, path, json=body)

    assert response.status_code == 401


def _signed(payload: dict, secret: str = settings.jwt_secret_key) -> str:
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


@pytest.mark.parametrize(
    "make_token",
    [
        pytest.param(lambda u: "garbage", id="malformed"),
        pytest.param(
            lambda u: JWTProvider.create_access_token(u.id, expires_delta=timedelta(seconds=-1)),
            id="expired",
        ),
        pytest.param(lambda u: u.refresh_token, id="refresh-token-as-access"),
        pytest.param(
            lambda u: _signed({"sub": str(u.id), "exp": 9999999999, "type": "access"}, "wrong"),
            id="wrong-signature",
        ),
        pytest.param(
            lambda u: _signed({"sub": "not-a-uuid", "exp": 9999999999, "type": "access"}),
            id="malformed-subject",
        ),
        pytest.param(lambda u: _signed({"sub": str(u.id), "type": "access"}), id="no-expiry"),
    ],
)
@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
async def test_protected_endpoints_reject_invalid_tokens(
    client, register_user, method, path, body, make_token
):
    user = await register_user(f"{uuid4().hex[:8]}@example.com")

    response = await client.request(method, path, json=body, headers=bearer(make_token(user)))

    assert response.status_code == 401


async def test_access_token_for_unknown_user_is_rejected(client):
    token = JWTProvider.create_access_token(uuid4())

    assert (await client.get(ME, headers=bearer(token))).status_code == 401


async def test_profile_update_only_changes_the_caller(client, register_user):
    alice = await register_user("alice2@example.com")
    bob = await register_user("bob2@example.com")

    response = await client.put(PROFILE, headers=alice.headers, json={"full_name": " Alice B "})

    assert response.status_code == 200
    assert response.json()["full_name"] == "Alice B"
    assert (await client.get(ME, headers=bob.headers)).json()["full_name"] == "Test User"
