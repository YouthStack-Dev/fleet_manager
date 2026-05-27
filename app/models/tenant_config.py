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

    # ── OTA/OTD Delay Classification (Feature 4) ───────────────────
    # Grace window before a first-stop lateness is attributed to the driver
    delay_driver_grace_minutes = Column(Integer, nullable=False, server_default="10")
    # Per-stop grace window before employee boarding lateness is counted
    delay_employee_grace_minutes = Column(Integer, nullable=False, server_default="5")

    # ── Driver Duty Hours & Rest-Time Enforcement (Feature 1) ──────
    # Maximum minutes a driver may be on duty within any 24-hour window
    # (default 600 = 10 hours; required rest = 24h - max_duty)
    driver_max_duty_minutes = Column(Integer, nullable=False, server_default="600")
    # 'warn'  → assignment proceeds but response includes a warning
    # 'block' → assignment is rejected with HTTP 409 if rest is insufficient
    driver_rest_enforcement = Column(String(10), nullable=False, server_default="warn")

    # ── Female Employee Dark-Hour Boarding Block (Feature 12) ──────
    # 'off'   → feature disabled (default; zero impact on existing tenants)
    # 'warn'  → boarding proceeds, but response includes "dark_hour_no_escort" warning
    # 'block' → boarding rejected with HTTP 423 when female employee in dark hours
    #           without a boarded escort; also fires a security push notification
    dark_hour_boarding_mode = Column(String(10), nullable=False, server_default="off")

    # ── IMP-7: Geofence Arrival Triggers ───────────────────────────
    # Radius (metres) within which the driver is considered "arriving" at a stop.
    # When the driver enters this zone, an FCM is sent to the waiting employee.
    geofence_arrival_radius_meters = Column(Integer, nullable=False, server_default="300")

    # ── IMP-6: ETA Recalculation from Live Location ─────────────────
    # Minimum ETA change (minutes) required before a new estimate is pushed
    # to the employee via FCM.  Prevents notification spam for tiny fluctuations.
    eta_change_threshold_minutes = Column(Integer, nullable=False, server_default="5")

    # ── IMP-5: Stale Driver Alerting ─────────────────────────────────
    # Minutes without a GPS ping before an ONGOING route's driver is flagged
    # as "stale" and ops admins are alerted via FCM.  Default 5 min.
    stale_driver_threshold_minutes = Column(Integer, nullable=False, server_default="5")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship back to tenant
    tenant = relationship("Tenant", back_populates="config", uselist=False)