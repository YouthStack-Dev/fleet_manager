from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, Enum, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database.session import Base
from enum import Enum as PyEnum

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
        UniqueConstraint("vendor_id", "alt_govt_id_number", name="uq_vendor_driver_alt_govt_id"),
    )

    driver_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    code = Column(String(50), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(20), nullable=False)
    gender = Column(Enum(GenderEnum, native_enum=False))
    password = Column(String(255), nullable=False)
    date_of_joining = Column(Date)
    date_of_birth = Column(Date)
    permanent_address = Column(Text)
    current_address = Column(Text)
    
    bg_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    bg_verify_date = Column(Date)
    bg_verify_url = Column(Text)
    
    police_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    police_verify_date = Column(Date)
    police_verify_url = Column(Text)
    
    medical_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    medical_verify_date = Column(Date)
    medical_verify_url = Column(Text)
    
    training_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    training_verify_date = Column(Date)
    training_verify_url = Column(Text)
    
    eye_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    eye_verify_date = Column(Date)
    eye_verify_url = Column(Text)
    
    license_number = Column(String(100))
    license_expiry_date = Column(Date)
    
    induction_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    induction_date = Column(Date)
    induction_url = Column(Text)
    
    badge_number = Column(String(100))
    badge_expiry_date = Column(Date)
    badge_url = Column(Text)
    
    alt_govt_id_number = Column(String(20))
    alt_govt_id_type = Column(String(50))
    alt_govt_id_url = Column(Text)
    
    photo_url = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    vendor = relationship("Vendor", back_populates="drivers")
    vehicles = relationship("Vehicle", back_populates="driver")
