from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base
from app.models.vendor import Vendor

class VendorUser(Base):
    __tablename__ = "vendor_users"
    __table_args__ = {'extend_existing': True}

    vendor_user_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    vendor = relationship("app.models.vendor.Vendor", back_populates="vendor_users")
    tenants = relationship("TenantVendorUser", back_populates="vendor_user", cascade="all, delete-orphan")


class TenantVendorUser(Base):
    __tablename__ = "tenant_vendor_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vendor_user_id", name="uq_tenant_vendor_user"),
    )
    __table_args__ = {'extend_existing': True}

    tenant_vendor_user_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    vendor_user_id = Column(Integer, ForeignKey("vendor_users.vendor_user_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="VendorAdmin")  # VendorAdmin, Dispatcher, etc.
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    tenant = relationship("Tenant", back_populates="vendor_users")
    vendor_user = relationship("VendorUser", back_populates="tenants")

