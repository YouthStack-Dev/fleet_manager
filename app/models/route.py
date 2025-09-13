from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text,
    ForeignKey, Enum, func, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database.session import Base
from enum import Enum as PyEnum


class RouteStatusEnum(str, PyEnum):
    PLANNED = "Planned"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        Index("ix_routes_shift_status", "shift_id", "status"),
        UniqueConstraint("tenant_id", "route_code", name="uq_route_code_per_tenant"),
    )
    __table_args__ = {'extend_existing': True}

    route_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)

    shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="CASCADE"))
    route_code = Column(String(100), nullable=False)
    status = Column(Enum(RouteStatusEnum, native_enum=False), default=RouteStatusEnum.PLANNED, nullable=False)
    planned_distance_km = Column(Float)
    planned_duration_minutes = Column(Integer)
    actual_distance_km = Column(Float)
    actual_duration_minutes = Column(Integer)
    actual_start_time = Column(DateTime)
    actual_end_time = Column(DateTime)
    optimized_polyline = Column(Text)

    # Current assignment (denormalized for fast reads)
    assigned_vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"))
    assigned_vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"))
    assigned_driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"))

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)  # for regeneration control
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="routes")
    shift = relationship("Shift", back_populates="routes")
    bookings = relationship("RouteBooking", back_populates="route", cascade="all, delete-orphan")
