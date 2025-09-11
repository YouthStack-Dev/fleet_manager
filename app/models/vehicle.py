from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from database.session import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(Integer, primary_key=True, index=True)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"))
    rc_number = Column(String(100), unique=True, nullable=False)
    rc_expiry_date = Column(Date)
    description = Column(Text)
    puc_expiry_date = Column(Date)
    puc_url = Column(Text)
    fitness_expiry_date = Column(Date)
    fitness_url = Column(Text)
    tax_receipt_date = Column(Date)
    tax_receipt_url = Column(Text)
    insurance_expiry_date = Column(Date)
    insurance_url = Column(Text)
    permit_expiry_date = Column(Date)
    permit_url = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vehicle_type = relationship("VehicleType", back_populates="vehicles")
    vendor = relationship("Vendor", back_populates="vehicles")
    driver = relationship("Driver", back_populates="vehicles")
