from sqlalchemy import Column, String, DateTime, ForeignKey, func, Interval, Boolean
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

    booking_login_cutoff = Column(Interval, nullable=False, server_default="0")
    cancel_login_cutoff = Column(Interval, nullable=False, server_default="0")
    booking_logout_cutoff = Column(Interval, nullable=False, server_default="0")
    cancel_logout_cutoff = Column(Interval, nullable=False, server_default="0")
    medical_emergency_booking_cutoff = Column(Interval, nullable=False, server_default="0")
    medical_emergency_cancel_cutoff = Column(Interval, nullable=False, server_default="0")
    adhoc_booking_cutoff = Column(Interval, nullable=False, server_default="0")
    
    # Enable/disable flags for special booking types
    allow_adhoc_booking = Column(Boolean, nullable=False, server_default="false")
    allow_medical_emergency_booking = Column(Boolean, nullable=False, server_default="false")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    tenant = relationship("Tenant", back_populates="cutoff", uselist=False)
    __table_args__ = {"extend_existing": True}