"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "event-analytics-api"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    bcrypt_rounds: int = 12

    database_url: str = "postgresql+asyncpg://events:events@localhost:5432/events"
    database_url_sync: str = "postgresql://events:events@localhost:5432/events"
    redis_url: str = "redis://localhost:6379/0"

    ingest_mode: str = "async"  # async | sync
    event_stream_name: str = "stream:events"
    event_dlq_stream_name: str = "stream:events:dlq"
    event_consumer_group: str = "cg:event-writers"
    event_consumer_name: str = "worker-1"
    batch_size: int = 100
    # Reclaim messages stuck in PEL longer than this (ms) — classic Streams reliability pattern.
    event_claim_min_idle_ms: int = 60_000
    # After this many deliveries, message is dead-lettered instead of infinite retry.
    event_max_deliveries: int = 5
    event_stream_maxlen: int = 1_000_000
    event_dlq_maxlen: int = 100_000

    rate_limit_window_seconds: int = 60
    rate_limit_ip: int = 120
    rate_limit_user: int = 300
    rate_limit_events: int = 600

    cache_ttl_dau: int = 300
    cache_ttl_funnel: int = 300
    cache_ttl_retention: int = 600
    cache_ttl_realtime: int = 30
    idem_ttl_seconds: int = 86400

    # Request body size limit (bytes) for ingest endpoints.
    max_request_body_bytes: int = 256 * 1024

    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "Admin123!"
    seed_analyst_email: str = "analyst@example.com"
    seed_analyst_password: str = "Analyst123!"
    seed_client_email: str = "client@example.com"
    seed_client_password: str = "Client123!"

    @property
    def is_async_ingest(self) -> bool:
        return self.ingest_mode.lower() == "async"


@lru_cache
def get_settings() -> Settings:
    return Settings()
