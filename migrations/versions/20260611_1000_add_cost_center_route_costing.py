"""add cost center and route costing tables

Revision ID: 20260611_costing
Revises: 20260527_stale
Create Date: 2026-06-11 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_costing"
down_revision = "20260527_stale"
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
    if not _has_table("cost_centers"):
        op.create_table(
            "cost_centers",
            sa.Column("cost_center_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "code", name="uq_cost_center_code_per_tenant"),
        )
        op.create_index("ix_cost_centers_cost_center_id", "cost_centers", ["cost_center_id"])
        op.create_index("ix_cost_centers_tenant_id", "cost_centers", ["tenant_id"])
        op.create_index("ix_cost_centers_tenant_active", "cost_centers", ["tenant_id", "is_active"])

    if not _has_table("cost_center_assignments"):
        op.create_table(
            "cost_center_assignments",
            sa.Column("assignment_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False),
            sa.Column("scope_type", sa.String(20), nullable=False),
            sa.Column("scope_id", sa.String(50), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_cost_center_assignments_assignment_id", "cost_center_assignments", ["assignment_id"])
        op.create_index("ix_cca_scope", "cost_center_assignments", ["tenant_id", "scope_type", "scope_id", "is_active"])
        op.create_index("ix_cca_cost_center", "cost_center_assignments", ["cost_center_id"])

    if not _has_column("bookings", "cost_center_id"):
        op.add_column("bookings", sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.cost_center_id", ondelete="SET NULL"), nullable=True))
        op.create_index("ix_bookings_cost_center_id", "bookings", ["cost_center_id"])

    if not _has_table("rate_cards"):
        op.create_table(
            "rate_cards",
            sa.Column("rate_card_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=True),
            sa.Column("vehicle_type_id", sa.Integer(), sa.ForeignKey("vehicle_types.vehicle_type_id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_rate_cards_rate_card_id", "rate_cards", ["rate_card_id"])
        op.create_index("ix_rate_cards_tenant_id", "rate_cards", ["tenant_id"])
        op.create_index("ix_rate_cards_vendor_id", "rate_cards", ["vendor_id"])
        op.create_index("ix_rate_cards_vehicle_type_id", "rate_cards", ["vehicle_type_id"])
        op.create_index("ix_rate_cards_lookup", "rate_cards", ["tenant_id", "vendor_id", "vehicle_type_id", "status"])
        op.create_index("ix_rate_cards_effective", "rate_cards", ["effective_from", "effective_to"])

    if not _has_table("rate_card_slots"):
        op.create_table(
            "rate_card_slots",
            sa.Column("slot_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("rate_card_id", sa.Integer(), sa.ForeignKey("rate_cards.rate_card_id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("shift_log_type", sa.String(10), nullable=False, server_default="ANY"),
            sa.Column("day_type", sa.String(20), nullable=False, server_default="any"),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("base_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("base_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("base_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("extra_km_rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("extra_hour_rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("waiting_rate_per_hour", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("escort_rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("night_allowance", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("tax_percent", sa.Numeric(6, 3), nullable=False, server_default="0"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_rate_card_slots_slot_id", "rate_card_slots", ["slot_id"])
        op.create_index("ix_rate_card_slots_rate_card_id", "rate_card_slots", ["rate_card_id"])
        op.create_index("ix_rate_card_slots_card_active", "rate_card_slots", ["rate_card_id", "is_active"])
        op.create_index("ix_rate_card_slots_match", "rate_card_slots", ["shift_log_type", "day_type", "priority"])

    if not _has_table("garage_configs"):
        op.create_table(
            "garage_configs",
            sa.Column("garage_config_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"), nullable=True),
            sa.Column("method", sa.String(30), nullable=False, server_default="none"),
            sa.Column("garage_latitude", sa.Float(), nullable=True),
            sa.Column("garage_longitude", sa.Float(), nullable=True),
            sa.Column("fixed_start_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("fixed_end_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("fixed_start_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("fixed_end_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("apply_same_km_rate", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("apply_same_hour_rate", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_garage_configs_garage_config_id", "garage_configs", ["garage_config_id"])
        op.create_index("ix_garage_configs_tenant_id", "garage_configs", ["tenant_id"])
        op.create_index("ix_garage_configs_vendor_id", "garage_configs", ["vendor_id"])
        op.create_index("ix_garage_configs_vehicle_id", "garage_configs", ["vehicle_id"])
        op.create_index("ix_garage_configs_lookup", "garage_configs", ["tenant_id", "vendor_id", "vehicle_id", "is_active"])

    if not _has_table("route_costs"):
        op.create_table(
            "route_costs",
            sa.Column("route_cost_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("route_id", sa.Integer(), sa.ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True),
            sa.Column("vehicle_type_id", sa.Integer(), sa.ForeignKey("vehicle_types.vehicle_type_id", ondelete="SET NULL"), nullable=True),
            sa.Column("rate_card_id", sa.Integer(), sa.ForeignKey("rate_cards.rate_card_id", ondelete="SET NULL"), nullable=True),
            sa.Column("slot_id", sa.Integer(), sa.ForeignKey("rate_card_slots.slot_id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("distance_source", sa.String(20), nullable=False, server_default="planned"),
            sa.Column("trip_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("trip_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("garage_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("garage_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("base_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("extra_km_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("extra_hour_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("garage_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("waiting_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("escort_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("expense_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("variance_percent", sa.Numeric(10, 3), nullable=True),
            sa.Column("calculation_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("route_id", name="uq_route_cost_route_id"),
        )
        op.create_index("ix_route_costs_route_cost_id", "route_costs", ["route_cost_id"])
        op.create_index("ix_route_costs_route_id", "route_costs", ["route_id"])
        op.create_index("ix_route_costs_tenant_id", "route_costs", ["tenant_id"])
        op.create_index("ix_route_costs_tenant_status", "route_costs", ["tenant_id", "status"])
        op.create_index("ix_route_costs_vendor", "route_costs", ["vendor_id"])

    if not _has_table("route_cost_line_items"):
        op.create_table(
            "route_cost_line_items",
            sa.Column("line_item_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("route_cost_id", sa.Integer(), sa.ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False),
            sa.Column("item_type", sa.String(40), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("quantity", sa.Numeric(10, 3), nullable=True),
            sa.Column("rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_route_cost_line_items_line_item_id", "route_cost_line_items", ["line_item_id"])
        op.create_index("ix_route_cost_line_items_cost", "route_cost_line_items", ["route_cost_id"])

    if not _has_table("route_cost_allocations"):
        op.create_table(
            "route_cost_allocations",
            sa.Column("allocation_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("route_cost_id", sa.Integer(), sa.ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False),
            sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False),
            sa.Column("basis", sa.String(30), nullable=False, server_default="headcount"),
            sa.Column("booking_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("allocation_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("allocated_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_route_cost_allocations_allocation_id", "route_cost_allocations", ["allocation_id"])
        op.create_index("ix_route_cost_allocations_cost", "route_cost_allocations", ["route_cost_id"])
        op.create_index("ix_route_cost_allocations_center", "route_cost_allocations", ["cost_center_id"])

    if not _has_table("route_booking_costs"):
        op.create_table(
            "route_booking_costs",
            sa.Column("route_booking_cost_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("route_cost_id", sa.Integer(), sa.ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False),
            sa.Column("route_id", sa.Integer(), sa.ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False),
            sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False),
            sa.Column("distance_source", sa.String(20), nullable=False),
            sa.Column("allocation_basis", sa.String(30), nullable=False, server_default="headcount"),
            sa.Column("route_total_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("route_total_hours", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("booking_planned_km", sa.Numeric(10, 3), nullable=True),
            sa.Column("booking_actual_km", sa.Numeric(10, 3), nullable=True),
            sa.Column("allocation_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("allocated_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("calculation_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("route_cost_id", "booking_id", name="uq_route_booking_cost_once"),
        )
        op.create_index("ix_route_booking_costs_route_booking_cost_id", "route_booking_costs", ["route_booking_cost_id"])
        op.create_index("ix_route_booking_costs_route_id", "route_booking_costs", ["route_id"])
        op.create_index("ix_route_booking_costs_booking_id", "route_booking_costs", ["booking_id"])
        op.create_index("ix_route_booking_costs_tenant_id", "route_booking_costs", ["tenant_id"])
        op.create_index("ix_route_booking_costs_cost", "route_booking_costs", ["route_cost_id"])
        op.create_index("ix_route_booking_costs_booking", "route_booking_costs", ["booking_id"])
        op.create_index("ix_route_booking_costs_center", "route_booking_costs", ["cost_center_id"])

    if not _has_table("route_expenses"):
        op.create_table(
            "route_expenses",
            sa.Column("expense_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("route_id", sa.Integer(), sa.ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False),
            sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
            sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False),
            sa.Column("expense_type", sa.String(40), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("attachment_url", sa.Text(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("created_by_type", sa.String(30), nullable=True),
            sa.Column("created_by_id", sa.String(50), nullable=True),
            sa.Column("approved_by_type", sa.String(30), nullable=True),
            sa.Column("approved_by_id", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_route_expenses_expense_id", "route_expenses", ["expense_id"])
        op.create_index("ix_route_expenses_route_id", "route_expenses", ["route_id"])
        op.create_index("ix_route_expenses_tenant_id", "route_expenses", ["tenant_id"])
        op.create_index("ix_route_expenses_vendor_id", "route_expenses", ["vendor_id"])
        op.create_index("ix_route_expenses_route_status", "route_expenses", ["route_id", "status"])
        op.create_index("ix_route_expenses_tenant_vendor", "route_expenses", ["tenant_id", "vendor_id"])


def downgrade() -> None:
    op.drop_table("route_expenses")
    op.drop_table("route_booking_costs")
    op.drop_table("route_cost_allocations")
    op.drop_table("route_cost_line_items")
    op.drop_table("route_costs")
    op.drop_table("garage_configs")
    op.drop_table("rate_card_slots")
    op.drop_table("rate_cards")

    if _has_column("bookings", "cost_center_id"):
        op.drop_index("ix_bookings_cost_center_id", table_name="bookings")
        op.drop_column("bookings", "cost_center_id")

    op.drop_table("cost_center_assignments")
    op.drop_table("cost_centers")
