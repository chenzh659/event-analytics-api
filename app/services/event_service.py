"""Event ingest service: idempotency + sync/async write paths."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models.event import Event
from app.db.redis import get_redis
from app.mq.streams import enqueue_event, serialize_event_payload
from app.observability.metrics import EVENTS_INGESTED
from app.schemas.event import EventCreate, EventIngestResult

logger = get_logger(__name__)


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


class EventService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.redis = get_redis()

    def _idem_key(self, event_id: UUID) -> str:
        return f"idem:{event_id}"

    async def _claim_idempotency(self, event_id: UUID) -> bool:
        """Return True if this call won the claim (new event)."""
        key = self._idem_key(event_id)
        claimed = await self.redis.set(
            key,
            "pending",
            nx=True,
            ex=self.settings.idem_ttl_seconds,
        )
        return bool(claimed)

    async def _mark_done(self, event_id: UUID) -> None:
        await self.redis.set(
            self._idem_key(event_id),
            "done",
            ex=self.settings.idem_ttl_seconds,
            xx=True,
        )

    async def _already_in_db(self, event_id: UUID) -> bool:
        result = await self.db.execute(
            select(Event.id).where(Event.event_id == event_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def ingest_one(
        self,
        payload: EventCreate,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EventIngestResult:
        mode = "async" if self.settings.is_async_ingest else "sync"

        claimed = await self._claim_idempotency(payload.event_id)
        if not claimed:
            # Either concurrent request or replay; check DB for definitive state.
            if await self._already_in_db(payload.event_id):
                EVENTS_INGESTED.labels(mode=mode, result="deduplicated").inc()
                return EventIngestResult(
                    event_id=payload.event_id,
                    status="deduplicated",
                    deduplicated=True,
                    mode=mode,
                )
            # Redis says pending/done but not in DB yet (async in-flight) → treat as dedup
            EVENTS_INGESTED.labels(mode=mode, result="deduplicated").inc()
            return EventIngestResult(
                event_id=payload.event_id,
                status="deduplicated",
                deduplicated=True,
                mode=mode,
            )

        ip_hash = hash_ip(ip)
        client_ts_str = payload.client_ts.isoformat() if payload.client_ts else None

        if self.settings.is_async_ingest:
            body = serialize_event_payload(
                event_id=payload.event_id,
                user_id=payload.user_id,
                session_id=payload.session_id,
                event_type=payload.event_type.value,
                properties=payload.properties,
                client_ts=client_ts_str,
                ip_hash=ip_hash,
                user_agent=user_agent,
            )
            await enqueue_event(body, self.redis)
            # Keep redis key as pending until worker marks done.
            EVENTS_INGESTED.labels(mode=mode, result="accepted").inc()
            return EventIngestResult(
                event_id=payload.event_id,
                status="queued",
                deduplicated=False,
                mode=mode,
            )

        # Sync path: write in request transaction.
        stmt = (
            insert(Event)
            .values(
                event_id=payload.event_id,
                user_id=payload.user_id,
                session_id=payload.session_id,
                event_type=payload.event_type.value,
                properties=payload.properties,
                client_ts=payload.client_ts,
                server_ts=datetime.now(UTC),
                ip_hash=ip_hash,
                user_agent=user_agent,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(Event.event_id)
        )
        result = await self.db.execute(stmt)
        inserted = result.scalar_one_or_none()
        await self._mark_done(payload.event_id)
        if inserted is None:
            EVENTS_INGESTED.labels(mode=mode, result="deduplicated").inc()
            return EventIngestResult(
                event_id=payload.event_id,
                status="deduplicated",
                deduplicated=True,
                mode=mode,
            )
        EVENTS_INGESTED.labels(mode=mode, result="accepted").inc()
        return EventIngestResult(
            event_id=payload.event_id,
            status="accepted",
            deduplicated=False,
            mode=mode,
        )

    async def get_by_event_id(self, event_id: UUID) -> Event | None:
        result = await self.db.execute(select(Event).where(Event.event_id == event_id))
        return result.scalar_one_or_none()
