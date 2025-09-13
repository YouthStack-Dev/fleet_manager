from sqlalchemy import Column, Integer, String, DateTime, Date, Float, ForeignKey, Enum, func
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum

class BookingStatusEnum(str, PyEnum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELED = "Canceled"

class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = {'extend_existing': True}

    booking_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)

    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="CASCADE"))
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"))

    booking_date = Column(Date, nullable=False)
    pickup_latitude = Column(Float)
    pickup_longitude = Column(Float)
    pickup_location = Column(String(255))
    drop_latitude = Column(Float)
    drop_longitude = Column(Float)
    drop_location = Column(String(255))
    status = Column(Enum(BookingStatusEnum, native_enum=False), default=BookingStatusEnum.PENDING)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="bookings")
    employee = relationship("Employee", back_populates="bookings")
    shift = relationship("Shift", back_populates="bookings")
    team = relationship("Team", back_populates="bookings")
    route_bookings = relationship("RouteBooking", back_populates="booking", cascade="all, delete-orphan")

