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

logger = get_logger(__name__)


class NotificationService:
    """
    Unified notification service for alerts
    Supports: Email, SMS, Push notifications, Voice calls
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()
    
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
            
            success = self.email_service.send_email(
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
        Send SMS notification
        TODO: Integrate with SMS provider (Twilio, AWS SNS, etc.)
        """
        try:
            if not to_phone:
                logger.warning("[notification.sms] No phone provided")
                return False
            
            # TODO: Implement SMS sending
            # Example with Twilio:
            # from twilio.rest import Client
            # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # message = client.messages.create(
            #     body=message,
            #     from_=settings.TWILIO_PHONE_NUMBER,
            #     to=to_phone
            # )
            
            logger.info(f"[notification.sms] SMS would be sent to {to_phone}")
            # For now, log only
            logger.info(f"[notification.sms] Message: {message[:100]}...")
            
            # Return True for testing, implement actual SMS sending
            return True
            
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
        Send push notification via Firebase
        TODO: Integrate with Firebase Cloud Messaging
        """
        try:
            # TODO: Implement Firebase push notifications
            # from firebase_admin import messaging
            # message = messaging.Message(
            #     notification=messaging.Notification(
            #         title=subject,
            #         body=message
            #     ),
            #     data={
            #         "alert_id": str(alert.alert_id),
            #         "alert_type": alert.alert_type.value,
            #         "severity": alert.severity.value
            #     },
            #     token=recipient.get("fcm_token")  # Need to store FCM tokens
            # )
            # response = messaging.send(message)
            
            logger.info(f"[notification.push] Push notification would be sent to {recipient.get('name')}")
            logger.info(f"[notification.push] Subject: {subject}")
            
            # Return True for testing
            return True
            
        except Exception as e:
            logger.error(f"[notification.push] Error: {str(e)}")
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
