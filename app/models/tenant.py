from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, func
from app.database.session import Base
from sqlalchemy.orm import relationship

class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {'extend_existing': True}

    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    address = Column(String(255))
    longitude = Column(Numeric(9, 6))
    latitude = Column(Numeric(9, 6))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    teams = relationship("Team", back_populates="tenant", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="tenant", cascade="all, delete-orphan")
    shifts = relationship("Shift", back_populates="tenant", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="tenant", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="tenant", cascade="all, delete-orphan")
    # policy = relationship("Policy", back_populates="tenant", cascade="all, delete-orphan")
    cutoff = relationship("Cutoff", back_populates="tenant", uselist=False, cascade="all, delete-orphan")

    # ✅ One-to-many Tenant → Vendor
    vendors = relationship("Vendor", back_populates="tenant", cascade="all, delete-orphan")

    roles = relationship("Role", back_populates="tenant")

