from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .entities import AuditEvent, RefreshToken, User
from .value_objects import EventType


class UserRepository(ABC):
    """Repository interface for User entity operations."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user."""
        pass

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        pass

    @abstractmethod
    async def update(self, user: User) -> User:
        """Update existing user."""
        pass

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """Delete user by ID."""
        pass


class AuditEventRepository(ABC):
    """Repository interface for AuditEvent entity operations."""

    @abstractmethod
    async def create(self, event: AuditEvent) -> AuditEvent:
        """Create a new audit event."""
        pass

    @abstractmethod
    async def list(
        self,
        user_id: Optional[UUID] = None,
        resource_id: Optional[UUID] = None,
        event_type: Optional[EventType] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[AuditEvent], int]:
        """List audit events with optional filters and pagination."""
        pass


class RefreshTokenRepository(ABC):
    """Repository interface for RefreshToken entity operations."""

    @abstractmethod
    async def create(self, token: RefreshToken) -> RefreshToken:
        """Create a new refresh token."""
        pass

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:
        """Get refresh token by token hash."""
        pass

    @abstractmethod
    async def revoke_by_user_id(self, user_id: UUID) -> None:
        """Revoke all refresh tokens for a user."""
        pass

    @abstractmethod
    async def revoke_by_token_hash(self, token_hash: str) -> None:
        """Revoke a specific refresh token."""
        pass
