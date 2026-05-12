"""add speed violations table, speed_limit_kmph to tenant_configs, vehicle override

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-05-12 12:00:00.000000

Changes:
1. Add `speed_limit_kmph` (Float, nullable) to `tenant_configs`      — tenant-wide speed limit
2. Add `speed_limit_override_kmph` (Float, nullable) to `vehicles`   — per-vehicle override
3. Create `speed_violations` table with full indexing
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision      = "f1a2b3c4d5e6"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on    = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add speed_limit_kmph to tenant_configs
    # ------------------------------------------------------------------
    if _has_table(bind, "tenant_configs") and not _has_column(bind, "tenant_configs", "speed_limit_kmph"):
        op.add_column(
            "tenant_configs",
            sa.Column("speed_limit_kmph", sa.Float(), nullable=True,
                      server_default=sa.text("60.0")),
        )
        op.alter_column("tenant_configs", "speed_limit_kmph", server_default=None)

    # ------------------------------------------------------------------
    # 2. Add speed_limit_override_kmph to vehicles
    # ------------------------------------------------------------------
    if _has_table(bind, "vehicles") and not _has_column(bind, "vehicles", "speed_limit_override_kmph"):
        op.add_column(
            "vehicles",
            sa.Column("speed_limit_override_kmph", sa.Float(), nullable=True),
        )

    # ------------------------------------------------------------------
    # 3. Create speed_violations table
    # ------------------------------------------------------------------
    if not _has_table(bind, "speed_violations"):
        op.create_table(
            "speed_violations",
            sa.Column("violation_id",   sa.Integer(),  autoincrement=True, nullable=False),
            sa.Column("tenant_id",      sa.String(50), nullable=False),
            sa.Column("route_id",       sa.Integer(),  nullable=True),
            sa.Column("driver_id",      sa.Integer(),  nullable=True),
            sa.Column("vehicle_id",     sa.Integer(),  nullable=True),
            sa.Column("speed_recorded", sa.Float(),    nullable=False),
            sa.Column("speed_limit",    sa.Float(),    nullable=False),
            sa.Column("latitude",       sa.Float(),    nullable=True),
            sa.Column("longitude",      sa.Float(),    nullable=True),
            sa.Column("recorded_at",    sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at",     sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("violation_id"),
            sa.ForeignKeyConstraint(["tenant_id"],  ["tenants.tenant_id"],
                                    ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["route_id"],   ["route_management.route_id"],
                                    ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["driver_id"],  ["drivers.driver_id"],
                                    ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"],
                                    ondelete="SET NULL"),
        )

        op.create_index("ix_speed_violations_violation_id",  "speed_violations", ["violation_id"])
        op.create_index("ix_speed_violations_tenant_id",     "speed_violations", ["tenant_id"])
        op.create_index("ix_speed_violations_route_id",      "speed_violations", ["route_id"])
        op.create_index("ix_speed_violations_driver_id",     "speed_violations", ["driver_id"])
        op.create_index("ix_speed_violations_tenant_route",  "speed_violations", ["tenant_id", "route_id"])
        op.create_index("ix_speed_violations_tenant_driver", "speed_violations", ["tenant_id", "driver_id"])
        op.create_index("ix_speed_violations_recorded_at",   "speed_violations", ["tenant_id", "recorded_at"])


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "speed_violations"):
        for idx in [
            "ix_speed_violations_recorded_at",
            "ix_speed_violations_tenant_driver",
            "ix_speed_violations_tenant_route",
            "ix_speed_violations_driver_id",
            "ix_speed_violations_route_id",
            "ix_speed_violations_tenant_id",
            "ix_speed_violations_violation_id",
        ]:
            op.drop_index(idx, table_name="speed_violations")
        op.drop_table("speed_violations")

    if _has_table(bind, "vehicles") and _has_column(bind, "vehicles", "speed_limit_override_kmph"):
        op.drop_column("vehicles", "speed_limit_override_kmph")

    if _has_table(bind, "tenant_configs") and _has_column(bind, "tenant_configs", "speed_limit_kmph"):
        op.drop_column("tenant_configs", "speed_limit_kmph")
