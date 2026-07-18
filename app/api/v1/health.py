from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.db.redis import get_redis
from app.db.session import engine
from app.schemas.common import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: process is up (k8s livenessProbe). Never checks dependencies."""
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    """Readiness: can serve traffic only if DB + Redis are reachable (k8s readinessProbe)."""
    db_status = "ok"
    redis_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    try:
        redis = get_redis()
        pong = await redis.ping()
        if not pong:
            redis_status = "error"
    except Exception:  # noqa: BLE001
        redis_status = "error"

    ok = db_status == "ok" and redis_status == "ok"
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ok" if ok else "degraded",
        database=db_status,
        redis=redis_status,
    )
