from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Float,
    ForeignKey, Enum, func, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum


class BookingStatusEnum(str, PyEnum):
    REQUEST = "Request"          # request raised
    SCHEDULED = "Scheduled"     # routing done
    ONGOING = "Ongoing"          # in vehicle
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"      
    NO_SHOW = "No-Show"
    EXPIRED = "Expired"          # auto-cancel before planning window


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        {"extend_existing": True}
    )

    booking_id = Column(Integer, primary_key=True, index=True)

    # Scope
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)
    employee_code = Column(String(50), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="CASCADE"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)  
    OTP = Column(Integer, nullable=True)  # One-Time Password for booking verification

    # Booking details
    booking_date = Column(Date, nullable=False)
    pickup_latitude = Column(Float, nullable=True)
    pickup_longitude = Column(Float, nullable=True)
    pickup_location = Column(String(255), nullable=True)
    drop_latitude = Column(Float, nullable=True)
    drop_longitude = Column(Float, nullable=True)
    drop_location = Column(String(255), nullable=True)

    status = Column(
        Enum(BookingStatusEnum, native_enum=False),
        default=BookingStatusEnum.REQUEST,
        nullable=False,
        index=True
    )

    # Audit & lifecycle
    reason = Column(Text, nullable=True)  # reason for cancellation/update

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="bookings")
    employee = relationship("Employee", back_populates="bookings")
    shift = relationship("Shift", back_populates="bookings")
    team = relationship("Team", back_populates="bookings")
