from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import User
from src.domain.repositories import UserRepository
from src.infrastructure.database.models import UserModel


class UserRepositoryImpl(UserRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:

        db_user = UserModel(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        self.session.add(db_user)
        await self.session.flush()
        await self.session.refresh(db_user)
        return User.model_validate(db_user)

    async def get_by_id(self, user_id: UUID) -> Optional[User]:

        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalar_one_or_none()
        return User.model_validate(db_user) if db_user else None

    async def get_by_email(self, email: str) -> Optional[User]:

        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        db_user = result.scalar_one_or_none()
        return User.model_validate(db_user) if db_user else None

    async def update(self, user: User) -> User:

        result = await self.session.execute(select(UserModel).where(UserModel.id == user.id))
        db_user = result.scalar_one_or_none()

        if db_user is None:
            raise ValueError(f"User {user.id} not found")

        db_user.email = user.email
        db_user.password_hash = user.password_hash
        db_user.full_name = user.full_name
        db_user.is_active = user.is_active
        db_user.updated_at = user.updated_at

        await self.session.flush()
        await self.session.refresh(db_user)
        return User.model_validate(db_user)

    async def delete(self, user_id: UUID) -> None:

        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user is None:
            return

        await self.session.delete(db_user)
        await self.session.flush()
