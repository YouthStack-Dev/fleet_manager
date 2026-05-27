"""add_driver_location_history

Revision ID: 20260527_dlh
Revises: 20260525_chat
Create Date: 2026-05-27 10:00:00.000000

Creates the driver_location_history table which stores every GPS ping sent
by the driver app while a route is ONGOING.

Purpose:
  - Full GPS breadcrumb trail (audit, playback, distance calculation)
  - Complements Firebase RTDB which only holds the *latest* position
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = "20260527_dlh"
down_revision = "20260525_chat"
branch_labels = None
depends_on    = None


def _has_table(name: str) -> bool:
    from alembic import op as _op
    bind = _op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    if _has_table("driver_location_history"):
        return  # idempotent guard — safe to re-run

    op.create_table(
        "driver_location_history",

        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),

        # Tenant scoping
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),

        # Active ride this ping belongs to
        sa.Column(
            "route_id",
            sa.Integer(),
            sa.ForeignKey("route_management.route_id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Driver who sent the ping
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("drivers.driver_id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Vendor (denormalised for fast tenant-vendor queries)
        sa.Column(
            "vendor_id",
            sa.Integer(),
            sa.ForeignKey("vendors.vendor_id", ondelete="SET NULL"),
            nullable=True,
        ),

        # GPS data
        sa.Column("latitude",    sa.Float(), nullable=False),
        sa.Column("longitude",   sa.Float(), nullable=False),
        sa.Column("speed",       sa.Float(), nullable=True),   # km/h from device

        # Timestamps
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Primary key index (created implicitly, listed here for clarity)
    op.create_index("ix_driver_location_history_id",       "driver_location_history", ["id"])
    op.create_index("ix_driver_location_history_tenant",   "driver_location_history", ["tenant_id"])
    op.create_index("ix_driver_location_history_route",    "driver_location_history", ["route_id"])
    op.create_index("ix_driver_location_history_driver",   "driver_location_history", ["driver_id"])

    # Composite indexes for query patterns described in the model
    op.create_index(
        "ix_dlh_route_recorded_at",
        "driver_location_history",
        ["route_id", "recorded_at"],
    )
    op.create_index(
        "ix_dlh_driver_recorded_at",
        "driver_location_history",
        ["driver_id", "recorded_at"],
    )
    op.create_index(
        "ix_dlh_tenant_driver",
        "driver_location_history",
        ["tenant_id", "driver_id"],
    )


def downgrade() -> None:
    op.drop_table("driver_location_history")
