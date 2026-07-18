from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DAUResponse(BaseModel):
    metric_date: date
    dau: int
    source: str  # cache | database | computed
    computed_at: datetime | None = None


class FunnelStep(BaseModel):
    step: str
    count: int
    conversion_from_previous: float | None = None


class FunnelResponse(BaseModel):
    funnel_name: str = "default"
    window_start: date
    window_end: date
    steps: list[FunnelStep]
    source: str
    computed_at: datetime | None = None


class RetentionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cohort_date: date
    cohort_size: int
    d1_retained: int
    d7_retained: int
    d1_rate: Decimal
    d7_rate: Decimal
    source: str
    computed_at: datetime | None = None


class RealtimeEPMResponse(BaseModel):
    events_per_minute: float
    window_seconds: int = Field(default=60)
    source: str


class MetricsSummary(BaseModel):
    dau_today: int | None = None
    events_total: int | None = None
    events_last_minute: float | None = None
    funnel: FunnelResponse | None = None
    retention: RetentionResponse | None = None
