from typing import Annotated
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.rbac import Permission
from app.db.models.user import User
from app.deps import DbSession, require_permission
from app.schemas.metric import (
    DAUResponse,
    FunnelResponse,
    MetricsSummary,
    RealtimeEPMResponse,
    RetentionResponse)
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dau", response_model=DAUResponse)
async def get_dau(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.METRICS_READ))],
    metric_date: date | None = Query(default=None),
) -> DAUResponse:
    return await MetricsService(db).get_dau(metric_date)


@router.get("/funnel", response_model=FunnelResponse)
async def get_funnel(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.METRICS_READ))],
    window_start: date | None = Query(default=None),
    window_end: date | None = Query(default=None),
) -> FunnelResponse:
    return await MetricsService(db).get_funnel(window_start, window_end)


@router.get("/retention", response_model=RetentionResponse)
async def get_retention(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.METRICS_READ))],
    cohort_date: date | None = Query(default=None),
) -> RetentionResponse:
    return await MetricsService(db).get_retention(cohort_date)


@router.get("/realtime/events-per-minute", response_model=RealtimeEPMResponse)
async def get_realtime_epm(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.METRICS_READ))],
) -> RealtimeEPMResponse:
    return await MetricsService(db).get_realtime_epm()


@router.get("/summary", response_model=MetricsSummary)
async def get_summary(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.METRICS_READ))],
) -> MetricsSummary:
    return await MetricsService(db).get_summary()
