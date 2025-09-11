from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from database.session import Base

class VehicleType(Base):
    __tablename__ = "vehicle_types"
    
    vehicle_type_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    vendor = relationship("Vendor", back_populates="vehicle_types")
    vehicles = relationship("Vehicle", back_populates="vehicle_type", cascade="all, delete-orphan")
