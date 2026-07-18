from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.event import EventCreate
from app.db.models.event import EventType


def test_event_create_schema():
    payload = EventCreate(
        event_id=uuid4(),
        session_id="s1",
        event_type=EventType.VIEW,
        properties={"page": "/home"},
        client_ts=datetime.now(UTC),
    )
    assert payload.event_type == EventType.VIEW
    assert payload.properties["page"] == "/home"
