from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class VendorUser(Base):
    __tablename__ = "vendor_users"
    __table_args__ = (
        UniqueConstraint("vendor_id", "email", name="uq_vendor_email"),
        UniqueConstraint("vendor_id", "phone", name="uq_vendor_phone"),
        {"extend_existing": True},
    )

    vendor_user_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(20), nullable=False)
    password = Column(String(255), nullable=False)

    role_id = Column(Integer, ForeignKey("iam_roles.role_id", ondelete="CASCADE"), nullable=False)  # VendorAdmin, Dispatcher, etc.
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("app.models.vendor.Vendor", back_populates="vendor_users")
    roles = relationship(
        "Role",
        back_populates="vendor_users"
    )
    
