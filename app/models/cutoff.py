from sqlalchemy import Column, String, DateTime, ForeignKey, func, Interval
from app.database.session import Base
from sqlalchemy.orm import relationship

class Cutoff(Base):
    __tablename__ = "cutoffs"

    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        unique=True  
    )

    booking_cutoff = Column(Interval, nullable=False, server_default="0")
    cancel_cutoff = Column(Interval, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    tenant = relationship("Tenant", back_populates="cutoff", uselist=False)
    __table_args__ = {"extend_existing": True}