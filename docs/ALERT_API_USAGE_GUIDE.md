# Alert System API - Complete Usage Guide

## Table of Contents
1. [Overview](#overview)
2. [Alert Configuration Endpoints](#alert-configuration-endpoints)
3. [Alert Management Endpoints](#alert-management-endpoints)
4. [Complete Workflows](#complete-workflows)
5. [Real-World Scenarios](#real-world-scenarios)

---

## Overview

The Alert System provides two main router groups:
- **Alert Router** (`/api/v1/alerts`) - Employee and responder endpoints
- **Alert Configuration Router** (`/api/v1/alert-config`) - Admin configuration endpoints

### Authentication
All endpoints require authentication. Include your JWT token in the header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Alert Configuration Endpoints

### 1. Create Alert Configuration

**Endpoint:** `POST /api/v1/alert-config`

**Purpose:** Configure how alerts are routed and escalated for your organization or team.

**Who can use:** Admins and Transport Managers only

**Important Notes:**
- **Admin users:** Must include `tenant_id` in the request body
- **Employee users:** `tenant_id` is automatically extracted from the authentication token (don't include it in the request)
- Each tenant can have one configuration per team (or one tenant-wide configuration if `team_id` is null)

**Request Body:**
```json
{
  "tenant_id": "vendor_1",
  "team_id": null,
  "config_name": "Emergency Response Team",
  "description": "Main emergency response configuration",
  "applicable_alert_types": ["SOS", "MEDICAL", "ACCIDENT"],
  "primary_recipients": [
    {
      "name": "Security Manager",
      "email": "security@company.com",
      "phone": "+911234567890",
      "role": "Security",
      "channels": ["EMAIL", "SMS", "PUSH"]
    },
    {
      "name": "Transport Manager",
      "email": "transport@company.com",
      "phone": "+911234567891",
      "role": "Manager",
      "channels": ["EMAIL", "SMS"]
    }
  ],
  "enable_escalation": true,
  "escalation_threshold_seconds": 300,
  "escalation_recipients": [
    {
      "name": "Operations Director",
      "email": "ops-director@company.com",
      "phone": "+911234567892",
      "role": "Director",
      "channels": ["EMAIL", "SMS", "VOICE"]
    }
  ],
  "notification_channels": ["EMAIL", "SMS", "PUSH"],
  "notify_on_status_change": true,
  "notify_on_escalation": true,
  "auto_close_false_alarm_seconds": 120,
  "require_closure_notes": true,
  "enable_geofencing_alerts": true,
  "geofence_radius_meters": 1000,
  "emergency_contacts": [
    {
      "name": "Police",
      "phone": "100",
      "service_type": "POLICE"
    },
    {
      "name": "Ambulance",
      "phone": "108",
      "service_type": "MEDICAL"
    }
  ],
  "priority": 100
}
```

**Response:**
```json
{
  "success": true,
  "message": "Alert configuration created successfully",
  "data": {
    "config_id": 1,
    "tenant_id": "tenant_123",
    "team_id": null,
    "config_name": "Emergency Response Team",
    "is_active": true,
    "created_at": "2025-12-30T10:00:00",
    ...
  }
}
```

**Use Case:** 
First-time setup for a company. The admin configures who receives alerts and how quickly they escalate if not acknowledged.

---

### 2. Get Alert Configurations

**Endpoint:** `GET /api/v1/alert-config?team_id={team_id}`

**Purpose:** View existing alert configurations.

**Query Parameters:**
- `team_id` (optional): Filter by specific team

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/alert-config" \
  -H "Authorization: Bearer your_token"
```

**Response:**
```json
{
  "success": true,
  "message": "Retrieved 2 configuration(s)",
  "data": [
    {
      "config_id": 1,
      "config_name": "Emergency Response Team",
      "team_id": null,
      "is_active": true,
      ...
    },
    {
      "config_id": 2,
      "config_name": "Night Shift Team",
      "team_id": 5,
      "is_active": true,
      ...
    }
  ]
}
```

---

### 3. Get Specific Configuration

**Endpoint:** `GET /api/v1/alert-config/{config_id}`

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/alert-config/1" \
  -H "Authorization: Bearer your_token"
```

---

### 4. Update Alert Configuration

**Endpoint:** `PUT /api/v1/alert-config/{config_id}`

**Purpose:** Modify existing configuration (e.g., add new recipients, change escalation time).

**Request Body (only include fields to update):**
```json
{
  "escalation_threshold_seconds": 180,
  "primary_recipients": [
    {
      "name": "New Security Manager",
      "email": "newsecurity@company.com",
      "phone": "+911234567893",
      "role": "Security",
      "channels": ["EMAIL", "SMS", "PUSH", "WHATSAPP"]
    }
  ]
}
```

**Use Case:** 
A new security manager joins the company. Update the configuration to route alerts to them instead.

---

### 5. Delete Configuration

**Endpoint:** `DELETE /api/v1/alert-config/{config_id}`

**Purpose:** Remove a configuration (Admin only).

---

### 6. Test Configuration

**Endpoint:** `POST /api/v1/alert-config/{config_id}/test-notification`

**Purpose:** Send test notifications to verify configuration is working.

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/alert-config/1/test-notification" \
  -H "Authorization: Bearer your_token"
```

**Response:**
```json
{
  "success": true,
  "message": "Test notifications sent successfully to 3 recipient(s)",
  "data": {
    "notifications_sent": 3,
    "recipients": ["Security Manager", "Transport Manager", "Operations Director"]
  }
}
```

**Use Case:**
After creating a new configuration, test it to ensure everyone receives the notifications.

---

### 7. Get Applicable Configuration

**Endpoint:** `GET /api/v1/alert-config/applicable/current`

**Purpose:** Get the configuration that applies to the current user (team-specific or tenant-wide).

**Response:**
```json
{
  "success": true,
  "message": "Configuration retrieved",
  "data": {
    "config_id": 1,
    "config_name": "Emergency Response Team",
    "primary_recipients": [...],
    "enable_escalation": true,
    ...
  }
}
```

---

## Alert Management Endpoints

### 1. Trigger SOS Alert

**Endpoint:** `POST /api/v1/alerts/trigger`

**Purpose:** Employee triggers an emergency alert (panic button).

**Who can use:** Employees only

**Request Body:**
```json
{
  "booking_id": 12345,
  "alert_type": "SOS",
  "severity": "CRITICAL",
  "current_latitude": 12.9716,
  "current_longitude": 77.5946,
  "trigger_notes": "Feeling unsafe, suspicious vehicle following",
  "evidence_urls": [
    "https://storage.example.com/uploads/photo1.jpg"
  ]
}
```

**Alert Types:**
- `SOS` - Emergency panic button
- `SAFETY_CONCERN` - Safety issue
- `MEDICAL` - Medical emergency
- `ACCIDENT` - Vehicle accident
- `ROUTE_DEVIATION` - Vehicle off route
- `DELAYED` - Significant delay
- `OTHER` - Other issues

**Severity Levels:**
- `CRITICAL` - Immediate danger
- `HIGH` - Serious concern
- `MEDIUM` - Moderate issue
- `LOW` - Minor concern

**Response:**
```json
{
  "success": true,
  "message": "Alert triggered successfully. Help is on the way!",
  "data": {
    "alert_id": 101,
    "status": "TRIGGERED",
    "triggered_at": "2025-12-30T18:45:00",
    "notification_sent_to": [
      "security@company.com",
      "transport@company.com"
    ]
  }
}
```

**Use Case:**
An employee feels unsafe during their commute. They press the SOS button in the mobile app, which calls this endpoint with their current location.

---

### 2. Get Active Alerts

**Endpoint:** `GET /api/v1/alerts/active`

**Purpose:** View all currently active (unresolved) alerts.

**Who can use:** Employees can see their own, Admins see all

**Response:**
```json
{
  "success": true,
  "message": "Retrieved 2 active alert(s)",
  "data": [
    {
      "alert_id": 101,
      "employee_id": 456,
      "alert_type": "SOS",
      "severity": "CRITICAL",
      "status": "TRIGGERED",
      "triggered_at": "2025-12-30T18:45:00",
      "trigger_latitude": 12.9716,
      "trigger_longitude": 77.5946,
      "response_time_seconds": null
    }
  ]
}
```

**Use Case:**
Security team dashboard showing all active emergencies that need response.

---

### 3. Get My Alerts

**Endpoint:** `GET /api/v1/alerts/my-alerts?status={status}&from_date={date}&limit=50`

**Purpose:** Employee views their alert history.

**Query Parameters:**
- `status` (optional): Filter by status (TRIGGERED, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, CLOSED, FALSE_ALARM)
- `from_date` (optional): Filter from date (ISO format)
- `to_date` (optional): Filter to date
- `limit` (optional): Number of results (default 50)
- `offset` (optional): Pagination offset

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/alerts/my-alerts?status=CLOSED&limit=10" \
  -H "Authorization: Bearer employee_token"
```

---

### 4. Get Alert Details

**Endpoint:** `GET /api/v1/alerts/{alert_id}`

**Purpose:** View complete details of a specific alert.

**Response:**
```json
{
  "success": true,
  "message": "Alert retrieved",
  "data": {
    "alert_id": 101,
    "tenant_id": "tenant_123",
    "employee_id": 456,
    "booking_id": 12345,
    "alert_type": "SOS",
    "severity": "CRITICAL",
    "status": "ACKNOWLEDGED",
    "trigger_latitude": 12.9716,
    "trigger_longitude": 77.5946,
    "trigger_address": "MG Road, Bangalore",
    "triggered_at": "2025-12-30T18:45:00",
    "acknowledged_at": "2025-12-30T18:46:30",
    "acknowledged_by": "Security Manager",
    "response_time_seconds": 90,
    "trigger_notes": "Feeling unsafe, suspicious vehicle following",
    "evidence_urls": ["https://storage.example.com/uploads/photo1.jpg"],
    "escalations": [
      {
        "escalation_id": 1,
        "escalation_level": 1,
        "escalated_to": "ops-director@company.com",
        "escalated_at": "2025-12-30T18:50:00",
        "is_auto_escalation": true
      }
    ],
    "notifications": [
      {
        "notification_id": 1,
        "recipient_name": "Security Manager",
        "channel": "SMS",
        "status": "DELIVERED",
        "sent_at": "2025-12-30T18:45:05"
      }
    ]
  }
}
```

---

### 5. Acknowledge Alert

**Endpoint:** `PUT /api/v1/alerts/{alert_id}/acknowledge`

**Purpose:** Responder acknowledges they've seen the alert and are responding.

**Who can use:** Security/Transport managers and Admins

**Request Body:**
```json
{
  "acknowledged_by": "John Smith - Security",
  "notes": "On my way, ETA 10 minutes",
  "estimated_arrival_minutes": 10
}
```

**Response:**
```json
{
  "success": true,
  "message": "Alert acknowledged successfully",
  "data": {
    "alert_id": 101,
    "status": "ACKNOWLEDGED",
    "acknowledged_at": "2025-12-30T18:46:30",
    "acknowledged_by": "John Smith - Security",
    "response_time_seconds": 90
  }
}
```

**Use Case:**
Security manager receives SMS alert, opens the admin dashboard, and clicks "Acknowledge" to let the system (and employee) know help is coming.

---

### 6. Update Alert Status

**Endpoint:** `PUT /api/v1/alerts/{alert_id}/status`

**Purpose:** Update alert to IN_PROGRESS or RESOLVED status.

**Request Body:**
```json
{
  "status": "IN_PROGRESS",
  "notes": "Reached location, employee safe, investigating the situation"
}
```

**Allowed Status Transitions:**
- TRIGGERED → ACKNOWLEDGED
- ACKNOWLEDGED → IN_PROGRESS
- IN_PROGRESS → RESOLVED

**Use Case:**
Security personnel arrives at the location and updates status to "In Progress" while ensuring employee's safety.

---

### 7. Close Alert

**Endpoint:** `PUT /api/v1/alerts/{alert_id}/close`

**Purpose:** Officially close an alert with resolution notes.

**Request Body:**
```json
{
  "closed_by": "John Smith - Security",
  "closure_notes": "Employee was feeling unsafe due to a suspicious vehicle. We verified the vehicle belonged to a local resident. Escorted employee home safely. No further action needed.",
  "is_false_alarm": false,
  "resolution_notes": "Provided escort service, ensured safe arrival"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Alert closed successfully",
  "data": {
    "alert_id": 101,
    "status": "CLOSED",
    "closed_at": "2025-12-30T19:15:00",
    "total_duration_minutes": 30,
    "resolution_time_seconds": 1800
  }
}
```

**Use Case:**
After ensuring the employee is safe and the situation is resolved, the security manager closes the alert with detailed notes for record-keeping.

---

### 8. Manual Escalation

**Endpoint:** `POST /api/v1/alerts/{alert_id}/escalate`

**Purpose:** Manually escalate an alert to higher management.

**Request Body:**
```json
{
  "escalated_by": "Security Manager",
  "escalation_level": 2,
  "escalated_to": "ceo@company.com",
  "reason": "Situation requires senior management intervention - potential criminal activity"
}
```

**Use Case:**
A situation is more serious than initially assessed. Security manager escalates to senior management immediately rather than waiting for auto-escalation.

---

### 9. Get Alert Timeline

**Endpoint:** `GET /api/v1/alerts/{alert_id}/timeline`

**Purpose:** View complete timeline of events for an alert.

**Response:**
```json
{
  "success": true,
  "message": "Alert timeline retrieved",
  "data": {
    "alert": {
      "alert_id": 101,
      "status": "CLOSED",
      ...
    },
    "timeline": [
      {
        "event_time": "2025-12-30T18:45:00",
        "event_type": "TRIGGERED",
        "actor": "Employee #456",
        "notes": "Feeling unsafe, suspicious vehicle following"
      },
      {
        "event_time": "2025-12-30T18:45:05",
        "event_type": "NOTIFICATION_SENT",
        "actor": "System",
        "notes": "SMS sent to Security Manager"
      },
      {
        "event_time": "2025-12-30T18:46:30",
        "event_type": "ACKNOWLEDGED",
        "actor": "John Smith - Security",
        "notes": "On my way, ETA 10 minutes"
      },
      {
        "event_time": "2025-12-30T18:50:00",
        "event_type": "ESCALATED",
        "actor": "System (Auto)",
        "notes": "Auto-escalated after 5 minutes - Level 1"
      },
      {
        "event_time": "2025-12-30T18:55:00",
        "event_type": "STATUS_CHANGED",
        "actor": "John Smith - Security",
        "notes": "Changed to IN_PROGRESS - Reached location"
      },
      {
        "event_time": "2025-12-30T19:10:00",
        "event_type": "RESOLVED",
        "actor": "John Smith - Security",
        "notes": "Employee safe, situation under control"
      },
      {
        "event_time": "2025-12-30T19:15:00",
        "event_type": "CLOSED",
        "actor": "John Smith - Security",
        "notes": "Case closed with detailed resolution notes"
      }
    ]
  }
}
```

---

## Complete Workflows

### Workflow 1: Setting Up Alert System (Admin)

1. **Create Configuration**
```bash
POST /api/v1/alert-config
{
  "config_name": "Main Alert Configuration",
  "primary_recipients": [...],
  "enable_escalation": true,
  "escalation_threshold_seconds": 300
}
```

2. **Test Configuration**
```bash
POST /api/v1/alert-config/1/test-notification
```

3. **Verify Test Notifications Received**
Check email, SMS, etc.

4. **Adjust if Needed**
```bash
PUT /api/v1/alert-config/1
{
  "escalation_threshold_seconds": 180
}
```

---

### Workflow 2: Employee Emergency (Complete Flow)

**Step 1: Employee Triggers Alert (Mobile App)**
```bash
POST /api/v1/alerts/trigger
{
  "booking_id": 12345,
  "alert_type": "SOS",
  "severity": "CRITICAL",
  "current_latitude": 12.9716,
  "current_longitude": 77.5946,
  "trigger_notes": "Feeling unsafe"
}
```

**Step 2: System Actions (Automatic)**
- Creates alert record
- Sends notifications to primary recipients (SMS, Email, Push)
- Starts escalation timer

**Step 3: Security Manager Acknowledges (Dashboard)**
```bash
PUT /api/v1/alerts/101/acknowledge
{
  "acknowledged_by": "Security Manager",
  "notes": "On my way",
  "estimated_arrival_minutes": 15
}
```

**Step 4: Security Manager Arrives**
```bash
PUT /api/v1/alerts/101/status
{
  "status": "IN_PROGRESS",
  "notes": "Reached location, assessing situation"
}
```

**Step 5: Situation Resolved**
```bash
PUT /api/v1/alerts/101/status
{
  "status": "RESOLVED",
  "notes": "Employee is safe"
}
```

**Step 6: Formal Closure**
```bash
PUT /api/v1/alerts/101/close
{
  "closed_by": "Security Manager",
  "closure_notes": "False alarm - employee misidentified security patrol vehicle",
  "is_false_alarm": true
}
```

---

### Workflow 3: Escalation Scenario

**Situation:** Alert not acknowledged within 5 minutes

**Minute 0:** Alert triggered
```bash
POST /api/v1/alerts/trigger
# alert_id: 102, status: TRIGGERED
```

**Minute 5:** Auto-escalation (if configured)
- System automatically escalates to Level 2 recipients
- Sends notifications to escalation recipients
- Creates escalation record

**Minute 6:** Director acknowledges
```bash
PUT /api/v1/alerts/102/acknowledge
{
  "acknowledged_by": "Operations Director",
  "notes": "Taking charge of situation"
}
```

**Check Escalations:**
```bash
GET /api/v1/alerts/102
# Response includes escalations array showing auto-escalation
```

---

## Real-World Scenarios

### Scenario 1: Female Employee Safety Concern

**Context:** A female employee traveling alone at night feels unsafe.

**Actions:**
1. Employee triggers SOS alert from mobile app
2. Security team receives instant notification with location
3. Security manager acknowledges within 30 seconds
4. Security vehicle dispatched to location
5. Manager calls employee to provide reassurance
6. Security reaches location in 8 minutes
7. Escort provided to destination
8. Alert closed with detailed notes

**API Calls:**
```bash
# Employee
POST /api/v1/alerts/trigger
{
  "alert_type": "SAFETY_CONCERN",
  "severity": "HIGH",
  "current_latitude": 12.9716,
  "current_longitude": 77.5946,
  "trigger_notes": "Traveling alone, area seems unsafe"
}

# Security Manager
PUT /api/v1/alerts/103/acknowledge
{
  "acknowledged_by": "Rajesh Kumar - Security",
  "notes": "Vehicle dispatched, ETA 8 minutes. Calling employee now."
}

# Update progress
PUT /api/v1/alerts/103/status
{
  "status": "IN_PROGRESS",
  "notes": "Security vehicle reached location, providing escort"
}

# Close after safe arrival
PUT /api/v1/alerts/103/close
{
  "closed_by": "Rajesh Kumar",
  "closure_notes": "Employee safely escorted home. Area was indeed poorly lit. Recommend adding to high-risk zones list.",
  "is_false_alarm": false
}
```

---

### Scenario 2: Medical Emergency During Commute

**Context:** Employee has a medical emergency (chest pain) in office cab.

**Actions:**
1. Co-passenger or driver triggers MEDICAL alert
2. Ambulance and security both notified
3. Driver diverts to nearest hospital
4. Family contacted
5. Situation tracked until resolved

**API Calls:**
```bash
# Driver triggers alert
POST /api/v1/alerts/trigger
{
  "booking_id": 67890,
  "alert_type": "MEDICAL",
  "severity": "CRITICAL",
  "current_latitude": 12.9352,
  "current_longitude": 77.6245,
  "trigger_notes": "Passenger experiencing chest pain, diverting to hospital"
}

# Medical response team acknowledges
PUT /api/v1/alerts/104/acknowledge
{
  "acknowledged_by": "Medical Response Team",
  "notes": "Ambulance dispatched to location. Coordinating with driver."
}

# Hospital arrival
PUT /api/v1/alerts/104/status
{
  "status": "IN_PROGRESS",
  "notes": "Patient admitted to Apollo Hospital Emergency. Family notified."
}

# After stabilization
PUT /api/v1/alerts/104/close
{
  "closed_by": "HR Manager",
  "closure_notes": "Employee stable, under medical care. Family present. Insurance claim initiated.",
  "is_false_alarm": false,
  "resolution_notes": "Quick response saved valuable time. Driver performed excellently."
}
```

---

### Scenario 3: Accidental Trigger (False Alarm)

**Context:** Employee accidentally presses panic button.

**Actions:**
1. Alert triggered
2. Employee immediately realizes mistake
3. Calls security to cancel
4. Marked as false alarm

**API Calls:**
```bash
# Accidental trigger
POST /api/v1/alerts/trigger
{
  "alert_type": "SOS",
  "severity": "CRITICAL",
  "current_latitude": 12.9716,
  "current_longitude": 77.5946
}

# Security acknowledges and verifies
PUT /api/v1/alerts/105/acknowledge
{
  "acknowledged_by": "Security Control Room",
  "notes": "Employee called back - accidental trigger, employee is safe"
}

# Quick closure as false alarm
PUT /api/v1/alerts/105/close
{
  "closed_by": "Security Control Room",
  "closure_notes": "Confirmed false alarm. Employee accidentally pressed button while phone was in pocket. No action needed. Reminded employee about button placement.",
  "is_false_alarm": true
}
```

---

### Scenario 4: Route Deviation Alert

**Context:** Vehicle goes significantly off planned route.

**API Calls:**
```bash
# System auto-generates alert
POST /api/v1/alerts/trigger
{
  "booking_id": 11111,
  "alert_type": "ROUTE_DEVIATION",
  "severity": "MEDIUM",
  "current_latitude": 12.8500,
  "current_longitude": 77.7000,
  "trigger_notes": "Vehicle 10km off planned route"
}

# Transport manager investigates
PUT /api/v1/alerts/106/acknowledge
{
  "acknowledged_by": "Transport Manager",
  "notes": "Contacting driver to verify reason"
}

# Legitimate reason found
PUT /api/v1/alerts/106/close
{
  "closed_by": "Transport Manager",
  "closure_notes": "Road closure due to construction. Driver took approved alternate route. All employees safe.",
  "is_false_alarm": false
}
```

---

## Best Practices

### For Employees:
1. **Keep GPS enabled** - Accurate location is crucial
2. **Use trigger notes** - Provide context (e.g., "Suspicious vehicle following")
3. **Add evidence** - Take photos/videos if safe to do so
4. **Don't use as joke** - False alarms waste resources and reduce trust

### For Admins:
1. **Test configurations regularly** - Use test endpoint monthly
2. **Keep contact lists updated** - Remove/add personnel promptly
3. **Review escalation times** - Adjust based on your team's response capacity
4. **Train your team** - Ensure everyone knows their role
5. **Analyze patterns** - Review closed alerts to improve safety

### For Responders:
1. **Acknowledge immediately** - Even if you need time to respond
2. **Keep status updated** - Employees and management track progress
3. **Document thoroughly** - Closure notes help with analysis and legal needs
4. **Close alerts promptly** - Don't leave alerts in "RESOLVED" state indefinitely

---

## Notification Channels

### EMAIL
- Detailed alert information
- Includes map link
- Suitable for non-urgent escalations

### SMS
- Instant delivery
- Brief alert details
- Primary channel for emergencies

### PUSH
- Mobile app notifications
- Rich content support
- Real-time updates

### VOICE
- Automated phone calls
- For critical escalations
- Ensures human attention

### WHATSAPP
- Popular in India
- Supports media sharing
- Good for evidence sharing

---

## Error Handling

### Common Errors:

**400 Bad Request**
```json
{
  "detail": "You already have an active alert: #101"
}
```
*Solution:* Close existing alert before triggering new one

**403 Forbidden**
```json
{
  "detail": "Admin access required"
}
```
*Solution:* Only admins can access configuration endpoints

**404 Not Found**
```json
{
  "detail": "Alert not found"
}
```
*Solution:* Verify alert ID and tenant access

**500 Internal Server Error**
*Solution:* Check server logs, contact support

---

## Testing Checklist

Before going live:

- [ ] Create test configuration
- [ ] Send test notifications to all recipients
- [ ] Verify all channels (Email, SMS, Push)
- [ ] Test trigger from mobile app
- [ ] Test acknowledgment flow
- [ ] Test escalation (wait for timeout)
- [ ] Test manual escalation
- [ ] Test closure with notes
- [ ] Test false alarm scenario
- [ ] Review all timestamps and durations
- [ ] Check notification delivery status

---

## Integration Examples

### Mobile App (React Native)
```javascript
// Trigger SOS Alert
const triggerSOS = async (location, notes) => {
  try {
    const response = await fetch('http://api.example.com/api/v1/alerts/trigger', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${userToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        alert_type: 'SOS',
        severity: 'CRITICAL',
        current_latitude: location.latitude,
        current_longitude: location.longitude,
        trigger_notes: notes,
        booking_id: currentBookingId
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      Alert.alert('Help is on the way', 
        `Alert #${result.data.alert_id} triggered. Security team notified.`);
    }
  } catch (error) {
    console.error('Failed to trigger alert:', error);
  }
};
```

### Admin Dashboard (React)
```javascript
// Acknowledge Alert
const acknowledgeAlert = async (alertId) => {
  try {
    const response = await fetch(`http://api.example.com/api/v1/alerts/${alertId}/acknowledge`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${adminToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        acknowledged_by: currentUser.name,
        notes: 'Responding to alert',
        estimated_arrival_minutes: 15
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      toast.success('Alert acknowledged');
      refreshAlertsList();
    }
  } catch (error) {
    toast.error('Failed to acknowledge alert');
  }
};
```

---

## Support

For issues or questions:
- **Technical Support:** support@company.com
- **Emergency Hotline:** +91-1800-XXX-XXXX
- **Documentation:** https://docs.company.com/alerts

---

*Last Updated: December 30, 2025*
