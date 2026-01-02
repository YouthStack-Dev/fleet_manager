# SOS Alert System - Employee Transport Safety

## Overview
The SOS Alert System provides employees with a panic button feature during their transport journey. When triggered, it immediately notifies configured recipients through multiple channels (Email, SMS, Push notifications) and tracks the complete resolution workflow.

## Features
- **Instant Alert Triggering**: Employees can trigger SOS with location, notes, and evidence (photos/videos)
- **Multi-Channel Notifications**: Email, SMS, Push, WhatsApp, Voice calls
- **Configurable Routing**: Tenant and team-level alert routing rules
- **Auto-Escalation**: Automatic escalation to higher authorities if not acknowledged
- **Real-time Tracking**: Complete timeline of alert events
- **Response Metrics**: Track response times, resolution times, false alarm rates
- **Evidence Management**: Support for photo/video evidence uploads

## Architecture

### Database Schema
```
┌─────────────────────────────────────────────────────────────┐
│                          alerts                              │
├──────────────────────────────────────────────────────────────┤
│ - alert_id (PK)                                              │
│ - tenant_id, employee_id, booking_id                        │
│ - alert_type, severity, status                              │
│ - trigger_latitude, trigger_longitude, trigger_notes        │
│ - evidence_urls (JSON)                                       │
│ - triggered_at, acknowledged_at, closed_at                  │
│ - response_time_seconds, resolution_time_seconds            │
│ - is_false_alarm, auto_escalated                            │
└──────────────────────────────────────────────────────────────┘
                        │
                        ├─────────────────────────┐
                        │                         │
        ┌───────────────▼──────────────┐  ┌──────▼─────────────────────┐
        │   alert_escalations          │  │   alert_notifications      │
        ├──────────────────────────────┤  ├────────────────────────────┤
        │ - escalation_id (PK)         │  │ - notification_id (PK)     │
        │ - alert_id (FK)              │  │ - alert_id (FK)            │
        │ - escalation_level           │  │ - recipient_name/email     │
        │ - escalated_to_recipients    │  │ - channel (EMAIL/SMS/PUSH) │
        │ - is_automatic               │  │ - status, sent_at          │
        └──────────────────────────────┘  └────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│               alert_configurations                           │
├──────────────────────────────────────────────────────────────┤
│ - config_id (PK)                                             │
│ - tenant_id, team_id (optional)                             │
│ - primary_recipients (JSON)                                  │
│ - escalation_recipients (JSON)                              │
│ - auto_escalate_after_seconds                               │
│ - notification_channels (ARRAY)                              │
│ - emergency_contacts (JSON)                                  │
└──────────────────────────────────────────────────────────────┘
```

### Alert Lifecycle
```
TRIGGERED → ACKNOWLEDGED → IN_PROGRESS → CLOSED/FALSE_ALARM
     ↓
  [Auto-Escalation Timer]
     ↓
  ESCALATED (Level 1, 2, 3...)
```

### Notification Channels
- **EMAIL**: Immediate email to configured recipients
- **SMS**: Text message for critical alerts
- **PUSH**: Firebase push notifications to mobile app
- **WHATSAPP**: WhatsApp Business API messages
- **VOICE**: Automated voice calls for highest priority

## API Endpoints

### Employee Endpoints

#### Trigger Alert
```http
POST /api/v1/alerts/trigger
Authorization: Bearer <employee_token>

Request:
{
  "booking_id": 123,
  "alert_type": "EMERGENCY",
  "severity": "CRITICAL",
  "trigger_latitude": 12.9716,
  "trigger_longitude": 77.5946,
  "trigger_notes": "Feeling unsafe, driver not following route",
  "evidence_urls": ["https://storage/photo1.jpg"]
}

Response:
{
  "success": true,
  "message": "Alert triggered successfully. Help is on the way.",
  "data": {
    "alert_id": 456,
    "status": "TRIGGERED",
    "triggered_at": "2024-12-30T22:00:00Z",
    "response_expected_within": "300 seconds"
  }
}
```

#### Get Active Alerts
```http
GET /api/v1/alerts/active
Authorization: Bearer <employee_token>

Response:
{
  "success": true,
  "data": [
    {
      "alert_id": 456,
      "status": "ACKNOWLEDGED",
      "acknowledged_by_name": "Security Team",
      "estimated_arrival_minutes": 10
    }
  ]
}
```

#### Get Alert History
```http
GET /api/v1/alerts/my-alerts?limit=20&offset=0
Authorization: Bearer <employee_token>

Response:
{
  "success": true,
  "data": {
    "alerts": [...],
    "total": 5,
    "has_more": false
  }
}
```

### Responder Endpoints

#### Acknowledge Alert
```http
PUT /api/v1/alerts/{alert_id}/acknowledge
Authorization: Bearer <responder_token>

Request:
{
  "acknowledgment_notes": "En route, ETA 10 minutes",
  "estimated_arrival_minutes": 10
}

Response:
{
  "success": true,
  "message": "Alert acknowledged. Response time: 45s",
  "data": {
    "alert_id": 456,
    "status": "ACKNOWLEDGED",
    "response_time_seconds": 45
  }
}
```

#### Close Alert
```http
PUT /api/v1/alerts/{alert_id}/close
Authorization: Bearer <responder_token>

Request:
{
  "resolution_notes": "Employee safely reached destination. Issue was traffic delay causing anxiety.",
  "is_false_alarm": false
}

Response:
{
  "success": true,
  "message": "Alert closed. Total resolution time: 1200s",
  "data": {
    "alert_id": 456,
    "status": "CLOSED",
    "resolution_time_seconds": 1200
  }
}
```

#### Manual Escalation
```http
POST /api/v1/alerts/{alert_id}/escalate
Authorization: Bearer <admin_token>

Request:
{
  "escalation_level": 2,
  "escalation_reason": "Situation requires senior management attention",
  "escalated_to_recipients": [
    {"name": "VP Operations", "email": "vp@company.com", "phone": "+919999999999"}
  ]
}
```

#### Get Alert Timeline
```http
GET /api/v1/alerts/{alert_id}/timeline
Authorization: Bearer <employee_or_responder_token>

Response:
{
  "success": true,
  "data": {
    "alert_id": 456,
    "current_status": "CLOSED",
    "events": [
      {
        "timestamp": "2024-12-30T22:00:00Z",
        "event_type": "TRIGGERED",
        "description": "Alert triggered by employee 789",
        "details": {...}
      },
      {
        "timestamp": "2024-12-30T22:00:45Z",
        "event_type": "ACKNOWLEDGED",
        "description": "Alert acknowledged by Security Team",
        "details": {...}
      },
      {
        "timestamp": "2024-12-30T22:20:00Z",
        "event_type": "CLOSED",
        "description": "Alert closed by Security Team",
        "details": {...}
      }
    ]
  }
}
```

### Admin Configuration Endpoints

#### Create Alert Configuration
```http
POST /api/v1/alert-config
Authorization: Bearer <admin_token>

Request:
{
  "team_id": null,  // null = tenant-level, specify ID for team-level
  "primary_recipients": [
    {
      "name": "Security Desk",
      "email": "security@company.com",
      "phone": "+919876543210",
      "role": "SECURITY",
      "channels": ["EMAIL", "SMS", "PUSH"]
    }
  ],
  "escalation_recipients": [
    {
      "name": "Transport Manager",
      "email": "transport@company.com",
      "phone": "+919876543211",
      "role": "TRANSPORT_MANAGER",
      "channels": ["EMAIL", "VOICE"]
    }
  ],
  "auto_escalate_after_seconds": 300,
  "notification_channels": ["EMAIL", "SMS", "PUSH"],
  "emergency_contacts": [
    {
      "name": "Police Emergency",
      "phone": "100",
      "relationship": "EMERGENCY_SERVICE"
    }
  ]
}
```

#### Update Alert Configuration
```http
PUT /api/v1/alert-config/{config_id}
Authorization: Bearer <admin_token>

Request:
{
  "auto_escalate_after_seconds": 180,  // Reduce escalation time to 3 minutes
  "notify_on_status_change": true
}
```

#### Test Notification Configuration
```http
POST /api/v1/alert-config/{config_id}/test-notification
Authorization: Bearer <admin_token>

Response:
{
  "success": true,
  "message": "Test notifications sent successfully to 3 recipient(s)",
  "data": {
    "notifications_sent": 3,
    "recipients": ["Security Desk", "Transport Manager", "VP Operations"]
  }
}
```

## Configuration Guide

### 1. Tenant-Level Configuration (Default)
```python
# Set up default alert routing for entire organization
{
  "team_id": null,
  "primary_recipients": [
    {"name": "Security Control Room", "email": "security@company.com", "channels": ["EMAIL", "SMS"]}
  ],
  "auto_escalate_after_seconds": 300
}
```

### 2. Team-Level Configuration (Override)
```python
# Set up specific routing for night shift team
{
  "team_id": 5,  # Night shift team
  "primary_recipients": [
    {"name": "Night Security", "email": "night-security@company.com", "channels": ["SMS", "VOICE"]}
  ],
  "auto_escalate_after_seconds": 120  # Faster escalation at night
}
```

### 3. Escalation Rules
```python
# Level 1: Primary recipients (auto-triggered on alert)
# Level 2: Escalation recipients (after auto_escalate_after_seconds)
# Level 3+: Manual escalation by responders
```

## Notification Templates

### Email Template
```html
Subject: 🚨 ALERT TRIGGERED - #456 - EMERGENCY

Alert #456 has been triggered.

Type: EMERGENCY
Severity: CRITICAL
Employee ID: 789
Booking ID: 123
Triggered At: 2024-12-30 22:00:00
Location: 12.9716, 77.5946

Notes: Feeling unsafe, driver not following route

Please respond immediately.
```

### SMS Template
```
🚨 ALERT #456
Employee 789 triggered EMERGENCY alert
Location: 12.9716, 77.5946
Respond immediately: https://app.com/alerts/456
```

## Integration Points

### 1. Email Service
Uses existing `app/core/email_service.py`:
```python
from app.core.email_service import EmailService

email_service = EmailService()
email_service.send_email(
    to_emails=["security@company.com"],
    subject="Alert Triggered",
    html_body=html_template
)
```

### 2. SMS Provider (To Implement)
```python
# Using Twilio
from twilio.rest import Client

client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
message = client.messages.create(
    body="Alert triggered",
    from_=settings.TWILIO_PHONE_NUMBER,
    to=recipient_phone
)
```

### 3. Firebase Push Notifications (To Implement)
```python
# Using Firebase Cloud Messaging
from firebase_admin import messaging

message = messaging.Message(
    notification=messaging.Notification(
        title="Alert Triggered",
        body="Employee needs assistance"
    ),
    data={"alert_id": "456"},
    token=user_fcm_token
)
messaging.send(message)
```

## Background Workers

### Auto-Escalation Worker
```python
# Runs every 60 seconds to check for alerts needing escalation
# TODO: Implement using Celery or APScheduler

from apscheduler.schedulers.background import BackgroundScheduler

def check_escalations():
    alerts = get_alerts_needing_escalation()
    for alert in alerts:
        escalate_alert(alert)

scheduler = BackgroundScheduler()
scheduler.add_job(check_escalations, 'interval', seconds=60)
scheduler.start()
```

## Metrics & Analytics

### Dashboard Metrics
- Total alerts (today, this week, this month)
- Active alerts (real-time)
- Average response time
- Average resolution time
- False alarm rate
- Escalation rate
- Alerts by severity
- Alerts by type
- Top 10 employees with most alerts

### Query Example
```sql
-- Get response time analytics
SELECT 
    DATE(triggered_at) as date,
    AVG(response_time_seconds) as avg_response_time,
    COUNT(*) as total_alerts
FROM alerts
WHERE tenant_id = 'vendor_1'
  AND triggered_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(triggered_at)
ORDER BY date DESC;
```

## Testing

### Unit Tests
```python
# tests/test_alert_system.py

def test_trigger_alert_success(client, auth_headers):
    response = client.post(
        "/api/v1/alerts/trigger",
        json={
            "trigger_latitude": 12.9716,
            "trigger_longitude": 77.5946,
            "trigger_notes": "Test alert"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    assert "alert_id" in response.json()["data"]

def test_trigger_duplicate_alert_fails(client, auth_headers):
    # Trigger first alert
    client.post("/api/v1/alerts/trigger", json={...}, headers=auth_headers)
    
    # Try to trigger second alert (should fail)
    response = client.post("/api/v1/alerts/trigger", json={...}, headers=auth_headers)
    assert response.status_code == 400
    assert "active alert" in response.json()["detail"]
```

### Load Testing
```bash
# Test alert triggering under load
ab -n 1000 -c 10 -H "Authorization: Bearer token" \
   -p alert_payload.json \
   http://localhost:8000/api/v1/alerts/trigger
```

## Security Considerations

1. **Authentication**: All endpoints require valid JWT token
2. **Authorization**: 
   - Employees can only trigger and view their own alerts
   - Responders can acknowledge/close any alert
   - Admins can escalate and configure routing
3. **Rate Limiting**: Prevent alert spam (TODO: implement)
4. **Location Validation**: Verify location is within reasonable range
5. **Evidence Upload**: Sanitize and scan uploaded files (TODO: implement)

## Migration Guide

### Step 1: Run Database Migration
```bash
cd c:\projects\fleet_manager\fleet_manager
alembic upgrade head
```

### Step 2: Update down_revision
Edit `migrations/versions/20251230_220942_alert_system.py`:
```python
# Set to your current latest migration ID
down_revision = 'your_latest_migration_id'
```

### Step 3: Seed Initial Configuration
```python
# Create default configuration for tenant
POST /api/v1/alert-config
{
  "primary_recipients": [
    {"name": "Admin", "email": "admin@company.com", "channels": ["EMAIL"]}
  ],
  "auto_escalate_after_seconds": 300
}
```

### Step 4: Test End-to-End
1. Trigger alert as employee
2. Check notification received
3. Acknowledge as responder
4. Close alert
5. Verify timeline

## Troubleshooting

### Issue: Notifications not sending
**Solution**: Check notification service logs, verify SMTP/SMS credentials

### Issue: Auto-escalation not working
**Solution**: Ensure background worker is running, check escalation threshold

### Issue: Alert trigger fails with 400
**Solution**: Check for existing active alert, verify booking exists

## Future Enhancements

1. **Real-time Updates**: WebSocket integration for live alert updates
2. **Geofencing**: Auto-trigger alerts if vehicle deviates from route
3. **Voice Recognition**: Voice-activated SOS trigger
4. **ML-based False Alarm Detection**: Reduce false positives
5. **Integration with External Services**: Police, ambulance, fire department
6. **Mobile App**: Native Android/iOS app with one-tap SOS

## Support

For issues or questions, contact:
- **Technical Support**: tech@company.com
- **Emergency**: +919999999999
- **Documentation**: https://docs.company.com/alerts

## License

Internal use only - Company confidential
