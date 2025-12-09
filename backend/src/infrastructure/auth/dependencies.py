from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.domain.entities import User
from src.domain.exceptions import AuthenticationError
from src.infrastructure.database import AsyncSessionLocal

from .jwt_provider import JWTProvider

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UUID:

    try:
        token = credentials.credentials
        user_id = JWTProvider.get_user_id_from_token(token)
        return user_id
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    user_id: UUID = Depends(get_current_user_id),
) -> User:

    from src.infrastructure.repositories.user_repository import UserRepositoryImpl

    async with AsyncSessionLocal() as session:
        repo = UserRepositoryImpl(session)
        user = await repo.get_by_id(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )

        return user


async def get_optional_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[UUID]:

    if credentials is None:
        return None

    try:
        token = credentials.credentials
        user_id = JWTProvider.get_user_id_from_token(token)
        return user_id
    except AuthenticationError:
        return None
