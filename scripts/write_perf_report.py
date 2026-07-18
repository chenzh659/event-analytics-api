"""Write performance report from Locust CSV stats. Never invents numbers."""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path


def load_stats(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt(val: str | None, digits: int = 2) -> str:
    if val is None or val == "":
        return "TBD"
    try:
        return f"{float(val):.{digits}f}"
    except ValueError:
        return val


def build_report(
    rows: list[dict[str, str]],
    *,
    users: str,
    duration: str,
    coverage: str | None,
    notes: str | None,
) -> str:
    # Prefer Aggregated row if present
    agg = None
    for row in rows:
        name = row.get("Name") or row.get("name") or ""
        if name.lower() in {"aggregated", "total"}:
            agg = row
            break
    if agg is None and rows:
        agg = rows[-1]

    def g(key_options: list[str]) -> str | None:
        if not agg:
            return None
        for k in key_options:
            if k in agg and agg[k] not in (None, ""):
                return agg[k]
        return None

    rps = g(["Requests/s", "Requests/s ", "Request Count"])  # may be count
    # Locust stats CSV columns (modern):
    # Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,
    # Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,
    # 50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
    request_count = g(["Request Count"])
    failure_count = g(["Failure Count"])
    median = g(["Median Response Time", "50%"])
    avg = g(["Average Response Time"])
    p95 = g(["95%"])
    p99 = g(["99%"])
    rps_val = g(["Requests/s"])
    fail_rate = "TBD"
    if request_count and failure_count:
        try:
            rc = float(request_count)
            fc = float(failure_count)
            fail_rate = f"{(fc / rc * 100):.3f}%" if rc else "0%"
        except ValueError:
            pass

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    cov_line = coverage if coverage else "TBD (run: pytest --cov=app)"

    endpoint_table = [
        "| Endpoint / Name | Requests | Failures | Median (ms) | p95 (ms) | RPS |",
        "|-----------------|----------|----------|-------------|----------|-----|",
    ]
    for row in rows:
        name = row.get("Name") or row.get("name") or ""
        if not name:
            continue
        endpoint_table.append(
            "| {name} | {rc} | {fc} | {med} | {p95} | {rps} |".format(
                name=name,
                rc=row.get("Request Count", ""),
                fc=row.get("Failure Count", ""),
                med=fmt(row.get("Median Response Time") or row.get("50%"), 1),
                p95=fmt(row.get("95%"), 1),
                rps=fmt(row.get("Requests/s"), 2),
            )
        )

    notes_block = notes or "No additional notes."

    return f"""# Performance Report

> **Honesty rule:** every number below comes from a real Locust run or pytest-cov.
> Do not hand-edit metrics. Re-run the load test and regenerate this file.

**Generated at:** {now}
**Tool:** Locust (headless)
**Virtual users:** {users}
**Duration:** {duration}
**Source CSV:** measured stats rows = {len(rows)}

## Summary (Aggregated)

| Metric | Value |
|--------|-------|
| Total requests | {request_count or 'TBD'} |
| Failures | {failure_count or 'TBD'} |
| Error rate | {fail_rate} |
| Median latency | {fmt(median, 1)} ms |
| Average latency | {fmt(avg, 1)} ms |
| p95 latency | {fmt(p95, 1)} ms |
| p99 latency | {fmt(p99, 1)} ms |
| Throughput (RPS) | {fmt(rps_val, 2)} |

## Per-endpoint

{chr(10).join(endpoint_table)}

## Test coverage

| Scope | Coverage |
|-------|----------|
| pytest --cov=app | {cov_line} |

## Index / slow-query notes

Run before and after index work:

```bash
docker compose exec postgres psql -U events -d events -f /dev/stdin < scripts/analyze_slow_queries.sql
```

Paste measured `mean_exec_time` / `total_exec_time` comparisons here after real runs.

## Notes

{notes_block}

## How to reproduce

```bash
docker compose up -d --build
# optional: python -m scripts.generate_load_data --days 7 --users 100 --events-per-day 200

locust -f tests/load/locustfile.py --host http://localhost:8000 \\
  --headless -u {users} -r 10 -t {duration} --csv=results/run

pytest -q --cov=app --cov-report=term-missing

python scripts/write_perf_report.py \\
  --csv results/run_stats.csv \\
  --users {users} \\
  --duration {duration} \\
  --out docs/performance-report.md
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build docs/performance-report.md from Locust CSV")
    parser.add_argument("--csv", required=True, type=Path, help="Locust *_stats.csv path")
    parser.add_argument("--out", type=Path, default=Path("docs/performance-report.md"))
    parser.add_argument("--users", default="TBD")
    parser.add_argument("--duration", default="TBD")
    parser.add_argument("--coverage", default=None)
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")

    rows = load_stats(args.csv)
    report = build_report(
        rows,
        users=str(args.users),
        duration=str(args.duration),
        coverage=args.coverage,
        notes=args.notes,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
