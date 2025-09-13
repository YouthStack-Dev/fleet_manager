from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base

class VehicleType(Base):
    __tablename__ = "vehicle_types"
    __table_args__ = (
        UniqueConstraint("vendor_id", "name", name="uq_vendor_vehicle_type_name"),
    )
    __table_args__ = {'extend_existing': True}
    
    vehicle_type_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    seats = Column(Integer, nullable=False)  # 👈 number of passenger seats
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    vendor = relationship("Vendor", back_populates="vehicle_types")
    vehicles = relationship("Vehicle", back_populates="vehicle_type", cascade="all, delete-orphan")
