from sqlalchemy import Column, Integer, String, Boolean, Time, ForeignKey, DateTime, Float, func
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

    # Speed limit configuration (km/h) — used to detect speed violations
    speed_limit_kmph = Column(Float, nullable=True, default=60.0)

    # One-trip-per-shift enforcement
    one_trip_per_shift_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    # When True: conflicting booking is auto-moved to new route; when False: operation is blocked
    auto_move_on_conflict = Column(Boolean, default=True, nullable=False, server_default="true")

    # ── Schedule Reminder Notifications ───────────────────────────
    # Enable/disable pre-trip push + SMS reminders for this tenant
    schedule_reminder_enabled = Column(Boolean, default=False, nullable=False, server_default="false")
    # How many minutes before pickup time to send the reminder (default: 30)
    schedule_reminder_minutes = Column(Integer, nullable=False, server_default="30")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship back to tenant
    tenant = relationship("Tenant", back_populates="config", uselist=False)