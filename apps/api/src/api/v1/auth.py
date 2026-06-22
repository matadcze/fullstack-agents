from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from src.domain.exceptions import AuthenticationError, ValidationError
from src.domain.services import AuthService
from src.infrastructure.auth.dependencies import get_current_user, get_current_user_id
from src.infrastructure.auth.rate_limiter import get_auth_rate_limiter
from src.infrastructure.dependencies import get_auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        client_ip = http_request.client.host if http_request.client else "unknown"
        rate_limiter = get_auth_rate_limiter()
        is_allowed, remaining, reset_time = await rate_limiter.check_register_rate_limit(client_ip)

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts. Please try again later.",
                headers={"Retry-After": str(int(reset_time - __import__("time").time()))},
            )

        created_user = await auth_service.register(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
        )

        return UserResponse.model_validate(created_user)

    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        client_ip = http_request.client.host if http_request.client else "unknown"

        tokens = await auth_service.login(
            email=request.email,
            password=request.password,
            client_ip=client_ip,
        )

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    http_request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        client_ip = http_request.client.host if http_request.client else "unknown"
        rate_limiter = get_auth_rate_limiter()
        is_allowed, remaining, reset_time = await rate_limiter.check_refresh_rate_limit(client_ip)

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many token refresh attempts. Please try again later.",
                headers={"Retry-After": str(int(reset_time - __import__("time").time()))},
            )

        tokens = await auth_service.refresh_access_token(request.refresh_token)

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.put("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        rate_limiter = get_auth_rate_limiter()
        is_allowed, remaining, reset_time = await rate_limiter.check_password_change_rate_limit(
            str(current_user_id)
        )

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password change attempts. Please try again later.",
                headers={"Retry-After": str(int(reset_time - __import__("time").time()))},
            )

        await auth_service.change_password(
            user_id=current_user_id,
            current_password=request.current_password,
            new_password=request.new_password,
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        updated_user = await auth_service.update_profile(
            user_id=current_user_id,
            full_name=request.full_name,
        )

        return UserResponse.model_validate(updated_user)

    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user=Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user_id: UUID = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        await auth_service.delete_account(user_id=current_user_id)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
