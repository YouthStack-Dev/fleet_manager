from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class TwilioAdapter:
    """Simple Twilio adapter for sending SMS and Verify operations."""

    def __init__(self):
        if not settings.TWILIO_ENABLED:
            logger.info("TwilioAdapter disabled via configuration")
        self.enabled = settings.TWILIO_ENABLED
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_PHONE_NUMBER
        self.verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID

        # Lazy import to avoid requiring package when disabled
        self._client = None

    def _get_client(self):
        if not self._client:
            try:
                from twilio.rest import Client
            except Exception as e:
                logger.error("Twilio SDK not installed or import failed: %s", e)
                raise
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    def send_sms(self, to: str, body: str) -> bool:
        """Send an SMS message via Twilio Messaging API."""
        logger.info("[twilio.sms] Attempting to send SMS to=%s, body_length=%d", to, len(body))
        
        if not self.enabled:
            logger.warning("[twilio.sms] Twilio disabled - skipping send_sms")
            return False

        try:
            logger.debug("[twilio.sms] Getting Twilio client")
            client = self._get_client()
            
            logger.debug("[twilio.sms] Creating message from=%s to=%s", self.from_number, to)
            msg = client.messages.create(body=body, from_=self.from_number, to=to)
            
            logger.info("[twilio.sms] ✓ SMS sent successfully: sid=%s to=%s status=%s", 
                       getattr(msg, 'sid', None), to, getattr(msg, 'status', None))
            
            # Log additional details for debugging
            if hasattr(msg, 'error_code') and msg.error_code:
                logger.warning("[twilio.sms] Message has error_code: %s - %s", msg.error_code, getattr(msg, 'error_message', ''))
            
            return True
        except Exception as e:
            logger.error("[twilio.sms] ✗ Failed to send SMS to=%s error=%s", to, str(e))
            # Try to extract more specific error information
            if hasattr(e, 'code'):
                logger.error("[twilio.sms] Error code: %s", e.code)
            if hasattr(e, 'status'):
                logger.error("[twilio.sms] HTTP status: %s", e.status)
            return False

    def start_verification(self, to: str, channel: str = 'sms') -> bool:
        """Start a Twilio Verify flow (sends OTP)."""
        logger.info("[twilio.verify] Starting verification for to=%s channel=%s", to, channel)
        
        if not self.enabled or not self.verify_service_sid:
            logger.warning("[twilio.verify] Twilio Verify disabled or not configured (enabled=%s, service_sid=%s)",
                         self.enabled, bool(self.verify_service_sid))
            return False
        try:
            logger.debug("[twilio.verify] Getting Twilio client")
            client = self._get_client()
            
            logger.debug("[twilio.verify] Creating verification request")
            verification = client.verify.services(self.verify_service_sid).verifications.create(to=to, channel=channel)
            
            logger.info("[twilio.verify] ✓ Verification started: sid=%s status=%s to=%s", 
                       getattr(verification, 'sid', None), getattr(verification, 'status', None), to)
            return True
        except Exception as e:
            logger.error("[twilio.verify] ✗ Failed to start verification for to=%s error=%s", to, str(e))
            return False

    def check_verification(self, to: str, code: str) -> bool:
        """Check a Twilio Verify code."""
        logger.info("[twilio.verify] Checking verification code for to=%s code_length=%d", to, len(code))
        
        if not self.enabled or not self.verify_service_sid:
            logger.warning("[twilio.verify] Twilio Verify disabled or not configured")
            return False
        try:
            logger.debug("[twilio.verify] Getting Twilio client")
            client = self._get_client()
            
            logger.debug("[twilio.verify] Submitting verification check")
            result = client.verify.services(self.verify_service_sid).verification_checks.create(to=to, code=code)
            
            status = getattr(result, 'status', None)
            is_approved = status == 'approved'
            
            if is_approved:
                logger.info("[twilio.verify] ✓ Verification approved for to=%s", to)
            else:
                logger.warning("[twilio.verify] ✗ Verification failed for to=%s status=%s", to, status)
            
            return is_approved
        except Exception as e:
            logger.error("[twilio.verify] ✗ Error checking verification for to=%s error=%s", to, str(e))
            return False
