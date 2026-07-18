#!/usr/bin/env bash
set -euo pipefail

echo "[api] waiting for database..."
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
    # asyncpg does not understand the +asyncpg scheme
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    for i in range(60):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            print("[api] database ready")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[api] db not ready ({i}): {exc}")
            await asyncio.sleep(1)
    sys.exit(1)


asyncio.run(wait())
PY

echo "[api] running migrations..."
alembic upgrade head

echo "[api] seeding roles/users..."
python -m scripts.seed

echo "[api] starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
