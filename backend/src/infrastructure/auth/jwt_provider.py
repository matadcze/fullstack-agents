from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt

from src.core.config import settings
from src.core.time import utc_now
from src.domain.exceptions import AuthenticationError


class JWTProvider:

    @staticmethod
    def create_access_token(user_id: UUID, expires_delta: Optional[timedelta] = None) -> str:

        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

        expire = utc_now() + expires_delta
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
        }

        encoded_jwt = jwt.encode(
            to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        return encoded_jwt

    @staticmethod
    def create_refresh_token(user_id: UUID, expires_delta: Optional[timedelta] = None) -> str:

        if expires_delta is None:
            expires_delta = timedelta(days=settings.refresh_token_expire_days)

        expire = utc_now() + expires_delta
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh",
        }

        encoded_jwt = jwt.encode(
            to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        return encoded_jwt

    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Dict:

        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )

            # Validate required claims
            required_claims = {"sub", "exp", "type"}
            if not all(claim in payload for claim in required_claims):
                raise AuthenticationError("Token missing required claims")

            # Validate token type
            if payload.get("type") != token_type:
                raise AuthenticationError(f"Invalid token type. Expected {token_type}")

            # Validate expiration with timezone-aware comparison
            exp_timestamp = payload.get("exp")
            if exp_timestamp is None:
                raise AuthenticationError("Token missing expiration")

            exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            if now > exp_datetime:
                raise AuthenticationError("Token has expired")

            # Validate nbf (not before) claim if present
            if "nbf" in payload:
                nbf_timestamp = payload.get("nbf")
                nbf_datetime = datetime.fromtimestamp(nbf_timestamp, tz=timezone.utc)
                if now < nbf_datetime:
                    raise AuthenticationError("Token not yet valid")

            return payload

        except ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except JWTError as e:
            raise AuthenticationError(f"Could not validate credentials: {str(e)}")

    @staticmethod
    def get_user_id_from_token(token: str) -> UUID:

        payload = JWTProvider.verify_token(token, token_type="access")
        user_id_str = payload.get("sub")

        if user_id_str is None:
            raise AuthenticationError("Token missing user ID")

        try:
            return UUID(user_id_str)
        except ValueError:
            raise AuthenticationError("Invalid user ID in token")
