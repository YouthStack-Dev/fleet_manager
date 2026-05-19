"""Feature 5+6: one-trip-per-shift enforcement + OTA/OTD delay tagging schema.

Revision ID: k5l6m7n8o9p0
Revises: i3j4k5l6m7n8
Create Date: 2026-05-19 13:00:00.000000

Changes
-------
1. tenant_configs
   - ADD one_trip_per_shift_enabled  BOOLEAN NOT NULL DEFAULT TRUE
   - ADD auto_move_on_conflict       BOOLEAN NOT NULL DEFAULT TRUE

2. route_management
   - ADD delay_type        VARCHAR(20)  NULL
   - ADD delay_minutes     INTEGER      NULL
   - ADD delay_tagged_at   TIMESTAMP    NULL
   - ADD ota_grace_minutes INTEGER      NOT NULL DEFAULT 5

3. CREATE TABLE route_delay_events
   - id             SERIAL PK
   - route_id       INTEGER FK → route_management.route_id ON DELETE CASCADE
   - tenant_id      VARCHAR(50) NOT NULL
   - event_kind     VARCHAR(10)  NOT NULL   -- "OTA" | "OTD"
   - delay_type     VARCHAR(20)  NOT NULL   -- "LATE" | "EARLY" | "ON_TIME"
   - delay_minutes  INTEGER      NOT NULL DEFAULT 0
   - notes          TEXT         NULL
   - tagged_at      TIMESTAMP    NOT NULL DEFAULT now()

All ADD COLUMN operations are idempotent (_has_column guard).
Table creation is idempotent (_has_table guard).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision      = "k5l6m7n8o9p0"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on    = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    cols = {c["name"] for c in inspect(bind).get_columns(table_name)}
    return column_name in cols


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade():
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. tenant_configs — enforcement flags
    # ------------------------------------------------------------------
    if not _has_column(bind, "tenant_configs", "one_trip_per_shift_enabled"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "one_trip_per_shift_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
                comment="When TRUE, a booking can only be on one active route at a time.",
            ),
        )

    if not _has_column(bind, "tenant_configs", "auto_move_on_conflict"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "auto_move_on_conflict",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
                comment=(
                    "When TRUE, a conflicting booking is silently moved to the new route. "
                    "When FALSE, the add operation is blocked."
                ),
            ),
        )

    # ------------------------------------------------------------------
    # 2. route_management — delay summary columns
    # ------------------------------------------------------------------
    if not _has_column(bind, "route_management", "delay_type"):
        op.add_column(
            "route_management",
            sa.Column(
                "delay_type",
                sa.String(20),
                nullable=True,
                comment="Latest OTA/OTD tag: LATE | EARLY | ON_TIME",
            ),
        )

    if not _has_column(bind, "route_management", "delay_minutes"):
        op.add_column(
            "route_management",
            sa.Column(
                "delay_minutes",
                sa.Integer(),
                nullable=True,
                comment="Delay in minutes: positive = late, negative = early.",
            ),
        )

    if not _has_column(bind, "route_management", "delay_tagged_at"):
        op.add_column(
            "route_management",
            sa.Column(
                "delay_tagged_at",
                sa.DateTime(),
                nullable=True,
                comment="Timestamp of the last delay tagging event.",
            ),
        )

    if not _has_column(bind, "route_management", "ota_grace_minutes"):
        op.add_column(
            "route_management",
            sa.Column(
                "ota_grace_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5"),
                comment="Grace window in minutes before a delay is recorded.",
            ),
        )

    # ------------------------------------------------------------------
    # 3. route_delay_events — full audit log
    # ------------------------------------------------------------------
    if not _has_table(bind, "route_delay_events"):
        op.create_table(
            "route_delay_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "route_id",
                sa.Integer(),
                sa.ForeignKey("route_management.route_id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("tenant_id", sa.String(50), nullable=False, index=True),
            sa.Column("event_kind", sa.String(10), nullable=False),   # OTA | OTD
            sa.Column("delay_type", sa.String(20), nullable=False),   # LATE | EARLY | ON_TIME
            sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "tagged_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade():
    bind = op.get_bind()

    # Drop table first (FK dependency)
    if _has_table(bind, "route_delay_events"):
        op.drop_table("route_delay_events")

    # route_management delay columns
    for col in ("ota_grace_minutes", "delay_tagged_at", "delay_minutes", "delay_type"):
        if _has_column(bind, "route_management", col):
            op.drop_column("route_management", col)

    # tenant_configs enforcement columns
    for col in ("auto_move_on_conflict", "one_trip_per_shift_enabled"):
        if _has_column(bind, "tenant_configs", col):
            op.drop_column("tenant_configs", col)
