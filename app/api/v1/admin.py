from typing import Annotated
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.core.rbac import Permission
from app.db.models.user import User
from app.deps import DbSession, require_permission
from app.mq.streams import stream_stats
from app.schemas.auth import UserAdminUpdate, UserRead
from app.schemas.common import JobTriggerResponse, QueueStats
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_user_read(user) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=user.role.name,
        version=user.version,
        created_at=user.created_at)


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[UserRead]:
    users = await UserService(db).list_users(limit=limit, offset=offset)
    return [_to_user_read(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: UUID,
    body: UserAdminUpdate,
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))],
) -> UserRead:
    updated = await UserService(db).update_user(user_id, body)
    return _to_user_read(updated)


@router.get("/queue", response_model=QueueStats)
async def get_queue_stats(
    user: Annotated[User, Depends(require_permission(Permission.QUEUE_READ))],
) -> QueueStats:
    stats = await stream_stats()
    return QueueStats(**stats)


@router.post("/jobs/{job_name}", response_model=JobTriggerResponse)
async def trigger_job(
    job_name: str,
    user: Annotated[User, Depends(require_permission(Permission.JOBS_TRIGGER))],
) -> JobTriggerResponse:
    allowed = {
        "compute_dau_job",
        "compute_funnel_job",
        "compute_retention_job",
        "cleanup_job",
        "process_event_stream",
    }
    if job_name not in allowed:
        return JobTriggerResponse(
            job=job_name, status="rejected", detail="Unknown job name"
        )
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(job_name)
        return JobTriggerResponse(
            job=job_name,
            status="enqueued",
            detail=job.job_id if job else None)
    finally:
        await redis.aclose()
