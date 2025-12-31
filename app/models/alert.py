"""
Alert System Models for Employee Transport SOS/Panic Button

Models:
- Alert: Core alert records (trigger, status, resolution)
- AlertEscalation: Escalation history and timing
- AlertNotification: Notification tracking across channels
- AlertConfiguration: Tenant/team-level alert routing rules
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text, 
    ForeignKey, Enum as SQLEnum, Index, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from app.database.session import Base


class AlertStatusEnum(str, PyEnum):
    """Alert lifecycle statuses"""
    TRIGGERED = "TRIGGERED"  # Initial state when SOS pressed
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Responder has seen the alert
    IN_PROGRESS = "IN_PROGRESS"  # Active response in progress
    RESOLVED = "RESOLVED"  # Issue resolved, awaiting closure
    CLOSED = "CLOSED"  # Officially closed with notes
    FALSE_ALARM = "FALSE_ALARM"  # Marked as accidental/false


class AlertSeverityEnum(str, PyEnum):
    """Alert severity levels"""
    CRITICAL = "CRITICAL"  # Immediate danger
    HIGH = "HIGH"  # Serious concern
    MEDIUM = "MEDIUM"  # Moderate issue
    LOW = "LOW"  # Minor concern


class AlertTypeEnum(str, PyEnum):
    """Types of alerts"""
    SOS = "SOS"  # Emergency panic button
    SAFETY_CONCERN = "SAFETY_CONCERN"  # Safety issue reported
    ROUTE_DEVIATION = "ROUTE_DEVIATION"  # Vehicle off planned route
    DELAYED = "DELAYED"  # Significant delay
    ACCIDENT = "ACCIDENT"  # Vehicle accident
    MEDICAL = "MEDICAL"  # Medical emergency
    OTHER = "OTHER"  # Other issues


class NotificationChannelEnum(str, PyEnum):
    """Notification delivery channels"""
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"  # Firebase push notification
    VOICE = "VOICE"  # Automated voice call
    WHATSAPP = "WHATSAPP"  # WhatsApp message


class NotificationStatusEnum(str, PyEnum):
    """Notification delivery status"""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class Alert(Base):
    """
    Core alert table - stores all SOS and safety alerts
    """
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_status", "tenant_id", "status"),
        Index("ix_alerts_employee", "employee_id", "triggered_at"),
        Index("ix_alerts_booking", "booking_id"),
        Index("ix_alerts_triggered_at", "triggered_at"),
        {"extend_existing": True},
    )

    alert_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    
    # Context information
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id"), nullable=True)
    
    # Alert details
    alert_type = Column(SQLEnum(AlertTypeEnum, native_enum=False), default=AlertTypeEnum.SOS, nullable=False)
    severity = Column(SQLEnum(AlertSeverityEnum, native_enum=False), default=AlertSeverityEnum.CRITICAL, nullable=False)
    status = Column(SQLEnum(AlertStatusEnum, native_enum=False), default=AlertStatusEnum.TRIGGERED, nullable=False)
    
    # Location at trigger time
    trigger_latitude = Column(Float, nullable=False)
    trigger_longitude = Column(Float, nullable=False)
    
    # Timestamps
    triggered_at = Column(DateTime, default=func.now(), nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, nullable=True)  # User ID who acknowledged
    acknowledged_by_name = Column(String(255), nullable=True)  # Name of acknowledger
    acknowledgment_notes = Column(Text, nullable=True)  # Notes when acknowledging
    estimated_arrival_minutes = Column(Integer, nullable=True)  # ETA provided by responder
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(Integer, nullable=True)  # User ID who closed
    closed_by_name = Column(String(255), nullable=True)  # Name of closer
    
    # Response details
    response_time_seconds = Column(Integer, nullable=True)  # Time to acknowledge
    resolution_time_seconds = Column(Integer, nullable=True)  # Time to resolve
    
    # Notes and evidence
    trigger_notes = Column(Text, nullable=True)  # Employee's note when triggering
    resolution_notes = Column(Text, nullable=True)  # Final resolution notes
    evidence_urls = Column(JSON, nullable=True)  # Array of file URLs (photos, recordings)
    
    # Metadata
    is_false_alarm = Column(Boolean, default=False, nullable=False)
    auto_escalated = Column(Boolean, default=False, nullable=False)
    alert_metadata = Column("metadata", JSON, nullable=True)  # Maps to 'metadata' column in DB
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    escalations = relationship("AlertEscalation", back_populates="alert", cascade="all, delete-orphan")
    notifications = relationship("AlertNotification", back_populates="alert", cascade="all, delete-orphan")


class AlertEscalation(Base):
    """
    Tracks escalation history for alerts
    """
    __tablename__ = "alert_escalations"
    __table_args__ = (
        Index("ix_alert_escalations_alert", "alert_id", "escalated_at"),
        {"extend_existing": True},
    )

    escalation_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False)
    
    escalation_level = Column(Integer, default=1, nullable=False)  # 1, 2, 3...
    escalated_to_recipients = Column(JSON, nullable=False)  # JSON array of recipients
    escalated_at = Column(DateTime, default=func.now(), nullable=False)
    escalation_reason = Column(Text, nullable=True)  # Why escalated
    is_automatic = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    alert = relationship("Alert", back_populates="escalations")


class AlertNotification(Base):
    """
    Tracks all notifications sent for alerts across channels
    """
    __tablename__ = "alert_notifications"
    __table_args__ = (
        Index("ix_alert_notifications_alert", "alert_id", "sent_at"),
        Index("ix_alert_notifications_status", "status", "channel"),
        {"extend_existing": True},
    )

    notification_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False)
    
    # Recipient details
    recipient_name = Column(String(200), nullable=True)
    recipient_email = Column(String(200), nullable=True)
    recipient_phone = Column(String(20), nullable=True)
    recipient_role = Column(String(100), nullable=True)  # Manager, Security, Admin, etc.
    
    # Notification details
    channel = Column(SQLEnum(NotificationChannelEnum, native_enum=False), nullable=False)
    status = Column(SQLEnum(NotificationStatusEnum, native_enum=False), default=NotificationStatusEnum.PENDING, nullable=False)
    
    # Content
    subject = Column(String(500), nullable=True)
    message = Column(Text, nullable=False)
    
    # Delivery tracking
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    alert = relationship("Alert", back_populates="notifications")


class AlertConfiguration(Base):
    """
    Configures alert routing and escalation rules per tenant/team
    """
    __tablename__ = "alert_configurations"
    __table_args__ = (
        Index("ix_alert_configurations_tenant", "tenant_id", "is_active"),
        Index("ix_alert_configurations_team", "team_id"),
        {"extend_existing": True},
    )

    config_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=True)  # Null = tenant-wide
    
    config_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Alert types this config applies to
    applicable_alert_types = Column(JSON, nullable=True)  # ["SOS", "SAFETY_CONCERN"] or null for all
    
    # Primary recipients (Level 1)
    primary_recipients = Column(JSON, nullable=False)  # [{name, email, phone, channels: []}]
    
    # Escalation rules
    enable_escalation = Column(Boolean, default=True, nullable=False)
    escalation_threshold_seconds = Column(Integer, default=300, nullable=False)  # 5 minutes default
    escalation_recipients = Column(JSON, nullable=True)  # Level 2+ recipients
    
    # Notification preferences
    notification_channels = Column(JSON, nullable=False)  # ["EMAIL", "SMS", "PUSH"]
    notify_on_status_change = Column(Boolean, default=True, nullable=False)
    notify_on_escalation = Column(Boolean, default=True, nullable=False)
    
    # Advanced settings
    auto_close_false_alarm_seconds = Column(Integer, nullable=True)  # Auto-close if resolved quickly
    require_closure_notes = Column(Boolean, default=True, nullable=False)
    enable_geofencing_alerts = Column(Boolean, default=False, nullable=False)
    geofence_radius_meters = Column(Integer, default=1000, nullable=True)
    
    # Emergency contacts
    emergency_contacts = Column(JSON, nullable=True)  # External emergency services contacts
    
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=100, nullable=False)  # Higher = higher priority
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
