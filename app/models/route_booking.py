from sqlalchemy import (
    Column, Integer, DateTime, ForeignKey, func, Index, UniqueConstraint, Text, Boolean, Enum
)
from sqlalchemy.orm import relationship
from app.database.session import Base
import enum


class RouteStopStatusEnum(str, enum.Enum):
    PLANNED = "Planned"
    ARRIVED = "Arrived"
    DEPARTED = "Departed"
    SKIPPED = "Skipped"  # if driver bypassed or employee absent


class RouteBooking(Base):
    __tablename__ = "route_bookings"
    __table_args__ = (
        Index("ix_route_bookings_route", "route_id"),
        UniqueConstraint("route_id", "booking_id", name="uq_route_booking_unique"),
        UniqueConstraint("booking_id", name="uq_booking_single_route"),
        {"extend_existing": True},
    )

    route_booking_id = Column(Integer, primary_key=True, index=True)

    route_id = Column(Integer, ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False)

    # Stop-level details
    sequence = Column(Integer, nullable=True)  # order of pickup/drop in the route
    planned_eta_minutes = Column(Integer, nullable=True)  # ETA from route start
    actual_arrival_time = Column(DateTime, nullable=True)
    actual_departure_time = Column(DateTime, nullable=True)
    status = Column(enum.Enum(RouteStopStatusEnum, native_enum=False), default=RouteStopStatusEnum.PLANNED, nullable=False)

    # Audit
    reason = Column(Text, nullable=True)  # why skipped/delayed/etc.
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    route = relationship("Route", back_populates="bookings")
    booking = relationship("Booking", back_populates="route_bookings")

