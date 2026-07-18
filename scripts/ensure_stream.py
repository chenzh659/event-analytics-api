"""Ensure Redis Stream consumer group exists."""

import asyncio

from app.mq.streams import ensure_consumer_group


async def main() -> None:
    await ensure_consumer_group()
    print("[stream] consumer group ready")


if __name__ == "__main__":
    asyncio.run(main())
