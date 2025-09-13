from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, func
from app.database.session import Base
from sqlalchemy.orm import relationship

class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {'extend_existing': True}

    tenant_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    tenant_code = Column(String(50), unique=True, nullable=False)
    address = Column(String(255))
    longitude = Column(Numeric(9, 6))
    latitude = Column(Numeric(9, 6))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    teams = relationship("Team", back_populates="tenant", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="tenant", cascade="all, delete-orphan")
    shifts = relationship("Shift", back_populates="tenant", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="tenant", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="tenant", cascade="all, delete-orphan")

    # TenantVendor relationship
    vendors = relationship("TenantVendor", back_populates="tenant", cascade="all, delete-orphan")
    vendor_users = relationship("TenantVendorUser", back_populates="tenant", cascade="all, delete-orphan")
