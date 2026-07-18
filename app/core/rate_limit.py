"""Sliding-window rate limiting with atomic Redis Lua (ZSET).

Interview talking point: fixed windows allow 2x burst at boundaries;
sliding windows count requests in a rolling time range — closer to
API Gateway / Envoy-style limits used in production platforms.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request

from app.config import get_settings
from app.core.exceptions import RateLimitError
from app.db.redis import get_redis
from app.observability.metrics import RATE_LIMIT_HITS

# KEYS[1] = zset key
# ARGV[1] = now_ms, ARGV[2] = window_ms, ARGV[3] = limit, ARGV[4] = member
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local min_score = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, min_score)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local reset_ms = window
  if oldest[2] then
    reset_ms = math.max(0, tonumber(oldest[2]) + window - now)
  end
  return {0, count, math.ceil(reset_ms / 1000)}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, count + 1, math.ceil(window / 1000)}
"""


async def _sliding_window(key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    """Return (allowed, current_count, reset_seconds)."""
    redis = get_redis()
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
    result = await redis.eval(
        _SLIDING_WINDOW_LUA,
        1,
        key,
        str(now_ms),
        str(window_ms),
        str(limit),
        member,
    )
    # result: [allowed(0|1), count, reset_seconds]
    allowed = int(result[0]) == 1
    count = int(result[1])
    reset = int(result[2])
    return allowed, count, reset


async def enforce_rate_limit(
    request: Request,
    *,
    user_id: str | None = None,
    event_write: bool = False,
) -> dict[str, str]:
    settings = get_settings()
    window = settings.rate_limit_window_seconds
    headers: dict[str, str] = {}

    client_ip = request.client.host if request.client else "unknown"
    ip_key = f"rl:sw:ip:{client_ip}"
    allowed, ip_count, ip_ttl = await _sliding_window(
        ip_key, limit=settings.rate_limit_ip, window_seconds=window
    )
    headers["X-RateLimit-Limit-IP"] = str(settings.rate_limit_ip)
    headers["X-RateLimit-Remaining-IP"] = str(max(0, settings.rate_limit_ip - ip_count))
    headers["X-RateLimit-Reset-IP"] = str(ip_ttl)
    headers["X-RateLimit-Policy"] = "sliding-window"
    if not allowed:
        RATE_LIMIT_HITS.labels(scope="ip").inc()
        raise RateLimitError(f"IP rate limit exceeded ({settings.rate_limit_ip}/{window}s)")

    if user_id:
        user_key = f"rl:sw:user:{user_id}"
        allowed, user_count, user_ttl = await _sliding_window(
            user_key, limit=settings.rate_limit_user, window_seconds=window
        )
        headers["X-RateLimit-Limit-User"] = str(settings.rate_limit_user)
        headers["X-RateLimit-Remaining-User"] = str(
            max(0, settings.rate_limit_user - user_count)
        )
        headers["X-RateLimit-Reset-User"] = str(user_ttl)
        if not allowed:
            RATE_LIMIT_HITS.labels(scope="user").inc()
            raise RateLimitError(
                f"User rate limit exceeded ({settings.rate_limit_user}/{window}s)"
            )

    if event_write:
        evt_scope = user_id or client_ip
        evt_key = f"rl:sw:events:{evt_scope}"
        allowed, evt_count, evt_ttl = await _sliding_window(
            evt_key, limit=settings.rate_limit_events, window_seconds=window
        )
        headers["X-RateLimit-Limit-Events"] = str(settings.rate_limit_events)
        headers["X-RateLimit-Remaining-Events"] = str(
            max(0, settings.rate_limit_events - evt_count)
        )
        headers["X-RateLimit-Reset-Events"] = str(evt_ttl)
        if not allowed:
            RATE_LIMIT_HITS.labels(scope="events").inc()
            raise RateLimitError(
                f"Event write rate limit exceeded ({settings.rate_limit_events}/{window}s)"
            )

    return headers
