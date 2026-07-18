from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.exceptions import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.rbac import Permission
from app.db.models.user import User
from app.deps import DbSession, client_ip, require_permission
from app.schemas.event import (
    EventBatchCreate,
    EventBatchResult,
    EventCreate,
    EventIngestResult,
    EventRead)
from app.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "",
    response_model=EventIngestResult,
    status_code=status.HTTP_202_ACCEPTED)
async def create_event(
    body: EventCreate,
    request: Request,
    response: Response,
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_WRITE))],
) -> EventIngestResult:
    headers = await enforce_rate_limit(
        request, user_id=str(user.id), event_write=True
    )
    for k, v in headers.items():
        response.headers[k] = v

    service = EventService(db)
    result = await service.ingest_one(
        body,
        ip=client_ip(request),
        user_agent=request.headers.get("User-Agent"))
    if result.deduplicated:
        response.status_code = status.HTTP_200_OK
    elif result.status == "accepted":
        response.status_code = status.HTTP_201_CREATED
    return result


@router.post(
    "/batch",
    response_model=EventBatchResult,
    status_code=status.HTTP_202_ACCEPTED)
async def create_events_batch(
    body: EventBatchCreate,
    request: Request,
    response: Response,
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_BATCH))],
) -> EventBatchResult:
    headers = await enforce_rate_limit(
        request, user_id=str(user.id), event_write=True
    )
    for k, v in headers.items():
        response.headers[k] = v

    service = EventService(db)
    results: list[EventIngestResult] = []
    accepted = 0
    deduplicated = 0
    for item in body.events:
        r = await service.ingest_one(
            item,
            ip=client_ip(request),
            user_agent=request.headers.get("User-Agent"))
        results.append(r)
        if r.deduplicated:
            deduplicated += 1
        else:
            accepted += 1
    return EventBatchResult(results=results, accepted=accepted, deduplicated=deduplicated)


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_READ))],
) -> EventRead:
    service = EventService(db)
    event = await service.get_by_event_id(event_id)
    if event is None:
        raise NotFoundError("Event not found")
    return EventRead.model_validate(event)
