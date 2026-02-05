"""
Alert Configuration Router
Admin endpoints for managing alert routing and escalation rules
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database.session import get_db
from app.schemas.alert import (
    AlertConfigurationCreate,
    AlertConfigurationUpdate,
    AlertConfigurationResponse
)
from app.models.alert import AlertConfiguration
from app.crud import alert as alert_crud
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/alert-config", tags=["alert-configuration"])


async def get_current_employee(user_data=Depends(PermissionChecker(["tenant_config.read", "tenant_config.write"]))):
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


@router.post("", response_model=dict)
def create_alert_configuration(
    request: AlertConfigurationCreate,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Create alert configuration
    
    Admin only endpoint to configure alert routing and escalation rules
    for tenant or specific team
    """
    try:
        # Resolve tenant_id based on user type
        user_type = current_employee.get("user_type")
        
        if user_type == "employee":
            # Employees use tenant_id from token
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
        elif user_type == "admin":
            # Admins must provide tenant_id in request body
            tenant_id = request.tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required in request body for admin users",
                        error_code="TENANT_ID_REQUIRED"
                    )
                )
        else:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Invalid user type",
                    error_code="INVALID_USER_TYPE"
                )
            )
        
        # Validate: team must belong to tenant if specified
        if request.team_id:
            from app.utils import cache_manager
            team = cache_manager.get_team_with_cache(db, tenant_id, request.team_id)
            
            if not team:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message=f"Team {request.team_id} does not belong to tenant {tenant_id}",
                        error_code="INVALID_TEAM_TENANT"
                    )
                )
            
            logger.info(f"[alert_config.create] Validated team {request.team_id} belongs to tenant {tenant_id}")
        
        # Check for existing configuration
        existing = alert_crud.get_alert_configuration(
            db=db,
            tenant_id=tenant_id,
            team_id=request.team_id
        )
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message=f"Configuration already exists for this {'team' if request.team_id else 'tenant'}",
                    error_code="CONFIG_ALREADY_EXISTS"
                )
            )
        
        # Create configuration
        config_data = request.dict(exclude_unset=True, exclude={'tenant_id'})
        config = alert_crud.create_alert_configuration(
            db=db,
            tenant_id=tenant_id,
            config_data=config_data,
            created_by=current_employee.get("user_id")
        )
        
        db.commit()
        db.refresh(config)
        
        logger.info(f"[alert_config.create] Configuration {config.config_id} created for tenant {tenant_id}")
        
        return ResponseWrapper.success(
            message="Alert configuration created successfully",
            data=AlertConfigurationResponse.from_orm(config).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert_config.create] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to create alert configuration",
                error_code="CREATE_FAILED",
                details={"error": str(e)}
            )
        )


@router.get("", response_model=dict)
def get_alert_configurations(
    team_id: Optional[int] = None,
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id", description="Tenant ID (required for admin users)"),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get alert configurations
    
    Returns configurations for tenant and optionally filtered by team
    
    For admins: Must provide tenant_id query parameter (or omit to see all)
    For employees: Uses tenant_id from token
    """
    try:
        user_type = current_employee.get("user_type")
        
        logger.info(f"[alert_config.list] User: {current_employee.get('user_id')}, User Type: {user_type}, team_id param: {team_id}")
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
            logger.info(f"[alert_config.list] Employee tenant_id: {tenant_id}")
            
            # Validate team_id if provided - must belong to employee's tenant
            if team_id:
                from app.utils import cache_manager
                team = cache_manager.get_team_with_cache(db, tenant_id, team_id)
                
                if not team:
                    raise HTTPException(
                        status_code=403,
                        detail=ResponseWrapper.error(
                            message=f"Team {team_id} does not belong to your tenant or does not exist",
                            error_code="INVALID_TEAM_ACCESS"
                        )
                    )
                logger.info(f"[alert_config.list] Validated team {team_id} belongs to tenant {tenant_id}")
            
            # Non-admin employees can only view their team's config
            if current_employee.get("role") not in ["ADMIN", "TRANSPORT_MANAGER"]:
                team_id = current_employee.get("team_id")
                logger.info(f"[alert_config.list] Non-admin employee, filtering by team_id: {team_id}")
        elif user_type == "admin":
            # Admins can optionally provide tenant_id to filter, or omit to see all
            tenant_id = tenant_id_param
            
            # If admin provides team_id without tenant_id, fetch tenant_id for that team
            if team_id and not tenant_id:
                logger.info(f"[alert_config.list] Admin provided team_id={team_id} without tenant_id, fetching team's tenant")
                from app.utils import cache_manager
                # For admin without tenant_id, we need to query DB to get tenant_id from team
                from app.models.team import Team
                team = db.query(Team).filter(Team.team_id == team_id).first()
                if team:
                    tenant_id = team.tenant_id
                    logger.info(f"[alert_config.list] Found team {team_id} belongs to tenant_id: {tenant_id}")
                else:
                    logger.warning(f"[alert_config.list] Team {team_id} not found")
                    raise HTTPException(
                        status_code=404,
                        detail=ResponseWrapper.error(
                            message=f"Team {team_id} not found",
                            error_code="TEAM_NOT_FOUND"
                        )
                    )
            
            logger.info(f"[alert_config.list] Admin user, tenant_id filter: {tenant_id}, team_id filter: {team_id}")
        else:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Invalid user type",
                    error_code="INVALID_USER_TYPE"
                )
            )
        
        logger.info(f"[alert_config.list] Fetching configs - tenant_id: {tenant_id}, team_id: {team_id}")
        configs = alert_crud.get_alert_configurations(
            db=db,
            tenant_id=tenant_id,
            team_id=team_id
        )
        
        logger.info(f"[alert_config.list] Found {len(configs)} configuration(s)")
        
        return ResponseWrapper.success(
            message=f"Retrieved {len(configs)} configuration(s)",
            data=[AlertConfigurationResponse.from_orm(config).dict() for config in configs]
        )
        
    except HTTPException:
        # Let explicit HTTPExceptions (403/404/400 etc.) propagate unchanged
        raise
    except Exception as e:
        logger.error(f"[alert_config.list] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to retrieve alert configurations",
                error_code="RETRIEVE_FAILED",
                details={"error": str(e)}
            )
        )


@router.get("/{config_id}", response_model=dict)
def get_alert_configuration(
    config_id: int,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get specific alert configuration by ID
    
    Employees: Can only view configs from their tenant
    Admins: Can view any config
    """
    try:
        user_type = current_employee.get("user_type")
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
            # Employee: Must match their tenant
            config = alert_crud.get_alert_configuration_by_id(db, config_id, tenant_id)
        elif user_type == "admin":
            # Admin: Can access any config
            config = db.query(AlertConfiguration).filter(
                AlertConfiguration.config_id == config_id
            ).first()
        else:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Invalid user type",
                    error_code="INVALID_USER_TYPE"
                )
            )
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Configuration not found",
                    error_code="CONFIG_NOT_FOUND"
                )
            )
        
        return ResponseWrapper.success(
            message="Configuration retrieved",
            data=AlertConfigurationResponse.from_orm(config).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert_config.get] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to retrieve alert configuration",
                error_code="RETRIEVE_FAILED",
                details={"error": str(e)}
            )
        )


@router.put("/{config_id}", response_model=dict)
def update_alert_configuration(
    config_id: int,
    request: AlertConfigurationUpdate,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Update alert configuration
    
    Admin only endpoint to modify routing and escalation rules
    """
    try:
        logger.info(f"[alert_config.update] Starting update for config_id={config_id}")
        logger.info(f"[alert_config.update] User: {current_employee.get('user_id')}, Role: {current_employee.get('role')}, User Type: {current_employee.get('user_type')}")
        
        # Allow employees and admins to update (consistent with create endpoint)
        user_type = current_employee.get("user_type")
        if user_type not in ["employee", "admin"]:
            logger.warning(f"[alert_config.update] Access denied for user {current_employee.get('user_id')} with user_type {user_type}")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Employee or admin access required",
                    error_code="ADMIN_ACCESS_REQUIRED"
                )
            )
        
        logger.info(f"[alert_config.update] Access check passed for user_type: {user_type}")
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
            logger.info(f"[alert_config.update] Employee tenant_id: {tenant_id}")
        else:  # admin
            # Admins can update any tenant's config - get tenant_id from the config itself
            tenant_id = None
            logger.info(f"[alert_config.update] Admin user - will fetch config without tenant filter")
        
        # Get existing configuration
        logger.info(f"[alert_config.update] Fetching config_id={config_id}")
        
        if tenant_id:
            # Employee: Must match their tenant
            config = alert_crud.get_alert_configuration_by_id(db, config_id, tenant_id)
        else:
            # Admin: Can access any tenant's config
            config = db.query(AlertConfiguration).filter(
                AlertConfiguration.config_id == config_id
            ).first()
        
        if not config:
            logger.warning(f"[alert_config.update] Configuration {config_id} not found")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Configuration not found",
                    error_code="CONFIG_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert_config.update] Found config: {config.config_name} (ID: {config.config_id})")
        
        # Validate team_id if being updated
        team_id_to_validate = getattr(request, 'team_id', None)
        if team_id_to_validate is not None:
            from app.utils import cache_manager
            team = cache_manager.get_team_with_cache(db, config.tenant_id, team_id_to_validate)
            
            if not team:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message=f"Team {team_id_to_validate} does not belong to tenant {config.tenant_id}",
                        error_code="INVALID_TEAM_TENANT"
                    )
                )
            
            logger.info(f"[alert_config.update] Validated team {team_id_to_validate} belongs to tenant {config.tenant_id}")
        
        # Update fields
        update_data = request.dict(exclude_unset=True)
        logger.info(f"[alert_config.update] Update data fields: {list(update_data.keys())}")
        logger.info(f"[alert_config.update] Update data: {update_data}")
        
        for field, value in update_data.items():
            if value is not None:
                old_value = getattr(config, field, None)
                logger.info(f"[alert_config.update] Updating field '{field}': {old_value} -> {value}")
                setattr(config, field, value)
        
        logger.info(f"[alert_config.update] All fields updated, committing to database")
        db.commit()
        
        logger.info(f"[alert_config.update] Commit successful, refreshing config")
        db.refresh(config)
        
        logger.info(f"[alert_config.update] Configuration {config_id} updated successfully")
        
        return ResponseWrapper.success(
            message="Configuration updated successfully",
            data=AlertConfigurationResponse.from_orm(config).dict()
        )
        
    except HTTPException:
        logger.error(f"[alert_config.update] HTTP exception raised for config_id={config_id}")
        raise
    except Exception as e:
        logger.error(f"[alert_config.update] Unexpected error for config_id={config_id}: {str(e)}")
        logger.exception(f"[alert_config.update] Full traceback:")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to update alert configuration",
                error_code="UPDATE_FAILED",
                details={"error": str(e)}
            )
        )


@router.delete("/{config_id}", response_model=dict)
def delete_alert_configuration(
    config_id: int,
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Delete alert configuration
    
    Admin only endpoint
    """
    try:
        # Check admin or employee access
        user_type = current_employee.get("user_type")
        if user_type not in ["employee", "admin"]:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Employee or admin access required",
                    error_code="ADMIN_ACCESS_REQUIRED"
                )
            )
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
        else:  # admin
            tenant_id = None  # Admins can delete any tenant's config
        
        # Get configuration
        if tenant_id:
            config = alert_crud.get_alert_configuration_by_id(db, config_id, tenant_id)
        else:
            config = db.query(AlertConfiguration).filter(
                AlertConfiguration.config_id == config_id
            ).first()
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Configuration not found",
                    error_code="CONFIG_NOT_FOUND"
                )
            )
        
        # Delete
        db.delete(config)
        db.commit()
        
        logger.info(f"[alert_config.delete] Configuration {config_id} deleted")
        
        return ResponseWrapper.success(
            message="Configuration deleted successfully",
            data={"deleted_config_id": config_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert_config.delete] Error: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to delete alert configuration",
                error_code="DELETE_FAILED",
                details={"error": str(e)}
            )
        )


@router.post("/{config_id}/test-notification", response_model=dict)
async def test_notification_configuration(
    config_id: int,
    dry_run: bool = Query(True, description="If True, only validates config without sending. If False, sends real notifications."),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Test notification configuration
    
    Validates configuration and optionally sends real test notifications
    
    Parameters:
    - dry_run=true (default): Only shows what would be sent
    - dry_run=false: Actually sends test notifications to configured recipients
    """
    try:
        logger.info(f"[alert_config.test] Starting test for config_id={config_id}, dry_run={dry_run}")
        
        # Check admin or employee access
        user_type = current_employee.get("user_type")
        logger.info(f"[alert_config.test] User: {current_employee.get('user_id')}, User Type: {user_type}")
        
        if user_type not in ["employee", "admin"]:
            logger.warning(f"[alert_config.test] Access denied for user_type: {user_type}")
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Employee or admin access required",
                    error_code="ADMIN_ACCESS_REQUIRED"
                )
            )
        
        logger.info(f"[alert_config.test] Access check passed")
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            if not tenant_id:
                logger.error(f"[alert_config.test] Employee missing tenant_id")
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
            logger.info(f"[alert_config.test] Employee tenant_id: {tenant_id}")
        else:  # admin
            tenant_id = None  # Admins can test any tenant's config
            logger.info(f"[alert_config.test] Admin user - can test any tenant's config")
        
        # Get configuration
        logger.info(f"[alert_config.test] Fetching config_id={config_id}")
        if tenant_id:
            config = alert_crud.get_alert_configuration_by_id(db, config_id, tenant_id)
        else:
            config = db.query(AlertConfiguration).filter(
                AlertConfiguration.config_id == config_id
            ).first()
        
        if not config:
            logger.warning(f"[alert_config.test] Configuration {config_id} not found")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Configuration not found",
                    error_code="CONFIG_NOT_FOUND"
                )
            )
        
        logger.info(f"[alert_config.test] Found config: {config.config_name} (tenant: {config.tenant_id})")
        logger.info(f"[alert_config.test] Config channels: {config.notification_channels}")
        logger.info(f"[alert_config.test] Primary recipients: {len(config.primary_recipients) if config.primary_recipients else 0}")
        logger.info(f"[alert_config.test] Escalation enabled: {config.enable_escalation}")
        logger.info(f"[alert_config.test] Escalation recipients: {len(config.escalation_recipients) if config.escalation_recipients else 0}")
        logger.info(f"[alert_config.test] Emergency contacts: {len(config.emergency_contacts) if config.emergency_contacts else 0}")
        
        # Send test notifications
        logger.info(f"[alert_config.test] Testing notification config_id={config_id} for tenant_id={config.tenant_id}, dry_run={dry_run}")
        
        # If dry_run, just validate and return mock data
        if dry_run:
            logger.info(f"[alert_config.test] DRY RUN MODE - No actual notifications will be sent")
            
            # Mock notification sending - extract recipients from config
            test_notifications = []
            
            # Add primary recipients
            if config.primary_recipients:
                logger.info(f"[alert_config.test] Processing {len(config.primary_recipients)} primary recipients")
                for idx, recipient in enumerate(config.primary_recipients):
                    logger.info(f"[alert_config.test]   Primary #{idx+1}: {recipient.get('name')} - Channels: {recipient.get('channels', [])}")
                    test_notifications.append({
                        "recipient_name": recipient.get("name"),
                        "recipient_email": recipient.get("email"),
                        "recipient_phone": recipient.get("phone"),
                        "recipient_role": recipient.get("role"),
                        "channels": recipient.get("channels", [])
                    })
            else:
                logger.warning(f"[alert_config.test] No primary recipients configured!")
            
            # Add escalation recipients if enabled
            if config.enable_escalation and config.escalation_recipients:
                logger.info(f"[alert_config.test] Processing {len(config.escalation_recipients)} escalation recipients")
                for idx, recipient in enumerate(config.escalation_recipients):
                    logger.info(f"[alert_config.test]   Escalation #{idx+1}: {recipient.get('name')} - Channels: {recipient.get('channels', [])}")
                    test_notifications.append({
                        "recipient_name": recipient.get("name"),
                        "recipient_email": recipient.get("email"),
                        "recipient_phone": recipient.get("phone"),
                        "recipient_role": recipient.get("role"),
                        "channels": recipient.get("channels", [])
                    })
            else:
                logger.info(f"[alert_config.test] No escalation recipients (enabled={config.enable_escalation})")
            
            # Add emergency contacts
            if config.emergency_contacts:
                logger.info(f"[alert_config.test] Processing {len(config.emergency_contacts)} emergency contacts")
                for idx, contact in enumerate(config.emergency_contacts):
                    logger.info(f"[alert_config.test]   Emergency #{idx+1}: {contact.get('name')} ({contact.get('service_type')}) - {contact.get('phone')}")
                    test_notifications.append({
                        "recipient_name": contact.get("name"),
                        "recipient_phone": contact.get("phone"),
                        "service_type": contact.get("service_type"),
                        "channels": ["VOICE"]  # Emergency contacts typically use voice
                    })
            else:
                logger.info(f"[alert_config.test] No emergency contacts configured")
            
            logger.info(f"[alert_config.test] DRY RUN complete - Would notify {len(test_notifications)} recipient(s)")
            
            return ResponseWrapper.success(
                message=f"Test notification configuration validated successfully for {len(test_notifications)} recipient(s)",
                data={
                    "config_id": config.config_id,
                    "config_name": config.config_name,
                    "tenant_id": config.tenant_id,
                    "notification_channels": config.notification_channels,
                    "recipients": test_notifications,
                    "total_recipients": len(test_notifications),
                    "note": "This is a dry-run test. No actual notifications were sent. Use dry_run=false to send real test notifications."
                }
            )
        
        # Real notification sending
        else:
            from app.services.notification_service import NotificationService
            from app.models.alert import Alert, AlertTypeEnum, AlertSeverityEnum, AlertStatusEnum
            from datetime import datetime
            
            logger.info(f"[alert_config.test] ⚠️ REAL TEST MODE - Actually sending notifications!")
            
            # Get employee_id - admins don't have employee_id, use 0 for test
            employee_id = current_employee.get("employee_id", 0)
            logger.info(f"[alert_config.test] Test alert employee_id: {employee_id}")
            
            # Use config's tenant_id
            alert_tenant_id = config.tenant_id
            logger.info(f"[alert_config.test] Test alert tenant_id: {alert_tenant_id}")
            
            # Create dummy alert for testing
            logger.info(f"[alert_config.test] Creating test alert object")
            test_alert = Alert(
                alert_id=0,
                tenant_id=alert_tenant_id,
                employee_id=employee_id,
                alert_type=AlertTypeEnum.SOS,
                severity=AlertSeverityEnum.HIGH,
                status=AlertStatusEnum.TRIGGERED,
                trigger_latitude=0.0,
                trigger_longitude=0.0,
                trigger_notes="⚠️ TEST NOTIFICATION - This is a test alert, not a real emergency",
                triggered_at=datetime.now()
            )
            logger.info(f"[alert_config.test] Test alert created: Type={test_alert.alert_type}, Severity={test_alert.severity}")
            
            try:
                notification_service = NotificationService(db)
                logger.info(f"[alert_config.test] NotificationService initialized")
                
                # Send notifications through each configured channel
                sent_notifications = []
                failed_notifications = []
                
                # Process primary recipients
                if config.primary_recipients:
                    logger.info(f"[alert_config.test] Processing {len(config.primary_recipients)} primary recipients for REAL notifications")
                    for idx, recipient in enumerate(config.primary_recipients):
                        recipient_name = recipient.get("name")
                        channels = recipient.get("channels", [])
                        logger.info(f"[alert_config.test]   Recipient #{idx+1}: {recipient_name} - Channels: {channels}")
                        
                        for channel in channels:
                            try:
                                contact = recipient.get("email") if channel in ["EMAIL", "PUSH"] else recipient.get("phone")
                                logger.info(f"[alert_config.test]     Sending {channel} to {recipient_name} ({contact})")
                                
                                # Actually send notifications through the service
                                if channel == "EMAIL":
                                    from app.core.email_service import EmailService
                                    email_service = EmailService()
                                    
                                    # Build email content
                                    subject = f"⚠️ TEST SOS ALERT - Not a Real Emergency"
                                    html_content = f"""
                                    <h2>🚨 TEST ALERT NOTIFICATION</h2>
                                    <p><strong>This is a TEST notification - NOT a real emergency</strong></p>
                                    
                                    <h3>Alert Details:</h3>
                                    <ul>
                                        <li><strong>Type:</strong> SOS (TEST)</li>
                                        <li><strong>Severity:</strong> HIGH</li>
                                        <li><strong>Employee ID:</strong> {employee_id}</li>
                                        <li><strong>Location:</strong> {test_alert.trigger_latitude}, {test_alert.trigger_longitude}</li>
                                        <li><strong>Time:</strong> {test_alert.triggered_at}</li>
                                    </ul>
                                    
                                    <p><strong>Notes:</strong> {test_alert.trigger_notes}</p>
                                    
                                    <p style="color: red; font-weight: bold;">⚠️ THIS IS A TEST - No action required</p>
                                    """
                                    
                                    result = await email_service.send_email(
                                        to_emails=recipient.get("email"),
                                        subject=subject,
                                        html_content=html_content
                                    )
                                    logger.info(f"[alert_config.test]     Email service result: {result}")
                                    
                                elif channel == "SMS":
                                    # TODO: Implement SMS service integration
                                    logger.warning(f"[alert_config.test]     SMS service not implemented - would send to {contact}")
                                    logger.info(f"[alert_config.test]     Message: ⚠️ TEST ALERT: SOS triggered. Employee ID: {employee_id}. This is a test, not a real emergency.")
                                    # Placeholder - mark as sent for testing purposes
                                    result = {"status": "simulated", "message": "SMS service not configured"}
                                    
                                elif channel == "PUSH":
                                    # TODO: Implement Firebase/Push notification service
                                    logger.warning(f"[alert_config.test]     Push notification service not implemented - would send to user {employee_id}")
                                    logger.info(f"[alert_config.test]     Title: ⚠️ TEST SOS ALERT")
                                    logger.info(f"[alert_config.test]     Body: This is a test notification. Not a real emergency.")
                                    # Placeholder - mark as sent for testing purposes
                                    result = {"status": "simulated", "message": "Push notification service not configured"}
                                    
                                elif channel == "VOICE":
                                    logger.warning(f"[alert_config.test]     VOICE calls not implemented - would call {contact}")
                                    # TODO: Integrate with voice calling service
                                    result = {"status": "simulated", "message": "Voice service not configured"}
                                
                                sent_notifications.append({
                                    "recipient": recipient_name,
                                    "channel": channel,
                                    "contact": contact,
                                    "status": "sent" if channel == "EMAIL" else "simulated"
                                })
                                logger.info(f"[alert_config.test]     ✅ {channel} {'sent' if channel == 'EMAIL' else 'simulated'} for {recipient_name}")
                                
                            except Exception as e:
                                logger.error(f"[alert_config.test]     ❌ Failed to send {channel} to {recipient_name}: {str(e)}")
                                logger.exception(f"[alert_config.test]     Exception details:")
                                failed_notifications.append({
                                    "recipient": recipient_name,
                                    "channel": channel,
                                    "error": str(e)
                                })
                else:
                    logger.warning(f"[alert_config.test] No primary recipients to notify!")
                
                logger.info(f"[alert_config.test] Real test complete - Sent: {len(sent_notifications)}, Failed: {len(failed_notifications)}")
                
                return ResponseWrapper.success(
                    message=f"Real test notifications processed: {len(sent_notifications)} sent, {len(failed_notifications)} failed",
                    data={
                        "config_id": config.config_id,
                        "config_name": config.config_name,
                        "tenant_id": config.tenant_id,
                        "sent_notifications": sent_notifications,
                        "failed_notifications": failed_notifications,
                        "total_sent": len(sent_notifications),
                        "total_failed": len(failed_notifications),
                        "note": "⚠️ REAL notifications were sent to recipients. This was NOT a dry-run."
                    }
                )
                
            except Exception as e:
                logger.error(f"[alert_config.test] Error during real notification test: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=ResponseWrapper.error(
                        message="Failed to send real test notifications",
                        error_code="TEST_NOTIFICATION_FAILED",
                        details={"error": str(e)}
                    )
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert_config.test] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to send test notifications",
                error_code="TEST_NOTIFICATION_FAILED",
                details={"error": str(e)}
            )
        )


@router.get("/applicable/current", response_model=dict)
def get_applicable_configuration(
    alert_type: str = Query(..., description="Alert type to get configuration for (SOS, EMERGENCY, etc.)"),
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id", description="Tenant ID (required for admin users)"),
    db: Session = Depends(get_db),
    current_employee: dict = Depends(get_current_employee)
):
    """
    Get applicable alert configuration for current employee
    
    Returns team-specific config if exists, otherwise tenant config
    Requires alert_type query parameter to match configuration rules
    
    For admins: Must provide tenant_id query parameter
    For employees: Uses tenant_id from token
    """
    try:
        from app.models.alert import AlertTypeEnum
        
        user_type = current_employee.get("user_type")
        
        # Get tenant_id based on user type
        if user_type == "employee":
            tenant_id = current_employee.get("tenant_id")
            team_id = current_employee.get("team_id")
            
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_MISSING"
                    )
                )
        elif user_type == "admin":
            # Admins must provide tenant_id as query parameter
            if not tenant_id_param:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Admin users must provide tenant_id query parameter",
                        error_code="TENANT_ID_REQUIRED",
                        details={"example": "/api/v1/alert-config/applicable/current?alert_type=SOS&tenant_id=TENANT001"}
                    )
                )
            tenant_id = tenant_id_param
            team_id = None  # Admins don't have teams
        else:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Invalid user type",
                    error_code="INVALID_USER_TYPE"
                )
            )
        
        logger.info(f"[alert_config.applicable] Looking for config - tenant_id: {tenant_id}, team_id: {team_id}, alert_type: {alert_type}")
        
        # Validate alert_type
        try:
            alert_type_enum = AlertTypeEnum(alert_type.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message=f"Invalid alert_type: {alert_type}. Valid types: {[e.value for e in AlertTypeEnum]}",
                    error_code="INVALID_ALERT_TYPE"
                )
            )
        
        config = alert_crud.get_applicable_configuration(
            db=db,
            tenant_id=tenant_id,
            alert_type=alert_type_enum,
            team_id=team_id
        )
        
        if not config:
            logger.warning(f"[alert_config.applicable] No config found for tenant_id: {tenant_id}, team_id: {team_id}, alert_type: {alert_type_enum.value}")
            return ResponseWrapper.success(
                message="No configuration found. Please contact admin to set up alert routing.",
                data=None
            )
        
        return ResponseWrapper.success(
            message="Configuration retrieved",
            data=AlertConfigurationResponse.from_orm(config).dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[alert_config.applicable] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Failed to retrieve applicable configuration",
                error_code="RETRIEVE_FAILED",
                details={"error": str(e)}
            )
        )

