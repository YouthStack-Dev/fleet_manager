from sqlalchemy import Column, Integer, String, Boolean, DateTime, Time, Enum, func
from sqlalchemy.orm import relationship
from database.session import Base
from enum import Enum as PyEnum

class ShiftLogTypeEnum(str, PyEnum):
    IN = "IN"
    OUT = "OUT"

class PickupTypeEnum(str, PyEnum):
    PICKUP = "Pickup"
    NODAL = "Nodal"

class GenderEnum(str, PyEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class Shift(Base):
    __tablename__ = "shifts"

    shift_id = Column(Integer, primary_key=True, index=True)
    shift_code = Column(String(50), unique=True, nullable=False)
    log_type = Column(Enum(ShiftLogTypeEnum, native_enum=False), nullable=False)
    shift_time = Column(Time, nullable=False)
    pickup_type = Column(Enum(PickupTypeEnum, native_enum=False))
    gender = Column(Enum(GenderEnum, native_enum=False))
    waiting_time_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    bookings = relationship("Booking", back_populates="shift")
    routes = relationship("Route", back_populates="shift")
