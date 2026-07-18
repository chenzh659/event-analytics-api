"""BRIN index for time-series scans on events.server_ts

Revision ID: 0002_brin_events
Revises: 0001_initial
Create Date: 2026-07-18 00:00:00.000000

BRIN (Block Range Index) is a standard choice for append-only time-series tables
at big-tech scale: tiny index size vs B-tree on high-cardinality timestamps,
excellent for range predicates like "last 24h / last 7d" used by DAU & funnel.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_brin_events"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the existing B-tree on server_ts for equality/sort; BRIN accelerates ranges.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_server_ts_brin "
        "ON events USING brin (server_ts) WITH (pages_per_range = 32)"
    )
    # Partial index for "active users today" style scans (user_id IS NOT NULL).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_user_server_ts_notnull "
        "ON events (user_id, server_ts DESC) "
        "WHERE user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_events_user_server_ts_notnull")
    op.execute("DROP INDEX IF EXISTS ix_events_server_ts_brin")
