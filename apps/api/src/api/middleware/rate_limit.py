import logging
import time
from typing import Callable, Optional

import redis.asyncio as aioredis
from fastapi import Request, Response, status
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.schemas import ErrorDetail, ErrorResponse
from src.core.config import settings
from src.core.logging import get_correlation_id, log_json, set_correlation_id
from src.infrastructure.auth.jwt_provider import JWTProvider

logger = logging.getLogger("app.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str | None = None, requests_per_minute: int | None = None):
        super().__init__(app)
        self.redis_url = redis_url or settings.redis_url
        self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
        self.window_size = 60
        self._redis_client: Optional[Redis] = None

    async def get_redis_client(self) -> Redis:
        if self._redis_client is None:
            self._redis_client = aioredis.from_url(
                self.redis_url, decode_responses=True, encoding="utf-8"
            )
        return self._redis_client

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ["/health", "/api/v1/health", "/api/v1/readiness"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("Authorization", "")
        user_key = self._extract_user_key(auth_header)
        rate_key = f"rate_limit:user:{user_key}" if user_key else f"rate_limit:ip:{client_ip}"
        correlation_id = (
            getattr(request.state, "correlation_id", None)
            or get_correlation_id()
            or request.headers.get("X-Correlation-ID")
        )
        if correlation_id:
            set_correlation_id(correlation_id)

        try:
            redis_client = await self.get_redis_client()
            is_allowed, remaining, reset_time = await self._check_rate_limit(redis_client, rate_key)

            if not is_allowed:
                error_detail = ErrorDetail(
                    code="RateLimitExceeded",
                    message="Too many requests. Please slow down and try again.",
                    details={
                        "limit": self.requests_per_minute,
                        "remaining": 0,
                        "reset": reset_time,
                    },
                    correlation_id=correlation_id,
                )
                log_json(
                    logger,
                    event="rate_limit.blocked",
                    method=request.method,
                    path=request.url.path,
                    key=rate_key,
                    limit=self.requests_per_minute,
                    reset=reset_time,
                )
                return Response(
                    content=ErrorResponse(error=error_detail).model_dump_json(),
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                        "Retry-After": str(max(0, int(reset_time - time.time()))),
                        **({"X-Correlation-ID": correlation_id} if correlation_id else {}),
                    },
                    media_type="application/json",
                )

            response = await call_next(request)

            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            if correlation_id:
                response.headers["X-Correlation-ID"] = correlation_id

            return response

        except Exception:
            return await call_next(request)

    def _extract_user_key(self, auth_header: str) -> str | None:
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            payload = JWTProvider.verify_token(token)
            return payload.get("sub")
        except Exception:
            return None

    async def _check_rate_limit(self, redis_client, key: str) -> tuple[bool, int, int]:
        now = time.time()

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - self.window_size)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, self.window_size)

        results = await pipe.execute()
        count = results[1]
        remaining = max(0, self.requests_per_minute - count - 1)
        reset_time = int(now + self.window_size)
        is_allowed = count < self.requests_per_minute

        return is_allowed, remaining, reset_time
