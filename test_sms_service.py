"""
Test script for SMS service
"""
from app.services.sms_service import SMSService

# Initialize SMS service
sms_service = SMSService()

# Test phone number - replace with your actual test number
test_phone = "+916363925996"  # Replace with your phone number

# Test message
test_message = """
Test SMS from Fleet Manager!

Driver Assignment Notification:
- Route: TEST-001
- Driver: John Doe
- Vehicle: KA01AB1234
- OTP: 1234

This is a test message.
"""

print(f"SMS Service Enabled: {sms_service.enabled}")
print(f"Twilio Phone Number: {sms_service.phone_number}")
print(f"\nAttempting to send test SMS to: {test_phone}")

# Uncomment the line below to actually send the SMS
result = sms_service.send_sms(test_phone, test_message)
print(f"SMS Send Result: {result}")

print("\n✅ SMS Service is configured and ready!")
print("To send a test SMS, uncomment the 'result = sms_service.send_sms()' line")
print("and replace test_phone with your actual phone number.")
