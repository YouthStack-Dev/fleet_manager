from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from database.session import Base

class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True)
    email = Column(String(150), unique=True)
    phone = Column(String(20), unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    drivers = relationship("Driver", back_populates="vendor", cascade="all, delete-orphan")
    vehicle_types = relationship("VehicleType", back_populates="vendor", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="vendor", cascade="all, delete-orphan")
    vendor_users = relationship("VendorUser", back_populates="vendor", cascade="all, delete-orphan")
