"""Seed local development data."""

import asyncio
import json
from pathlib import Path
from typing import Dict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.value_objects import EventType
from src.infrastructure.auth.password import hash_password
from src.infrastructure.database.models import AuditEventModel, UserModel
from src.infrastructure.database.session import AsyncSessionLocal

FIXTURES_DIR = Path(__file__).parent / "fixtures"
USERS_FIXTURE = FIXTURES_DIR / "users.json"


async def seed_users(session: AsyncSession) -> Dict[str, UserModel]:
    """Create users from the fixture file if they do not already exist."""
    if not USERS_FIXTURE.exists():
        print(f"User fixture not found at {USERS_FIXTURE}. Nothing to seed.")
        return {}

    users_data = json.loads(USERS_FIXTURE.read_text())
    created: Dict[str, UserModel] = {}

    for user in users_data:
        email = user["email"].lower()
        result = await session.execute(select(UserModel).where(UserModel.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            created[email] = existing
            continue

        db_user = UserModel(
            id=uuid4(),
            email=email,
            full_name=user.get("full_name"),
            password_hash=hash_password(user["password"]),
            is_active=user.get("is_active", True),
        )
        session.add(db_user)
        await session.flush()
        await session.refresh(db_user)
        created[email] = db_user

    return created


async def seed_audit_events(session: AsyncSession, users: Dict[str, UserModel]) -> int:
    """Add example audit events if the table is empty."""
    if not users:
        return 0

    existing_events = await session.execute(select(AuditEventModel.id).limit(1))
    if existing_events.first():
        return 0

    events = []
    for user in users.values():
        events.append(
            AuditEventModel(
                user_id=user.id,
                event_type=EventType.USER_REGISTERED,
                details={"note": "Seeded user signup"},
            )
        )
        events.append(
            AuditEventModel(
                user_id=user.id,
                event_type=EventType.USER_LOGGED_IN,
                details={"ip": "127.0.0.1", "note": "Seeded login"},
            )
        )

    session.add_all(events)
    await session.flush()
    return len(events)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        try:
            users = await seed_users(session)
            events_count = await seed_audit_events(session, users)
            await session.commit()
            print(f"Seeded {len(users)} users and {events_count} audit events.")
        except Exception:
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
