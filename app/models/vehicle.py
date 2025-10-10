from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("vendor_id", "rc_number", name="uq_vendor_rc_number"),
        UniqueConstraint("vendor_id", "puc_number", name="uq_vendor_puc_number"),
        UniqueConstraint("vendor_id", "fitness_number", name="uq_vendor_fitness_number"),
        UniqueConstraint("vendor_id", "tax_receipt_number", name="uq_vendor_tax_receipt_number"),
        UniqueConstraint("vendor_id", "insurance_number", name="uq_vendor_insurance_number"),
        UniqueConstraint("vendor_id", "permit_number", name="uq_vendor_permit_number"),
        {"extend_existing": True},
    )

    vehicle_id = Column(Integer, primary_key=True, index=True)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"))

    rc_number = Column(String(100), nullable=False)
    rc_expiry_date = Column(Date, nullable=True)      
    description = Column(Text)

    puc_number = Column(String(100))
    puc_expiry_date = Column(Date)
    puc_url = Column(Text)

    fitness_number = Column(String(100))
    fitness_expiry_date = Column(Date)
    fitness_url = Column(Text)

    tax_receipt_number = Column(String(100))
    tax_receipt_date = Column(Date)
    tax_receipt_url = Column(Text)

    insurance_number = Column(String(100))
    insurance_expiry_date = Column(Date)
    insurance_url = Column(Text)

    permit_number = Column(String(100))
    permit_expiry_date = Column(Date)
    permit_url = Column(Text)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vehicle_type = relationship("app.models.vehicle_type.VehicleType", back_populates="vehicles")
    vendor = relationship("app.models.vendor.Vendor", back_populates="vehicles")
    driver = relationship("app.models.driver.Driver", back_populates="vehicles")
