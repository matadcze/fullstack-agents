"""Dependency injection setup for infrastructure layer."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domain.repositories import AuditEventRepository, UserRepository
from src.domain.services import AgentService, AuthService
from src.domain.services.metrics_provider import MetricsProvider
from src.infrastructure.agents.providers import get_llm_provider
from src.infrastructure.auth.jwt_provider import JWTProvider
from src.infrastructure.auth.password import PasswordUtils
from src.infrastructure.auth.rate_limiter import AuthRateLimiter, get_auth_rate_limiter
from src.infrastructure.database.session import get_db
from src.infrastructure.metrics import PrometheusMetricsProvider
from src.infrastructure.repositories import (
    AuditEventRepositoryImpl,
    RefreshTokenRepositoryImpl,
    UserRepositoryImpl,
)


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """Get user repository instance."""
    return UserRepositoryImpl(db)


def get_audit_repository(db: AsyncSession = Depends(get_db)) -> AuditEventRepository:
    """Get audit event repository instance."""
    return AuditEventRepositoryImpl(db)


def get_refresh_token_repository(db: AsyncSession = Depends(get_db)):
    """Get refresh token repository instance."""
    return RefreshTokenRepositoryImpl(db)


def get_metrics_provider() -> MetricsProvider:
    """Get metrics provider instance."""
    return PrometheusMetricsProvider()


def get_rate_limiter() -> AuthRateLimiter:
    """Get rate limiter instance."""
    return get_auth_rate_limiter()


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    refresh_token_repo=Depends(get_refresh_token_repository),
    metrics: MetricsProvider = Depends(get_metrics_provider),
    rate_limiter: AuthRateLimiter = Depends(get_rate_limiter),
) -> AuthService:
    """Get authentication service instance."""
    return AuthService(
        user_repo=user_repo,
        refresh_token_repo=refresh_token_repo,
        metrics=metrics,
        jwt_provider=JWTProvider,
        password_utils=PasswordUtils,
        settings=settings,
        rate_limiter=rate_limiter,
    )


def get_agent_service() -> AgentService:
    """Get agent service instance."""
    provider = get_llm_provider()
    return AgentService(provider=provider)
