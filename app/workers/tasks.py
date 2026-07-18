"""ARQ worker jobs: stream consumer with reclaim/DLQ + metrics cron."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.models.event import Event
from app.db.redis import close_redis, get_redis
from app.db.session import async_session_factory
from app.mq.streams import (
    ack_messages,
    dead_letter,
    ensure_consumer_group,
    read_events_batch,
    reclaim_stale_messages,
    stream_stats,
)
from app.observability.metrics import DLQ_MESSAGES, EVENTS_WRITTEN, STREAM_LAG
from app.services.metrics_service import MetricsService

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    setup_logging()
    await ensure_consumer_group()
    ctx["redis"] = get_redis()
    logger.info("worker_started")


async def shutdown(ctx: dict) -> None:
    await close_redis()
    logger.info("worker_stopped")


async def _persist_event(session, redis, data: dict, settings) -> str:
    """Insert one event. Returns 'inserted' | 'conflict' | 'invalid'."""
    try:
        event_id = UUID(data["event_id"])
    except Exception:  # noqa: BLE001
        return "invalid"
    user_id = UUID(data["user_id"]) if data.get("user_id") else None
    client_ts = None
    if data.get("client_ts"):
        try:
            client_ts = datetime.fromisoformat(data["client_ts"])
        except ValueError:
            client_ts = None
    if not data.get("session_id") or not data.get("event_type"):
        return "invalid"

    stmt = (
        insert(Event)
        .values(
            event_id=event_id,
            user_id=user_id,
            session_id=data["session_id"],
            event_type=data["event_type"],
            properties=data.get("properties") or {},
            client_ts=client_ts,
            server_ts=datetime.now(UTC),
            ip_hash=data.get("ip_hash"),
            user_agent=data.get("user_agent"),
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(Event.event_id)
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        EVENTS_WRITTEN.labels(result="conflict").inc()
        outcome = "conflict"
    else:
        EVENTS_WRITTEN.labels(result="inserted").inc()
        outcome = "inserted"
        # HyperLogLog for approximate realtime DAU (O(1) memory).
        if user_id is not None:
            day = datetime.now(UTC).strftime("%Y%m%d")
            await redis.pfadd(f"hll:dau:{day}", str(user_id))
            await redis.expire(f"hll:dau:{day}", 3 * 86400)
    await redis.set(
        f"idem:{event_id}",
        "done",
        ex=settings.idem_ttl_seconds,
    )
    return outcome


async def process_event_stream(ctx: dict) -> dict:
    """
    Poll Redis Streams, reclaim stuck PEL entries, batch-insert into PostgreSQL.

    Reliability pattern (Kafka / Pulsar style, on Streams):
    1) XREADGROUP new messages
    2) XAUTOCLAIM idle PEL messages
    3) process; on poison after max deliveries → DLQ + ACK
    """
    redis = ctx.get("redis") or get_redis()
    settings = get_settings()

    fresh = await read_events_batch(redis, count=settings.batch_size, block_ms=500)
    reclaimed = await reclaim_stale_messages(redis, count=settings.batch_size)

    # Normalize to (message_id, data, delivery_count)
    work: list[tuple[str, dict, int]] = [(mid, data, 1) for mid, data in fresh]
    work.extend(reclaimed)

    if not work:
        stats = await stream_stats(redis)
        if stats.get("pending") is not None:
            STREAM_LAG.set(stats["pending"])
        return {"processed": 0, "reclaimed": 0}

    inserted = 0
    conflicts = 0
    dead = 0
    ids_to_ack: list[str] = []

    async with async_session_factory() as session:
        for message_id, data, delivery_count in work:
            if data.get("_parse_error") or not data.get("event_id"):
                if delivery_count >= settings.event_max_deliveries:
                    await dead_letter(
                        redis,
                        message_id=message_id,
                        payload=data,
                        reason="invalid_payload",
                        delivery_count=delivery_count,
                    )
                    DLQ_MESSAGES.labels(reason="invalid_payload").inc()
                    dead += 1
                # else leave in PEL for retry
                continue
            try:
                outcome = await _persist_event(session, redis, data, settings)
                if outcome == "invalid":
                    if delivery_count >= settings.event_max_deliveries:
                        await dead_letter(
                            redis,
                            message_id=message_id,
                            payload=data,
                            reason="invalid_event",
                            delivery_count=delivery_count,
                        )
                        DLQ_MESSAGES.labels(reason="invalid_event").inc()
                        dead += 1
                    continue
                if outcome == "inserted":
                    inserted += 1
                else:
                    conflicts += 1
                ids_to_ack.append(message_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "event_process_failed",
                    message_id=message_id,
                    error=str(exc),
                    delivery_count=delivery_count,
                )
                if delivery_count >= settings.event_max_deliveries:
                    await dead_letter(
                        redis,
                        message_id=message_id,
                        payload=data,
                        reason=f"exception:{type(exc).__name__}",
                        delivery_count=delivery_count,
                    )
                    DLQ_MESSAGES.labels(reason="exception").inc()
                    dead += 1
                # else remain in PEL for reclaim
        await session.commit()

    await ack_messages(redis, ids_to_ack)
    stats = await stream_stats(redis)
    if stats.get("pending") is not None:
        STREAM_LAG.set(stats["pending"])
    logger.info(
        "stream_batch_processed",
        inserted=inserted,
        conflicts=conflicts,
        reclaimed=len(reclaimed),
        dead_lettered=dead,
    )
    return {
        "processed": len(ids_to_ack),
        "inserted": inserted,
        "conflicts": conflicts,
        "reclaimed": len(reclaimed),
        "dead_lettered": dead,
    }


async def compute_dau_job(ctx: dict) -> dict:
    today = datetime.now(UTC).date()
    async with async_session_factory() as session:
        service = MetricsService(session)
        value = await service.compute_dau(today)
        await session.commit()
    logger.info("dau_computed", date=str(today), dau=value)
    return {"date": str(today), "dau": value}


async def compute_funnel_job(ctx: dict) -> dict:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=6)
    async with async_session_factory() as session:
        service = MetricsService(session)
        snap = await service.compute_funnel(start, today)
        await session.commit()
    return {
        "window_start": str(start),
        "window_end": str(today),
        "view": snap.view_count,
        "order": snap.order_count,
    }


async def compute_retention_job(ctx: dict) -> dict:
    cohort = datetime.now(UTC).date() - timedelta(days=8)
    async with async_session_factory() as session:
        service = MetricsService(session)
        snap = await service.compute_retention(cohort)
        await session.commit()
    return {
        "cohort_date": str(cohort),
        "cohort_size": snap.cohort_size,
        "d1_rate": str(snap.d1_rate),
        "d7_rate": str(snap.d7_rate),
    }


async def cleanup_job(ctx: dict) -> dict:
    async with async_session_factory() as session:
        service = MetricsService(session)
        deleted = await service.cleanup_idempotency()
        await session.commit()
    return {"deleted_idempotency_keys": deleted}


# WorkerSettings class lives in app.workers.settings so ARQ can load a single
# entrypoint with redis_settings + functions + cron_jobs.
