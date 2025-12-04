from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Boolean, Text
from sqlalchemy.orm import relationship
from app.database.session import Base


class Escort(Base):
    __tablename__ = "escorts"

    escort_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)

    # Personal Information
    name = Column(String(100), nullable=False)
    phone = Column(String(15), nullable=False, unique=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)

    # Status and Activity
    is_active = Column(Boolean, default=True, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)  # Available for assignment

    # Gender for safety matching (optional)
    gender = Column(String(10), nullable=True)

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="escorts")
    vendor = relationship("Vendor", back_populates="escorts")