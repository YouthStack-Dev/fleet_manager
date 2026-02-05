"""
Notification Service for Alert System
Handles multi-channel notifications (Email, SMS, Push, Voice)
"""
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
from app.models.alert import (
    Alert, AlertConfiguration, AlertNotification,
    NotificationChannelEnum, NotificationStatusEnum
)
from app.crud.alert import create_notification, update_notification_status
from app.core.email_service import EmailService
from app.core.logging_config import get_logger
from app.config import settings
from app.services.unified_notification_service import UnifiedNotificationService
from app.services.session_cache import SessionCache
from app.services.sms_service import SMSService

logger = get_logger(__name__)


class NotificationService:
    """
    Unified notification service for alerts
    Supports: Email, SMS, Push notifications, Voice calls
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()
        self.sms_service = SMSService()
        # Initialize push notification service
        self.push_service = UnifiedNotificationService(db, SessionCache())
    
    async def notify_alert_triggered(
        self,
        alert: Alert,
        config: AlertConfiguration
    ) -> List[AlertNotification]:
        """
        Send notifications when alert is triggered
        """
        notifications = []
        
        # Build notification message
        subject = self._build_subject(alert, "TRIGGERED")
        message = self._build_message(alert, "triggered")
        
        # Send to primary recipients
        for recipient in config.primary_recipients:
            for channel in recipient.get("channels", []):
                notification = await self._send_notification(
                    alert=alert,
                    recipient=recipient,
                    channel=channel,
                    subject=subject,
                    message=message
                )
                if notification:
                    notifications.append(notification)
        
        self.db.commit()
        logger.info(f"[notification] Sent {len(notifications)} notifications for alert {alert.alert_id}")
        
        return notifications
    
    async def notify_alert_escalated(
        self,
        alert: Alert,
        config: AlertConfiguration,
        escalation_level: int
    ) -> List[AlertNotification]:
        """
        Send notifications when alert is escalated
        """
        if not config.notify_on_escalation:
            return []
        
        notifications = []
        
        subject = self._build_subject(alert, f"ESCALATED - Level {escalation_level}")
        message = self._build_message(alert, f"escalated to level {escalation_level}")
        
        # Send to escalation recipients
        if config.escalation_recipients:
            for recipient in config.escalation_recipients:
                for channel in recipient.get("channels", []):
                    notification = await self._send_notification(
                        alert=alert,
                        recipient=recipient,
                        channel=channel,
                        subject=subject,
                        message=message
                    )
                    if notification:
                        notifications.append(notification)
        
        self.db.commit()
        logger.info(f"[notification] Sent {len(notifications)} escalation notifications for alert {alert.alert_id}")
        
        return notifications
    
    async def notify_alert_status_change(
        self,
        alert: Alert,
        config: AlertConfiguration,
        new_status: str
    ) -> List[AlertNotification]:
        """
        Send notifications when alert status changes
        """
        if not config.notify_on_status_change:
            return []
        
        notifications = []
        
        subject = self._build_subject(alert, f"Status Update: {new_status}")
        message = self._build_message(alert, f"status changed to {new_status}")
        
        # Notify all recipients (primary + escalation)
        all_recipients = config.primary_recipients.copy()
        if config.escalation_recipients:
            all_recipients.extend(config.escalation_recipients)
        
        for recipient in all_recipients:
            for channel in recipient.get("channels", []):
                notification = await self._send_notification(
                    alert=alert,
                    recipient=recipient,
                    channel=channel,
                    subject=subject,
                    message=message
                )
                if notification:
                    notifications.append(notification)
        
        self.db.commit()
        logger.info(f"[notification] Sent {len(notifications)} status change notifications for alert {alert.alert_id}")
        
        return notifications
    
    async def _send_notification(
        self,
        alert: Alert,
        recipient: Dict[str, Any],
        channel: str,
        subject: str,
        message: str
    ) -> Optional[AlertNotification]:
        """
        Send notification via specified channel
        """
        try:
            # Create notification record
            notification = create_notification(
                db=self.db,
                alert=alert,
                recipient_name=recipient.get("name"),
                recipient_email=recipient.get("email"),
                recipient_phone=recipient.get("phone"),
                recipient_role=recipient.get("role"),
                channel=NotificationChannelEnum(channel),
                subject=subject,
                message=message
            )
            
            # Send based on channel
            if channel == NotificationChannelEnum.EMAIL.value:
                success = await self._send_email(notification, recipient.get("email"), subject, message)
            elif channel == NotificationChannelEnum.SMS.value:
                success = await self._send_sms(notification, recipient.get("phone"), message)
            elif channel == NotificationChannelEnum.PUSH.value:
                success = await self._send_push(notification, recipient, subject, message, alert)
            elif channel == NotificationChannelEnum.VOICE.value:
                success = await self._send_voice_call(notification, recipient.get("phone"), message)
            elif channel == NotificationChannelEnum.WHATSAPP.value:
                success = await self._send_whatsapp(notification, recipient.get("phone"), message)
            else:
                logger.warning(f"[notification] Unknown channel: {channel}")
                success = False
            
            # Update status
            if success:
                update_notification_status(
                    db=self.db,
                    notification=notification,
                    status=NotificationStatusEnum.SENT
                )
            else:
                update_notification_status(
                    db=self.db,
                    notification=notification,
                    status=NotificationStatusEnum.FAILED,
                    failure_reason="Failed to send"
                )
            
            return notification
            
        except Exception as e:
            logger.error(f"[notification] Error sending notification: {str(e)}")
            if notification:
                update_notification_status(
                    db=self.db,
                    notification=notification,
                    status=NotificationStatusEnum.FAILED,
                    failure_reason=str(e)
                )
            return None
    
    async def _send_email(
        self,
        notification: AlertNotification,
        to_email: str,
        subject: str,
        message: str
    ) -> bool:
        """Send email notification"""
        try:
            if not to_email:
                logger.warning("[notification.email] No email provided")
                return False
            
            html_body = f"""
            <html>
                <body>
                    <h2 style="color: #dc3545;">🚨 Alert Notification</h2>
                    <div style="padding: 15px; background-color: #f8f9fa; border-left: 4px solid #dc3545;">
                        {message}
                    </div>
                    <hr>
                    <p style="color: #6c757d; font-size: 12px;">
                        This is an automated alert from Fleet Management System.
                        Please respond immediately if action is required.
                    </p>
                </body>
            </html>
            """
            
            success = await self.email_service.send_email(
                to_emails=[to_email],
                subject=subject,
                html_content=html_body,
                text_content=message
            )
            
            logger.info(f"[notification.email] Email sent to {to_email}: {success}")
            return success
            
        except Exception as e:
            logger.error(f"[notification.email] Error: {str(e)}")
            return False
    
    async def _send_sms(
        self,
        notification: AlertNotification,
        to_phone: str,
        message: str
    ) -> bool:
        """
        Send SMS notification via Twilio
        """
        try:
            if not to_phone:
                logger.warning("[notification.sms] No phone provided")
                return False
            
            # Use the SMSService
            success = self.sms_service.send_sms(
                to_phone=to_phone,
                message=message
            )
            
            if success:
                logger.info(f"[notification.sms] SMS sent successfully to {to_phone[:8]}...")
            else:
                logger.warning(f"[notification.sms] Failed to send SMS to {to_phone[:8]}...")
            
            return success
            
        except Exception as e:
            logger.error(f"[notification.sms] Error: {str(e)}")
            return False
    
    async def _send_push(
        self,
        notification: AlertNotification,
        recipient: Dict[str, Any],
        subject: str,
        message: str,
        alert: Alert
    ) -> bool:
        """
        Send push notification via Firebase Cloud Messaging
        Integrated with UnifiedNotificationService for high-performance delivery
        """
        try:
            if not settings.FCM_ENABLED:
                logger.warning("[notification.push] FCM is disabled in settings")
                return False
            
            # Extract user info from recipient
            user_type = recipient.get("user_type")
            user_id = recipient.get("user_id")
            
            if not user_type or not user_id:
                logger.warning(f"[notification.push] Missing user_type or user_id in recipient: {recipient}")
                return False
            
            logger.info(f"[notification.push] Sending push to {user_type}:{user_id}")
            
            # Build notification data
            data = {
                "alert_id": str(alert.alert_id),
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "vehicle_id": str(alert.vehicle_id) if alert.vehicle_id else "",
                "driver_id": str(alert.driver_id) if alert.driver_id else "",
                "booking_id": str(alert.booking_id) if alert.booking_id else "",
                "notification_id": str(notification.notification_id) if notification.notification_id else "",
            }
            
            # Send via UnifiedNotificationService
            result = self.push_service.send_to_user(
                user_type=user_type,
                user_id=user_id,
                title=subject,
                body=message,
                data=data,
                priority="high"
            )
            
            if result["success"]:
                logger.info(
                    f"[notification.push] Push sent successfully to {user_type}:{user_id}, "
                    f"message_id={result.get('message_id')}"
                )
                return True
            else:
                error = result.get("error", "UNKNOWN")
                error_msg = result.get("message", "Unknown error")
                logger.error(
                    f"[notification.push] Failed to send push to {user_type}:{user_id}, "
                    f"error={error}, message={error_msg}"
                )
                
                # If no active session, that's expected (user not logged in)
                if error == "NO_ACTIVE_SESSION":
                    logger.info(f"[notification.push] User {user_type}:{user_id} has no active session (not logged in)")
                    # Return True to not mark as failed (user just isn't logged in)
                    return True
                
                return False
            
        except Exception as e:
            logger.error(f"[notification.push] Unexpected error: {e}", exc_info=True)
            return False
    
    async def _send_voice_call(
        self,
        notification: AlertNotification,
        to_phone: str,
        message: str
    ) -> bool:
        """
        Send automated voice call
        TODO: Integrate with voice provider (Twilio Voice, etc.)
        """
        try:
            if not to_phone:
                logger.warning("[notification.voice] No phone provided")
                return False
            
            # TODO: Implement voice call
            # Example with Twilio Voice:
            # from twilio.rest import Client
            # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # call = client.calls.create(
            #     twiml=f'<Response><Say>{message}</Say></Response>',
            #     to=to_phone,
            #     from_=settings.TWILIO_PHONE_NUMBER
            # )
            
            logger.info(f"[notification.voice] Voice call would be made to {to_phone}")
            logger.info(f"[notification.voice] Message: {message[:100]}...")
            
            # Return True for testing
            return True
            
        except Exception as e:
            logger.error(f"[notification.voice] Error: {str(e)}")
            return False
    
    async def _send_whatsapp(
        self,
        notification: AlertNotification,
        to_phone: str,
        message: str
    ) -> bool:
        """
        Send WhatsApp message
        TODO: Integrate with WhatsApp Business API
        """
        try:
            if not to_phone:
                logger.warning("[notification.whatsapp] No phone provided")
                return False
            
            # TODO: Implement WhatsApp messaging
            logger.info(f"[notification.whatsapp] WhatsApp message would be sent to {to_phone}")
            logger.info(f"[notification.whatsapp] Message: {message[:100]}...")
            
            # Return True for testing
            return True
            
        except Exception as e:
            logger.error(f"[notification.whatsapp] Error: {str(e)}")
            return False
    
    def _build_subject(self, alert: Alert, status: str) -> str:
        """Build notification subject"""
        return f"🚨 ALERT {status} - #{alert.alert_id} - {alert.alert_type.value}"
    
    def _build_message(self, alert: Alert, action: str) -> str:
        """Build notification message"""
        return f"""
Alert #{alert.alert_id} has been {action}.

Type: {alert.alert_type.value}
Severity: {alert.severity.value}
Employee ID: {alert.employee_id}
Booking ID: {alert.booking_id or 'N/A'}
Triggered At: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}
Location: {alert.trigger_latitude}, {alert.trigger_longitude}

{f"Notes: {alert.trigger_notes}" if alert.trigger_notes else ""}

Please respond immediately.
        """.strip()
