from fastapi import APIRouter

from app.api.v1 import admin, auth, events, health, metrics

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(events.router)
api_router.include_router(metrics.router)
api_router.include_router(admin.router)
# health under v1 as well for convenience
api_router.include_router(health.router)
