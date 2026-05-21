"""Feature 4: OTA/OTD Delay Classification.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-05-20 11:00:00.000000

Changes
-------
1. route_delay_events
   - ADD delay_category  VARCHAR(30) NULL
     Root-cause classification: DRIVER_DELAY | EMPLOYEE_DELAY | TRAFFIC_DELAY | NONE.
     NULL for rows recorded before this feature was deployed.

2. tenant_configs
   - ADD delay_driver_grace_minutes  INTEGER NOT NULL DEFAULT 10
     Minutes late at the first pickup stop before it is attributed to the driver.
   - ADD delay_employee_grace_minutes  INTEGER NOT NULL DEFAULT 5
     Per-stop tolerance before employee boarding lateness is counted as the cause.

All ADD COLUMN operations are idempotent (_has_column guard).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision      = "m7n8o9p0q1r2"
down_revision = "l6m7n8o9p0q1"
branch_labels = None
depends_on    = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_column(bind, table_name: str, column_name: str) -> bool:
    cols = {c["name"] for c in inspect(bind).get_columns(table_name)}
    return column_name in cols


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade():
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. route_delay_events — root-cause category
    # ------------------------------------------------------------------
    if not _has_column(bind, "route_delay_events", "delay_category"):
        op.add_column(
            "route_delay_events",
            sa.Column(
                "delay_category",
                sa.String(30),
                nullable=True,
                comment=(
                    "Root-cause classification of the delay. "
                    "DRIVER_DELAY | EMPLOYEE_DELAY | TRAFFIC_DELAY | NONE. "
                    "NULL for rows created before this feature was deployed."
                ),
            ),
        )

    # ------------------------------------------------------------------
    # 2. tenant_configs — driver grace minutes
    # ------------------------------------------------------------------
    if not _has_column(bind, "tenant_configs", "delay_driver_grace_minutes"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "delay_driver_grace_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("10"),
                comment=(
                    "Minutes late the driver can arrive at the first stop "
                    "before the delay is attributed to DRIVER_DELAY."
                ),
            ),
        )

    # ------------------------------------------------------------------
    # 3. tenant_configs — employee grace minutes
    # ------------------------------------------------------------------
    if not _has_column(bind, "tenant_configs", "delay_employee_grace_minutes"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "delay_employee_grace_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5"),
                comment=(
                    "Minutes late each employee boarding can be before the stop "
                    "is attributed to EMPLOYEE_DELAY."
                ),
            ),
        )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade():
    bind = op.get_bind()

    # tenant_configs
    for col in ("delay_employee_grace_minutes", "delay_driver_grace_minutes"):
        if _has_column(bind, "tenant_configs", col):
            op.drop_column("tenant_configs", col)

    # route_delay_events
    if _has_column(bind, "route_delay_events", "delay_category"):
        op.drop_column("route_delay_events", "delay_category")
