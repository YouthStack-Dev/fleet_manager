from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text,
    ForeignKey, Enum, func, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum


class RouteManagementStatusEnum(str, PyEnum):
    PLANNED = "Planned"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class RouteManagement(Base):
    __tablename__ = "route_management"
    __table_args__ = (
        Index("ix_route_management_tenant_status", "tenant_id", "status"),
        UniqueConstraint("tenant_id", "route_code", name="uq_route_management_code_per_tenant"),
        {"extend_existing": True},
    )

    route_id = Column(String(100), primary_key=True, index=True)
    tenant_id = Column(String(50), nullable=False)  # Remove FK constraint temporarily
    shift_id = Column(Integer, nullable=True)  # Remove FK constraint temporarily
    route_code = Column(String(100), nullable=False)

    status = Column(Enum(RouteManagementStatusEnum, native_enum=False), default=RouteManagementStatusEnum.PLANNED, nullable=False)
    planned_distance_km = Column(Float)
    planned_duration_minutes = Column(Integer)

    actual_distance_km = Column(Float)
    actual_duration_minutes = Column(Integer)
    actual_start_time = Column(DateTime)
    actual_end_time = Column(DateTime)
    optimized_polyline = Column(Text)

    # Current assignment (denormalized for fast reads)
    assigned_vendor_id = Column(Integer, nullable=True)
    assigned_vehicle_id = Column(Integer, nullable=True)
    assigned_driver_id = Column(Integer, nullable=True)

    total_distance_km = Column(Float, nullable=True)
    total_time_minutes = Column(Float, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)  # for regeneration control
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    route_management_bookings = relationship("RouteManagementBooking", back_populates="route_management", cascade="all, delete-orphan")


class RouteManagementBooking(Base):
    __tablename__ = "route_management_bookings"
    __table_args__ = (
        UniqueConstraint("route_id", "booking_id", name="uq_route_management_booking_unique"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(String(100), ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, nullable=False)  # Keep as simple integer without FK

    # Order and timing
    stop_order = Column(Integer, nullable=False)
    estimated_pickup_time = Column(String(10), nullable=True)  # HH:MM format
    estimated_drop_time = Column(String(10), nullable=True)    # HH:MM format
    distance_from_previous = Column(Float, nullable=True)
    cumulative_distance = Column(Float, nullable=True)

    # Audit
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    route_management = relationship("RouteManagement", back_populates="route_management_bookings")
    # Remove booking relationship to avoid circular dependencies
