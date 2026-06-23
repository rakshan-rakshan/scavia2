"""
Tests for API Rate Limiter.

These tests verify:
1. APIRateLimiter class correctly interacts with Redis to check if a client is rate limited.
2. rate_limit dependency class extracts the correct IP from headers or client address.
3. rate_limit raises HTTPException 429 when rate limited.
4. rate_limit fails open (allows request) and logs warning when Redis is down or raises an exception.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException, Request

from api.utils.rate_limit import APIRateLimiter, rate_limit, api_rate_limiter


class TestAPIRateLimiter:
    """Unit tests for the APIRateLimiter class."""

    @pytest.mark.asyncio
    async def test_is_rate_limited_allowed(self):
        """Verify is_rate_limited returns False when the Lua script returns 1 (request allowed)."""
        limiter = APIRateLimiter()
        mock_redis = AsyncMock()
        # Lua script returns 1 for allowed requests, so eval returns 1
        mock_redis.eval = AsyncMock(return_value=1)
        limiter.redis_client = mock_redis

        result = await limiter.is_rate_limited("test_key", limit=5, period=60)
        assert result is False

        mock_redis.eval.assert_called_once()
        args, kwargs = mock_redis.eval.call_args
        assert args[1] == 1  # numkeys parameter
        assert args[2] == "test_key"  # key parameter

    @pytest.mark.asyncio
    async def test_is_rate_limited_blocked(self):
        """Verify is_rate_limited returns True when the Lua script returns 0 (rate limited)."""
        limiter = APIRateLimiter()
        mock_redis = AsyncMock()
        # Lua script returns 0 for rate limited requests, so eval returns 0
        mock_redis.eval = AsyncMock(return_value=0)
        limiter.redis_client = mock_redis

        result = await limiter.is_rate_limited("test_key", limit=5, period=60)
        assert result is True

    @pytest.mark.asyncio
    async def test_close_connection(self):
        """Verify close closes the Redis client connection and resets it."""
        limiter = APIRateLimiter()
        mock_redis = AsyncMock()
        limiter.redis_client = mock_redis

        await limiter.close()
        mock_redis.close.assert_called_once()
        assert limiter.redis_client is None


class TestRateLimitDependency:
    """Unit tests for the rate_limit FastAPI dependency class."""

    @pytest.mark.asyncio
    async def test_dependency_allows_request(self):
        """Verify rate_limit dependency allows request when not rate limited."""
        with patch.object(
            api_rate_limiter, "is_rate_limited", new_callable=AsyncMock
        ) as mock_is_rate_limited:
            mock_is_rate_limited.return_value = False

            scope = {
                "type": "http",
                "headers": [],
                "client": ("192.168.1.1", 12345),
            }
            request = Request(scope=scope)

            limiter_dep = rate_limit(limit=5, period=60)
            # Should not raise any exception (allows the request)
            await limiter_dep(request)

            mock_is_rate_limited.assert_called_once_with(
                key="rate_limit:ip:192.168.1.1", limit=5, period=60
            )

    @pytest.mark.asyncio
    async def test_dependency_blocks_request(self):
        """Verify rate_limit dependency raises HTTPException 429 when rate limited."""
        with patch.object(
            api_rate_limiter, "is_rate_limited", new_callable=AsyncMock
        ) as mock_is_rate_limited:
            mock_is_rate_limited.return_value = True

            scope = {
                "type": "http",
                "headers": [],
                "client": ("192.168.1.1", 12345),
            }
            request = Request(scope=scope)

            limiter_dep = rate_limit(limit=5, period=60)

            with pytest.raises(HTTPException) as exc_info:
                await limiter_dep(request)

            assert exc_info.value.status_code == 429
            assert exc_info.value.detail == "Too many requests"

    @pytest.mark.asyncio
    async def test_dependency_fails_open_on_redis_exception(self):
        """Verify that if Redis raises an exception, the rate limiter fails open and logs warning."""
        with patch.object(
            api_rate_limiter, "is_rate_limited", new_callable=AsyncMock
        ) as mock_is_rate_limited:
            mock_is_rate_limited.side_effect = Exception("Redis connection failed")

            scope = {
                "type": "http",
                "headers": [],
                "client": ("192.168.1.1", 12345),
            }
            request = Request(scope=scope)

            limiter_dep = rate_limit(limit=5, period=60)

            with patch("api.utils.rate_limit.logger.warning") as mock_warning:
                # Should fail open and not raise any exception
                await limiter_dep(request)

                mock_warning.assert_called_once()
                warning_msg = mock_warning.call_args[0][0]
                assert "Failing open" in warning_msg
                assert "Redis connection failed" in warning_msg

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers,client,expected_ip",
        [
            # X-Forwarded-For header single IP
            (
                [(b"x-forwarded-for", b"203.0.113.195")],
                ("127.0.0.1", 12345),
                "203.0.113.195",
            ),
            # X-Forwarded-For header multiple IPs (takes the first one)
            (
                [
                    (
                        b"x-forwarded-for",
                        b"203.0.113.195, 70.41.3.18, 150.172.238.178",
                    )
                ],
                ("127.0.0.1", 12345),
                "203.0.113.195",
            ),
            # X-Real-IP header
            (
                [(b"x-real-ip", b"198.51.100.1")],
                ("127.0.0.1", 12345),
                "198.51.100.1",
            ),
            # Client host
            ([], ("192.0.2.1", 12345), "192.0.2.1"),
            # No client or headers -> unknown
            ([], None, "unknown"),
        ],
    )
    async def test_dependency_ip_extraction(self, headers, client, expected_ip):
        """Verify that client IP is correctly extracted from request headers and client info."""
        with patch.object(
            api_rate_limiter, "is_rate_limited", new_callable=AsyncMock
        ) as mock_is_rate_limited:
            mock_is_rate_limited.return_value = False

            scope = {
                "type": "http",
                "headers": headers,
                "client": client,
            }
            request = Request(scope=scope)

            limiter_dep = rate_limit(limit=5, period=60)
            await limiter_dep(request)

            mock_is_rate_limited.assert_called_once_with(
                key=f"rate_limit:ip:{expected_ip}", limit=5, period=60
            )
