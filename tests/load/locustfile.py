"""Locust load test. Numbers in docs must come from real runs of this file."""

from __future__ import annotations

import os
import random
import uuid
from datetime import UTC, datetime

from locust import HttpUser, between, task

EVENT_TYPES = ["view", "search", "add_to_cart", "order"]
WEIGHTS = [0.55, 0.25, 0.12, 0.08]

CLIENT_EMAIL = os.getenv("LOAD_CLIENT_EMAIL", "client@example.com")
CLIENT_PASSWORD = os.getenv("LOAD_CLIENT_PASSWORD", "Client123!")
ANALYST_EMAIL = os.getenv("LOAD_ANALYST_EMAIL", "analyst@example.com")
ANALYST_PASSWORD = os.getenv("LOAD_ANALYST_PASSWORD", "Analyst123!")


class EventIngestUser(HttpUser):
    wait_time = between(0.05, 0.2)
    weight = 8

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
            name="auth_login_client",
        )
        if resp.status_code != 200:
            self.token = None
            return
        self.token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user_id = str(uuid.uuid4())
        self.session_id = f"load-{uuid.uuid4().hex[:12]}"

    @task(10)
    def post_event(self) -> None:
        if not getattr(self, "token", None):
            return
        event_id = str(uuid.uuid4())
        payload = {
            "event_id": event_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "event_type": random.choices(EVENT_TYPES, weights=WEIGHTS, k=1)[0],
            "properties": {"source": "locust", "sku": f"sku-{random.randint(1, 500)}"},
            "client_ts": datetime.now(UTC).isoformat(),
        }
        self.client.post(
            "/api/v1/events",
            json=payload,
            headers=self.headers,
            name="POST /api/v1/events",
        )

    @task(1)
    def post_event_idempotent_replay(self) -> None:
        """Send the same event_id twice to exercise dedup path."""
        if not getattr(self, "token", None):
            return
        event_id = str(uuid.uuid4())
        payload = {
            "event_id": event_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "event_type": "view",
            "properties": {"source": "locust-dedup"},
            "client_ts": datetime.now(UTC).isoformat(),
        }
        self.client.post(
            "/api/v1/events",
            json=payload,
            headers=self.headers,
            name="POST /api/v1/events (first)",
        )
        self.client.post(
            "/api/v1/events",
            json=payload,
            headers=self.headers,
            name="POST /api/v1/events (dedup)",
        )


class AnalystUser(HttpUser):
    wait_time = between(1, 3)
    weight = 2

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": ANALYST_EMAIL, "password": ANALYST_PASSWORD},
            name="auth_login_analyst",
        )
        if resp.status_code != 200:
            self.headers = {}
            return
        token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    @task(3)
    def metrics_dau(self) -> None:
        self.client.get("/api/v1/metrics/dau", headers=self.headers, name="GET /metrics/dau")

    @task(2)
    def metrics_funnel(self) -> None:
        self.client.get(
            "/api/v1/metrics/funnel", headers=self.headers, name="GET /metrics/funnel"
        )

    @task(1)
    def metrics_summary(self) -> None:
        self.client.get(
            "/api/v1/metrics/summary", headers=self.headers, name="GET /metrics/summary"
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")
