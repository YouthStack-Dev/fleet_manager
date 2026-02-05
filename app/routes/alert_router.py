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
from app.crud.booking import booking_crud
from app.crud import employee as employee_crud
from app.services.notification_service import NotificationService
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


async def get_current_employee(user_data=Depends(PermissionChecker(["app-employee.read", "app-employee.write","booking.read"]))):
    """Ensures the token belongs to an employee persona and returns employee data."""
    if user_data.get("user_type") not in ["employee", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=ResponseWrapper.error(
                message="Employee access only",
                error_code="ACCESS_FORBIDDEN"
            )
        )
    return user_data


def check_user_permission(permissions: list, module: str, action: str = None) -> bool:
    """
    Check if user has permission for a module/action
    
    Args:
        permissions: List of permission dicts from JWT token
        module: Module name (e.g., 'alert', 'booking')
        action: Optional action name (e.g., 'read', 'write', 'respond')
    
    Returns:
        bool: True if user has permission
    """
    if not isinstance(permissions, list):
        return False
    
    for perm in permissions:
        if not isinstance(perm, dict):
            continue
        
        perm_module = perm.get("module", "")
        perm_actions = perm.get("action", [])
        
        # Check for admin module (grants all access)
        if perm_module == "admin":
            return True
        
        # Check for exact module match
        if perm_module == module:
            if action is None:
                return True
            if isinstance(perm_actions, list) and action in perm_actions:
                return True
    
    return False


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
        # Get employee_id from token (could be in employee_id or user_id field)
        employee_id = current_employee.get("employee_id") or current_employee.get("user_id")
        tenant_id = current_employee.get("tenant_id")
        
        if not employee_id:
            logger.error(f"[alert.trigger] No employee_id in token. Token data: {current_employee.keys()}")
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="Employee ID not found in authentication token",
                    error_code="INVALID_TOKEN"
                )
            )
        
        # Convert employee_id to int for database comparison
        employee_id = int(employee_id)
        
        logger.info(f"[alert.trigger] Employee {employee_id} triggering alert")
        
        # Normalize booking_id: treat 0 as None
        booking_id = request.booking_id if request.booking_id else None
        logger.info(f"[alert.trigger] Booking ID received: {request.booking_id}, normalized: {booking_id}")
        
        # Validate booking if provided
        if booking_id:
            booking = booking_crud.get_by_id(db, booking_id=booking_id)
            logger.info(f"[alert.trigger] Booking found: {booking is not None}")
            
            if not booking:
                logger.error(f"[alert.trigger] Booking {booking_id} not found in database")
                raise HTTPException(
                    status_code=404,
                    detail=ResponseWrapper.error(
                        message="Booking not found",
                        error_code="BOOKING_NOT_FOUND"
                    )
                )
            
            logger.info(f"[alert.trigger] Booking validation - booking.tenant_id={booking.tenant_id}, current tenant_id={tenant_id}")
            logger.info(f"[alert.trigger] Booking validation - booking.employee_id={booking.employee_id}, current employee_id={employee_id}")
            
            # Validate tenant and employee
            if booking.tenant_id != tenant_id:
                logger.error(f"[alert.trigger] Tenant mismatch: booking.tenant_id={booking.tenant_id} != current tenant={tenant_id}")
                raise HTTPException(
                    status_code=403,
                    detail=ResponseWrapper.error(
                        message="Booking not found in your organization",
                        error_code="ACCESS_FORBIDDEN"
                    )
                )
            
            if booking.employee_id != employee_id:
                logger.error(f"[alert.trigger] Employee mismatch: booking.employee_id={booking.employee_id} (type={type(booking.employee_id).__name__}) != current employee={employee_id} (type={type(employee_id).__name__})")
                raise HTTPException(
                    status_code=403,
                    detail=ResponseWrapper.error(
                        message="Not your booking",
                        error_code="ACCESS_FORBIDDEN"
                    )
                )
            
            logger.info(f"[alert.trigger] Booking validation passed - checking date")
            # Check if booking is active (today)
            if booking.booking_date != date.today():
                logger.error(f"[alert.trigger] Booking date mismatch: booking.booking_date={booking.booking_date} != today={date.today()}")
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Booking is not active today",
                        error_code="INVALID_BOOKING_DATE"
                    )
                )
        
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
                detail=ResponseWrapper.error(
                    message=f"You already have an active alert: #{active_alerts[0].alert_id}",
                    error_code="DUPLICATE_ALERT"
                )
            )
        
        # Create alert
        alert = alert_crud.create_alert(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            booking_id=booking_id,  # Use normalized booking_id (None instead of 0)
            alert_type=request.alert_type or AlertTypeEnum.SOS,
            severity=request.severity or AlertSeverityEnum.CRITICAL,
            trigger_latitude=request.current_latitude,
            trigger_longitude=request.current_longitude,
            trigger_notes=request.trigger_notes,
            evidence_urls=request.evidence_urls
        )
        
        logger.info(f"[alert.trigger] Alert {alert.alert_id} created successfully")
        
        # Commit the alert to database before background task
        db.commit()
        logger.info(f"[alert.trigger] Alert {alert.alert_id} committed to database")
        
        # Get configuration (convert alert_type string to enum)
        alert_type_enum = AlertTypeEnum(alert.alert_type) if isinstance(alert.alert_type, str) else alert.alert_type
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            alert_type=alert_type_enum,
            team_id=current_employee.get("team_id")
        )
        
        if not config:
            logger.warning(f"[alert.trigger] No alert configuration found for tenant {tenant_id}")
            # Continue without notifications
        else:
            # Send notifications in background
            logger.info(f"[alert.trigger] Configuration found (config_id={config.config_id}), scheduling notification task")
            background_tasks.add_task(
                send_alert_notifications,
                alert_id=alert.alert_id,
                config_id=config.config_id
            )
            logger.info(f"[alert.trigger] Notification task scheduled for alert {alert.alert_id}")
        
        return ResponseWrapper.success(
            message="Alert triggered successfully. Help is on the way.",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.trigger] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to trigger alert: {str(e)}",
                error_code="TRIGGER_FAILED"
            )
        )


@router.get("/active", response_model=dict)
def get_active_alerts(
    team_id: Optional[int] = Query(None, description="Filter by team (branch managers only)"),
    employee_id: Optional[int] = Query(None, description="Filter by employee (branch managers only)"),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get active alerts
    
    - Regular employees: see only their own active alerts
    - Branch managers (with alert.read permission): see all active alerts in tenant, can filter by team_id or employee_id
    """
    try:
        current_employee_id = current_employee.get("employee_id") or current_employee.get("user_id")
        tenant_id = current_employee.get("tenant_id")
        user_permissions = current_employee.get("permissions", [])
        
        # Convert current_employee_id to int
        current_employee_id = int(current_employee_id) if current_employee_id else None
        
        # Check if user has permission to view all alerts (branch manager)
        has_read_permission = check_user_permission(user_permissions, "alert", "read")
        
        if has_read_permission:
            # Branch manager: can see all alerts or filter by team_id/employee_id
            target_team_id = team_id if team_id else None
            target_employee_id = employee_id if employee_id else None
            logger.info(f"[alert.active] Branch manager viewing active alerts - tenant={tenant_id}, filter_team_id={target_team_id}, filter_employee_id={target_employee_id}")
        else:
            # Regular employee: can only see their own alerts
            if (employee_id and employee_id != current_employee_id) or team_id:
                raise HTTPException(
                    status_code=403,
                    detail=ResponseWrapper.error(
                        message="You can only view your own alerts",
                        error_code="ACCESS_FORBIDDEN"
                    )
                )
            target_team_id = None
            target_employee_id = current_employee_id
            logger.info(f"[alert.active] Employee viewing own active alerts - employee_id={target_employee_id}")
        
        # Get active alerts (TRIGGERED or ACKNOWLEDGED)
        alerts = alert_crud.get_active_alerts(
            db=db,
            tenant_id=tenant_id,
            team_id=target_team_id,
            employee_id=target_employee_id
        )
        
        return ResponseWrapper.success(
            message=f"Found {len(alerts)} active alert(s)",
            data=[AlertResponse.from_orm(alert).dict() for alert in alerts]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.active] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve active alerts: {str(e)}",
                error_code="RETRIEVE_FAILED"
            )
        )


@router.get("/team-alerts", response_model=dict)
def get_team_alerts(
    team_id: Optional[int] = Query(None, description="Filter by specific team ID"),
    employee_id: Optional[int] = Query(None, description="Filter by specific employee ID"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[AlertStatusEnum] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get all team/tenant alerts (for branch managers and responders)
    
    - Branch managers (employees with alert.read permission) can see all alerts in their tenant
    - Supports filtering by team_id, employee_id, status, and date range
    - Returns paginated results
    """
    try:
        tenant_id = current_employee.get("tenant_id")
        user_permissions = current_employee.get("permissions", [])
        
        # Check if user has permission to view all alerts (branch manager/responder)
        has_read_permission = check_user_permission(user_permissions, "alert", "read")
        
        if not has_read_permission:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view team alerts",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.team-alerts] User viewing team alerts - tenant={tenant_id}, filter_team_id={team_id}, filter_employee_id={employee_id}")
        
        # Convert dates to datetime for filtering
        from_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        to_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None
        
        # Get alerts (all if no filters, or filtered by team/employee)
        alerts = alert_crud.get_alerts(
            db=db,
            tenant_id=tenant_id,
            team_id=team_id,  # None = all teams, int = specific team
            employee_id=employee_id,  # None = all employees, int = specific employee
            status=status,
            from_date=from_datetime,
            to_date=to_datetime,
            limit=limit,
            offset=offset
        )
        
        # Calculate page number from offset
        page = (offset // limit) + 1 if limit > 0 else 1
        
        response_data = AlertListResponse(
            alerts=[AlertResponse.from_orm(alert).dict() for alert in alerts],
            total=len(alerts),
            page=page,
            page_size=limit
        )
        
        return ResponseWrapper.success(
            message=f"Retrieved {len(alerts)} team alert(s)",
            data=response_data.dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.team-alerts] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve team alerts: {str(e)}",
                error_code="RETRIEVE_FAILED"
            )
        )


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
    Get employee's own alert history with filters
    """
    try:
        employee_id = current_employee.get("employee_id") or current_employee.get("user_id")
        tenant_id = current_employee.get("tenant_id")
        
        # Convert employee_id to int for database comparison
        employee_id = int(employee_id) if employee_id else None
        
        # Convert dates to datetime for filtering
        from_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        to_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None
        
        alerts = alert_crud.get_alerts(
            db=db,
            tenant_id=tenant_id,
            employee_id=employee_id,
            status=status,
            from_date=from_datetime,
            to_date=to_datetime,
            limit=limit,
            offset=offset
        )
        
        # Check if more results exist
        has_more = len(alerts) == limit
        
        # Calculate page number from offset
        page = (offset // limit) + 1 if limit > 0 else 1
        
        response_data = AlertListResponse(
            alerts=[AlertResponse.from_orm(alert).dict() for alert in alerts],
            total=len(alerts),
            page=page,
            page_size=limit
        )
        
        return ResponseWrapper.success(
            message=f"Retrieved {len(alerts)} alert(s)",
            data=response_data.dict()
        )
        
    except Exception as e:
        logger.error(f"[alert.my-alerts] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve alert history: {str(e)}",
                error_code="RETRIEVE_FAILED"
            )
        )


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
        tenant_id = current_employee.get("tenant_id")
        employee_id = current_employee.get("employee_id") or current_employee.get("user_id")
        
        # Convert employee_id to int for database comparison
        employee_id = int(employee_id) if employee_id else None
        
        logger.info(f"[alert.details] Fetching alert {alert_id} for tenant={tenant_id}, employee={employee_id}")
        logger.info(f"[alert.details] User role: {current_employee.get('role')}, user_type: {current_employee.get('user_type')}")
        
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        logger.info(f"[alert.details] Alert found: {alert is not None}")
        
        if not alert:
            logger.error(f"[alert.details] Alert {alert_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert.details] Alert data - alert.employee_id={alert.employee_id}, alert.tenant_id={alert.tenant_id}, alert.status={alert.status}")
        
        # Check access: either own alert or has alert.read permission
        user_permissions = current_employee.get("permissions", [])
        is_responder = check_user_permission(user_permissions, "alert", "read")
        logger.info(f"[alert.details] Access check - is_responder={is_responder}, alert.employee_id={alert.employee_id}, current employee_id={employee_id}")
        
        if alert.employee_id != employee_id and not is_responder:
            logger.error(f"[alert.details] Access denied - alert belongs to employee {alert.employee_id}, requested by {employee_id}, not a responder")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Access denied to this alert",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.details] Access granted - returning alert {alert_id}")
        
        return ResponseWrapper.success(
            message="Alert retrieved",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.details] Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve alert details: {str(e)}",
                error_code="RETRIEVE_FAILED"
            )
        )


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
        tenant_id = current_employee.get("tenant_id")
        responder_id = current_employee.get("employee_id") or current_employee.get("user_id")
        responder_name = current_employee.get("name", "Unknown")
        
        logger.info(f"[alert.acknowledge] Starting acknowledgment - alert_id={alert_id}, responder={responder_name}, tenant={tenant_id}")
        logger.info(f"[alert.acknowledge] Request data - notes={request.notes}, acknowledged_by={request.acknowledged_by}")
        
        # Convert responder_id to int
        responder_id = int(responder_id) if responder_id else None
        logger.info(f"[alert.acknowledge] Responder ID: {responder_id} (type={type(responder_id).__name__})")
        
        # Check responder permissions
        user_permissions = current_employee.get("permissions", [])
        logger.info(f"[alert.acknowledge] User permissions: {user_permissions}")
        is_responder = check_user_permission(user_permissions, "alert", "respond")
        logger.info(f"[alert.acknowledge] Permission check - is_responder={is_responder}")
        
        if not is_responder:
            logger.error(f"[alert.acknowledge] Permission denied - user does not have alert.respond or admin permission")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Only responders can acknowledge alerts",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.acknowledge] Fetching alert {alert_id} for acknowledgment")
        
        # Get the alert first
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        logger.info(f"[alert.acknowledge] Alert found: {alert is not None}")
        
        if not alert:
            logger.error(f"[alert.acknowledge] Alert {alert_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert.acknowledge] Calling CRUD to acknowledge alert {alert_id}")
        
        # Acknowledge alert
        alert = alert_crud.acknowledge_alert(
            db=db,
            alert=alert,
            responder_id=responder_id,
            responder_name=responder_name,
            notes=request.notes
        )
        
        # Commit changes to database
        db.commit()
        db.refresh(alert)
        logger.info(f"[alert.acknowledge] Changes committed to database")
        
        logger.info(f"[alert.acknowledge] Alert {alert_id} acknowledged by {responder_name}, response_time={alert.response_time_seconds}s")
        
        # Get configuration for notifications
        logger.info(f"[alert.acknowledge] Fetching alert configuration for notifications")
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            alert_type=AlertTypeEnum(alert.alert_type) if isinstance(alert.alert_type, str) else alert.alert_type,
            team_id=None  # Get tenant-level config
        )
        
        logger.info(f"[alert.acknowledge] Config found: {config is not None}, notify_on_status_change={config.notify_on_status_change if config else 'N/A'}")
        
        if config and config.notify_on_status_change:
            logger.info(f"[alert.acknowledge] Scheduling status notification background task")
            # Send status update notifications
            background_tasks.add_task(
                send_status_notification,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                new_status=AlertStatusEnum.ACKNOWLEDGED.value
            )
        
        logger.info(f"[alert.acknowledge] Successfully acknowledged alert {alert_id}")
        
        return ResponseWrapper.success(
            message=f"Alert acknowledged. Response time: {alert.response_time_seconds}s",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.acknowledge] Error: {str(e)}", exc_info=True)
        logger.error(f"[alert.acknowledge] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to acknowledge alert: {str(e)}",
                error_code="ACKNOWLEDGE_FAILED"
            )
        )


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
        tenant_id = current_employee.get("tenant_id")
        closed_by = current_employee.get("employee_id") or current_employee.get("user_id")
        closed_by_name = current_employee.get("name", "Unknown")
        
        logger.info(f"[alert.close] Starting close - alert_id={alert_id}, closed_by={closed_by_name}, tenant={tenant_id}")
        logger.info(f"[alert.close] Request data - is_false_alarm={request.is_false_alarm}, resolution_notes length={len(request.resolution_notes) if request.resolution_notes else 0}")
        
        # Convert closed_by to int
        closed_by = int(closed_by) if closed_by else None
        logger.info(f"[alert.close] Closer ID: {closed_by} (type={type(closed_by).__name__})")
        
        # Check permissions
        user_permissions = current_employee.get("permissions", [])
        logger.info(f"[alert.close] User permissions: {user_permissions}")
        is_authorized = check_user_permission(user_permissions, "alert", "close")
        logger.info(f"[alert.close] Permission check - is_authorized={is_authorized}")
        
        if not is_authorized:
            logger.error(f"[alert.close] Permission denied - user does not have required permission")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Only authorized personnel can close alerts",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.close] Fetching alert {alert_id} for closing")
        
        # Get the alert first
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        logger.info(f"[alert.close] Alert found: {alert is not None}")
        
        if not alert:
            logger.error(f"[alert.close] Alert {alert_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert.close] Alert current status: {alert.status}")
        logger.info(f"[alert.close] Calling CRUD to close alert {alert_id}")
        
        # Close alert
        alert = alert_crud.close_alert(
            db=db,
            alert=alert,
            closed_by=closed_by,
            closed_by_name=closed_by_name,
            resolution_notes=request.resolution_notes,
            is_false_alarm=request.is_false_alarm
        )
        
        # Commit changes to database
        db.commit()
        db.refresh(alert)
        logger.info(f"[alert.close] Changes committed to database")
        
        logger.info(f"[alert.close] Alert {alert_id} closed by {closed_by_name}, resolution_time={alert.resolution_time_seconds}s")
        
        # Get configuration for notifications
        logger.info(f"[alert.close] Fetching alert configuration for notifications")
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            alert_type=AlertTypeEnum(alert.alert_type) if isinstance(alert.alert_type, str) else alert.alert_type,
            team_id=None
        )
        
        logger.info(f"[alert.close] Config found: {config is not None}, notify_on_status_change={config.notify_on_status_change if config else 'N/A'}")
        
        if config and config.notify_on_status_change:
            logger.info(f"[alert.close] Scheduling status notification background task")
            background_tasks.add_task(
                send_status_notification,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                new_status=alert.status.value
            )
        
        logger.info(f"[alert.close] Successfully closed alert {alert_id}")
        
        return ResponseWrapper.success(
            message=f"Alert closed. Total resolution time: {alert.resolution_time_seconds}s",
            data=AlertResponse.from_orm(alert).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.close] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to close alert: {str(e)}",
                error_code="CLOSE_FAILED"
            )
        )


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
        tenant_id = current_employee.get("tenant_id")
        escalated_by = current_employee.get("employee_id") or current_employee.get("user_id")
        escalated_by_name = current_employee.get("name", "Unknown")
        
        logger.info(f"[alert.escalate] Starting escalation - alert_id={alert_id}, escalated_by={escalated_by_name}, tenant={tenant_id}")
        logger.info(f"[alert.escalate] Request data - level={request.escalation_level}, escalated_to={request.escalated_to}, reason={request.reason[:50] if request.reason else 'None'}...")
        
        # Convert escalated_by to int
        escalated_by = int(escalated_by) if escalated_by else None
        logger.info(f"[alert.escalate] Escalator ID: {escalated_by} (type={type(escalated_by).__name__})")
        
        # Check permissions
        user_permissions = current_employee.get("permissions", [])
        logger.info(f"[alert.escalate] User permissions: {user_permissions}")
        is_authorized = check_user_permission(user_permissions, "alert", "escalate")
        logger.info(f"[alert.escalate] Permission check - is_authorized={is_authorized}")
        
        if not is_authorized:
            logger.error(f"[alert.escalate] Permission denied - user does not have required permission")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Only authorized personnel can escalate alerts",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.escalate] Fetching alert {alert_id} for escalation")
        
        # Get alert
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        logger.info(f"[alert.escalate] Alert found: {alert is not None}")
        
        if not alert:
            logger.error(f"[alert.escalate] Alert {alert_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert.escalate] Alert current status: {alert.status}")
        
        if alert.status in [AlertStatusEnum.CLOSED, AlertStatusEnum.FALSE_ALARM]:
            logger.error(f"[alert.escalate] Cannot escalate closed alert - status={alert.status}")
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="Cannot escalate closed alert",
                    error_code="INVALID_ALERT_STATUS"
                )
            )
        
        logger.info(f"[alert.escalate] Calling CRUD to create escalation - level={request.escalation_level}")
        
        # Create escalation - pass request object to CRUD
        escalation = alert_crud.create_escalation(
            db=db,
            alert=alert,
            request=request,
            is_auto=False
        )
        
        # Commit changes to database
        db.commit()
        db.refresh(escalation)
        db.refresh(alert)
        logger.info(f"[alert.escalate] Changes committed to database")
        
        logger.info(f"[alert.escalate] Alert {alert_id} manually escalated to level {request.escalation_level}")
        
        # Get configuration for notifications
        logger.info(f"[alert.escalate] Fetching alert configuration for notifications")
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            alert_type=AlertTypeEnum(alert.alert_type) if isinstance(alert.alert_type, str) else alert.alert_type,
            team_id=None
        )
        
        logger.info(f"[alert.escalate] Config found: {config is not None}")
        
        if config:
            logger.info(f"[alert.escalate] Scheduling escalation notification background task")
            background_tasks.add_task(
                send_escalation_notification,
                alert_id=alert.alert_id,
                config_id=config.config_id,
                escalation_level=request.escalation_level
            )
        
        logger.info(f"[alert.escalate] Successfully escalated alert {alert_id}")
        
        # Import schema at runtime to avoid circular import
        from app.schemas.alert import AlertEscalationResponse
        
        return ResponseWrapper.success(
            message=f"Alert escalated to level {request.escalation_level}",
            data={"escalation": AlertEscalationResponse.from_orm(escalation).dict()}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.escalate] Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to escalate alert: {str(e)}",
                error_code="ESCALATE_FAILED"
            )
        )


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
        tenant_id = current_employee.get("tenant_id")
        employee_id = current_employee.get("employee_id") or current_employee.get("user_id")
        
        logger.info(f"[alert.timeline] Starting timeline retrieval - alert_id={alert_id}, tenant={tenant_id}")
        
        # Convert employee_id to int
        employee_id = int(employee_id) if employee_id else None
        logger.info(f"[alert.timeline] Employee ID: {employee_id}")
        
        # Get timeline data from CRUD
        timeline_data = alert_crud.get_alert_timeline(db, alert_id, tenant_id)
        
        logger.info(f"[alert.timeline] Timeline data found: {timeline_data is not None}")
        
        if not timeline_data:
            logger.error(f"[alert.timeline] Alert {alert_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert.timeline] Timeline has {timeline_data.get('total_events', 0)} events")
        
        # Get the full alert object
        alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        
        logger.info(f"[alert.timeline] Alert object retrieved: {alert is not None}")
        
        if not alert:
            logger.error(f"[alert.timeline] Alert {alert_id} not found in database")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )
        
        # Check access permissions
        user_permissions = current_employee.get("permissions", [])
        is_responder = check_user_permission(user_permissions, "alert", "read")
        logger.info(f"[alert.timeline] Access check - is_responder={is_responder}, alert.employee_id={alert.employee_id}, current employee_id={employee_id}")
        
        if alert.employee_id != employee_id and not is_responder:
            logger.error(f"[alert.timeline] Access denied - alert belongs to employee {alert.employee_id}, requested by {employee_id}")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Access denied to this alert",
                    error_code="ACCESS_FORBIDDEN"
                )
            )
        
        logger.info(f"[alert.timeline] Building response with AlertResponse and timeline events")
        
        # Build proper response matching schema
        response_data = {
            "alert": AlertResponse.from_orm(alert).dict(),
            "timeline": timeline_data.get("events", [])
        }
        
        logger.info(f"[alert.timeline] Successfully retrieved timeline for alert {alert_id}")
        
        return ResponseWrapper.success(
            message="Timeline retrieved",
            data=response_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.timeline] Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve alert timeline: {str(e)}",
                error_code="RETRIEVE_FAILED"
            )
        )


# Background task functions
async def send_alert_notifications(alert_id: int, config_id: int):
    """Send notifications when alert is triggered"""
    from app.database.session import SessionLocal
    
    db_session = SessionLocal()
    try:
        logger.info(f"[background.notify] Starting notification for alert_id={alert_id}, config_id={config_id}")
        
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        logger.info(f"[background.notify] Alert found: {alert is not None}, Config found: {config is not None}")
        
        if alert and config:
            logger.info(f"[background.notify] Creating NotificationService and sending notification")
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_triggered(alert, config)
            logger.info(f"[background.notify] Notification sent successfully for alert {alert_id}")
        else:
            logger.warning(f"[background.notify] Cannot send notification - alert={alert is not None}, config={config is not None}")
    except Exception as e:
        logger.error(f"[background.notify] Error sending notifications: {str(e)}", exc_info=True)
    finally:
        db_session.close()


async def send_status_notification(
    alert_id: int,
    config_id: int,
    new_status: str
):
    """Send notification on status change"""
    from app.database.session import SessionLocal
    
    db_session = SessionLocal()
    try:
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        if alert and config:
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_status_change(alert, config, new_status)
    except Exception as e:
        logger.error(f"[background.status_notify] Error: {str(e)}")
    finally:
        db_session.close()


async def send_escalation_notification(
    alert_id: int,
    config_id: int,
    escalation_level: int
):
    """Send notification on escalation"""
    from app.database.session import SessionLocal
    
    db_session = SessionLocal()
    try:
        alert = db_session.query(alert_crud.Alert).filter_by(alert_id=alert_id).first()
        config = db_session.query(alert_crud.AlertConfiguration).filter_by(config_id=config_id).first()
        
        if alert and config:
            notification_service = NotificationService(db_session)
            await notification_service.notify_alert_escalated(alert, config, escalation_level)
    except Exception as e:
        logger.error(f"[background.escalate_notify] Error: {str(e)}")
    finally:
        db_session.close()



@router.delete("/{alert_id}", response_model=dict)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Delete an alert

    - Employees can only delete alerts belonging to their tenant
    - Admins can delete any alert
    """
    try:
        user_type = current_employee.get("user_type")
        tenant_id = current_employee.get("tenant_id") if user_type != "admin" else None

        logger.info(f"[alert.delete] User: {current_employee.get('user_id')}, user_type: {user_type}, tenant_filter: {tenant_id}")

        # Fetch alert (respect tenant filter for non-admins)
        if tenant_id:
            alert = alert_crud.get_alert_by_id(db, alert_id, tenant_id)
        else:
            from app.models.alert import Alert
            alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()

        if not alert:
            logger.warning(f"[alert.delete] Alert {alert_id} not found for tenant filter: {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Alert not found",
                    error_code="ALERT_NOT_FOUND"
                )
            )

        # Additional access control: if user is employee, ensure alert belongs to their tenant
        if user_type != "admin" and alert.tenant_id != tenant_id:
            logger.error(f"[alert.delete] Access denied - alert tenant {alert.tenant_id} != user tenant {tenant_id}")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Access denied to delete this alert",
                    error_code="ACCESS_FORBIDDEN"
                )
            )

        db.delete(alert)
        db.commit()

        logger.info(f"[alert.delete] Alert {alert_id} deleted by user {current_employee.get('user_id')}")

        return ResponseWrapper.success(
            message="Alert deleted successfully",
            data={"deleted_alert_id": alert_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert.delete] Error: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Failed to delete alert: {str(e)}",
                error_code="DELETE_FAILED"
            )
        )

