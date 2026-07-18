from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    database: str
    redis: str


class QueueStats(BaseModel):
    stream: str
    group: str
    length: int
    pending: int
    lag: int | None = None
    dlq_length: int = 0


class JobTriggerResponse(BaseModel):
    job: str
    status: str
    detail: str | None = None
