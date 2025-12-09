import hashlib
import time
from datetime import datetime, timedelta
from typing import NamedTuple, Optional
from uuid import UUID

from src.core.time import utc_now

from ..entities import RefreshToken, User
from ..exceptions import AuthenticationError, ValidationError
from ..repositories import RefreshTokenRepository, UserRepository
from .metrics_provider import MetricsProvider


class AuthTokens(NamedTuple):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class AuthService:
    @staticmethod
    def _utcnow() -> datetime:
        return utc_now()

    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: RefreshTokenRepository,
        metrics: MetricsProvider,
        jwt_provider,
        password_utils,
        settings,
        rate_limiter=None,
    ):
        self.user_repo = user_repo
        self.refresh_token_repo = refresh_token_repo
        self.metrics = metrics
        self.jwt_provider = jwt_provider
        self.password_utils = password_utils
        self.settings = settings
        self.rate_limiter = rate_limiter

    async def register(self, email: str, password: str, full_name: str) -> User:
        start_time = time.time()

        try:
            existing_user = await self.user_repo.get_by_email(email)
            if existing_user:
                raise ValidationError("Email already registered")

            if not email or "@" not in email:
                raise ValidationError("Invalid email format")

            if not password or len(password) < 8:
                raise ValidationError("Password must be at least 8 characters")

            if not full_name or not full_name.strip():
                raise ValidationError("Full name cannot be empty")

            password_hash = self.password_utils.hash_password(password)

            user = User(
                email=email,
                password_hash=password_hash,
                full_name=full_name.strip(),
            )

            created_user = await self.user_repo.create(user)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("register", "success", duration=duration)

            return created_user

        except ValidationError:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("register", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("register", "error", duration=duration)
            raise

    async def login(self, email: str, password: str, client_ip: Optional[str] = None) -> AuthTokens:
        start_time = time.time()

        try:
            user = await self.user_repo.get_by_email(email)

            # Check if account is locked (if rate limiter is available)
            if self.rate_limiter and user:
                is_locked, lockout_remaining = await self.rate_limiter.is_account_locked(
                    str(user.id)
                )
                if is_locked:
                    raise AuthenticationError(
                        f"Account locked due to too many failed login attempts. "
                        f"Please try again in {lockout_remaining // 60} minute(s)."
                    )

            if not user:
                raise AuthenticationError("Invalid email or password")

            if not self.password_utils.verify_password(password, user.password_hash):
                # Record failed login attempt (if rate limiter is available)
                if self.rate_limiter:
                    result = await self.rate_limiter.record_failed_login(
                        str(user.id), client_ip or "unknown"
                    )
                    failed_count, should_lock = result if isinstance(result, tuple) else (0, False)
                    if should_lock:
                        raise AuthenticationError(
                            f"Account locked due to too many failed login attempts. "
                            f"Please try again in {self.rate_limiter.ACCOUNT_LOCKOUT_MINUTES} minutes."
                        )

                raise AuthenticationError("Invalid email or password")

            if not user.can_authenticate():
                raise AuthenticationError("Account is not active")

            # Reset failed login counter on successful login
            if self.rate_limiter:
                reset_fn = getattr(self.rate_limiter, "reset_failed_login", None) or getattr(
                    self.rate_limiter, "reset_failed_logins", None
                )
                if reset_fn:
                    await reset_fn(str(user.id))

            access_token = self.jwt_provider.create_access_token(user.id)
            refresh_token = self.jwt_provider.create_refresh_token(user.id)

            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            refresh_token_entity = RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=self._utcnow() + timedelta(days=self.settings.refresh_token_expire_days),
            )
            await self.refresh_token_repo.create(refresh_token_entity)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("login", "success", duration=duration)

            return AuthTokens(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="Bearer",
                expires_in=self.settings.access_token_expire_minutes * 60,
            )

        except AuthenticationError:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("login", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("login", "error", duration=duration)
            raise

    async def refresh_access_token(self, refresh_token: str) -> AuthTokens:
        start_time = time.time()

        try:
            payload = self.jwt_provider.verify_token(refresh_token, token_type="refresh")
            user_id = UUID(payload["sub"])

            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            _stored_token = await self.refresh_token_repo.get_by_token_hash(token_hash)

            await self.refresh_token_repo.revoke_by_token_hash(token_hash)

            access_token = self.jwt_provider.create_access_token(user_id)
            new_refresh_token = self.jwt_provider.create_refresh_token(user_id)

            new_token_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest()
            refresh_token_entity = RefreshToken(
                user_id=user_id,
                token_hash=new_token_hash,
                expires_at=self._utcnow() + timedelta(days=self.settings.refresh_token_expire_days),
            )
            await self.refresh_token_repo.create(refresh_token_entity)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("refresh", "success", duration=duration)

            return AuthTokens(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="Bearer",
                expires_in=self.settings.access_token_expire_minutes * 60,
            )

        except AuthenticationError:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("refresh", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("refresh", "error", duration=duration)
            raise

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> User:
        start_time = time.time()

        try:
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise ValidationError("User not found")

            if not self.password_utils.verify_password(current_password, user.password_hash):
                raise AuthenticationError("Current password is incorrect")

            if not new_password or len(new_password) < 8:
                raise ValidationError("Password must be at least 8 characters")

            if new_password == current_password:
                raise ValidationError("New password must be different from current password")

            new_password_hash = self.password_utils.hash_password(new_password)

            user.password_hash = new_password_hash
            updated_user = await self.user_repo.update(user)
            await self.refresh_token_repo.revoke_by_user_id(user.id)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("change_password", "success", duration=duration)

            return updated_user

        except (ValidationError, AuthenticationError):
            duration = time.time() - start_time
            self.metrics.track_auth_operation("change_password", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("change_password", "error", duration=duration)
            raise

    async def update_profile(self, user_id: UUID, full_name: str) -> User:
        start_time = time.time()

        try:
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise ValidationError("User not found")

            if not full_name or not full_name.strip():
                raise ValidationError("Full name cannot be empty")

            normalized_full_name = full_name.strip()

            if user.full_name == normalized_full_name:
                duration = time.time() - start_time
                self.metrics.track_auth_operation("update_profile", "success", duration=duration)
                return user

            user.full_name = normalized_full_name
            user.updated_at = self._utcnow()

            updated_user = await self.user_repo.update(user)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("update_profile", "success", duration=duration)

            return updated_user

        except ValidationError:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("update_profile", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("update_profile", "error", duration=duration)
            raise

    async def delete_account(self, user_id: UUID) -> None:
        """Delete user account and revoke all tokens."""
        start_time = time.time()

        try:
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise ValidationError("User not found")

            await self.refresh_token_repo.revoke_by_user_id(user_id)
            await self.user_repo.delete(user_id)

            duration = time.time() - start_time
            self.metrics.track_auth_operation("delete_account", "success", duration=duration)
        except ValidationError:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("delete_account", "error", duration=duration)
            raise
        except Exception:
            duration = time.time() - start_time
            self.metrics.track_auth_operation("delete_account", "error", duration=duration)
            raise
