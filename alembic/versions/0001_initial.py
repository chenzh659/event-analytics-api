"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role_id", "users", ["role_id"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("client_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "server_ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_events_event_id", "events", ["event_id"])
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_type_server_ts", "events", ["event_type", "server_ts"])
    op.create_index("ix_events_user_server_ts", "events", ["user_id", "server_ts"])
    op.create_index("ix_events_session_id", "events", ["session_id"])
    op.create_index("ix_events_server_ts", "events", ["server_ts"])
    op.create_index(
        "ix_events_properties_gin",
        "events",
        ["properties"],
        postgresql_using="gin",
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_idempotency_key"),
    )

    op.create_table(
        "metrics_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("dim_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("value", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_date", "name", "dim_hash", name="uq_metrics_daily"),
    )
    op.create_index("ix_metrics_daily_metric_date", "metrics_daily", ["metric_date"])
    op.create_index("ix_metrics_daily_name", "metrics_daily", ["name"])

    op.create_table(
        "funnel_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("funnel_name", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cart_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "window_start", "window_end", "funnel_name", name="uq_funnel_snap"
        ),
    )
    op.create_index("ix_funnel_snapshots_window_start", "funnel_snapshots", ["window_start"])

    op.create_table(
        "retention_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cohort_date", sa.Date(), nullable=False),
        sa.Column("cohort_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d1_retained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d7_retained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d1_rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("d7_rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cohort_date", name="uq_retention_cohort"),
    )
    op.create_index("ix_retention_snapshots_cohort_date", "retention_snapshots", ["cohort_date"])


def downgrade() -> None:
    op.drop_table("retention_snapshots")
    op.drop_table("funnel_snapshots")
    op.drop_table("metrics_daily")
    op.drop_table("idempotency_keys")
    op.drop_table("events")
    op.drop_table("users")
    op.drop_table("roles")
