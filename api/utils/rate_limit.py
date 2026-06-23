import time
import uuid
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from loguru import logger

from api.constants import REDIS_URL


class APIRateLimiter:
    """Sliding window rate limiter for API endpoints using Redis."""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self.redis_client is None:
            self.redis_client = await aioredis.from_url(
                REDIS_URL, decode_responses=True
            )
        return self.redis_client

    async def is_rate_limited(self, key: str, limit: int, period: int) -> bool:
        """
        Check if the key has exceeded the limit in the sliding window period.
        Returns True if rate limited, False if request is allowed.
        """
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - period
        member = f"{now}_{uuid.uuid4().hex[:8]}"

        # Lua script for atomic sliding window rate limiting.
        # Returns 1 if allowed, 0 if rate limited.
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local max_requests = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])
        local member = ARGV[5]

        -- Remove timestamps older than window
        redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

        -- Count requests in current window
        local current_requests = redis.call('ZCARD', key)

        if current_requests < max_requests then
            -- Add current timestamp with a unique member value
            redis.call('ZADD', key, now, member)
            -- Set expiration on the key to ensure cleanup
            redis.call('EXPIRE', key, ttl)
            return 1
        else
            return 0
        end
        """

        result = await redis_client.eval(
            lua_script, 1, key, now, window_start, limit, period, member
        )
        return result == 0

    async def close(self):
        """Close the Redis client connection."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None


# Global instance of the rate limiter
api_rate_limiter = APIRateLimiter()


class rate_limit:
    """FastAPI dependency class for applying rate limits to endpoints based on client IP."""

    def __init__(self, limit: int, period: int):
        self.limit = limit
        self.period = period

    async def __call__(self, request: Request):
        client_ip = None
        if request.client:
            client_ip = request.client.host

        # Extract client IP behind potential reverse proxies
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
        else:
            x_real_ip = request.headers.get("x-real-ip")
            if x_real_ip:
                client_ip = x_real_ip

        client_ip = client_ip or "unknown"
        key = f"rate_limit:ip:{client_ip}"

        try:
            is_limited = await api_rate_limiter.is_rate_limited(
                key=key, limit=self.limit, period=self.period
            )
            if is_limited:
                raise HTTPException(status_code=429, detail="Too many requests")
        except HTTPException:
            # Re-raise FastAPIs HTTPException so that status 429 is propagated
            raise
        except Exception as e:
            # Fail open if Redis is down or has errors
            logger.warning(
                f"Rate limiter exception for IP {client_ip}. Failing open. Error: {e}",
                exc_info=True,
            )
