from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, Enum, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum
from app.models.vendor import Vendor

class GenderEnum(str, PyEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class VerificationStatusEnum(str, PyEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"

class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("vendor_id", "email", name="uq_vendor_driver_email"),
        UniqueConstraint("vendor_id", "phone", name="uq_vendor_driver_phone"),
        UniqueConstraint("vendor_id", "badge_number", name="uq_vendor_driver_badge"),
        UniqueConstraint("vendor_id", "license_number", name="uq_vendor_driver_license"),
        UniqueConstraint("vendor_id", "code", name="uq_vendor_driver_code"),
        UniqueConstraint("vendor_id", "alt_govt_id_number", name="uq_vendor_driver_alt_govt_id"),
        {"extend_existing": True},
    )

    driver_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("iam_roles.role_id", ondelete="CASCADE"), nullable=False)
    # Personal info
    name = Column(String(150), nullable=False)
    code = Column(String(50), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(20), nullable=False)
    gender = Column(Enum(GenderEnum, native_enum=False))
    password = Column(String(255), nullable=False)
    date_of_birth = Column(Date)
    date_of_joining = Column(Date)
    permanent_address = Column(Text)
    current_address = Column(Text)
    photo_url = Column(Text)

    # Verification statuses
    bg_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    bg_expiry_date = Column(Date)
    bg_verify_url = Column(Text)

    police_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    police_expiry_date = Column(Date)
    police_verify_url = Column(Text)

    medical_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    medical_expiry_date = Column(Date)
    medical_verify_url = Column(Text)

    training_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    training_expiry_date = Column(Date)
    training_verify_url = Column(Text)

    eye_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    eye_expiry_date = Column(Date)
    eye_verify_url = Column(Text)

    # License info
    license_number = Column(String(100))
    license_expiry_date = Column(Date)
    license_url = Column(Text)

    # Badge info
    badge_number = Column(String(100))
    badge_expiry_date = Column(Date)
    badge_url = Column(Text)

    # Alternate government ID
    alt_govt_id_number = Column(String(20))
    alt_govt_id_type = Column(String(50))
    alt_govt_id_url = Column(Text)

    # Induction
    induction_date = Column(Date)
    induction_url = Column(Text)

    # System fields
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("app.models.vendor.Vendor", back_populates="drivers")
    vehicles = relationship("app.models.vehicle.Vehicle", back_populates="driver")
    role = relationship("Role", back_populates="drivers")