from sqlalchemy import Column, String, Boolean, Time, ForeignKey, DateTime, func
from app.database.session import Base
from sqlalchemy.orm import relationship

class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        unique=True
    )

    # Escort Safety Configuration
    escort_required_start_time = Column(Time, nullable=True)  # e.g., 18:00 (6 PM)
    escort_required_end_time = Column(Time, nullable=True)    # e.g., 06:00 (6 AM)
    escort_required_for_women = Column(Boolean, default=True, nullable=False)  # Enable women safety escorts

    # OTP requirements (boarding/deboarding flags)
    login_boarding_otp = Column(Boolean, nullable=False, server_default="true")
    login_deboarding_otp = Column(Boolean, nullable=False, server_default="true")
    logout_boarding_otp = Column(Boolean, nullable=False, server_default="true")
    logout_deboarding_otp = Column(Boolean, nullable=False, server_default="true")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship back to tenant
    tenant = relationship("Tenant", back_populates="config", uselist=False)

    __table_args__ = (
        {"extend_existing": True}
    )