from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("vendor_id", "contract_name", name="uq_vendor_contract_name"),
        UniqueConstraint("vendor_id", "vehicle_type_id", name="uq_vendor_vehicle_type_contract"),
        Index("ix_contracts_vendor_active", "vendor_id", "is_active"),
    )

    contract_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="CASCADE"), nullable=False)
    # Placeholder for the future employee-side Cost Center module. No FK yet because cost_centers does not exist.
    cost_center_id = Column(Integer, nullable=True)
    contract_name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    vendor = relationship("Vendor", back_populates="contracts")
    vehicle_type = relationship("VehicleType", back_populates="contracts")
    slabs = relationship(
        "ContractSlab",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ContractSlab.min_km",
    )
    vehicles = relationship("Vehicle", back_populates="contract")


class ContractSlab(Base):
    __tablename__ = "contract_slabs"
    __table_args__ = (
        UniqueConstraint("contract_id", "min_km", name="uq_contract_slab_min_km"),
        CheckConstraint("min_km >= 0", name="ck_contract_slabs_min_km_non_negative"),
        CheckConstraint("max_km IS NULL OR max_km > min_km", name="ck_contract_slabs_max_gt_min"),
        CheckConstraint("rate > 0", name="ck_contract_slabs_rate_positive"),
        Index("ix_contract_slabs_contract_active", "contract_id", "is_active"),
    )

    slab_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    contract_id = Column(Integer, ForeignKey("contracts.contract_id", ondelete="CASCADE"), nullable=False)
    min_km = Column(Float, nullable=False)
    max_km = Column(Float, nullable=True)
    rate = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    contract = relationship("Contract", back_populates="slabs")
