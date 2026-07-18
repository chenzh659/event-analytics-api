from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app import __version__
from app.api.v1 import api_router
from app.api.v1.health import router as health_router
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.db.redis import close_redis
from app.mq.streams import ensure_consumer_group


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    try:
        await ensure_consumer_group()
    except Exception:  # noqa: BLE001
        # Redis may not be up yet in some local runs; worker will recreate.
        pass
    yield
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "User behavior collection and real-time metrics API. "
            "JWT + RBAC, idempotent event ingest via Redis Streams, "
            "DAU/funnel/retention jobs, Prometheus metrics."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    # Unversioned ops endpoints
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
