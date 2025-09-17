from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, UniqueConstraint, String, Boolean
from sqlalchemy.orm import relationship
from app.database.session import Base


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)

    name = Column(String(150), nullable=False)
    vendor_code = Column(String(50), unique=True, nullable=False)  # unique for login
    email = Column(String(150), nullable=True)  # make non-unique so same email can exist in diff tenants
    phone = Column(String(20), nullable=True)  # same reason as above
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_vendor_name_per_tenant"),
        UniqueConstraint("tenant_id", "vendor_code", name="uq_vendor_code_per_tenant"),
        UniqueConstraint("tenant_id", "email", name="uq_vendor_email_per_tenant"),  # prevent duplicate vendor email within tenant
        UniqueConstraint("tenant_id", "phone", name="uq_vendor_phone_per_tenant"),  # prevent duplicate vendor phone within tenant
        {"extend_existing": True},
    )

    # ✅ Backref to Tenant
    tenant = relationship("Tenant", back_populates="vendors")

    # Future relationships
    drivers = relationship("Driver", back_populates="vendor", cascade="all, delete-orphan")
    vehicle_types = relationship("VehicleType", back_populates="vendor", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="vendor", cascade="all, delete-orphan")
    vendor_users = relationship("VendorUser", back_populates="vendor", cascade="all, delete-orphan")