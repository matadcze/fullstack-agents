"""API request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domain.value_objects import EventType


# Generic error schemas
class ErrorDetail(BaseModel):
    """Error detail information."""

    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail


# Health check schemas
class HealthResponse(BaseModel):
    """Health check response."""

    status: str


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    components: Dict[str, str]


# Authentication schemas
class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., max_length=72, description="User password")


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class RefreshTokenRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Password change request."""

    current_password: str = Field(..., max_length=72, description="Current password")
    new_password: str = Field(
        ..., min_length=8, max_length=72, description="New password (8-72 characters)"
    )


class UpdateProfileRequest(BaseModel):
    """User profile update request."""

    full_name: str = Field(..., min_length=1, max_length=100, description="Updated full name")


class UserResponse(BaseModel):
    """User information response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str]
    created_at: datetime


# Audit schemas
class AuditEventResponse(BaseModel):
    """Audit event response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID]
    event_type: EventType
    resource_id: Optional[UUID]
    details: Dict[str, Any]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    """Paginated audit event list response."""

    items: List[AuditEventResponse]
    page: int
    page_size: int
    total: int


# Agent schemas
class AgentRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt for the agent")
    system: Optional[str] = Field(None, description="Optional system guidance")
    tools: Optional[List[str]] = Field(None, description="Requested tools (future use)")


class AgentStep(BaseModel):
    step_type: str
    content: str


class AgentRunResponse(BaseModel):
    output: str
    steps: List[AgentStep]
