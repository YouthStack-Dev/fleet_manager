"""
SMS Service for Fleet Manager
Handles SMS sending via Twilio
"""
from typing import Optional
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class SMSService:
    """
    SMS service wrapper for Twilio
    
    Features:
    - Send SMS messages via Twilio
    - Error handling and logging
    - Automatic enablement check
    """
    
    def __init__(self):
        """Initialize SMS Service with Twilio credentials"""
        self.enabled = settings.TWILIO_ENABLED
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.phone_number = settings.TWILIO_PHONE_NUMBER
        
        if self.enabled:
            try:
                from twilio.rest import Client
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("[sms_service] Twilio SMS service initialized successfully")
            except ImportError:
                logger.error("[sms_service] Twilio library not installed. Run: pip install twilio")
                self.enabled = False
            except Exception as e:
                logger.error(f"[sms_service] Failed to initialize Twilio client: {e}")
                self.enabled = False
        else:
            logger.info("[sms_service] SMS service is disabled in configuration")
    
    def send_sms(
        self,
        to_phone: str,
        message: str,
        max_length: int = 1600
    ) -> bool:
        """
        Send SMS message to a phone number
        
        Args:
            to_phone: Recipient phone number (E.164 format: +1234567890)
            message: Message content
            max_length: Maximum message length (default 1600 for concatenated SMS)
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[sms_service] SMS service is disabled, skipping send")
            return False
        
        if not to_phone:
            logger.warning("[sms_service] No phone number provided")
            return False
        
        try:
            # Ensure phone number is in E.164 format
            if not to_phone.startswith('+'):
                # Try to add country code if missing (assuming India +91)
                if len(to_phone) == 10:
                    to_phone = f"+91{to_phone}"
                else:
                    logger.warning(f"[sms_service] Invalid phone format: {to_phone}")
                    return False
            
            # Truncate message if too long
            if len(message) > max_length:
                message = message[:max_length - 3] + "..."
                logger.warning(f"[sms_service] Message truncated to {max_length} characters")
            
            # Send SMS via Twilio
            message_obj = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_phone
            )
            
            logger.info(
                f"[sms_service] SMS sent successfully to {to_phone[:8]}... | "
                f"SID: {message_obj.sid} | Status: {message_obj.status}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[sms_service] Failed to send SMS to {to_phone}: {e}", exc_info=True)
            return False
    
    def send_bulk_sms(
        self,
        recipients: list[dict],
        message: str
    ) -> dict:
        """
        Send SMS to multiple recipients
        
        Args:
            recipients: List of dicts with 'phone' and optional 'name' keys
            message: Message content
            
        Returns:
            dict: Summary with success_count and failed_numbers
        """
        if not self.enabled:
            logger.warning("[sms_service] SMS service is disabled, skipping bulk send")
            return {"success_count": 0, "failed_count": len(recipients)}
        
        success_count = 0
        failed_numbers = []
        
        for recipient in recipients:
            phone = recipient.get("phone")
            if not phone:
                continue
            
            # Personalize message if name provided
            personalized_message = message
            if recipient.get("name"):
                personalized_message = f"Hi {recipient['name']}, {message}"
            
            if self.send_sms(phone, personalized_message):
                success_count += 1
            else:
                failed_numbers.append(phone)
        
        logger.info(
            f"[sms_service] Bulk SMS complete: {success_count} sent, "
            f"{len(failed_numbers)} failed"
        )
        
        return {
            "success_count": success_count,
            "failed_count": len(failed_numbers),
            "failed_numbers": failed_numbers
        }
