from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.session import Base


_JsonB = JSON().with_variant(JSONB(), "postgresql")


class CostCenter(Base):
    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_cost_center_code_per_tenant"),
        Index("ix_cost_centers_tenant_active", "tenant_id", "is_active"),
    )

    cost_center_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    assignments = relationship("CostCenterAssignment", back_populates="cost_center", cascade="all, delete-orphan")
    allocations = relationship("RouteCostAllocation", back_populates="cost_center")


class CostCenterAssignment(Base):
    __tablename__ = "cost_center_assignments"
    __table_args__ = (
        Index("ix_cca_scope", "tenant_id", "scope_type", "scope_id", "is_active"),
        Index("ix_cca_cost_center", "cost_center_id"),
    )

    assignment_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False)
    scope_type = Column(String(20), nullable=False)  # employee | team | tenant
    scope_id = Column(String(50), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    cost_center = relationship("CostCenter", back_populates="assignments")


class RateCard(Base):
    __tablename__ = "rate_cards"
    __table_args__ = (
        Index("ix_rate_cards_lookup", "tenant_id", "vendor_id", "vehicle_type_id", "status"),
        Index("ix_rate_cards_effective", "effective_from", "effective_to"),
    )

    rate_card_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=True, index=True)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    currency = Column(String(3), nullable=False, default="INR", server_default="INR")
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    slots = relationship("RateCardSlot", back_populates="rate_card", cascade="all, delete-orphan")


class RateCardSlot(Base):
    __tablename__ = "rate_card_slots"
    __table_args__ = (
        Index("ix_rate_card_slots_card_active", "rate_card_id", "is_active"),
        Index("ix_rate_card_slots_match", "shift_log_type", "day_type", "priority"),
    )

    slot_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rate_card_id = Column(Integer, ForeignKey("rate_cards.rate_card_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    shift_log_type = Column(String(10), nullable=False, default="ANY", server_default="ANY")
    day_type = Column(String(20), nullable=False, default="any", server_default="any")
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    base_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    base_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    base_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    extra_km_rate = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    extra_hour_rate = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    waiting_rate_per_hour = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    escort_rate = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    night_allowance = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax_percent = Column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    rate_card = relationship("RateCard", back_populates="slots")
    distance_slabs = relationship(
        "RateCardDistanceSlab",
        back_populates="slot",
        cascade="all, delete-orphan",
        order_by="RateCardDistanceSlab.min_km.asc(), RateCardDistanceSlab.max_km.asc(), RateCardDistanceSlab.distance_slab_id.asc()",
    )


class RateCardDistanceSlab(Base):
    __tablename__ = "rate_card_distance_slabs"
    __table_args__ = (
        Index("ix_rate_card_distance_slabs_slot_active", "slot_id", "is_active"),
        Index("ix_rate_card_distance_slabs_range", "slot_id", "min_km", "max_km"),
    )

    distance_slab_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    slot_id = Column(Integer, ForeignKey("rate_card_slots.slot_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    min_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    max_km = Column(Numeric(10, 3), nullable=False)
    buffer_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    rate_per_km = Column(Numeric(12, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    slot = relationship("RateCardSlot", back_populates="distance_slabs")


class GarageConfig(Base):
    __tablename__ = "garage_configs"
    __table_args__ = (
        Index("ix_garage_configs_lookup", "tenant_id", "vendor_id", "vehicle_id", "is_active"),
    )

    garage_config_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"), nullable=True, index=True)
    method = Column(String(30), nullable=False, default="none", server_default="none")
    garage_latitude = Column(Float, nullable=True)
    garage_longitude = Column(Float, nullable=True)
    fixed_start_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    fixed_end_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    fixed_start_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    fixed_end_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    apply_same_km_rate = Column(Boolean, nullable=False, default=True, server_default="true")
    apply_same_hour_rate = Column(Boolean, nullable=False, default=True, server_default="true")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class RouteCost(Base):
    __tablename__ = "route_costs"
    __table_args__ = (
        UniqueConstraint("route_id", name="uq_route_cost_route_id"),
        Index("ix_route_costs_tenant_status", "tenant_id", "status"),
        Index("ix_route_costs_vendor", "vendor_id"),
    )

    route_cost_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="SET NULL"), nullable=True)
    rate_card_id = Column(Integer, ForeignKey("rate_cards.rate_card_id", ondelete="SET NULL"), nullable=True)
    slot_id = Column(Integer, ForeignKey("rate_card_slots.slot_id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    distance_source = Column(String(20), nullable=False, default="planned", server_default="planned")
    trip_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    trip_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    garage_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    garage_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    base_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    extra_km_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    extra_hour_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    garage_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    waiting_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    escort_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    expense_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    total_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    variance_percent = Column(Numeric(10, 3), nullable=True)
    calculation_snapshot = Column(_JsonB, nullable=False, default=dict, server_default="{}")
    calculated_at = Column(DateTime, nullable=False, default=func.now())
    approved_at = Column(DateTime, nullable=True)
    finalized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    line_items = relationship("RouteCostLineItem", back_populates="route_cost", cascade="all, delete-orphan")
    allocations = relationship("RouteCostAllocation", back_populates="route_cost", cascade="all, delete-orphan")
    booking_costs = relationship("RouteBookingCost", back_populates="route_cost", cascade="all, delete-orphan")


class RouteCostLineItem(Base):
    __tablename__ = "route_cost_line_items"
    __table_args__ = (
        Index("ix_route_cost_line_items_cost", "route_cost_id"),
    )

    line_item_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_cost_id = Column(Integer, ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String(40), nullable=False)
    description = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 3), nullable=True)
    rate = Column(Numeric(12, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    details = Column(_JsonB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=func.now())

    route_cost = relationship("RouteCost", back_populates="line_items")


class RouteCostAllocation(Base):
    __tablename__ = "route_cost_allocations"
    __table_args__ = (
        Index("ix_route_cost_allocations_cost", "route_cost_id"),
        Index("ix_route_cost_allocations_center", "cost_center_id"),
    )

    allocation_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_cost_id = Column(Integer, ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False)
    basis = Column(String(30), nullable=False, default="headcount", server_default="headcount")
    booking_count = Column(Integer, nullable=False, default=0, server_default="0")
    allocation_percent = Column(Numeric(8, 4), nullable=False, default=0, server_default="0")
    allocated_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    details = Column(_JsonB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=func.now())

    route_cost = relationship("RouteCost", back_populates="allocations")
    cost_center = relationship("CostCenter", back_populates="allocations")


class RouteBookingCost(Base):
    __tablename__ = "route_booking_costs"
    __table_args__ = (
        UniqueConstraint("route_cost_id", "booking_id", name="uq_route_booking_cost_once"),
        Index("ix_route_booking_costs_cost", "route_cost_id"),
        Index("ix_route_booking_costs_booking", "booking_id"),
        Index("ix_route_booking_costs_center", "cost_center_id"),
    )

    route_booking_cost_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_cost_id = Column(Integer, ForeignKey("route_costs.route_cost_id", ondelete="CASCADE"), nullable=False)
    route_id = Column(Integer, ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.cost_center_id", ondelete="CASCADE"), nullable=False)
    distance_source = Column(String(20), nullable=False)
    allocation_basis = Column(String(30), nullable=False, default="headcount", server_default="headcount")
    route_total_km = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    route_total_hours = Column(Numeric(10, 3), nullable=False, default=0, server_default="0")
    booking_planned_km = Column(Numeric(10, 3), nullable=True)
    booking_actual_km = Column(Numeric(10, 3), nullable=True)
    allocation_percent = Column(Numeric(8, 4), nullable=False, default=0, server_default="0")
    allocated_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    calculation_snapshot = Column(_JsonB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=func.now())

    route_cost = relationship("RouteCost", back_populates="booking_costs")
    cost_center = relationship("CostCenter")


class RouteExpense(Base):
    __tablename__ = "route_expenses"
    __table_args__ = (
        Index("ix_route_expenses_route_status", "route_id", "status"),
        Index("ix_route_expenses_tenant_vendor", "tenant_id", "vendor_id"),
    )

    expense_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False, index=True)
    expense_type = Column(String(40), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    comment = Column(Text, nullable=True)
    attachment_url = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="draft", server_default="draft")
    rejection_reason = Column(Text, nullable=True)
    created_by_type = Column(String(30), nullable=True)
    created_by_id = Column(String(50), nullable=True)
    approved_by_type = Column(String(30), nullable=True)
    approved_by_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
