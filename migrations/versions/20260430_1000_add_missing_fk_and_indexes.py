"""add missing FK constraints and performance indexes

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
Create Date: 2026-04-30 10:00:00.000000

Adds:
  - FK: route_management_bookings.booking_id → bookings.booking_id
  - FK: route_management.tenant_id           → tenants.tenant_id
  - FK: route_management.shift_id            → shifts.shift_id
  - FK: route_management.assigned_vendor_id  → vendors.vendor_id
  - FK: route_management.assigned_vehicle_id → vehicles.vehicle_id
  - FK: route_management.assigned_driver_id  → drivers.driver_id
  - Index: bookings(tenant_id, booking_date) — primary list-query filter
  - Index: bookings(tenant_id, status)
  - Index: route_management_bookings(booking_id)
  - Index: route_management(tenant_id, shift_id)
  - Index: route_management(tenant_id, assigned_driver_id)
  - Index: user_sessions(user_type, user_id, is_active) — batch lookup
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def _fk_exists(connection, table: str, constraint_name: str) -> bool:
    """Check whether a named constraint already exists (idempotency guard)."""
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE constraint_type = 'FOREIGN KEY'
              AND table_name = :table
              AND constraint_name = :name
            """
        ),
        {"table": table, "name": constraint_name},
    )
    return result.fetchone() is not None


def _index_exists(connection, index_name: str) -> bool:
    result = connection.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :name"
        ),
        {"name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()

    # ── route_management_bookings.booking_id → bookings ──────────
    if not _fk_exists(conn, "route_management_bookings", "fk_rmb_booking_id"):
        op.create_foreign_key(
            "fk_rmb_booking_id",
            "route_management_bookings",
            "bookings",
            ["booking_id"],
            ["booking_id"],
            ondelete="CASCADE",
        )

    # ── route_management.tenant_id → tenants ─────────────────────
    if not _fk_exists(conn, "route_management", "fk_rm_tenant_id"):
        op.create_foreign_key(
            "fk_rm_tenant_id",
            "route_management",
            "tenants",
            ["tenant_id"],
            ["tenant_id"],
            ondelete="CASCADE",
        )

    # ── route_management.shift_id → shifts ───────────────────────
    if not _fk_exists(conn, "route_management", "fk_rm_shift_id"):
        op.create_foreign_key(
            "fk_rm_shift_id",
            "route_management",
            "shifts",
            ["shift_id"],
            ["shift_id"],
            ondelete="SET NULL",
        )

    # ── route_management.assigned_vendor_id → vendors ────────────
    if not _fk_exists(conn, "route_management", "fk_rm_vendor_id"):
        op.create_foreign_key(
            "fk_rm_vendor_id",
            "route_management",
            "vendors",
            ["assigned_vendor_id"],
            ["vendor_id"],
            ondelete="SET NULL",
        )

    # ── route_management.assigned_vehicle_id → vehicles ──────────
    if not _fk_exists(conn, "route_management", "fk_rm_vehicle_id"):
        op.create_foreign_key(
            "fk_rm_vehicle_id",
            "route_management",
            "vehicles",
            ["assigned_vehicle_id"],
            ["vehicle_id"],
            ondelete="SET NULL",
        )

    # ── route_management.assigned_driver_id → drivers ────────────
    if not _fk_exists(conn, "route_management", "fk_rm_driver_id"):
        op.create_foreign_key(
            "fk_rm_driver_id",
            "route_management",
            "drivers",
            ["assigned_driver_id"],
            ["driver_id"],
            ondelete="SET NULL",
        )

    # ── Indexes ───────────────────────────────────────────────────
    if not _index_exists(conn, "ix_bookings_tenant_date"):
        op.create_index(
            "ix_bookings_tenant_date",
            "bookings",
            ["tenant_id", "booking_date"],
        )

    if not _index_exists(conn, "ix_bookings_tenant_status"):
        op.create_index(
            "ix_bookings_tenant_status",
            "bookings",
            ["tenant_id", "status"],
        )

    if not _index_exists(conn, "ix_rmb_booking_id"):
        op.create_index(
            "ix_rmb_booking_id",
            "route_management_bookings",
            ["booking_id"],
        )

    if not _index_exists(conn, "ix_rm_tenant_shift"):
        op.create_index(
            "ix_rm_tenant_shift",
            "route_management",
            ["tenant_id", "shift_id"],
        )

    if not _index_exists(conn, "ix_rm_tenant_driver"):
        op.create_index(
            "ix_rm_tenant_driver",
            "route_management",
            ["tenant_id", "assigned_driver_id"],
        )

    if not _index_exists(conn, "ix_user_sessions_lookup"):
        op.create_index(
            "ix_user_sessions_lookup",
            "user_sessions",
            ["user_type", "user_id", "is_active"],
        )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_lookup", table_name="user_sessions")
    op.drop_index("ix_rm_tenant_driver",     table_name="route_management")
    op.drop_index("ix_rm_tenant_shift",      table_name="route_management")
    op.drop_index("ix_rmb_booking_id",       table_name="route_management_bookings")
    op.drop_index("ix_bookings_tenant_status", table_name="bookings")
    op.drop_index("ix_bookings_tenant_date", table_name="bookings")

    op.drop_constraint("fk_rm_driver_id",  "route_management",          type_="foreignkey")
    op.drop_constraint("fk_rm_vehicle_id", "route_management",          type_="foreignkey")
    op.drop_constraint("fk_rm_vendor_id",  "route_management",          type_="foreignkey")
    op.drop_constraint("fk_rm_shift_id",   "route_management",          type_="foreignkey")
    op.drop_constraint("fk_rm_tenant_id",  "route_management",          type_="foreignkey")
    op.drop_constraint("fk_rmb_booking_id", "route_management_bookings", type_="foreignkey")
