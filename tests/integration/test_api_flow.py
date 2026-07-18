"""
Full-stack integration tests against a running API (Docker compose).

Run:
  docker compose exec -e RUN_INTEGRATION=1 -e API_BASE_URL=http://localhost:8000 \
    api pytest tests/integration -q
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION", "0") != "1",
    reason="Set RUN_INTEGRATION=1 with live stack",
)

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE, timeout=30.0) as c:
        yield c


def _login(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_health(client: httpx.Client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_and_me(client: httpx.Client):
    token = _login(client, "client@example.com", "Client123!")
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "client_app"


def test_event_idempotency(client: httpx.Client):
    token = _login(client, "client@example.com", "Client123!")
    headers = {"Authorization": f"Bearer {token}"}
    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "user_id": str(uuid.uuid4()),
        "session_id": "itest-session",
        "event_type": "view",
        "properties": {"source": "pytest"},
    }
    r1 = client.post("/api/v1/events", json=payload, headers=headers)
    assert r1.status_code in (200, 201, 202), r1.text
    r2 = client.post("/api/v1/events", json=payload, headers=headers)
    assert r2.status_code in (200, 202), r2.text
    body = r2.json()
    assert body["deduplicated"] is True


def test_metrics_requires_analyst(client: httpx.Client):
    client_token = _login(client, "client@example.com", "Client123!")
    denied = client.get(
        "/api/v1/metrics/dau",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert denied.status_code == 403

    analyst_token = _login(client, "analyst@example.com", "Analyst123!")
    ok = client.get(
        "/api/v1/metrics/dau",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert ok.status_code == 200
    assert "dau" in ok.json()


def test_admin_queue(client: httpx.Client):
    admin = _login(client, "admin@example.com", "Admin123!")
    resp = client.get(
        "/api/v1/admin/queue",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "stream" in body
    assert "length" in body
