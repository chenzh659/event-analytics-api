# Performance Report (Template)

> **Honesty rule:** every number below must come from a real Locust run or
> `pytest --cov`. Do not estimate or invent values. Until you run the pipeline,
> leave placeholders as **TBD**.

**Generated at:** TBD  
**Tool:** Locust (headless)  
**Virtual users:** TBD  
**Duration:** TBD  

## Summary (Aggregated)

| Metric | Value |
|--------|-------|
| Total requests | TBD |
| Failures | TBD |
| Error rate | TBD |
| Median latency | TBD ms |
| Average latency | TBD ms |
| p95 latency | TBD ms |
| p99 latency | TBD ms |
| Throughput (RPS) | TBD |

## Per-endpoint

| Endpoint / Name | Requests | Failures | Median (ms) | p95 (ms) | RPS |
|-----------------|----------|----------|-------------|----------|-----|
| TBD | TBD | TBD | TBD | TBD | TBD |

## Test coverage

| Scope | Coverage |
|-------|----------|
| pytest --cov=app | TBD |

## Index / slow-query notes

Paste measured `pg_stat_statements` before/after index changes here after real runs.

## How to produce real numbers

```bash
docker compose up -d --build

# Optional historical data for metrics jobs
docker compose exec api python -m scripts.generate_load_data --days 7 --users 100 --events-per-day 200

# Load test (example: 50 users, 5 minutes)
mkdir -p results
docker compose exec api locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --headless -u 50 -r 10 -t 5m --csv=results/run1

# Coverage
docker compose exec api pytest -q --cov=app --cov-report=term-missing

# Write this report from measured CSV only
docker compose exec api python scripts/write_perf_report.py \
  --csv results/run1_stats.csv \
  --users 50 \
  --duration 5m \
  --out docs/performance-report.md
```
