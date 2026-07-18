# Architecture

## Components

| Component | Role |
|-----------|------|
| FastAPI (`api`) | Auth, event ingest, metrics read, admin |
| PostgreSQL 16/17 | Source of truth: users, events, metric snapshots |
| Redis 7 | Cache, **sliding-window rate limit**, HyperLogLog DAU, **Streams MQ + DLQ**, ARQ broker |
| ARQ worker | Stream consumer (**XREADGROUP + XAUTOCLAIM + DLQ**) + cron (DAU / funnel / retention) |
| Prometheus + Grafana | Scrape `/metrics` (cardinality-safe path labels) |

## Data flow

```
Client / Locust
  → FastAPI /api/v1/*
       POST /events
         → JWT + RBAC
         → sliding-window rate limit (Lua ZSET)
         → Redis SET NX (idempotency)
         → async: XADD stream:events (MAXLEN ~) → 202
         → sync (INGEST_MODE=sync): INSERT ON CONFLICT DO NOTHING
       GET /metrics/*
         → cache-aside Redis → snapshots / live SQL
         → optional HLL approx DAU for realtime gauge

stream:events
  → ARQ process_event_stream (~5s)
       → XREADGROUP new messages
       → XAUTOCLAIM idle PEL (> claim_min_idle_ms)
       → batch INSERT ON CONFLICT DO NOTHING
       → PFADD hll:dau:{yyyymmdd}
       → success: XACK; poison after max deliveries: XADD DLQ + XACK
       → update stream lag / DLQ size gauges

ARQ cron
  → compute_dau_job / funnel / retention (advisory lock)
  → cleanup_job
```

## Reliability (message pipeline)

| Concern | Mechanism |
|---------|-----------|
| At-least-once | Consumer group + explicit ACK |
| Stuck consumer | XAUTOCLAIM min-idle reclaim |
| Poison message | delivery_count ≥ max → `stream:events:dlq` |
| Memory bound | Approximate MAXLEN on main + DLQ streams |
| Idempotent write | event_id UNIQUE + ON CONFLICT DO NOTHING |

## Idempotency

Client must supply `event_id` (UUID). Redis key `idem:{event_id}` is claimed with `SET NX`. Replays return `deduplicated: true`. Worker insert uses unique constraint as the final safety net under at-least-once delivery.

## RBAC

| Role | Key permissions |
|------|-----------------|
| `client_app` | events write/batch |
| `analyst` | + metrics read, events read |
| `admin` | + users manage, jobs, queue stats |

## API versioning and probes

- Business APIs: `/api/v1/*`
- **Liveness** `/health` — process up only
- **Readiness** `/ready` — DB + Redis; **503** if degraded
- Metrics: `/metrics` (unversioned)

## Index strategy

- B-tree: `event_id` UNIQUE, `(event_type, server_ts)`, `(user_id, server_ts)` partial
- **BRIN(`server_ts`)** for large time-range scans (DAU / funnel windows)
- GIN on `properties` for JSON filters
- `pg_stat_statements` enabled in Compose for slow-query analysis

## Rate limiting

Sliding window via Redis ZSET + Lua (atomic). Scopes: IP, user, event-write. Headers include `X-RateLimit-Policy: sliding-window`.

## Observability rules

- JSON logs + `X-Request-ID` correlation
- Prometheus path labels **normalized** (`UUID` / numeric → `{id}`) to protect cardinality
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- Body size cap via `MAX_REQUEST_BODY_BYTES`

## Resume / interview notes

See [resume-talk-track.md](resume-talk-track.md).
