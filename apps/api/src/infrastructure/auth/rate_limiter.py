import time
from typing import Optional, Tuple

import redis.asyncio as aioredis
from redis.asyncio import Redis

from src.core.config import settings


class AuthRateLimiter:
    LOGIN_ATTEMPTS_PER_MINUTE = 5
    REGISTER_ATTEMPTS_PER_MINUTE = 3
    REFRESH_TOKEN_ATTEMPTS_PER_MINUTE = 10
    PASSWORD_CHANGE_ATTEMPTS_PER_MINUTE = 5

    FAILED_LOGIN_THRESHOLD = 5
    ACCOUNT_LOCKOUT_MINUTES = 15

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url
        self._redis_client: Optional[Redis] = None

    async def get_redis_client(self) -> Redis:
        if self._redis_client is None:
            self._redis_client = aioredis.from_url(
                self.redis_url, decode_responses=True, encoding="utf-8"
            )
        return self._redis_client

    async def check_login_rate_limit(self, client_ip: str) -> Tuple[bool, int, int]:
        return await self._check_rate_limit(
            f"auth:login:{client_ip}",
            self.LOGIN_ATTEMPTS_PER_MINUTE,
            60,
        )

    async def check_register_rate_limit(self, client_ip: str) -> Tuple[bool, int, int]:
        return await self._check_rate_limit(
            f"auth:register:{client_ip}",
            self.REGISTER_ATTEMPTS_PER_MINUTE,
            60,
        )

    async def check_refresh_rate_limit(self, client_ip: str) -> Tuple[bool, int, int]:
        return await self._check_rate_limit(
            f"auth:refresh:{client_ip}",
            self.REFRESH_TOKEN_ATTEMPTS_PER_MINUTE,
            60,
        )

    async def check_password_change_rate_limit(self, user_id: str) -> Tuple[bool, int, int]:
        return await self._check_rate_limit(
            f"auth:password_change:{user_id}",
            self.PASSWORD_CHANGE_ATTEMPTS_PER_MINUTE,
            60,
        )

    async def record_failed_login(self, user_id: str, client_ip: str) -> Tuple[int, bool]:
        redis_client = await self.get_redis_client()
        key = f"auth:failed_login:{user_id}"

        failed_count = await redis_client.incr(key)
        await redis_client.expire(key, 3600)

        should_lock = failed_count >= self.FAILED_LOGIN_THRESHOLD

        if should_lock:
            lockout_key = f"auth:locked:{user_id}"
            await redis_client.setex(
                lockout_key,
                self.ACCOUNT_LOCKOUT_MINUTES * 60,
                "locked",
            )

        return failed_count, should_lock

    async def reset_failed_login(self, user_id: str) -> None:
        redis_client = await self.get_redis_client()
        await redis_client.delete(f"auth:failed_login:{user_id}")

    async def is_account_locked(self, user_id: str) -> Tuple[bool, int]:
        redis_client = await self.get_redis_client()
        lockout_key = f"auth:locked:{user_id}"

        ttl = await redis_client.ttl(lockout_key)

        if ttl == -1:  # Key exists but no expiry (shouldn't happen)
            return True, self.ACCOUNT_LOCKOUT_MINUTES * 60
        elif ttl == -2:  # Key doesn't exist
            return False, 0
        else:  # Key exists with expiry
            return True, ttl

    async def _check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        redis_client = await self.get_redis_client()
        now = time.time()

        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            count = results[1]

            remaining = max(0, max_requests - count - 1)
            reset_time = int(now + window_seconds)
            is_allowed = count < max_requests

            return is_allowed, remaining, reset_time

        except Exception:
            return True, max_requests, int(time.time() + window_seconds)


_auth_rate_limiter = None


def get_auth_rate_limiter() -> AuthRateLimiter:
    global _auth_rate_limiter
    if _auth_rate_limiter is None:
        _auth_rate_limiter = AuthRateLimiter()
    return _auth_rate_limiter
