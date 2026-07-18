"""Prometheus metrics registry."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

EVENTS_INGESTED = Counter(
    "events_ingested_total",
    "Events accepted for ingest",
    ["mode", "result"],  # result: accepted | deduplicated
)

EVENTS_WRITTEN = Counter(
    "events_written_total",
    "Events written to PostgreSQL by worker",
    ["result"],  # inserted | conflict
)

CACHE_OPS = Counter(
    "cache_ops_total",
    "Redis cache operations",
    ["op", "result"],  # hit | miss | set
)

STREAM_LAG = Gauge(
    "event_stream_lag",
    "Approximate pending messages in event stream consumer group",
)

STREAM_DLQ_SIZE = Gauge(
    "event_stream_dlq_size",
    "Messages currently in the dead-letter stream",
)

DLQ_MESSAGES = Counter(
    "event_dlq_messages_total",
    "Messages moved to dead-letter queue",
    ["reason"],
)

RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Rate limit rejections",
    ["scope"],
)

DAU_HLL = Gauge(
    "dau_hll_estimate",
    "HyperLogLog approximate DAU for today (UTC)",
)
