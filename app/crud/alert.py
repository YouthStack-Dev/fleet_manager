"""
CRUD operations for Alert System
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, desc, exists, cast, Text
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.models.alert import (
    Alert, AlertEscalation, AlertNotification, AlertConfiguration,
    AlertStatusEnum, AlertSeverityEnum, AlertTypeEnum,
    NotificationChannelEnum, NotificationStatusEnum
)
from app.schemas.alert import (
    AlertTriggerRequest, AlertAcknowledgeRequest, AlertCloseRequest,
    AlertEscalateRequest, AlertUpdateRequest
)
from common_utils import get_current_ist_time
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# Alert CRUD Operations
# ============================================================================

def create_alert(
    db: Session,
    tenant_id: str,
    employee_id: int,
    booking_id: Optional[int] = None,
    alert_type: AlertTypeEnum = AlertTypeEnum.SOS,
    severity: AlertSeverityEnum = AlertSeverityEnum.CRITICAL,
    trigger_latitude: float = 0.0,
    trigger_longitude: float = 0.0,
    trigger_notes: Optional[str] = None,
    evidence_urls: Optional[List[str]] = None
) -> Alert:
    """Create a new alert"""
    now = get_current_ist_time()
    
    alert = Alert(
        tenant_id=tenant_id,
        employee_id=employee_id,
        booking_id=booking_id,
        alert_type=alert_type,
        severity=severity,
        status=AlertStatusEnum.TRIGGERED,
        trigger_latitude=trigger_latitude,
        trigger_longitude=trigger_longitude,
        trigger_notes=trigger_notes,
        evidence_urls=evidence_urls,
        triggered_at=now,
        created_at=now,
        updated_at=now
    )
    
    db.add(alert)
    db.flush()  # Get alert_id
    
    logger.info(f"[alert.create] Created alert {alert.alert_id} for employee {employee_id}, tenant {tenant_id}")
    
    return alert


def get_alert_by_id(
    db: Session,
    alert_id: int,
    tenant_id: str,
    include_relations: bool = False
) -> Optional[Alert]:
    """Get alert by ID"""
    query = db.query(Alert).filter(
        Alert.alert_id == alert_id,
        Alert.tenant_id == tenant_id
    )
    
    if include_relations:
        query = query.options(
            joinedload(Alert.escalations),
            joinedload(Alert.notifications)
        )
    
    return query.first()


def get_alerts(
    db: Session,
    tenant_id: str,
    employee_id: Optional[int] = None,
    booking_id: Optional[int] = None,
    status: Optional[AlertStatusEnum] = None,
    alert_type: Optional[AlertTypeEnum] = None,
    severity: Optional[AlertSeverityEnum] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    is_false_alarm: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Alert]:
    """Get alerts with filters"""
    query = db.query(Alert).filter(Alert.tenant_id == tenant_id)
    
    if employee_id:
        query = query.filter(Alert.employee_id == employee_id)
    
    if booking_id:
        query = query.filter(Alert.booking_id == booking_id)
    
    if status:
        query = query.filter(Alert.status == status)
    
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    if from_date:
        query = query.filter(Alert.triggered_at >= from_date)
    
    if to_date:
        query = query.filter(Alert.triggered_at <= to_date)
    
    if is_false_alarm is not None:
        query = query.filter(Alert.is_false_alarm == is_false_alarm)
    
    query = query.order_by(desc(Alert.triggered_at))
    
    return query.limit(limit).offset(offset).all()


def get_active_alerts(db: Session, tenant_id: str, employee_id: Optional[int] = None) -> List[Alert]:
    """Get active (not closed) alerts"""
    query = db.query(Alert).filter(
        Alert.tenant_id == tenant_id,
        Alert.status.in_([
            AlertStatusEnum.TRIGGERED,
            AlertStatusEnum.ACKNOWLEDGED,
            AlertStatusEnum.IN_PROGRESS,
            AlertStatusEnum.RESOLVED
        ])
    )
    
    if employee_id:
        query = query.filter(Alert.employee_id == employee_id)
    
    return query.order_by(desc(Alert.triggered_at)).all()


def acknowledge_alert(
    db: Session,
    alert: Alert,
    responder_id: int,
    responder_name: str,
    notes: Optional[str] = None
) -> Alert:
    """Acknowledge an alert"""
    now = get_current_ist_time()
    
    if alert.status == AlertStatusEnum.TRIGGERED:
        alert.status = AlertStatusEnum.ACKNOWLEDGED
    
    alert.acknowledged_at = now
    alert.acknowledged_by = responder_id
    alert.acknowledged_by_name = responder_name
    
    # Make triggered_at timezone-aware if it's naive
    triggered_at = alert.triggered_at
    if triggered_at.tzinfo is None:
        from datetime import timezone, timedelta
        ist_offset = timedelta(hours=5, minutes=30)
        triggered_at = triggered_at.replace(tzinfo=timezone(ist_offset))
    
    alert.response_time_seconds = int((now - triggered_at).total_seconds())
    
    if notes:
        alert.resolution_notes = notes
    
    alert.updated_at = now
    
    db.add(alert)
    logger.info(f"[alert.acknowledge] Alert {alert.alert_id} acknowledged by {responder_name} (ID: {responder_id})")
    
    return alert


def update_alert_status(
    db: Session,
    alert: Alert,
    new_status: AlertStatusEnum,
    updated_by: Optional[str] = None
) -> Alert:
    """Update alert status"""
    now = get_current_ist_time()
    old_status = alert.status
    
    alert.status = new_status
    alert.updated_at = now
    
    if new_status == AlertStatusEnum.RESOLVED:
        # Make triggered_at timezone-aware if it's naive
        triggered_at = alert.triggered_at
        if triggered_at.tzinfo is None:
            from datetime import timezone, timedelta
            ist_offset = timedelta(hours=5, minutes=30)
            triggered_at = triggered_at.replace(tzinfo=timezone(ist_offset))
        alert.resolution_time_seconds = int((now - triggered_at).total_seconds())
    
    db.add(alert)
    logger.info(f"[alert.status] Alert {alert.alert_id} status changed: {old_status} → {new_status}")
    
    return alert


def close_alert(
    db: Session,
    alert: Alert,
    closed_by: int,
    closed_by_name: str,
    resolution_notes: str,
    is_false_alarm: bool
) -> Alert:
    """Close an alert"""
    now = get_current_ist_time()
    
    alert.status = AlertStatusEnum.FALSE_ALARM if is_false_alarm else AlertStatusEnum.CLOSED
    alert.closed_at = now
    alert.closed_by = closed_by
    alert.closed_by_name = closed_by_name
    alert.is_false_alarm = is_false_alarm
    
    if resolution_notes:
        alert.resolution_notes = resolution_notes
    
    # Make triggered_at timezone-aware if it's naive
    triggered_at = alert.triggered_at
    if triggered_at.tzinfo is None:
        from datetime import timezone, timedelta
        ist_offset = timedelta(hours=5, minutes=30)
        triggered_at = triggered_at.replace(tzinfo=timezone(ist_offset))
    
    alert.resolution_time_seconds = int((now - triggered_at).total_seconds())
    
    alert.updated_at = now
    
    db.add(alert)
    logger.info(f"[alert.close] Alert {alert.alert_id} closed by {closed_by_name} (ID: {closed_by}), false_alarm={is_false_alarm}")
    
    return alert


def update_alert(
    db: Session,
    alert: Alert,
    request: AlertUpdateRequest
) -> Alert:
    """Update alert details"""
    now = get_current_ist_time()
    
    if request.status:
        alert.status = request.status
    
    if request.severity:
        alert.severity = request.severity
    
    if request.resolution_notes:
        alert.resolution_notes = request.resolution_notes
    
    alert.updated_at = now
    db.add(alert)
    
    return alert


def check_escalation_needed(db: Session, alert: Alert, config: AlertConfiguration) -> bool:
    """Check if alert needs escalation based on config"""
    if not config.enable_escalation:
        return False
    
    if alert.status in [AlertStatusEnum.CLOSED, AlertStatusEnum.FALSE_ALARM]:
        return False
    
    # Check if already escalated
    if alert.auto_escalated:
        return False
    
    # Check time threshold
    now = get_current_ist_time()
    elapsed = (now - alert.triggered_at).total_seconds()
    
    return elapsed >= config.escalation_threshold_seconds


# ============================================================================
# Alert Escalation CRUD
# ============================================================================

def create_escalation(
    db: Session,
    alert: Alert,
    request: Optional[AlertEscalateRequest] = None,
    is_auto: bool = False,
    escalation_level: int = 1,
    escalated_to_recipients: list = None,
    reason: str = ""
) -> AlertEscalation:
    """Create escalation record"""
    now = get_current_ist_time()
    
    # Build recipients list
    if request:
        recipients = [{"email": request.escalated_to}]
    elif escalated_to_recipients:
        recipients = escalated_to_recipients
    else:
        recipients = []
    
    escalation = AlertEscalation(
        alert_id=alert.alert_id,
        escalation_level=request.escalation_level if request else escalation_level,
        escalated_to_recipients=recipients,
        escalated_at=now,
        escalation_reason=request.reason if request else reason,
        is_automatic=is_auto,
        created_at=now
    )
    
    db.add(escalation)
    
    if is_auto:
        alert.auto_escalated = True
        alert.updated_at = now
        db.add(alert)
    
    # Flush to get the auto-generated escalation_id
    db.flush()
    db.refresh(escalation)
    
    logger.info(f"[alert.escalation] Alert {alert.alert_id} escalated to level {escalation.escalation_level}, auto={is_auto}, escalation_id={escalation.escalation_id}")
    
    return escalation


def get_escalations_for_alert(db: Session, alert_id: int) -> List[AlertEscalation]:
    """Get all escalations for an alert"""
    return db.query(AlertEscalation).filter(
        AlertEscalation.alert_id == alert_id
    ).order_by(AlertEscalation.escalated_at).all()


# ============================================================================
# Alert Notification CRUD
# ============================================================================

def create_notification(
    db: Session,
    alert: Alert,
    recipient_name: Optional[str],
    recipient_email: Optional[str],
    recipient_phone: Optional[str],
    recipient_role: Optional[str],
    channel: NotificationChannelEnum,
    subject: str,
    message: str
) -> AlertNotification:
    """Create notification record"""
    now = get_current_ist_time()
    
    notification = AlertNotification(
        alert_id=alert.alert_id,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        recipient_phone=recipient_phone,
        recipient_role=recipient_role,
        channel=channel,
        status=NotificationStatusEnum.PENDING,
        subject=subject,
        message=message,
        created_at=now,
        updated_at=now
    )
    
    db.add(notification)
    
    return notification


def update_notification_status(
    db: Session,
    notification: AlertNotification,
    status: NotificationStatusEnum,
    failure_reason: Optional[str] = None
) -> AlertNotification:
    """Update notification delivery status"""
    now = get_current_ist_time()
    
    notification.status = status
    notification.updated_at = now
    
    if status == NotificationStatusEnum.SENT:
        notification.sent_at = now
    elif status == NotificationStatusEnum.DELIVERED:
        notification.delivered_at = now
    elif status in [NotificationStatusEnum.FAILED, NotificationStatusEnum.BOUNCED]:
        notification.failure_reason = failure_reason
    
    db.add(notification)
    
    return notification


def get_notifications_for_alert(db: Session, alert_id: int) -> List[AlertNotification]:
    """Get all notifications for an alert"""
    return db.query(AlertNotification).filter(
        AlertNotification.alert_id == alert_id
    ).order_by(AlertNotification.created_at).all()


# ============================================================================
# Alert Configuration CRUD
# ============================================================================

def create_alert_configuration(
    db: Session,
    tenant_id: str,
    config_data: Dict[str, Any],
    created_by: Optional[str] = None
) -> AlertConfiguration:
    """Create alert configuration"""
    now = get_current_ist_time()
    
    # Convert Pydantic models to dicts for JSON storage
    if 'primary_recipients' in config_data and isinstance(config_data['primary_recipients'], list):
        config_data['primary_recipients'] = [
            r.dict() if hasattr(r, 'dict') else r for r in config_data['primary_recipients']
        ]
    
    if 'escalation_recipients' in config_data and config_data['escalation_recipients']:
        config_data['escalation_recipients'] = [
            r.dict() if hasattr(r, 'dict') else r for r in config_data['escalation_recipients']
        ]
    
    if 'emergency_contacts' in config_data and config_data['emergency_contacts']:
        config_data['emergency_contacts'] = [
            c.dict() if hasattr(c, 'dict') else c for c in config_data['emergency_contacts']
        ]
    
    config = AlertConfiguration(
        tenant_id=tenant_id,
        **config_data,
        created_at=now,
        updated_at=now,
        created_by=created_by
    )
    
    db.add(config)
    logger.info(f"[alert.config] Created config {config.config_name} for tenant {tenant_id}")
    
    return config



def get_alert_configuration_by_id(
    db: Session,
    config_id: int,
    tenant_id: str
) -> Optional[AlertConfiguration]:
    """Get configuration by ID"""
    return db.query(AlertConfiguration).filter(
        AlertConfiguration.config_id == config_id,
        AlertConfiguration.tenant_id == tenant_id
    ).first()


def get_alert_configurations(
    db: Session,
    tenant_id: str,
    team_id: Optional[int] = None,
    is_active: Optional[bool] = True
) -> List[AlertConfiguration]:
    """Get alert configurations for tenant/team"""
    query = db.query(AlertConfiguration).filter(
        AlertConfiguration.tenant_id == tenant_id
    )
    
    if team_id is not None:
        query = query.filter(AlertConfiguration.team_id == team_id)
    
    if is_active is not None:
        query = query.filter(AlertConfiguration.is_active == is_active)
    
    return query.order_by(desc(AlertConfiguration.priority)).all()


def get_alert_configuration(
    db: Session,
    tenant_id: str,
    team_id: Optional[int] = None
) -> Optional[AlertConfiguration]:
    """Get a single alert configuration for tenant/team (checks for existing)"""
    query = db.query(AlertConfiguration).filter(
        AlertConfiguration.tenant_id == tenant_id
    )
    
    if team_id is not None:
        query = query.filter(AlertConfiguration.team_id == team_id)
    else:
        query = query.filter(AlertConfiguration.team_id.is_(None))
    
    return query.first()


def get_applicable_configuration(
    db: Session,
    tenant_id: str,
    alert_type: AlertTypeEnum,
    team_id: Optional[int] = None
) -> Optional[AlertConfiguration]:
    """Get the most applicable configuration for an alert"""
    import json
    
    logger.info(f"[get_applicable_configuration] Searching for tenant_id={tenant_id}, alert_type={alert_type.value}, team_id={team_id}")
    
    query = db.query(AlertConfiguration).filter(
        AlertConfiguration.tenant_id == tenant_id,
        AlertConfiguration.is_active == True
    )
    
    # For JSON column querying in PostgreSQL, we need to cast to text
    # and search for the value in the JSON array string representation
    alert_type_str = f'"{alert_type.value}"'  # JSON string format
    
    logger.info(f"[get_applicable_configuration] Searching for alert_type_str: {alert_type_str}")
    
    # Try team-specific first if team_id provided
    if team_id:
        logger.info(f"[get_applicable_configuration] Checking team-specific config for team_id={team_id}")
        team_config = query.filter(
            AlertConfiguration.team_id == team_id,
            or_(
                AlertConfiguration.applicable_alert_types.is_(None),
                cast(AlertConfiguration.applicable_alert_types, Text).contains(alert_type_str)
            )
        ).order_by(desc(AlertConfiguration.priority)).first()
        
        if team_config:
            logger.info(f"[get_applicable_configuration] Found team-specific config: {team_config.config_id}")
            return team_config
    
    # Fall back to tenant-wide
    logger.info(f"[get_applicable_configuration] Checking tenant-wide config")
    
    # First, let's see all configs for this tenant
    all_tenant_configs = db.query(AlertConfiguration).filter(
        AlertConfiguration.tenant_id == tenant_id,
        AlertConfiguration.is_active == True,
        AlertConfiguration.team_id.is_(None)
    ).all()
    
    logger.info(f"[get_applicable_configuration] Found {len(all_tenant_configs)} active tenant configs with NULL team_id")
    for cfg in all_tenant_configs:
        logger.info(f"  - Config ID {cfg.config_id}: applicable_alert_types={cfg.applicable_alert_types}, priority={cfg.priority}")
    
    tenant_config = query.filter(
        AlertConfiguration.team_id.is_(None),
        or_(
            AlertConfiguration.applicable_alert_types.is_(None),
            cast(AlertConfiguration.applicable_alert_types, Text).contains(alert_type_str)
        )
    ).order_by(desc(AlertConfiguration.priority)).first()
    
    if tenant_config:
        logger.info(f"[get_applicable_configuration] Found tenant-wide config: {tenant_config.config_id}")
    else:
        logger.warning(f"[get_applicable_configuration] No config found for tenant_id={tenant_id}, alert_type={alert_type.value}")
    
    return tenant_config


def update_alert_configuration(
    db: Session,
    config: AlertConfiguration,
    update_data: Dict[str, Any],
    updated_by: Optional[str] = None
) -> AlertConfiguration:
    """Update alert configuration"""
    now = get_current_ist_time()
    
    for key, value in update_data.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    
    config.updated_at = now
    config.updated_by = updated_by
    
    db.add(config)
    
    return config


def delete_alert_configuration(db: Session, config: AlertConfiguration) -> None:
    """Soft delete configuration by marking inactive"""
    config.is_active = False
    config.updated_at = get_current_ist_time()
    db.add(config)


# ============================================================================
# Analytics & Metrics
# ============================================================================

def get_alert_metrics(
    db: Session,
    tenant_id: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get alert system metrics"""
    query = db.query(Alert).filter(Alert.tenant_id == tenant_id)
    
    if from_date:
        query = query.filter(Alert.triggered_at >= from_date)
    
    if to_date:
        query = query.filter(Alert.triggered_at <= to_date)
    
    all_alerts = query.all()
    total = len(all_alerts)
    
    if total == 0:
        return {
            "total_alerts": 0,
            "active_alerts": 0,
            "alerts_by_status": {},
            "alerts_by_severity": {},
            "alerts_by_type": {},
            "average_response_time_seconds": None,
            "average_resolution_time_seconds": None,
            "false_alarm_rate": None,
            "escalation_rate": None
        }
    
    # Count by status
    status_counts = {}
    for alert in all_alerts:
        status_counts[alert.status.value] = status_counts.get(alert.status.value, 0) + 1
    
    # Count by severity
    severity_counts = {}
    for alert in all_alerts:
        severity_counts[alert.severity.value] = severity_counts.get(alert.severity.value, 0) + 1
    
    # Count by type
    type_counts = {}
    for alert in all_alerts:
        type_counts[alert.alert_type.value] = type_counts.get(alert.alert_type.value, 0) + 1
    
    # Calculate averages
    response_times = [a.response_time_seconds for a in all_alerts if a.response_time_seconds]
    resolution_times = [a.resolution_time_seconds for a in all_alerts if a.resolution_time_seconds]
    false_alarms = len([a for a in all_alerts if a.is_false_alarm])
    escalated = len([a for a in all_alerts if a.auto_escalated])
    
    active_count = len([a for a in all_alerts if a.status not in [
        AlertStatusEnum.CLOSED, AlertStatusEnum.FALSE_ALARM
    ]])
    
    return {
        "total_alerts": total,
        "active_alerts": active_count,
        "alerts_by_status": status_counts,
        "alerts_by_severity": severity_counts,
        "alerts_by_type": type_counts,
        "average_response_time_seconds": sum(response_times) / len(response_times) if response_times else None,
        "average_resolution_time_seconds": sum(resolution_times) / len(resolution_times) if resolution_times else None,
        "false_alarm_rate": (false_alarms / total * 100) if total > 0 else None,
        "escalation_rate": (escalated / total * 100) if total > 0 else None
    }


def get_alert_timeline(
    db: Session,
    alert_id: int,
    tenant_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get alert event timeline
    Returns all events related to an alert in chronological order
    """
    alert = db.query(Alert).filter(
        Alert.alert_id == alert_id,
        Alert.tenant_id == tenant_id
    ).first()
    
    if not alert:
        return None
    
    events = []
    
    # Triggered event
    events.append({
        "timestamp": alert.triggered_at,
        "event_type": "TRIGGERED",
        "description": f"Alert triggered by employee {alert.employee_id}",
        "details": {
            "location": f"{alert.trigger_latitude}, {alert.trigger_longitude}",
            "notes": alert.trigger_notes,
            "severity": alert.severity.value,
            "type": alert.alert_type.value
        }
    })
    
    # Acknowledged event
    if alert.acknowledged_at:
        events.append({
            "timestamp": alert.acknowledged_at,
            "event_type": "ACKNOWLEDGED",
            "description": f"Alert acknowledged by {alert.acknowledged_by_name}",
            "details": {
                "responder_id": alert.acknowledged_by,
                "acknowledgment_notes": alert.acknowledgment_notes,
                "response_time_seconds": alert.response_time_seconds
            }
        })
    
    # Escalation events
    escalations = db.query(AlertEscalation).filter(
        AlertEscalation.alert_id == alert_id
    ).order_by(AlertEscalation.escalated_at).all()
    
    for escalation in escalations:
        events.append({
            "timestamp": escalation.escalated_at,
            "event_type": "ESCALATED",
            "description": f"Alert escalated to level {escalation.escalation_level}",
            "details": {
                "level": escalation.escalation_level,
                "is_automatic": escalation.is_automatic,
                "recipients": escalation.escalated_to_recipients,
                "reason": escalation.escalation_reason
            }
        })
    
    # Closed event
    if alert.closed_at:
        events.append({
            "timestamp": alert.closed_at,
            "event_type": "CLOSED",
            "description": f"Alert closed by {alert.closed_by_name}",
            "details": {
                "closed_by_id": alert.closed_by,
                "resolution_notes": alert.resolution_notes,
                "is_false_alarm": alert.is_false_alarm,
                "resolution_time_seconds": alert.resolution_time_seconds
            }
        })
    
    # Sort by timestamp
    events.sort(key=lambda x: x["timestamp"])
    
    return {
        "alert_id": alert_id,
        "current_status": alert.status.value,
        "events": events,
        "total_events": len(events)
    }


def update_notification_status(
    db: Session,
    notification: AlertNotification,
    status: NotificationStatusEnum,
    failure_reason: Optional[str] = None
) -> AlertNotification:
    """Update notification status"""
    now = get_current_ist_time()
    
    notification.status = status
    notification.updated_at = now
    
    if status == NotificationStatusEnum.SENT:
        notification.sent_at = now
    elif status == NotificationStatusEnum.DELIVERED:
        notification.delivered_at = now
    elif status == NotificationStatusEnum.FAILED:
        notification.failure_reason = failure_reason
    
    db.commit()
    db.refresh(notification)
    
    return notification
