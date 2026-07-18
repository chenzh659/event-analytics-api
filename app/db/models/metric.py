from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    __table_args__ = (
        UniqueConstraint("metric_date", "name", "dim_hash", name="uq_metrics_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dim_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelSnapshot(Base):
    __tablename__ = "funnel_snapshots"
    __table_args__ = (
        UniqueConstraint("window_start", "window_end", "funnel_name", name="uq_funnel_snap"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    funnel_name: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    window_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RetentionSnapshot(Base):
    __tablename__ = "retention_snapshots"
    __table_args__ = (UniqueConstraint("cohort_date", name="uq_retention_cohort"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cohort_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cohort_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    d1_retained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    d7_retained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    d1_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    d7_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
