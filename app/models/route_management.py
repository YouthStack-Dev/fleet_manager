from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text,
    ForeignKey, Enum, func, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum


class RouteManagementStatusEnum(str, PyEnum):
    PLANNED = "Planned"
    VENDOR_ASSIGNED = "Vendor Assigned"
    DRIVER_ASSIGNED = "Driver Assigned"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class RouteManagement(Base):
    __tablename__ = "route_management"
    __table_args__ = (
        Index("ix_route_management_tenant_status", "tenant_id", "status"),
        {"extend_existing": True},
    )

    route_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False)
    shift_id = Column(Integer, nullable=True)
    route_code = Column(String(100), nullable=True)

    # Current assignment (denormalized for fast reads)
    assigned_vendor_id = Column(Integer, nullable=True)
    assigned_vehicle_id = Column(Integer, nullable=True)
    assigned_driver_id = Column(Integer, nullable=True)
    assigned_escort_id = Column(Integer, ForeignKey('escorts.escort_id'), nullable=True)

    # Escort safety requirements
    escort_required = Column(Boolean, default=False, nullable=False)  # Route requires escort based on safety rules

    status = Column(Enum(RouteManagementStatusEnum, native_enum=False), default=RouteManagementStatusEnum.PLANNED, nullable=False)
    estimated_total_time = Column(Float, nullable=True)  # New column
    estimated_total_distance = Column(Float, nullable=True)  # New column
    actual_total_time = Column(Float, nullable=True)  # New column
    actual_total_distance = Column(Float, nullable=True)  # New column
    buffer_time = Column(Float, nullable=True)  # New column

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    route_management_bookings = relationship("RouteManagementBooking", back_populates="route_management", cascade="all, delete-orphan")


class RouteManagementBooking(Base):
    __tablename__ = "route_management_bookings"
    __table_args__ = (
        UniqueConstraint("route_id", "booking_id", name="uq_route_management_booking_unique"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("route_management.route_id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, nullable=False)

    order_id = Column(Integer, nullable=False)  # New column
    estimated_pick_up_time = Column(String(10), nullable=True)  # New column
    estimated_distance = Column(Float, nullable=True)  # New column
    actual_pick_up_time = Column(String(10), nullable=True)  # New column
    actual_distance = Column(Float, nullable=True)  # New column
    estimated_drop_time = Column(String(10), nullable=True)  # New column
    actual_drop_time = Column(String(10), nullable=True)  # New column

    created_at = Column(DateTime, default=func.now(), nullable=False)

    route_management = relationship("RouteManagement", back_populates="route_management_bookings")
