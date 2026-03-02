from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, JSON, func, Index, ForeignKey
from app.database.session import Base


class NotificationLog(Base):
    """
    Tracks every batch of notifications sent for a route.
    One record is created per dispatch (vehicle assignment or manual resend).
    """
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_tenant_route", "tenant_id", "route_id"),
        Index("ix_notification_logs_created_at", "created_at"),
        Index("ix_notification_logs_tenant_shift_date", "tenant_id", "shift_id", "booking_date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Context
    tenant_id = Column(String(50), nullable=False)
    route_id = Column(Integer, nullable=False)
    route_code = Column(String(100), nullable=True)
    shift_id = Column(Integer, nullable=True)
    booking_date = Column(Date, nullable=True)
    triggered_by = Column(String(50), nullable=False, default="vehicle_assignment")
    # e.g. "vehicle_assignment" | "resend" | "dispatch"

    # Counts
    total_employees = Column(Integer, nullable=False, default=0)
    email_sent = Column(Integer, nullable=False, default=0)
    email_failed = Column(Integer, nullable=False, default=0)
    sms_sent = Column(Integer, nullable=False, default=0)
    sms_failed = Column(Integer, nullable=False, default=0)
    push_sent = Column(Integer, nullable=False, default=0)
    push_failed = Column(Integer, nullable=False, default=0)

    # Per-booking breakdown (list of dicts with booking_id, employee_id, email/sms/push status)
    details = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
