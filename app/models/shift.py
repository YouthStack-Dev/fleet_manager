from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Time, Enum, ForeignKey, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base
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
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)

    shift_code = Column(String(50), nullable=False)  # unique per tenant
    log_type = Column(Enum(ShiftLogTypeEnum, native_enum=False), nullable=False)
    shift_time = Column(Time, nullable=False)
    pickup_type = Column(Enum(PickupTypeEnum, native_enum=False))
    gender = Column(Enum(GenderEnum, native_enum=False))
    waiting_time_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "shift_code", name="uq_shift_code_per_tenant"),
        {"extend_existing": True}
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="shifts")
    bookings = relationship("Booking", back_populates="shift")
    routes = relationship("Route", back_populates="shift")

