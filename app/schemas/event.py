from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.event import EventType


class EventCreate(BaseModel):
    event_id: UUID
    user_id: UUID | None = None
    session_id: str = Field(min_length=1, max_length=64)
    event_type: EventType
    properties: dict[str, Any] = Field(default_factory=dict)
    client_ts: datetime | None = None


class EventBatchCreate(BaseModel):
    events: list[EventCreate] = Field(min_length=1, max_length=100)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    user_id: UUID | None
    session_id: str
    event_type: str
    properties: dict[str, Any]
    client_ts: datetime | None
    server_ts: datetime


class EventIngestResult(BaseModel):
    event_id: UUID
    status: str  # accepted | deduplicated | queued
    deduplicated: bool = False
    mode: str


class EventBatchResult(BaseModel):
    results: list[EventIngestResult]
    accepted: int
    deduplicated: int
