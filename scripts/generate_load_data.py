"""Generate synthetic historical events for demo / retention metrics."""

import argparse
import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.db.models.event import Event
from app.db.session import async_session_factory

EVENT_TYPES = ["view", "search", "add_to_cart", "order"]
# Weight toward top of funnel.
WEIGHTS = [0.55, 0.25, 0.12, 0.08]


async def generate(days: int, users: int, events_per_day: int) -> None:
    now = datetime.now(UTC)
    user_ids = [uuid.uuid4() for _ in range(users)]

    async with async_session_factory() as session:
        batch: list[dict] = []
        total = 0
        for day_offset in range(days, 0, -1):
            day = now - timedelta(days=day_offset)
            for _ in range(events_per_day):
                etype = random.choices(EVENT_TYPES, weights=WEIGHTS, k=1)[0]
                uid = random.choice(user_ids)
                ts = day.replace(
                    hour=random.randint(0, 23),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                    microsecond=0,
                )
                batch.append(
                    {
                        "id": uuid.uuid4(),
                        "event_id": uuid.uuid4(),
                        "user_id": uid,
                        "session_id": f"sess-{uid.hex[:8]}-{day_offset}",
                        "event_type": etype,
                        "properties": {"source": "seed", "day_offset": day_offset},
                        "client_ts": ts,
                        "server_ts": ts,
                        "ip_hash": None,
                        "user_agent": "seed-script/1.0",
                    }
                )
                if len(batch) >= 500:
                    await session.execute(insert(Event).values(batch).on_conflict_do_nothing())
                    await session.commit()
                    total += len(batch)
                    batch.clear()
                    print(f"[seed-data] inserted ~{total}")

        if batch:
            await session.execute(insert(Event).values(batch).on_conflict_do_nothing())
            await session.commit()
            total += len(batch)
        print(f"[seed-data] done, total rows attempted={total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--events-per-day", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(generate(args.days, args.users, args.events_per_day))


if __name__ == "__main__":
    main()
