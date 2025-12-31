"""
Pydantic schemas for Alert System
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.alert import (
    AlertStatusEnum, AlertSeverityEnum, AlertTypeEnum,
    NotificationChannelEnum, NotificationStatusEnum
)


# ============================================================================
# Alert Schemas
# ============================================================================

class AlertTriggerRequest(BaseModel):
    """Request to trigger an SOS alert"""
    booking_id: Optional[int] = Field(None, description="Current booking ID if on trip")
    alert_type: AlertTypeEnum = Field(AlertTypeEnum.SOS, description="Type of alert")
    severity: AlertSeverityEnum = Field(AlertSeverityEnum.CRITICAL, description="Alert severity")
    current_latitude: float = Field(..., description="Current location latitude")
    current_longitude: float = Field(..., description="Current location longitude")
    trigger_notes: Optional[str] = Field(None, max_length=1000, description="Additional notes from employee")
    evidence_urls: Optional[List[str]] = Field(None, description="URLs to uploaded evidence (photos, recordings)")
    
    model_config = ConfigDict(use_enum_values=True)


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert"""
    acknowledged_by: str = Field(..., max_length=100, description="Name/ID of responder")
    notes: Optional[str] = Field(None, max_length=500, description="Acknowledgment notes")


class AlertCloseRequest(BaseModel):
    """Request to close an alert"""
    closed_by: int = Field(..., description="User ID of person closing")
    resolution_notes: str = Field(..., max_length=2000, description="Detailed resolution notes")
    is_false_alarm: bool = Field(False, description="Mark as false alarm")


class AlertEscalateRequest(BaseModel):
    """Request to manually escalate an alert"""
    escalated_by: str = Field(..., max_length=100, description="Name/ID of person escalating")
    escalation_level: int = Field(..., ge=1, le=10, description="Escalation level (1-10)")
    escalated_to: str = Field(..., max_length=200, description="Email/phone of escalation recipient")
    reason: str = Field(..., max_length=500, description="Reason for escalation")


class AlertUpdateRequest(BaseModel):
    """Request to update alert status/details"""
    status: Optional[AlertStatusEnum] = Field(None, description="New status")
    severity: Optional[AlertSeverityEnum] = Field(None, description="New severity")
    resolution_notes: Optional[str] = Field(None, max_length=2000, description="Resolution notes")
    
    model_config = ConfigDict(use_enum_values=True)


# Response Schemas

class AlertEscalationResponse(BaseModel):
    """Alert escalation record"""
    escalation_id: int
    alert_id: int
    escalation_level: int
    escalated_to_recipients: List[Dict[str, Any]]  # JSON array of recipients
    escalated_at: datetime
    escalation_reason: Optional[str]
    is_automatic: bool
    
    model_config = ConfigDict(from_attributes=True)


class AlertNotificationResponse(BaseModel):
    """Alert notification record"""
    notification_id: int
    alert_id: int
    recipient_name: Optional[str]
    recipient_email: Optional[str]
    recipient_phone: Optional[str]
    recipient_role: Optional[str]
    channel: str
    status: str
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    failure_reason: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


class AlertResponse(BaseModel):
    """Complete alert details"""
    alert_id: int
    tenant_id: str
    employee_id: int
    booking_id: Optional[int]
    
    alert_type: str
    severity: str
    status: str
    
    trigger_latitude: float
    trigger_longitude: float
    
    triggered_at: datetime
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[int]
    acknowledged_by_name: Optional[str]
    acknowledgment_notes: Optional[str]
    estimated_arrival_minutes: Optional[int]
    closed_at: Optional[datetime]
    closed_by: Optional[int]
    closed_by_name: Optional[str]
    
    response_time_seconds: Optional[int]
    resolution_time_seconds: Optional[int]
    
    trigger_notes: Optional[str]
    resolution_notes: Optional[str]
    evidence_urls: Optional[List[str]]
    
    is_false_alarm: bool
    auto_escalated: bool
    alert_metadata: Optional[Dict[str, Any]]
    
    created_at: datetime
    updated_at: datetime
    
    # Include relationships if needed
    escalations: Optional[List[AlertEscalationResponse]] = None
    notifications: Optional[List[AlertNotificationResponse]] = None
    
    model_config = ConfigDict(from_attributes=True)


class AlertSummaryResponse(BaseModel):
    """Simplified alert summary for lists"""
    alert_id: int
    tenant_id: str
    employee_id: int
    booking_id: Optional[int]
    alert_type: str
    severity: str
    status: str
    triggered_at: datetime
    response_time_seconds: Optional[int]
    is_false_alarm: bool
    
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Alert Configuration Schemas
# ============================================================================

class RecipientConfig(BaseModel):
    """Notification recipient configuration"""
    name: str = Field(..., max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[str] = Field(None, max_length=100)
    channels: List[NotificationChannelEnum] = Field(..., description="Preferred notification channels")
    
    model_config = ConfigDict(use_enum_values=True)


class EmergencyContact(BaseModel):
    """External emergency service contact"""
    name: str = Field(..., max_length=200, description="e.g., Police, Ambulance, Fire Brigade")
    phone: str = Field(..., max_length=20, description="Contact phone number")
    email: Optional[str] = Field(None, max_length=200, description="Contact email address")
    service_type: Optional[str] = Field(None, max_length=50, description="POLICE, MEDICAL, FIRE, etc.")


class AlertConfigurationCreate(BaseModel):
    """Create alert configuration"""
    tenant_id: Optional[str] = Field(None, description="Tenant ID (required for admin, auto-filled for employee)")
    team_id: Optional[int] = Field(None, description="Team-level config, null for tenant-wide")
    config_name: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    
    applicable_alert_types: Optional[List[AlertTypeEnum]] = Field(None, description="Alert types this applies to")
    primary_recipients: List[RecipientConfig] = Field(..., min_length=1, description="Level 1 recipients")
    
    enable_escalation: bool = Field(True)
    escalation_threshold_seconds: int = Field(300, ge=30, le=3600, description="Time before escalation")
    escalation_recipients: Optional[List[RecipientConfig]] = Field(None, description="Level 2+ recipients")
    
    notification_channels: List[NotificationChannelEnum] = Field(..., min_length=1)
    notify_on_status_change: bool = Field(True)
    notify_on_escalation: bool = Field(True)
    
    auto_close_false_alarm_seconds: Optional[int] = Field(None, ge=60, le=600)
    require_closure_notes: bool = Field(True)
    enable_geofencing_alerts: bool = Field(False)
    geofence_radius_meters: Optional[int] = Field(1000, ge=100, le=10000)
    
    emergency_contacts: Optional[List[EmergencyContact]] = Field(None)
    priority: int = Field(100, ge=1, le=1000)
    
    model_config = ConfigDict(use_enum_values=True)


class AlertConfigurationUpdate(BaseModel):
    """Update alert configuration"""
    config_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    applicable_alert_types: Optional[List[AlertTypeEnum]] = None
    primary_recipients: Optional[List[RecipientConfig]] = None
    enable_escalation: Optional[bool] = None
    escalation_threshold_seconds: Optional[int] = Field(None, ge=30, le=3600)
    escalation_recipients: Optional[List[RecipientConfig]] = None
    notification_channels: Optional[List[NotificationChannelEnum]] = None
    notify_on_status_change: Optional[bool] = None
    notify_on_escalation: Optional[bool] = None
    auto_close_false_alarm_seconds: Optional[int] = Field(None, ge=60, le=600)
    require_closure_notes: Optional[bool] = None
    enable_geofencing_alerts: Optional[bool] = None
    geofence_radius_meters: Optional[int] = Field(None, ge=100, le=10000)
    emergency_contacts: Optional[List[EmergencyContact]] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    
    model_config = ConfigDict(use_enum_values=True)


class AlertConfigurationResponse(BaseModel):
    """Alert configuration response"""
    config_id: int
    tenant_id: str
    team_id: Optional[int]
    config_name: str
    description: Optional[str]
    applicable_alert_types: Optional[List[str]]
    primary_recipients: List[Dict[str, Any]]
    enable_escalation: bool
    escalation_threshold_seconds: int
    escalation_recipients: Optional[List[Dict[str, Any]]]
    notification_channels: List[str]
    notify_on_status_change: bool
    notify_on_escalation: bool
    auto_close_false_alarm_seconds: Optional[int]
    require_closure_notes: bool
    enable_geofencing_alerts: bool
    geofence_radius_meters: Optional[int]
    emergency_contacts: Optional[List[Dict[str, Any]]]
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    updated_by: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Dashboard & Analytics Schemas
# ============================================================================

class AlertMetrics(BaseModel):
    """Alert system metrics"""
    total_alerts: int
    active_alerts: int
    alerts_by_status: Dict[str, int]
    alerts_by_severity: Dict[str, int]
    alerts_by_type: Dict[str, int]
    average_response_time_seconds: Optional[float]
    average_resolution_time_seconds: Optional[float]
    false_alarm_rate: Optional[float]
    escalation_rate: Optional[float]


class AlertTimelineEvent(BaseModel):
    """Event in alert timeline"""
    event_time: datetime
    event_type: str  # TRIGGERED, ACKNOWLEDGED, ESCALATED, RESOLVED, CLOSED
    actor: Optional[str]
    notes: Optional[str]
    metadata: Optional[Dict[str, Any]]


class AlertListResponse(BaseModel):
    """Paginated list of alerts"""
    total: int
    alerts: List[AlertSummaryResponse]
    page: int
    page_size: int
    
    model_config = ConfigDict(from_attributes=True)


class AlertTimelineResponse(BaseModel):
    """Complete alert timeline with all events"""
    alert: AlertResponse
    timeline: List[AlertTimelineEvent]
    
    model_config = ConfigDict(from_attributes=True)
