import hashlib
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time import utc_now
from src.domain.entities import RefreshToken
from src.domain.repositories import RefreshTokenRepository
from src.infrastructure.database.models import RefreshTokenModel


class RefreshTokenRepositoryImpl(RefreshTokenRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _hash_token(token: str) -> str:

        return hashlib.sha256(token.encode()).hexdigest()

    async def create(self, token: RefreshToken) -> RefreshToken:

        db_token = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked=token.revoked,
        )
        self.session.add(db_token)
        await self.session.flush()
        await self.session.refresh(db_token)
        return RefreshToken.model_validate(db_token)

    async def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:

        result = await self.session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.revoked.is_(False),
                RefreshTokenModel.expires_at > utc_now(),
            )
        )
        db_token = result.scalar_one_or_none()
        return RefreshToken.model_validate(db_token) if db_token else None

    async def revoke_by_token_hash(self, token_hash: str) -> None:

        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .values(revoked=True)
        )
        await self.session.flush()

    async def revoke_by_user_id(self, user_id: UUID) -> None:

        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id)
            .values(revoked=True)
        )
        await self.session.flush()
