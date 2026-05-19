"""Add nodal points feature: nodal_points table, employee_nodal_points table,
nodal_point_id column on bookings.

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-12 13:00:00.000000

Changes:
1. Create `nodal_points` table
2. Create `employee_nodal_points` table (one employee → one nodal point)
3. Add `nodal_point_id` (nullable FK) to `bookings`
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision      = "g1h2i3j4k5l6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on    = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()

    # ── 1. nodal_points ───────────────────────────────────────────
    if not _has_table(bind, "nodal_points"):
        op.create_table(
            "nodal_points",
            sa.Column("nodal_point_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("latitude",  sa.Numeric(9, 6), nullable=False),
            sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index("ix_nodal_points_nodal_point_id", "nodal_points", ["nodal_point_id"])
        op.create_index("ix_nodal_points_tenant_id",      "nodal_points", ["tenant_id"])

    # ── 2. employee_nodal_points ──────────────────────────────────
    if not _has_table(bind, "employee_nodal_points"):
        op.create_table(
            "employee_nodal_points",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "employee_id",
                sa.Integer(),
                sa.ForeignKey("employees.employee_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "nodal_point_id",
                sa.Integer(),
                sa.ForeignKey("nodal_points.nodal_point_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "is_overridden",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint("employee_id", name="uq_employee_nodal_point"),
        )
        op.create_index("ix_employee_nodal_points_id",             "employee_nodal_points", ["id"])
        op.create_index("ix_employee_nodal_points_employee_id",    "employee_nodal_points", ["employee_id"])
        op.create_index("ix_employee_nodal_points_nodal_point_id", "employee_nodal_points", ["nodal_point_id"])
        op.create_index("ix_employee_nodal_points_tenant_id",      "employee_nodal_points", ["tenant_id"])

    # ── 3. bookings.nodal_point_id ────────────────────────────────
    if not _has_column(bind, "bookings", "nodal_point_id"):
        op.add_column(
            "bookings",
            sa.Column(
                "nodal_point_id",
                sa.Integer(),
                sa.ForeignKey("nodal_points.nodal_point_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index("ix_bookings_nodal_point_id", "bookings", ["nodal_point_id"])


def downgrade():
    bind = op.get_bind()

    # Remove FK column from bookings
    if _has_column(bind, "bookings", "nodal_point_id"):
        op.drop_index("ix_bookings_nodal_point_id", table_name="bookings")
        op.drop_column("bookings", "nodal_point_id")

    # Drop employee_nodal_points
    if _has_table(bind, "employee_nodal_points"):
        op.drop_index("ix_employee_nodal_points_tenant_id",      table_name="employee_nodal_points")
        op.drop_index("ix_employee_nodal_points_nodal_point_id", table_name="employee_nodal_points")
        op.drop_index("ix_employee_nodal_points_employee_id",    table_name="employee_nodal_points")
        op.drop_index("ix_employee_nodal_points_id",             table_name="employee_nodal_points")
        op.drop_table("employee_nodal_points")

    # Drop nodal_points
    if _has_table(bind, "nodal_points"):
        op.drop_index("ix_nodal_points_tenant_id",      table_name="nodal_points")
        op.drop_index("ix_nodal_points_nodal_point_id", table_name="nodal_points")
        op.drop_table("nodal_points")
