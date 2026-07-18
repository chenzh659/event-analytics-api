#!/usr/bin/env bash
set -euo pipefail

echo "[worker] waiting for database..."
python - <<'PY'
import asyncio
import os
import sys

import asyncpg


async def wait() -> None:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://events:events@postgres:5432/events",
    )
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    for i in range(60):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            print("[worker] database ready")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] db not ready ({i}): {exc}")
            await asyncio.sleep(1)
    sys.exit(1)


asyncio.run(wait())
PY

echo "[worker] ensuring stream consumer group..."
python -m scripts.ensure_stream

echo "[worker] starting ARQ..."
exec arq app.workers.settings.WorkerSettings
