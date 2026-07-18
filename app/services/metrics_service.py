"""Metrics computation and cache-aside reads."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models.event import Event
from app.db.models.metric import FunnelSnapshot, MetricsDaily, RetentionSnapshot
from app.db.redis import get_redis
from app.observability.metrics import CACHE_OPS, DAU_HLL
from app.schemas.metric import (
    DAUResponse,
    FunnelResponse,
    FunnelStep,
    MetricsSummary,
    RealtimeEPMResponse,
    RetentionResponse,
)

logger = get_logger(__name__)

FUNNEL_ORDER = ("view", "search", "add_to_cart", "order")


class MetricsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.redis = get_redis()

    async def _cache_get(self, key: str) -> str | None:
        val = await self.redis.get(key)
        CACHE_OPS.labels(op="get", result="hit" if val else "miss").inc()
        return val

    async def _cache_set(self, key: str, value: str, ttl: int) -> None:
        await self.redis.set(key, value, ex=ttl)
        CACHE_OPS.labels(op="set", result="ok").inc()

    async def compute_dau(self, metric_date: date) -> int:
        """Count distinct users with any event on metric_date (UTC)."""
        # Advisory lock to avoid concurrent recompute races for same date.
        lock_key = int(metric_date.strftime("%Y%m%d"))
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

        start = datetime(metric_date.year, metric_date.month, metric_date.day, tzinfo=UTC)
        end = start + timedelta(days=1)
        result = await self.db.execute(
            select(func.count(func.distinct(Event.user_id))).where(
                Event.server_ts >= start,
                Event.server_ts < end,
                Event.user_id.is_not(None),
            )
        )
        dau = int(result.scalar_one() or 0)

        stmt = (
            insert(MetricsDaily)
            .values(
                metric_date=metric_date,
                name="dau",
                dimensions={},
                dim_hash="",
                value=dau,
                computed_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                constraint="uq_metrics_daily",
                set_={"value": dau, "computed_at": datetime.now(UTC)},
            )
        )
        await self.db.execute(stmt)
        await self._cache_set(
            f"metrics:dau:{metric_date.isoformat()}",
            json.dumps({"dau": dau, "computed_at": datetime.now(UTC).isoformat()}),
            self.settings.cache_ttl_dau,
        )
        return dau

    async def get_approx_dau_hll(self, metric_date: date | None = None) -> int:
        """O(1) approximate DAU via Redis HyperLogLog (updated on ingest path)."""
        metric_date = metric_date or datetime.now(UTC).date()
        key = f"hll:dau:{metric_date.strftime('%Y%m%d')}"
        estimate = int(await self.redis.pfcount(key) or 0)
        if metric_date == datetime.now(UTC).date():
            DAU_HLL.set(estimate)
        return estimate

    async def get_dau(self, metric_date: date | None = None) -> DAUResponse:
        metric_date = metric_date or datetime.now(UTC).date()
        cache_key = f"metrics:dau:{metric_date.isoformat()}"
        cached = await self._cache_get(cache_key)
        if cached:
            data = json.loads(cached)
            return DAUResponse(
                metric_date=metric_date,
                dau=int(data["dau"]),
                source="cache",
                computed_at=datetime.fromisoformat(data["computed_at"])
                if data.get("computed_at")
                else None,
            )

        result = await self.db.execute(
            select(MetricsDaily).where(
                MetricsDaily.metric_date == metric_date,
                MetricsDaily.name == "dau",
            )
        )
        row = result.scalar_one_or_none()
        if row:
            payload = json.dumps(
                {"dau": int(row.value), "computed_at": row.computed_at.isoformat()}
            )
            await self._cache_set(cache_key, payload, self.settings.cache_ttl_dau)
            return DAUResponse(
                metric_date=metric_date,
                dau=int(row.value),
                source="database",
                computed_at=row.computed_at,
            )

        dau = await self.compute_dau(metric_date)
        return DAUResponse(
            metric_date=metric_date,
            dau=dau,
            source="computed",
            computed_at=datetime.now(UTC),
        )

    async def compute_funnel(self, window_start: date, window_end: date) -> FunnelSnapshot:
        lock_key = int(window_start.strftime("%Y%m%d")) + 1_000_000
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

        start = datetime(
            window_start.year, window_start.month, window_start.day, tzinfo=UTC
        )
        end = datetime(window_end.year, window_end.month, window_end.day, tzinfo=UTC) + timedelta(
            days=1
        )

        # Distinct users per event type in window.
        counts: dict[str, int] = {}
        for step in FUNNEL_ORDER:
            result = await self.db.execute(
                select(func.count(func.distinct(Event.user_id))).where(
                    Event.server_ts >= start,
                    Event.server_ts < end,
                    Event.event_type == step,
                    Event.user_id.is_not(None),
                )
            )
            counts[step] = int(result.scalar_one() or 0)

        snap = FunnelSnapshot(
            funnel_name="default",
            window_start=window_start,
            window_end=window_end,
            view_count=counts["view"],
            search_count=counts["search"],
            cart_count=counts["add_to_cart"],
            order_count=counts["order"],
            computed_at=datetime.now(UTC),
        )
        stmt = (
            insert(FunnelSnapshot)
            .values(
                funnel_name=snap.funnel_name,
                window_start=snap.window_start,
                window_end=snap.window_end,
                view_count=snap.view_count,
                search_count=snap.search_count,
                cart_count=snap.cart_count,
                order_count=snap.order_count,
                computed_at=snap.computed_at,
            )
            .on_conflict_do_update(
                constraint="uq_funnel_snap",
                set_={
                    "view_count": snap.view_count,
                    "search_count": snap.search_count,
                    "cart_count": snap.cart_count,
                    "order_count": snap.order_count,
                    "computed_at": snap.computed_at,
                },
            )
        )
        await self.db.execute(stmt)

        cache_payload = {
            "view": snap.view_count,
            "search": snap.search_count,
            "add_to_cart": snap.cart_count,
            "order": snap.order_count,
            "computed_at": snap.computed_at.isoformat(),
        }
        await self._cache_set(
            f"metrics:funnel:{window_start}:{window_end}",
            json.dumps(cache_payload),
            self.settings.cache_ttl_funnel,
        )
        return snap

    def _funnel_to_response(
        self,
        *,
        window_start: date,
        window_end: date,
        view: int,
        search: int,
        cart: int,
        order: int,
        source: str,
        computed_at: datetime | None,
    ) -> FunnelResponse:
        raw = [view, search, cart, order]
        steps: list[FunnelStep] = []
        for i, (name, count) in enumerate(zip(FUNNEL_ORDER, raw, strict=True)):
            conv = None
            if i > 0 and raw[i - 1] > 0:
                conv = round(count / raw[i - 1], 4)
            steps.append(FunnelStep(step=name, count=count, conversion_from_previous=conv))
        return FunnelResponse(
            window_start=window_start,
            window_end=window_end,
            steps=steps,
            source=source,
            computed_at=computed_at,
        )

    async def get_funnel(
        self, window_start: date | None = None, window_end: date | None = None
    ) -> FunnelResponse:
        today = datetime.now(UTC).date()
        window_end = window_end or today
        window_start = window_start or (window_end - timedelta(days=6))

        cache_key = f"metrics:funnel:{window_start}:{window_end}"
        cached = await self._cache_get(cache_key)
        if cached:
            data = json.loads(cached)
            return self._funnel_to_response(
                window_start=window_start,
                window_end=window_end,
                view=data["view"],
                search=data["search"],
                cart=data["add_to_cart"],
                order=data["order"],
                source="cache",
                computed_at=datetime.fromisoformat(data["computed_at"])
                if data.get("computed_at")
                else None,
            )

        result = await self.db.execute(
            select(FunnelSnapshot).where(
                FunnelSnapshot.window_start == window_start,
                FunnelSnapshot.window_end == window_end,
                FunnelSnapshot.funnel_name == "default",
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return self._funnel_to_response(
                window_start=window_start,
                window_end=window_end,
                view=row.view_count,
                search=row.search_count,
                cart=row.cart_count,
                order=row.order_count,
                source="database",
                computed_at=row.computed_at,
            )

        snap = await self.compute_funnel(window_start, window_end)
        return self._funnel_to_response(
            window_start=window_start,
            window_end=window_end,
            view=snap.view_count,
            search=snap.search_count,
            cart=snap.cart_count,
            order=snap.order_count,
            source="computed",
            computed_at=snap.computed_at,
        )

    async def compute_retention(self, cohort_date: date) -> RetentionSnapshot:
        lock_key = int(cohort_date.strftime("%Y%m%d")) + 2_000_000
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

        day0 = datetime(cohort_date.year, cohort_date.month, cohort_date.day, tzinfo=UTC)
        day1 = day0 + timedelta(days=1)
        day2 = day0 + timedelta(days=2)
        day8 = day0 + timedelta(days=8)

        # Cohort = users with first-ever event on cohort_date.
        first_event = (
            select(
                Event.user_id.label("uid"),
                func.min(Event.server_ts).label("first_ts"),
            )
            .where(Event.user_id.is_not(None))
            .group_by(Event.user_id)
            .subquery()
        )
        cohort_q = await self.db.execute(
            select(first_event.c.uid).where(
                first_event.c.first_ts >= day0,
                first_event.c.first_ts < day1,
            )
        )
        cohort_ids = [row[0] for row in cohort_q.all()]
        cohort_size = len(cohort_ids)
        if cohort_size == 0:
            d1_retained = 0
            d7_retained = 0
        else:
            d1_q = await self.db.execute(
                select(func.count(func.distinct(Event.user_id))).where(
                    Event.user_id.in_(cohort_ids),
                    Event.server_ts >= day1,
                    Event.server_ts < day2,
                )
            )
            d1_retained = int(d1_q.scalar_one() or 0)
            d7_q = await self.db.execute(
                select(func.count(func.distinct(Event.user_id))).where(
                    Event.user_id.in_(cohort_ids),
                    Event.server_ts >= day0 + timedelta(days=7),
                    Event.server_ts < day8,
                )
            )
            d7_retained = int(d7_q.scalar_one() or 0)

        d1_rate = Decimal(d1_retained) / Decimal(cohort_size) if cohort_size else Decimal("0")
        d7_rate = Decimal(d7_retained) / Decimal(cohort_size) if cohort_size else Decimal("0")
        now = datetime.now(UTC)

        stmt = (
            insert(RetentionSnapshot)
            .values(
                cohort_date=cohort_date,
                cohort_size=cohort_size,
                d1_retained=d1_retained,
                d7_retained=d7_retained,
                d1_rate=d1_rate,
                d7_rate=d7_rate,
                computed_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_retention_cohort",
                set_={
                    "cohort_size": cohort_size,
                    "d1_retained": d1_retained,
                    "d7_retained": d7_retained,
                    "d1_rate": d1_rate,
                    "d7_rate": d7_rate,
                    "computed_at": now,
                },
            )
        )
        await self.db.execute(stmt)

        payload = {
            "cohort_size": cohort_size,
            "d1_retained": d1_retained,
            "d7_retained": d7_retained,
            "d1_rate": str(d1_rate),
            "d7_rate": str(d7_rate),
            "computed_at": now.isoformat(),
        }
        await self._cache_set(
            f"metrics:retention:{cohort_date.isoformat()}",
            json.dumps(payload),
            self.settings.cache_ttl_retention,
        )
        return RetentionSnapshot(
            cohort_date=cohort_date,
            cohort_size=cohort_size,
            d1_retained=d1_retained,
            d7_retained=d7_retained,
            d1_rate=d1_rate,
            d7_rate=d7_rate,
            computed_at=now,
        )

    async def get_retention(self, cohort_date: date | None = None) -> RetentionResponse:
        today = datetime.now(UTC).date()
        # Default: cohort from 8 days ago so D7 is complete.
        cohort_date = cohort_date or (today - timedelta(days=8))
        cache_key = f"metrics:retention:{cohort_date.isoformat()}"
        cached = await self._cache_get(cache_key)
        if cached:
            data = json.loads(cached)
            return RetentionResponse(
                cohort_date=cohort_date,
                cohort_size=data["cohort_size"],
                d1_retained=data["d1_retained"],
                d7_retained=data["d7_retained"],
                d1_rate=Decimal(data["d1_rate"]),
                d7_rate=Decimal(data["d7_rate"]),
                source="cache",
                computed_at=datetime.fromisoformat(data["computed_at"])
                if data.get("computed_at")
                else None,
            )

        result = await self.db.execute(
            select(RetentionSnapshot).where(RetentionSnapshot.cohort_date == cohort_date)
        )
        row = result.scalar_one_or_none()
        if row:
            return RetentionResponse(
                cohort_date=row.cohort_date,
                cohort_size=row.cohort_size,
                d1_retained=row.d1_retained,
                d7_retained=row.d7_retained,
                d1_rate=row.d1_rate,
                d7_rate=row.d7_rate,
                source="database",
                computed_at=row.computed_at,
            )

        snap = await self.compute_retention(cohort_date)
        return RetentionResponse(
            cohort_date=snap.cohort_date,
            cohort_size=snap.cohort_size,
            d1_retained=snap.d1_retained,
            d7_retained=snap.d7_retained,
            d1_rate=snap.d1_rate,
            d7_rate=snap.d7_rate,
            source="computed",
            computed_at=snap.computed_at,
        )

    async def get_realtime_epm(self) -> RealtimeEPMResponse:
        cache_key = "metrics:rt:epm"
        cached = await self._cache_get(cache_key)
        if cached:
            data = json.loads(cached)
            return RealtimeEPMResponse(
                events_per_minute=float(data["epm"]),
                source="cache",
            )

        since = datetime.now(UTC) - timedelta(seconds=60)
        result = await self.db.execute(
            select(func.count()).select_from(Event).where(Event.server_ts >= since)
        )
        count = int(result.scalar_one() or 0)
        epm = float(count)  # already per 60s window
        await self._cache_set(
            cache_key,
            json.dumps({"epm": epm}),
            self.settings.cache_ttl_realtime,
        )
        return RealtimeEPMResponse(events_per_minute=epm, source="database")

    async def get_summary(self) -> MetricsSummary:
        today = datetime.now(UTC).date()
        dau = await self.get_dau(today)
        # Side-channel approx metric for dashboards / SRE (not the source of truth).
        await self.get_approx_dau_hll(today)
        epm = await self.get_realtime_epm()
        funnel = await self.get_funnel()
        total_q = await self.db.execute(select(func.count()).select_from(Event))
        total = int(total_q.scalar_one() or 0)
        retention = None
        try:
            retention = await self.get_retention()
        except Exception:  # noqa: BLE001
            logger.warning("retention_summary_failed")
        return MetricsSummary(
            dau_today=dau.dau,
            events_total=total,
            events_last_minute=epm.events_per_minute,
            funnel=funnel,
            retention=retention,
        )

    async def cleanup_idempotency(self, older_than_hours: int = 48) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = await self.db.execute(
            text("DELETE FROM idempotency_keys WHERE expires_at < :cutoff RETURNING id"),
            {"cutoff": cutoff},
        )
        rows = result.fetchall()
        return len(rows)
