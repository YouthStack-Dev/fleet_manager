"""
Alert Router - SOS Alert System
Employee and responder facing endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from app.database.session import get_db
from app.models.alert import AlertStatusEnum, AlertSeverityEnum, AlertTypeEnum
from app.schemas.alert import (
    AlertTriggerRequest,
    AlertAcknowledgeRequest,
    AlertCloseRequest,
    AlertEscalateRequest,
    AlertResponse,
    AlertListResponse,
    AlertTimelineResponse
)
from app.crud import alert as alert_crud
from app.crud import booking as booking_crud
from app.crud import employee as employee_crud
from app.services.notification_service import NotificationService
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


async def get_current_employee(user_data=Depends(PermissionChecker(["app-employee.read", "app-employee.write"]))):
    """Ensures the token belongs to an employee persona and returns employee data."""
    if user_data.get("user_type") not in ["employee", "admin"]:
        raise HTTPException(status_code=403, detail="Employee access only")
    return user_data


@router.post("/trigger", response_model=dict)
async def trigger_alert(
    request: AlertTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Trigger SOS alert from employee
    
    - Validates active booking
    - Creates alert with location
    - Sends notifications to configured recipients
    - Returns alert details
    """
    try:
        employee_id = current_employee["employee_id"]
        tenant_id = current_employee["tenant_id"]
        
        logger.info(f"[alert.trigger] Employee {employee_id} triggering alert")
        
        # Validate booking if provided
        if request.booking_id:
            booking = booking_crud.get_booking_by_id(db, request.booking_id, tenant_id)
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            
            if booking.employee_id != employee_id:
                raise HTTPException(status_code=403, detail="Not your booking")
            
            # Check if booking is active (today)
            if booking.booking_date != date.today():
                raise HTTPException(status_code=400, detail="Booking is not active today")
        
        # Check for duplicate active alert
        active_alerts = alert_crud.get_alerts(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            status=AlertStatusEnum.TRIGGERED,
            limit=1
        )
        
        if active_alerts:
            raise HTTPException(
                status_code=400,
                detail=f"You already have an active alert: #{active_alerts[0].alert_id}"
            )
        
        # Create alert
        alert = alert_crud.create_alert(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            booking_id=request.booking_id,
            alert_type=request.alert_type or AlertTypeEnum.SOS,
            severity=request.severity or AlertSeverityEnum.CRITICAL,
            trigger_latitude=request.trigger_latitude,
            trigger_longitude=request.trigger_longitude,
            trigger_notes=request.trigger_notes,
            evidence_urls=request.evidence_urls
        )
        
        logger.info(f"[alert.trigger] Alert {alert.alert_id} created successfully")
        
        # Get configuration
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            team_id=current_employee.get("team_id")
        )
        
        if not config:
            logger.warning(f"[alert.trigger] No alert configuration found for tenant {tenant_id}")
            # Continue without notifications
        else:
            # Send notifications in background
            background_tasks.add_task(
                send_alert_notifications,
                db_session=db,
                alert_id=alert.alert_id,
                config_id=config.config_id
            )
        
        return ResponseWrapper(
            success=True,
            message="Alert triggered successfully. Help is on the way.",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.trigger] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger alert: {str(e)}")


@router.get("/active", response_model=dict)
def get_active_alerts(
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get employee's active alerts
    """
    try:
        employee_id = current_employee["employee_id"]
        tenant_id = current_employee["tenant_id"]
        
        # Get active alerts (TRIGGERED or ACKNOWLEDGED)
        alerts = alert_crud.get_alerts(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            status=[AlertStatusEnum.TRIGGERED, AlertStatusEnum.ACKNOWLEDGED],
            limit=10
        )
        
        return ResponseWrapper(
            success=True,
            message=f"Found {len(alerts)} active alert(s)",
            data=[AlertResponse.from_orm(alert).dict() for alert in alerts]
        )
        
    except Exception as e:
        logger.error(f"[alert.active] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-alerts", response_model=dict)
def get_my_alerts(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[AlertStatusEnum] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get employee's alert history with filters
    """
    try:
        employee_id = current_employee["employee_id"]
        tenant_id = current_employee["tenant_id"]
        
        alerts = alert_crud.get_alerts(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        
        # Check if more results exist
        has_more = len(alerts) == limit
        
        response_data = AlertListResponse(
            alerts=[AlertResponse.from_orm(alert).dict() for alert in alerts],
            total=len(alerts),
            has_more=has_more
        )
        
        return ResponseWrapper(
            success=True,
            message=f"Retrieved {len(alerts)} alert(s)",
            data=response_data.dict()
        )
        
    except Exception as e:
        logger.error(f"[alert.my-alerts] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}", response_model=dict)
def get_alert_details(
    alert_id: int,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get alert details by ID
    - Employee can view their own alerts
    - Responders can view alerts they're handling
    """
    try:
        tenant_id = current_employee["tenant_id"]
        employee_id = current_employee["employee_id"]
        
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        # Check access: either own alert or responder
        is_responder = current_employee.get("role") in ["ADMIN", "TRANSPORT_MANAGER", "SECURITY"]
        if alert.employee_id != employee_id and not is_responder:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return ResponseWrapper(
            success=True,
            message="Alert retrieved",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.details] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{alert_id}/acknowledge", response_model=dict)
async def acknowledge_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Acknowledge alert (responder only)
    
    - Changes status to ACKNOWLEDGED
    - Records responder details
    - Calculates response time
    - Sends status notification
    """
    try:
        tenant_id = current_employee["tenant_id"]
        responder_id = current_employee["employee_id"]
        responder_name = current_employee.get("name", "Unknown")
        
        # Check responder role
        is_responder = current_employee.get("role") in ["ADMIN", "TRANSPORT_MANAGER", "SECURITY"]
        if not is_responder:
            raise HTTPException(status_code=403, detail="Only responders can acknowledge alerts")
        
        # Acknowledge alert
        alert = alert_crud.acknowledge_alert(
            db=db,
            alert_id=alert_id,
            tenant_id=tenant_id,
            acknowledged_by=responder_id,
            acknowledged_by_name=responder_name,
            acknowledgment_notes=request.acknowledgment_notes,
            estimated_arrival_minutes=request.estimated_arrival_minutes
        )
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        logger.info(f"[alert.acknowledge] Alert {alert_id} acknowledged by {responder_name}")
        
        # Get configuration for notifications
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            team_id=None  # Get tenant-level config
        )
        
        if config and config.notify_on_status_change:
            # Send status update notifications
            background_tasks.add_task(
                send_status_notification,
                db_session=db,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                new_status=AlertStatusEnum.ACKNOWLEDGED.value
            )
        
        return ResponseWrapper(
            success=True,
            message=f"Alert acknowledged. Response time: {alert.response_time_seconds}s",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.acknowledge] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{alert_id}/close", response_model=dict)
async def close_alert(
    alert_id: int,
    request: AlertCloseRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Close alert with resolution
    
    - Changes status to CLOSED or FALSE_ALARM
    - Records resolution details
    - Calculates resolution time
    - Sends final notification
    """
    try:
        tenant_id = current_employee["tenant_id"]
        closed_by = current_employee["employee_id"]
        closed_by_name = current_employee.get("name", "Unknown")
        
        # Check role
        is_authorized = current_employee.get("role") in ["ADMIN", "TRANSPORT_MANAGER", "SECURITY"]
        if not is_authorized:
            raise HTTPException(status_code=403, detail="Only authorized personnel can close alerts")
        
        # Close alert
        alert = alert_crud.close_alert(
            db=db,
            alert_id=alert_id,
            tenant_id=tenant_id,
            closed_by=closed_by,
            closed_by_name=closed_by_name,
            resolution_notes=request.resolution_notes,
            is_false_alarm=request.is_false_alarm
        )
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        logger.info(f"[alert.close] Alert {alert_id} closed by {closed_by_name}")
        
        # Get configuration for notifications
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            team_id=None
        )
        
        if config and config.notify_on_status_change:
            background_tasks.add_task(
                send_status_notification,
                db_session=db,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                new_status=alert.status.value
            )
        
        return ResponseWrapper(
            success=True,
            message=f"Alert closed. Total resolution time: {alert.resolution_time_seconds}s",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.close] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/escalate", response_model=dict)
async def manual_escalate_alert(
    alert_id: int,
    request: AlertEscalateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Manually escalate alert to higher level
    """
    try:
        tenant_id = current_employee["tenant_id"]
        escalated_by = current_employee["employee_id"]
        escalated_by_name = current_employee.get("name", "Unknown")
        
        # Check role
        is_authorized = current_employee.get("role") in ["ADMIN", "TRANSPORT_MANAGER", "SECURITY"]
        if not is_authorized:
            raise HTTPException(status_code=403, detail="Only authorized personnel can escalate alerts")
        
        # Get alert
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        if alert.status in [AlertStatusEnum.CLOSED, AlertStatusEnum.FALSE_ALARM]:
            raise HTTPException(status_code=400, detail="Cannot escalate closed alert")
        
        # Create escalation
        escalation = alert_crud.create_escalation(
            db=db,
            alert=alert,
            escalation_level=request.escalation_level,
            escalated_to_recipients=request.escalated_to_recipients,
            escalation_reason=request.escalation_reason,
            is_automatic=False
        )
        
        logger.info(f"[alert.escalate] Alert {alert_id} manually escalated to level {request.escalation_level}")
        
        # Get configuration for notifications
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            team_id=None
        )
        
        if config:
            background_tasks.add_task(
                send_escalation_notification,
                db_session=db,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                escalation_level=request.escalation_level
            )
        
        return ResponseWrapper(
            success=True,
            message=f"Alert escalated to level {request.escalation_level}",
            data={"escalation": escalation}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.escalate] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}/timeline", response_model=dict)
def get_alert_timeline(
    alert_id: int,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get alert event timeline
    """
    try:
        tenant_id = current_employee["tenant_id"]
        
        timeline = alert_crud.get_alert_timeline(db, alert_id, tenant_id)
        
        if not timeline:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return ResponseWrapper(
            success=True,
            message="Timeline retrieved",
            data=AlertTimelineResponse(**timeline).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.timeline] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Background task functions
async def send_alert_notifications(db_session: Session, alert_id: int, config_id: int):
    """Send notifications when alert is triggered"""
    try:
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        if alert and config:
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_triggered(alert, config)
    except Exception as e:
        logger.error(f"[background.notify] Error sending notifications: {str(e)}")


async def send_status_notification(
    db_session: Session,
    alert_id: int,
    config_id: int,
    new_status: str
):
    """Send notification on status change"""
    try:
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        if alert and config:
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_status_change(alert, config, new_status)
    except Exception as e:
        logger.error(f"[background.status_notify] Error: {str(e)}")


async def send_escalation_notification(
    db_session: Session,
    alert_id: int,
    config_id: int,
    escalation_level: int
):
    """Send notification on escalation"""
    try:
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        if alert and config:
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_escalated(alert, config, escalation_level)
    except Exception as e:
        logger.error(f"[background.escalate_notify] Error: {str(e)}")

