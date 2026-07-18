"""Redis Streams helpers: produce, consume, reclaim, DLQ, stats."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value) if value is not None else ""


async def ensure_consumer_group(redis: Redis | None = None) -> None:
    settings = get_settings()
    if redis is None:
        from app.db.redis import get_redis

        redis = get_redis()
    try:
        await redis.xgroup_create(
            name=settings.event_stream_name,
            groupname=settings.event_consumer_group,
            id="0",
            mkstream=True,
        )
        logger.info(
            "consumer_group_created",
            stream=settings.event_stream_name,
            group=settings.event_consumer_group,
        )
    except Exception as exc:  # noqa: BLE001
        if "BUSYGROUP" not in str(exc):
            raise

    # Ensure DLQ stream exists (empty create via XADD+DEL is heavy; XGROUP is enough via first write).
    try:
        # Touch stream metadata; length check creates nothing but is safe.
        await redis.xlen(settings.event_dlq_stream_name)
    except Exception:  # noqa: BLE001
        pass


async def enqueue_event(payload: dict[str, Any], redis: Redis | None = None) -> str:
    settings = get_settings()
    if redis is None:
        from app.db.redis import get_redis

        redis = get_redis()
    fields = {"data": json.dumps(payload, default=str)}
    # Approximate MAXLEN keeps memory bounded under burst (big-tech stream hygiene).
    message_id = await redis.xadd(
        settings.event_stream_name,
        fields,
        maxlen=settings.event_stream_maxlen,
        approximate=True,
    )
    return message_id


def _parse_fields(fields: dict[Any, Any]) -> dict[str, Any]:
    raw = fields.get("data") or fields.get(b"data")
    if isinstance(raw, bytes):
        raw = raw.decode()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw, "_parse_error": True}


async def read_events_batch(
    redis: Redis,
    *,
    count: int | None = None,
    block_ms: int = 2000,
) -> list[tuple[str, dict[str, Any]]]:
    """Read new messages (>) from the consumer group."""
    settings = get_settings()
    count = count or settings.batch_size
    results = await redis.xreadgroup(
        groupname=settings.event_consumer_group,
        consumername=settings.event_consumer_name,
        streams={settings.event_stream_name: ">"},
        count=count,
        block=block_ms,
    )
    messages: list[tuple[str, dict[str, Any]]] = []
    if not results:
        return messages
    for _stream, entries in results:
        for message_id, fields in entries:
            mid = _decode(message_id)
            messages.append((mid, _parse_fields(fields)))
    return messages


async def reclaim_stale_messages(
    redis: Redis,
    *,
    count: int | None = None,
) -> list[tuple[str, dict[str, Any], int]]:
    """
    XAUTOCLAIM messages stuck in PEL longer than min_idle_ms.

    Returns list of (message_id, payload, delivery_count).
    delivery_count comes from XPENDING detail when available (default 1).
    """
    settings = get_settings()
    count = count or settings.batch_size
    try:
        # redis-py: xautoclaim(name, groupname, consumername, min_idle_time, start_id, count=...)
        claimed = await redis.xautoclaim(
            name=settings.event_stream_name,
            groupname=settings.event_consumer_group,
            consumername=settings.event_consumer_name,
            min_idle_time=settings.event_claim_min_idle_ms,
            start_id="0-0",
            count=count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("xautoclaim_failed", error=str(exc))
        return []

    # Response shape: (next_start_id, [(id, fields), ...], deleted_ids?)
    entries: list[Any] = []
    if isinstance(claimed, (list, tuple)) and len(claimed) >= 2:
        entries = claimed[1] or []

    # Build delivery count map via XPENDING
    delivery_counts: dict[str, int] = {}
    try:
        pending = await redis.xpending_range(
            name=settings.event_stream_name,
            groupname=settings.event_consumer_group,
            min="-",
            max="+",
            count=count,
        )
        for item in pending or []:
            # item may be dict-like
            if isinstance(item, dict):
                mid = _decode(item.get("message_id") or item.get("message") or "")
                times = int(item.get("times_delivered") or item.get("delivery_count") or 1)
            else:
                # tuple form: (message_id, consumer, time_since_delivered, times_delivered)
                mid = _decode(item[0]) if item else ""
                times = int(item[3]) if len(item) > 3 else 1
            if mid:
                delivery_counts[mid] = times
    except Exception:  # noqa: BLE001
        pass

    out: list[tuple[str, dict[str, Any], int]] = []
    for message_id, fields in entries:
        mid = _decode(message_id)
        out.append((mid, _parse_fields(fields or {}), delivery_counts.get(mid, 1)))
    if out:
        logger.info("reclaimed_stale_messages", count=len(out))
    return out


async def dead_letter(
    redis: Redis,
    *,
    message_id: str,
    payload: dict[str, Any],
    reason: str,
    delivery_count: int,
) -> None:
    """Move poison message to DLQ stream and ACK original so PEL does not grow forever."""
    settings = get_settings()
    body = {
        "original_id": message_id,
        "reason": reason,
        "delivery_count": str(delivery_count),
        "data": json.dumps(payload, default=str),
    }
    await redis.xadd(
        settings.event_dlq_stream_name,
        body,
        maxlen=settings.event_dlq_maxlen,
        approximate=True,
    )
    await redis.xack(
        settings.event_stream_name,
        settings.event_consumer_group,
        message_id,
    )
    # Optional: remove from main stream to free memory
    try:
        await redis.xdel(settings.event_stream_name, message_id)
    except Exception:  # noqa: BLE001
        pass
    logger.warning(
        "event_dead_lettered",
        message_id=message_id,
        reason=reason,
        delivery_count=delivery_count,
    )


async def ack_messages(redis: Redis, message_ids: list[str]) -> None:
    if not message_ids:
        return
    settings = get_settings()
    await redis.xack(
        settings.event_stream_name,
        settings.event_consumer_group,
        *message_ids,
    )


async def stream_stats(redis: Redis | None = None) -> dict[str, Any]:
    settings = get_settings()
    if redis is None:
        from app.db.redis import get_redis

        redis = get_redis()
    length = await redis.xlen(settings.event_stream_name)
    dlq_length = 0
    try:
        dlq_length = int(await redis.xlen(settings.event_dlq_stream_name))
    except Exception:  # noqa: BLE001
        pass
    pending = 0
    lag = None
    try:
        groups = await redis.xinfo_groups(settings.event_stream_name)
        for g in groups:
            name = g.get("name") or g.get(b"name")
            if isinstance(name, bytes):
                name = name.decode()
            if name == settings.event_consumer_group:
                pending = int(g.get("pending") or g.get(b"pending") or 0)
                lag_val = g.get("lag", g.get(b"lag"))
                if lag_val is not None:
                    lag = int(lag_val)
    except Exception:  # noqa: BLE001
        pass
    return {
        "stream": settings.event_stream_name,
        "group": settings.event_consumer_group,
        "length": int(length),
        "pending": pending,
        "lag": lag,
        "dlq_length": dlq_length,
    }


def serialize_event_payload(
    *,
    event_id: UUID,
    user_id: UUID | None,
    session_id: str,
    event_type: str,
    properties: dict,
    client_ts: str | None,
    ip_hash: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    return {
        "event_id": str(event_id),
        "user_id": str(user_id) if user_id else None,
        "session_id": session_id,
        "event_type": event_type,
        "properties": properties,
        "client_ts": client_ts,
        "ip_hash": ip_hash,
        "user_agent": user_agent,
    }
