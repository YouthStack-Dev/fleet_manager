from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, UniqueConstraint, String, Boolean
from sqlalchemy.orm import relationship
from database.session import Base


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = {'extend_existing': True}

    vendor_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    vendor_code = Column(String(50), unique=True)
    email = Column(String(150), unique=True)
    phone = Column(String(20), unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    drivers = relationship("app.models.driver.Driver", back_populates="vendor", cascade="all, delete-orphan")
    vehicle_types = relationship("app.models.vehicle_type.VehicleType", back_populates="vendor", cascade="all, delete-orphan")
    vehicles = relationship("app.models.vehicle.Vehicle", back_populates="vendor", cascade="all, delete-orphan")
    vendor_users = relationship("app.models.vendor_user.VendorUser", back_populates="vendor", cascade="all, delete-orphan")

    # Link to tenants
    tenants = relationship("TenantVendor", back_populates="vendor", cascade="all, delete-orphan")


class TenantVendor(Base):
    __tablename__ = "tenant_vendors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vendor_id", name="uq_tenant_vendor"),
    )
    __table_args__ = {'extend_existing': True}

    tenant_vendor_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)

    # Status fields
    is_active = Column(Boolean, default=True, nullable=False)  # active/inactive link
    linked_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="vendors")
    vendor = relationship("Vendor", back_populates="tenants")