"""Audit event API endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import AuditEventListResponse, AuditEventResponse
from src.domain.value_objects import EventType
from src.infrastructure.auth.dependencies import get_current_user_id
from src.infrastructure.database.session import get_db
from src.infrastructure.repositories import AuditEventRepositoryImpl

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    event_type: Optional[EventType] = Query(None, description="Filter by event type"),
    resource_id: Optional[UUID] = Query(None, description="Filter by resource ID"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List audit events with optional filters and pagination."""
    audit_repo = AuditEventRepositoryImpl(db)

    events, total = await audit_repo.list(
        user_id=current_user_id,
        event_type=event_type,
        resource_id=resource_id,
        from_date=start_date,
        to_date=end_date,
        page=page,
        page_size=page_size,
    )

    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(event) for event in events],
        page=page,
        page_size=page_size,
        total=total,
    )
