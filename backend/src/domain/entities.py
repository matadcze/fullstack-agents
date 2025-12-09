from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.core.time import utc_now

from .value_objects import EventType


class User(BaseModel):
    """User entity representing an authenticated user in the system."""

    id: UUID = Field(default_factory=uuid4)
    email: str
    password_hash: str
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)

    def can_authenticate(self) -> bool:
        """Check if user can authenticate (is active)."""
        return self.is_active

    def can_be_accessed_by(self, user_id: UUID) -> bool:
        """Check if user data can be accessed by given user_id."""
        return self.id == user_id


class AuditEvent(BaseModel):
    """Audit event entity for tracking system actions."""

    id: UUID = Field(default_factory=uuid4)
    user_id: Optional[UUID] = None
    event_type: EventType
    resource_id: Optional[UUID] = None  # Generic resource ID for any entity
    details: Dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class RefreshToken(BaseModel):
    """Refresh token entity for JWT token refresh flow."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked: bool = False

    model_config = ConfigDict(from_attributes=True)
