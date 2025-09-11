from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, func
from database.session import Base

class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    address = Column(String(255))
    longitude = Column(Numeric(9, 6))
    latitude = Column(Numeric(9, 6))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
