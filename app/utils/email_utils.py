from typing import Optional, Dict, Any, List, Union
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
import re
from datetime import datetime

from app.core.email_service import get_email_service, EmailPriority, EmailAttachment
from app.core.logging_config import get_logger
from app.models.employee import Employee
from app.models.booking import Booking
from app.models.driver import Driver
from app.models.admin import Admin
from common_utils import get_current_ist_time

logger = get_logger(__name__)

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def send_email_background(
    background_tasks: BackgroundTasks,
    to_emails: Union[str, List[str]],
    subject: str,
    html_content: Optional[str] = None,
    text_content: Optional[str] = None,
    template: Optional[str] = None,
    template_data: Optional[Dict[str, Any]] = None,
    priority: EmailPriority = EmailPriority.NORMAL,
    **kwargs
):
    """
    Add email to background tasks - all emails sent from global admin
    
    Args:
        background_tasks: FastAPI background tasks
        to_emails: Recipient email(s)
        subject: Email subject
        html_content: HTML content
        text_content: Text content
        template: Template name for template emails
        template_data: Data for template emails
        priority: Email priority
        **kwargs: Additional email parameters
    """
    background_tasks.add_task(
        _send_email_task,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        template=template,
        template_data=template_data,
        priority=priority,
        **kwargs
    )

def _send_email_task(
    to_emails: Union[str, List[str]],
    subject: str,
    html_content: Optional[str] = None,
    text_content: Optional[str] = None,
    template: Optional[str] = None,
    template_data: Optional[Dict[str, Any]] = None,
    priority: EmailPriority = EmailPriority.NORMAL,
    **kwargs
):
    """Background task to send email from global admin"""
    try:
        email_service = get_email_service()
        
        # Only send regular email since templates are removed
        success = email_service.send_email(
            to_emails=to_emails,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            priority=priority,
            **kwargs
        )
        
        if success:
            logger.info(f"Email sent successfully to {to_emails}: {subject}")
        else:
            logger.error(f"Failed to send email to {to_emails}: {subject}")
        
    except Exception as e:
        logger.error(f"Error in email background task: {str(e)}")

def send_booking_notification_to_employee(
    background_tasks: BackgroundTasks,
    db: Session,
    booking: Booking,
    notification_type: str = "confirmation",
    old_status: Optional[str] = None
):
    """
    Send booking-related email notification to employee from global admin
    
    Args:
        background_tasks: FastAPI background tasks
        db: Database session
        booking: Booking object
        notification_type: Type of notification (confirmation, status_update, driver_assigned)
        old_status: Previous status for status updates
    """
    try:
        # Get employee details
        employee = db.query(Employee).filter(Employee.employee_id == booking.employee_id).first()
        if not employee:
            logger.error(f"Employee not found for booking {booking.booking_id}")
            return
        
        email_service = get_email_service()
        
        booking_data = {
            'booking_id': booking.booking_id,
            'employee_name': employee.name,
            'pickup_date': str(booking.pickup_date),
            'pickup_time': str(booking.pickup_time),
            'pickup_location': booking.pickup_location,
            'drop_location': booking.drop_location,
            'status': booking.status
        }
        
        if notification_type == "confirmation":
            background_tasks.add_task(
                email_service.send_booking_confirmation_email,
                user_email=employee.email,
                booking_data=booking_data
            )
        
        elif notification_type == "status_update" and old_status:
            background_tasks.add_task(
                email_service.send_booking_status_update_email,
                user_email=employee.email,
                booking_data=booking_data,
                old_status=old_status
            )
        
        elif notification_type == "driver_assigned":
            # Get driver details if available
            if hasattr(booking, 'route') and booking.route and booking.route.driver_id:
                driver = db.query(Driver).filter(Driver.driver_id == booking.route.driver_id).first()
                if driver:
                    booking_data.update({
                        'driver_name': driver.name,
                        'driver_phone': driver.phone,
                        'vehicle_number': booking.route.vehicle.vehicle_number if hasattr(booking.route, 'vehicle') and booking.route.vehicle else 'TBD'
                    })
                    
                    background_tasks.add_task(
                        email_service.send_driver_assignment_email,
                        user_email=employee.email,
                        booking_data=booking_data
                    )
        
    except Exception as e:
        logger.error(f"Failed to send booking notification: {str(e)}")

def send_bulk_notification_emails(
    background_tasks: BackgroundTasks,
    recipients: List[Dict[str, Any]],
    template: str,
    common_data: Optional[Dict[str, Any]] = None,
    subject: str = "Notification"
):
    """
    Send notification emails to multiple recipients
    
    Args:
        background_tasks: FastAPI background tasks
        recipients: List of dicts with 'email' and individual data
        template: Email template name
        common_data: Common data for all emails
        subject: Email subject
    """
    background_tasks.add_task(
        _send_bulk_emails_task,
        recipients=recipients,
        subject=subject,
        html_content=common_data.get('html_content') if common_data else None,
        text_content=common_data.get('text_content') if common_data else None
    )

def _send_bulk_emails_task(
    recipients: List[Dict[str, Any]],
    subject: str,
    html_content: Optional[str] = None,
    text_content: Optional[str] = None
):
    """Background task for bulk emails"""
    try:
        email_service = get_email_service()
        results = email_service.send_bulk_emails(
            recipients=recipients,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
        
        successful_count = sum(1 for success in results.values() if success)
        logger.info(f"Bulk email completed: {successful_count}/{len(recipients)} emails sent successfully")
        
    except Exception as e:
        logger.error(f"Error in bulk email task: {str(e)}")

def send_system_alert_email(
    background_tasks: BackgroundTasks,
    admin_emails: List[str],
    alert_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Send system alert email to administrators
    
    Args:
        background_tasks: FastAPI background tasks
        admin_emails: List of administrator email addresses
        alert_type: Type of alert (error, warning, info)
        message: Alert message
        details: Additional alert details
    """
    priority_map = {
        'error': EmailPriority.URGENT,
        'warning': EmailPriority.HIGH,
        'info': EmailPriority.NORMAL
    }
    
    priority = priority_map.get(alert_type.lower(), EmailPriority.NORMAL)
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: {'#ffebee' if alert_type == 'error' else '#fff3e0' if alert_type == 'warning' else '#e3f2fd'}; 
                    border-left: 4px solid {'#f44336' if alert_type == 'error' else '#ff9800' if alert_type == 'warning' else '#2196f3'}; 
                    padding: 20px; margin: 20px 0;">
            <h2 style="color: {'#c62828' if alert_type == 'error' else '#ef6c00' if alert_type == 'warning' else '#1976d2'};">
                🚨 System Alert: {alert_type.upper()}
            </h2>
            <p><strong>Message:</strong> {message}</p>
            <p><strong>Time:</strong> {get_current_ist_time().strftime('%Y-%m-%d %H:%M:%S')}</p>
            {f"<p><strong>Details:</strong></p><pre>{details}</pre>" if details else ""}
        </div>
        <p>This is an automated system alert from Fleet Manager.</p>
    </div>
    """
    
    send_email_background(
        background_tasks=background_tasks,
        to_emails=admin_emails,
        subject=f"🚨 System Alert: {alert_type.upper()} - {message}",
        html_content=html_content,
        priority=priority
    )

def send_user_welcome_email(
    background_tasks: BackgroundTasks,
    user_email: str,
    user_name: str,
    user_type: str,
    login_credentials: Dict[str, str]
):
    """
    Send welcome email to new users from global admin
    
    Args:
        background_tasks: FastAPI background tasks
        user_email: User's email address
        user_name: User's full name
        user_type: Type of user (employee, driver, admin, etc.)
        login_credentials: Login credentials dict
    """
    background_tasks.add_task(
        get_email_service().send_welcome_email,
        user_email=user_email,
        user_name=user_name,
        login_credentials=login_credentials
    )

def send_password_reset_email(
    background_tasks: BackgroundTasks,
    user_email: str,
    user_name: str,
    reset_token: str
):
    """
    Send password reset email
    
    Args:
        background_tasks: FastAPI background tasks
        user_email: User's email address
        user_name: User's full name
        reset_token: Password reset token
    """
    background_tasks.add_task(
        get_email_service().send_password_reset_email,
        user_email=user_email,
        reset_token=reset_token,
        user_name=user_name
    )

def send_route_assignment_email(
    background_tasks: BackgroundTasks,
    driver_email: str,
    driver_name: str,
    route_data: Dict[str, Any]
):
    """
    Send route assignment email to driver
    
    Args:
        background_tasks: FastAPI background tasks
        driver_email: Driver's email address
        driver_name: Driver's name
        route_data: Route information
    """
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>🚐 New Route Assignment</h2>
        <p>Hello {driver_name},</p>
        <p>You have been assigned a new route:</p>
        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3>Route Details:</h3>
            <p><strong>Route ID:</strong> {route_data.get('route_id')}</p>
            <p><strong>Start Time:</strong> {route_data.get('start_time')}</p>
            <p><strong>End Time:</strong> {route_data.get('end_time')}</p>
            <p><strong>Vehicle:</strong> {route_data.get('vehicle_number')}</p>
            <p><strong>Total Stops:</strong> {route_data.get('total_stops', 'N/A')}</p>
        </div>
        <p>Please check your mobile app for detailed route information and passenger pickup points.</p>
        <p>Safe driving!<br>The Fleet Manager Team</p>
    </div>
    """
    
    send_email_background(
        background_tasks=background_tasks,
        to_emails=driver_email,
        subject=f"🚐 New Route Assignment - {route_data.get('route_id')}",
        html_content=html_content
    )

def get_admin_emails(db: Session, tenant_id: Optional[str] = None) -> List[str]:
    """
    Get administrator email addresses
    
    Args:
        db: Database session
        tenant_id: Optional tenant ID to filter admins
    
    Returns:
        List[str]: List of admin email addresses
    """
    try:
        query = db.query(Admin).filter(Admin.is_active == True)
        
        if tenant_id:
            # Get tenant-specific admins (if you have tenant-admin relationship)
            pass  # Implement based on your Admin-Tenant relationship
        
        admins = query.all()
        return [admin.email for admin in admins if validate_email(admin.email)]
    
    except Exception as e:
        logger.error(f"Failed to get admin emails: {str(e)}")
        return []

def test_email_service() -> Dict[str, Any]:
    """Test email service configuration and connectivity"""
    email_service = get_email_service()
    
    return {
        'configured': email_service.is_configured,
        'connection_test': email_service.test_connection() if email_service.is_configured else False,
        'stats': email_service.get_email_stats()
    }

def send_tenant_welcome_emails(
    background_tasks: BackgroundTasks,
    tenant_data: Dict[str, Any],
    admin_email: str,
    admin_name: str,
    login_credentials: Dict[str, str]
):
    """
    Send both welcome and tenant created emails from global admin
    
    Args:
        background_tasks: FastAPI background tasks
        tenant_data: Tenant information
        admin_email: Admin email address
        admin_name: Admin name
        login_credentials: Login credentials
    """
    email_service = get_email_service()
    
    # Send welcome email
    background_tasks.add_task(
        email_service.send_welcome_email,
        user_email=admin_email,
        user_name=admin_name,
        login_credentials=login_credentials
    )
    
    # Send tenant created notification
    background_tasks.add_task(
        email_service.send_tenant_created_email,
        admin_email=admin_email,
        tenant_data=tenant_data
    )
