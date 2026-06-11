"""remove all costing tables

Revision ID: 20260611_remove_costing
Revises: 20260611_rate_slabs
Create Date: 2026-06-11 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_remove_costing"
down_revision = "20260611_rate_slabs"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return False
    return column in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    if _has_table("rate_card_distance_slabs"):
        op.drop_table("rate_card_distance_slabs")

    if _has_table("route_booking_costs"):
        op.drop_table("route_booking_costs")

    if _has_table("route_expenses"):
        op.drop_table("route_expenses")

    if _has_table("route_cost_allocations"):
        op.drop_table("route_cost_allocations")

    if _has_table("route_cost_line_items"):
        op.drop_table("route_cost_line_items")

    if _has_table("route_costs"):
        op.drop_table("route_costs")

    if _has_table("garage_configs"):
        op.drop_table("garage_configs")

    if _has_table("rate_card_slots"):
        op.drop_table("rate_card_slots")

    if _has_table("rate_cards"):
        op.drop_table("rate_cards")

    if _has_column("bookings", "cost_center_id"):
        op.drop_column("bookings", "cost_center_id")

    if _has_table("cost_center_assignments"):
        op.drop_table("cost_center_assignments")

    if _has_table("cost_centers"):
        op.drop_table("cost_centers")


def downgrade() -> None:
    pass
