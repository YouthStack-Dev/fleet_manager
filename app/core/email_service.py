import smtplib
import ssl
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Any, Union
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class EmailPriority(str, Enum):
    """Email priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

@dataclass
class EmailAttachment:
    """Email attachment data structure"""
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

class EmailService:
    """Centralized email service for the Fleet Manager application"""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.smtp_use_ssl = settings.SMTP_USE_SSL
        self.app_name = settings.APP_NAME
        self.email_enabled = settings.EMAIL_ENABLED
        self.retry_attempts = settings.EMAIL_RETRY_ATTEMPTS
        self.retry_delay = settings.EMAIL_RETRY_DELAY
        
        # Global Admin Email Settings (fixed sender for all emails)
        self.sender_email = settings.SENDER_EMAIL
        self.sender_name = settings.SENDER_NAME
        self.support_email = settings.SUPPORT_EMAIL
        
        # Validate configuration
        self.is_configured = self._validate_config()
        
        # Email statistics
        self._emails_sent = 0
        self._emails_failed = 0
    
    def _validate_config(self) -> bool:
        """Validate SMTP configuration"""
        if not self.email_enabled:
            logger.info("Email service is disabled by configuration")
            return False
            
        if not all([self.smtp_server, self.smtp_port, self.smtp_username, 
                   self.smtp_password, self.sender_email]):
            logger.warning("SMTP configuration incomplete. Email notifications will be disabled.")
            logger.debug(f"Missing config - Server: {bool(self.smtp_server)}, "
                        f"Port: {bool(self.smtp_port)}, Username: {bool(self.smtp_username)}, "
                        f"Password: {bool(self.smtp_password)}, Sender: {bool(self.sender_email)}")
            return False
        
        logger.info(f"Email service configured with {self.smtp_server}:{self.smtp_port} using sender: {self.sender_email}")
        return True
    
    @contextmanager
    def _create_smtp_connection(self):
        """Create and return SMTP connection with proper error handling"""
        server = None
        try:
            if self.smtp_use_ssl:
                # Use SSL connection (port 465)
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context)
                logger.debug("Created SMTP_SSL connection")
            else:
                # Use regular connection with optional TLS (port 587)
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                if self.smtp_use_tls:
                    server.starttls()
                    logger.debug("Started TLS on SMTP connection")
            
            server.login(self.smtp_username, self.smtp_password)
            logger.debug("SMTP authentication successful")
            yield server
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {str(e)}")
            raise
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"SMTP server disconnected: {str(e)}")
            raise
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to create SMTP connection: {str(e)}")
            raise
        finally:
            if server:
                try:
                    server.quit()
                    logger.debug("SMTP connection closed")
                except:
                    pass
    
    def _create_message(
        self,
        to_emails: List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        attachments: Optional[List[EmailAttachment]] = None,
        reply_to: Optional[str] = None,
        priority: EmailPriority = EmailPriority.NORMAL
    ) -> MIMEMultipart:
        """Create email message with fixed global admin sender"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.sender_name} <{self.sender_email}>"
        msg['To'] = ', '.join(to_emails)
        
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Set priority
        if priority == EmailPriority.HIGH:
            msg['X-Priority'] = '2'
            msg['X-MSMail-Priority'] = 'High'
        elif priority == EmailPriority.URGENT:
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
        elif priority == EmailPriority.LOW:
            msg['X-Priority'] = '4'
            msg['X-MSMail-Priority'] = 'Low'
        
        # Add content
        if text_content:
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(text_part)
        
        if html_content:
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
        
        # Add attachments
        if attachments:
            for attachment in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename={attachment.filename}'
                )
                msg.attach(part)
        
        return msg
    
    def send_email(
        self,
        to_emails: Union[str, List[str]],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        cc_emails: Optional[Union[str, List[str]]] = None,
        bcc_emails: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[EmailAttachment]] = None,
        reply_to: Optional[str] = None,
        priority: EmailPriority = EmailPriority.NORMAL
    ) -> bool:
        """
        Send email with HTML/text content and optional attachments
        All emails sent from the global admin email address
        
        Args:
            to_emails: Recipient email address(es)
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (fallback)
            cc_emails: CC recipient email address(es)
            bcc_emails: BCC recipient email address(es)
            attachments: List of EmailAttachment objects
            reply_to: Reply-to email address (defaults to sender email)
            priority: Email priority level
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.error("Email service not configured. Cannot send email.")
            return False
        
        # Set default reply-to as the sender email if not specified
        if not reply_to:
            reply_to = self.sender_email
        
        # Normalize email lists
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        if isinstance(cc_emails, str):
            cc_emails = [cc_emails]
        if isinstance(bcc_emails, str):
            bcc_emails = [bcc_emails]
        
        # Validate inputs
        if not to_emails or not subject:
            logger.error("to_emails and subject are required")
            return False
        
        if not html_content and not text_content:
            logger.error("Either html_content or text_content is required")
            return False
        
        # Attempt to send with retries
        for attempt in range(self.retry_attempts):
            try:
                msg = self._create_message(
                    to_emails=to_emails,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    cc_emails=cc_emails,
                    bcc_emails=bcc_emails,
                    attachments=attachments,
                    reply_to=reply_to,
                    priority=priority
                )
                
                with self._create_smtp_connection() as server:
                    all_recipients = to_emails[:]
                    if cc_emails:
                        all_recipients.extend(cc_emails)
                    if bcc_emails:
                        all_recipients.extend(bcc_emails)
                    
                    server.send_message(msg, to_addrs=all_recipients)
                    
                self._emails_sent += 1
                logger.info(f"Email sent successfully to {', '.join(to_emails)} - Subject: {subject}")
                return True
                
            except Exception as e:
                logger.warning(f"Email send attempt {attempt + 1}/{self.retry_attempts} failed: {str(e)}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                else:
                    self._emails_failed += 1
                    logger.error(f"Failed to send email after {self.retry_attempts} attempts: {str(e)}")
                    return False
        
        return False
    
    def send_driver_assignment_email(self, user_email: str, booking_data: Dict[str, Any]) -> bool:
        """Send driver assignment notification email"""
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #f8f9fa; padding: 20px; border-bottom: 3px solid #007bff; margin-bottom: 20px;">
                <h2 style="color: #007bff; margin: 0;">🚗 Driver Assigned</h2>
                <p style="color: #6c757d; margin: 5px 0 0 0;">Fleet Manager Notification</p>
            </div>
            <p>Hello {booking_data.get('employee_name')},</p>
            <p>A driver has been assigned to your booking <strong>{booking_data.get('booking_id')}</strong>.</p>
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3>Driver Details:</h3>
                <p><strong>Name:</strong> {booking_data.get('driver_name')}</p>
                <p><strong>Phone:</strong> {booking_data.get('driver_phone')}</p>
                <p><strong>Vehicle:</strong> {booking_data.get('vehicle_number')}</p>
            </div>
            <p>For any questions or support, please contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
            <p>Best regards,<br>The {self.app_name} Team</p>
        </div>
        """
        
        return self.send_email(
            to_emails=user_email,
            subject=f"Driver Assigned - Booking {booking_data.get('booking_id')}",
            html_content=html_content
        )
    
    def get_email_stats(self) -> Dict[str, int]:
        """Get email service statistics"""
        return {
            'emails_sent': self._emails_sent,
            'emails_failed': self._emails_failed,
            'success_rate': round(
                (self._emails_sent / max(self._emails_sent + self._emails_failed, 1)) * 100, 2
            )
        }
    
    def test_connection(self) -> bool:
        """Test SMTP connection"""
        if not self.is_configured:
            return False
        
        try:
            with self._create_smtp_connection():
                logger.info("SMTP connection test successful")
                return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {str(e)}")
            return False

    # Convenience methods for common email types with hardcoded HTML content
    def send_welcome_email(self, user_email: str, user_name: str, login_credentials: Dict[str, str]) -> bool:
        """Send welcome email to new user"""
        subject = f"Welcome to {self.app_name}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>Welcome to {self.app_name}!</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {user_name},</h2>
                <p>Welcome to {self.app_name}! Your account has been created successfully.</p>
                <div style="background-color: #e8f5e8; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3>Your Login Credentials:</h3>
                    <p><strong>Username:</strong> {login_credentials.get('username', user_email)}</p>
                    <p><strong>Password:</strong> {login_credentials.get('password', 'Contact admin for password')}</p>
                    <p style="color: #d32f2f; font-size: 14px;"><strong>Important:</strong> Please change your password after first login for security.</p>
                </div>
                <p><strong>Login URL:</strong> <a href="{settings.FRONTEND_URL}">{settings.FRONTEND_URL}</a></p>
                <p>If you have any questions or need assistance, please don't hesitate to contact us.</p>
                <p>Best regards,<br>The {self.app_name} Team</p>
            </div>
            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                <p>Need help? Contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=user_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_tenant_created_email(self, admin_email: str, tenant_data: Dict[str, Any]) -> bool:
        """Send notification when new tenant is created"""
        subject = f"Tenant Created Successfully - {tenant_data.get('name')}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #2196F3; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>🎉 Tenant Created Successfully!</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {tenant_data.get('admin_name')},</h2>
                <p>Congratulations! Your tenant organization has been successfully created in {self.app_name}.</p>
                <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3>Tenant Details:</h3>
                    <p><strong>Organization Name:</strong> {tenant_data.get('name')}</p>
                    <p><strong>Tenant ID:</strong> {tenant_data.get('tenant_id')}</p>
                    <p><strong>Administrator:</strong> {tenant_data.get('admin_name')}</p>
                </div>
                <p>As a tenant administrator, you now have access to:</p>
                <ul>
                    <li>Employee management</li>
                    <li>Team and shift management</li>
                    <li>Booking and route management</li>
                    <li>Fleet and driver oversight</li>
                    <li>Reports and analytics</li>
                </ul>
                <p><strong>Login URL:</strong> <a href="{settings.FRONTEND_URL}">{settings.FRONTEND_URL}</a></p>
                <p><strong>Next Steps:</strong></p>
                <ol>
                    <li>Log in to your admin dashboard</li>
                    <li>Complete your organization profile</li>
                    <li>Add your team members</li>
                    <li>Configure your fleet settings</li>
                </ol>
                <p>If you need any assistance getting started, our support team is here to help.</p>
                <p>Welcome aboard!<br>The {self.app_name} Team</p>
            </div>
            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                <p>Need help? Contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=admin_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_booking_confirmation_email(self, user_email: str, booking_data: Dict[str, Any]) -> bool:
        """Send booking confirmation email"""
        subject = f"Booking Confirmed - {booking_data.get('booking_id')}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>✅ Booking Confirmed!</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {booking_data.get('employee_name')},</h2>
                <p>Your transportation booking has been confirmed. Here are your booking details:</p>
                <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #ddd;">
                        <span style="font-weight: bold; color: #555;">Booking ID:</span>
                        <span style="color: #333;"><strong>{booking_data.get('booking_id')}</strong></span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #ddd;">
                        <span style="font-weight: bold; color: #555;">Date:</span>
                        <span style="color: #333;">{booking_data.get('pickup_date')}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #ddd;">
                        <span style="font-weight: bold; color: #555;">Pickup Time:</span>
                        <span style="color: #333;">{booking_data.get('pickup_time')}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #ddd;">
                        <span style="font-weight: bold; color: #555;">Pickup Location:</span>
                        <span style="color: #333;">{booking_data.get('pickup_location')}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #ddd;">
                        <span style="font-weight: bold; color: #555;">Drop Location:</span>
                        <span style="color: #333;">{booking_data.get('drop_location')}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0;">
                        <span style="font-weight: bold; color: #555;">Status:</span>
                        <span style="background-color: #4CAF50; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px;">Confirmed</span>
                    </div>
                </div>
                <p><strong>Important Notes:</strong></p>
                <ul>
                    <li>Please be at the pickup location 5 minutes before scheduled time</li>
                    <li>Keep your booking ID handy for reference</li>
                    <li>You will receive another notification when your driver is assigned</li>
                    <li>Contact support if you need to make any changes</li>
                </ul>
                <p>Thank you for using {self.app_name}!</p>
                <p>Safe travels,<br>The {self.app_name} Team</p>
            </div>
            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                <p>Need help? Contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=user_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_booking_status_update_email(self, user_email: str, booking_data: Dict[str, Any], old_status: str) -> bool:
        """Send booking status update email"""
        subject = f"Booking Status Updated - {booking_data.get('booking_id')}"
        
        status_colors = {
            'confirmed': '#4CAF50',
            'ongoing': '#2196F3',
            'completed': '#4CAF50',
            'canceled': '#f44336'
        }
        
        new_status = booking_data.get('status', '').lower()
        status_color = status_colors.get(new_status, '#6c757d')
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #FF9800; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>📢 Booking Status Update</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {booking_data.get('employee_name')},</h2>
                <p>There's an update on your transportation booking:</p>
                <div style="background-color: #fff3e0; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #FF9800;">
                    <h3>Status Changed</h3>
                    <p>Your booking <strong>{booking_data.get('booking_id')}</strong> status has been updated:</p>
                    <p>
                        <span style="background-color: #6c757d; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">{old_status}</span>
                        →
                        <span style="background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">{booking_data.get('status')}</span>
                    </p>
                </div>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h4>Booking Details:</h4>
                    <p><strong>Booking ID:</strong> {booking_data.get('booking_id')}</p>
                    <p><strong>Date:</strong> {booking_data.get('pickup_date')}</p>
                    <p><strong>Time:</strong> {booking_data.get('pickup_time')}</p>
                </div>
                <p>If you have any questions about this update, please don't hesitate to reach out to our support team.</p>
                <p>Best regards,<br>The {self.app_name} Team</p>
            </div>
            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                <p>Need help? Contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=user_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_password_reset_email(self, user_email: str, reset_token: str, user_name: str) -> bool:
        """Send password reset email"""
        subject = f"Password Reset Request - {self.app_name}"
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f44336; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>🔐 Password Reset Request</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {user_name},</h2>
                <p>We received a request to reset your password for your {self.app_name} account.</p>
                <div style="background-color: #ffebee; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #f44336;">
                    <h3>Reset Your Password</h3>
                    <p>Click the button below to create a new password:</p>
                    <p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: #f44336; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0;">Reset Password</a></p>
                    <p><strong>This link will expire in 24 hours.</strong></p>
                </div>
                <p>If the button doesn't work, you can also copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 3px;">{reset_url}</p>
                <div style="background-color: #fff3e0; padding: 15px; border-radius: 5px; margin: 20px 0; font-size: 14px;">
                    <h4>🛡️ Security Note:</h4>
                    <ul>
                        <li>If you didn't request this password reset, please ignore this email</li>
                        <li>Never share your password with anyone</li>
                        <li>Choose a strong, unique password</li>
                    </ul>
                </div>
                <p>If you continue to have trouble or didn't request this reset, please contact our support team immediately.</p>
                <p>Best regards,<br>The {self.app_name} Team</p>
            </div>
            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                <p>Need help? Contact us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=user_email,
            subject=subject,
            html_content=html_content
        )
    def send_employee_created_email(self, user_email: str, user_name: str, details: Dict[str, Any]) -> bool:
        """Send email when a new employee is created"""
        subject = f"Employee Account Created - {self.app_name}"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1>🎉 Your Employee Account is Ready!</h1>
            </div>

            <div style="background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                <h2>Hello {user_name},</h2>
                <p>Your employee account has been created successfully in <strong>{self.app_name}</strong>.</p>

                <div style="background-color: #e8f5e8; padding: 18px; border-radius: 5px; margin: 20px 0;">
                    <h3>Employee Details:</h3>
                    <p><strong>Employee ID:</strong> {details.get('employee_id')}</p>
                    <p><strong>Name:</strong> {details.get('name')}</p>
                    <p><strong>Email:</strong> {details.get('email')}</p>
                    <p><strong>Phone:</strong> {details.get('phone')}</p>
                    <p><strong>Tenant ID:</strong> {details.get('tenant_id')}</p>
                    <p><strong>Team:</strong> {details.get('team_id')}</p>
                </div>

                <p><strong>What’s Next?</strong></p>
                <ul>
                    <li>Log in using your registered email</li>
                    <li>Contact admin if you need your temporary password</li>
                    <li>Update your personal profile after login</li>
                </ul>

                <p>For any support, email us at <a href="mailto:{self.support_email}">{self.support_email}</a></p>

                <p>Welcome aboard!<br>The {self.app_name} Team</p>
            </div>

            <div style="text-align: center; color: #666; font-size: 12px; margin-top: 20px;">
                <p>&copy; 2024 {self.app_name}. All rights reserved.</p>
            </div>
        </div>
        """

        return self.send_email(
            to_emails=user_email,
            subject=subject,
            html_content=html_content
        )

# Singleton instance
email_service = EmailService()

# Convenience function for easy import
def get_email_service() -> EmailService:
    """Get the email service instance"""
    return email_service
