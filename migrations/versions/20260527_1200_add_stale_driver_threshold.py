"""add_stale_driver_threshold

Revision ID: 20260527_stale
Revises: 20260527_geo
Create Date: 2026-05-27 12:00:00.000000

Adds one configuration column for Phase 5 (IMP-5):

  IMP-5  Stale Driver Alerting
  ────────────────────────────
  tenant_configs.stale_driver_threshold_minutes
    Number of minutes without a GPS ping before a driver on an ONGOING route
    is considered "stale" and operations admins are alerted via FCM.
    Default 5 min.  Configurable per tenant.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = "20260527_stale"
down_revision = "20260527_geo"
branch_labels = None
depends_on    = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    if not _has_column("tenant_configs", "stale_driver_threshold_minutes"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "stale_driver_threshold_minutes",
                sa.Integer(),
                nullable=False,
                server_default="5",
            ),
        )


def downgrade() -> None:
    op.drop_column("tenant_configs", "stale_driver_threshold_minutes")
