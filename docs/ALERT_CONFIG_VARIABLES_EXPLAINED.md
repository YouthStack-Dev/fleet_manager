# Alert Configuration Variables - Complete Explanation

## Table of Contents
1. [Configuration Structure](#configuration-structure)
2. [Basic Configuration Fields](#basic-configuration-fields)
3. [Alert Type Configuration](#alert-type-configuration)
4. [Recipient Configuration](#recipient-configuration)
5. [Escalation Configuration](#escalation-configuration)
6. [Notification Configuration](#notification-configuration)
7. [Advanced Settings](#advanced-settings)
8. [Emergency Contacts](#emergency-contacts)
9. [Usage Flow Diagram](#usage-flow-diagram)

---

## Configuration Structure

```json
{
  "team_id": null,
  "config_name": "Emergency Response Team",
  "description": "Main emergency response configuration",
  "applicable_alert_types": ["SOS", "MEDICAL", "ACCIDENT"],
  "primary_recipients": [...],
  "enable_escalation": true,
  "escalation_threshold_seconds": 300,
  "escalation_recipients": [...],
  "notification_channels": ["EMAIL", "SMS", "PUSH"],
  "notify_on_status_change": true,
  "notify_on_escalation": true,
  "auto_close_false_alarm_seconds": 120,
  "require_closure_notes": true,
  "enable_geofencing_alerts": true,
  "geofence_radius_meters": 1000,
  "emergency_contacts": [...],
  "priority": 100
}
```

---

## Basic Configuration Fields

### 1. `team_id`
**Type:** `integer | null`  
**Required:** No (can be null)

**Purpose:** Determines the scope of this configuration.

**Usage:**
- `null` = Applies to **entire tenant** (all teams)
- `5` = Applies only to **Team ID 5**

**Where Used:**
- **Database:** `alert_configurations.team_id` column
- **CRUD:** `alert_crud.get_applicable_configuration()` checks team_id to find the right config
- **Router:** When employee triggers alert, system looks for their team's config first, then falls back to tenant-wide

**Example Scenarios:**

**Scenario 1: Company-Wide Configuration**
```json
{
  "team_id": null,
  "config_name": "Company-Wide Emergency Response"
}
```
→ Every employee in the company uses this configuration.

**Scenario 2: Team-Specific Configuration**
```json
{
  "team_id": 7,
  "config_name": "Night Shift Team Alert Config"
}
```
→ Only employees in Team 7 (Night Shift) use this configuration.
→ Night shift might need different responders (night security guards instead of day shift).

**Database Query Logic:**
```sql
-- System searches in this order:
1. SELECT * FROM alert_configurations WHERE tenant_id = 'tenant_123' AND team_id = 7
2. If not found, SELECT * FROM alert_configurations WHERE tenant_id = 'tenant_123' AND team_id IS NULL
```

---

### 2. `config_name`
**Type:** `string`  
**Required:** Yes  
**Max Length:** 200 characters

**Purpose:** Human-readable name for the configuration.

**Usage:**
- **Display:** Shows in admin dashboard when listing configurations
- **Logging:** Used in log messages for tracking which config was applied
- **Audit:** Helps identify configuration changes in audit trails

**Where Used:**
- **Database:** `alert_configurations.config_name` column
- **Admin UI:** Dropdown lists showing "Select Configuration: Emergency Response Team"
- **Logs:** `"Using config 'Emergency Response Team' for alert #101"`

**Best Practices:**
```json
// Good names (descriptive)
"Emergency Response Team"
"Night Shift Safety Configuration"
"Medical Emergency Protocol"
"IT Team Alerts"

// Bad names (not descriptive)
"Config 1"
"Test"
"Default"
```

---

### 3. `description`
**Type:** `string | null`  
**Required:** No  
**Max Length:** 1000 characters

**Purpose:** Detailed explanation of what this configuration is for.

**Usage:**
- **Documentation:** Helps future admins understand the configuration's purpose
- **Admin UI:** Shows tooltip or help text when viewing configuration
- **Onboarding:** New admins can understand existing setups

**Where Used:**
- **Database:** `alert_configurations.description` column
- **Admin Dashboard:** Info icon showing description on hover

**Example:**
```json
{
  "description": "Main emergency response configuration for all employees. Security team and transport managers are notified immediately. Escalates to operations director after 5 minutes if not acknowledged. Used for SOS, Medical, and Accident alerts only."
}
```

---

## Alert Type Configuration

### 4. `applicable_alert_types`
**Type:** `array of strings | null`  
**Required:** No (null means all types)

**Purpose:** Specifies which types of alerts this configuration handles.

**Available Alert Types:**
- `SOS` - Emergency panic button
- `MEDICAL` - Medical emergency
- `ACCIDENT` - Vehicle accident
- `SAFETY_CONCERN` - Safety issue
- `ROUTE_DEVIATION` - Vehicle off route
- `DELAYED` - Significant delay
- `OTHER` - Other issues

**Usage:**
- **Filtering:** System checks if triggered alert type matches this list
- **Multiple Configs:** Allows different handling for different alert types

**Where Used:**
- **CRUD:** `alert_crud.get_applicable_configuration()` filters by alert type
- **Alert Trigger:** When employee triggers "MEDICAL" alert, system finds configs with "MEDICAL" in applicable_alert_types

**Example Scenarios:**

**Scenario 1: General Emergency Config**
```json
{
  "config_name": "General Emergency",
  "applicable_alert_types": ["SOS", "MEDICAL", "ACCIDENT"]
}
```
→ Handles serious emergencies only.

**Scenario 2: Operational Issues Config**
```json
{
  "config_name": "Operational Monitoring",
  "applicable_alert_types": ["ROUTE_DEVIATION", "DELAYED"]
}
```
→ Different team (transport coordinators) handles operational issues.

**Scenario 3: All Types (Default)**
```json
{
  "config_name": "Catch-All Configuration",
  "applicable_alert_types": null
}
```
→ Handles any alert type that doesn't match other configs.

**System Logic:**
```python
# When alert is triggered
alert_type = "MEDICAL"

# System searches:
1. Find config where "MEDICAL" in applicable_alert_types
2. If not found, find config where applicable_alert_types is null
3. Use that config for routing
```

**Real-World Use Case:**
A company might have:
- **Security Team Config:** Handles SOS, SAFETY_CONCERN
- **Medical Team Config:** Handles MEDICAL
- **Transport Team Config:** Handles ROUTE_DEVIATION, DELAYED, ACCIDENT
- **Fallback Config:** Handles OTHER or anything missed

---

## Recipient Configuration

### 5. `primary_recipients`
**Type:** `array of recipient objects`  
**Required:** Yes (must have at least 1)

**Purpose:** First level of responders who receive immediate notification when alert is triggered.

**Recipient Object Structure:**
```json
{
  "name": "Security Manager",
  "email": "security@company.com",
  "phone": "+911234567890",
  "role": "Security",
  "channels": ["EMAIL", "SMS", "PUSH"]
}
```

**Where Used:**
- **Database:** Stored as JSON in `alert_configurations.primary_recipients`
- **Notification Service:** `notification_service.notify_alert_triggered()` reads this list
- **Alert Notifications:** Creates `alert_notifications` records for each recipient

**Recipient Fields Explained:**

#### `name`
- **Purpose:** Recipient's name for display and logging
- **Used in:** SMS messages, email subject lines, notification logs
- **Example:** "SMS sent to Security Manager"

#### `email`
- **Purpose:** Email address for EMAIL notifications
- **Validation:** Must be valid email format
- **Used in:** Sending email alerts
- **Can be null if:** Recipient doesn't use email channel

#### `phone`
- **Purpose:** Phone number for SMS and VOICE notifications
- **Format:** International format recommended (+911234567890)
- **Used in:** Sending SMS and making voice calls
- **Can be null if:** Recipient doesn't use SMS/VOICE channels

#### `role`
- **Purpose:** Describes recipient's role in the organization
- **Used in:** Logging, reporting, UI display
- **Example Roles:** "Security", "Manager", "Director", "Medical Staff", "HR"

#### `channels`
- **Purpose:** Preferred notification channels for this recipient
- **Options:** `["EMAIL", "SMS", "PUSH", "VOICE", "WHATSAPP"]`
- **Logic:** System sends notifications through ALL specified channels simultaneously

**Flow Example:**

```
Employee triggers SOS alert
↓
System reads primary_recipients
↓
For each recipient:
  - Security Manager (EMAIL, SMS, PUSH)
    → Send email to security@company.com
    → Send SMS to +911234567890
    → Send push notification via Firebase
  
  - Transport Manager (EMAIL, SMS)
    → Send email to transport@company.com
    → Send SMS to +911234567891
```

**Why Multiple Recipients?**
- **Redundancy:** If one person is unavailable, others can respond
- **Different Expertise:** Security for threats, medical for health issues
- **Backup:** Always have someone available

**Database Storage:**
```sql
-- Stored as JSON array
primary_recipients: '[
  {"name": "Security Manager", "email": "security@company.com", ...},
  {"name": "Transport Manager", "email": "transport@company.com", ...}
]'
```

---

## Escalation Configuration

### 6. `enable_escalation`
**Type:** `boolean`  
**Required:** Yes  
**Default:** `true`

**Purpose:** Controls whether alerts auto-escalate if not acknowledged in time.

**Usage:**
- `true` = Escalation is active (recommended for emergencies)
- `false` = No auto-escalation (used for low-priority alerts)

**Where Used:**
- **Background Job:** Escalation checker runs periodically
- **CRUD:** `alert_crud.check_escalations()` checks this flag
- **Database:** `alert_configurations.enable_escalation`

**Real-World Scenarios:**

**Scenario 1: Critical Alerts (enable_escalation = true)**
```json
{
  "config_name": "SOS Emergency",
  "enable_escalation": true,
  "escalation_threshold_seconds": 300
}
```
→ If no one acknowledges SOS alert within 5 minutes, escalate to director.

**Scenario 2: Minor Issues (enable_escalation = false)**
```json
{
  "config_name": "Delay Notifications",
  "applicable_alert_types": ["DELAYED"],
  "enable_escalation": false
}
```
→ Route delays don't auto-escalate (not life-threatening).

---

### 7. `escalation_threshold_seconds`
**Type:** `integer`  
**Required:** Yes (if enable_escalation is true)  
**Range:** 30-3600 seconds (30 seconds to 1 hour)  
**Default:** 300 (5 minutes)

**Purpose:** Time to wait before auto-escalating unacknowledged alerts.

**Usage:**
- System checks: `triggered_at + threshold_seconds < current_time`
- If true and not acknowledged, escalate

**Where Used:**
- **Background Job:** Runs every minute checking for escalation
- **Database:** `alert_configurations.escalation_threshold_seconds`
- **Calculation:** `SELECT * FROM alerts WHERE status = 'TRIGGERED' AND triggered_at < NOW() - INTERVAL '300 seconds'`

**Choosing the Right Value:**

**High Urgency (60-180 seconds)**
```json
{
  "applicable_alert_types": ["SOS", "MEDICAL"],
  "escalation_threshold_seconds": 120
}
```
→ Life-threatening situations need immediate response.
→ Escalate after 2 minutes if not acknowledged.

**Medium Urgency (300-600 seconds)**
```json
{
  "applicable_alert_types": ["ACCIDENT", "SAFETY_CONCERN"],
  "escalation_threshold_seconds": 300
}
```
→ Serious but allow reasonable response time.
→ Escalate after 5 minutes.

**Low Urgency (600+ seconds)**
```json
{
  "applicable_alert_types": ["DELAYED"],
  "escalation_threshold_seconds": 900
}
```
→ Non-emergency issues.
→ Escalate after 15 minutes.

**Example Timeline:**
```
18:45:00 - Alert triggered
18:45:00 - Primary recipients notified
18:50:00 - Threshold reached (300 seconds passed)
18:50:00 - System checks: Still TRIGGERED status?
18:50:00 - YES → Create escalation, notify escalation_recipients
```

---

### 8. `escalation_recipients`
**Type:** `array of recipient objects | null`  
**Required:** No (but recommended if enable_escalation is true)

**Purpose:** Second level of responders who are notified if alert is not acknowledged in time.

**Structure:** Same as primary_recipients

**Where Used:**
- **Escalation Job:** When threshold is reached
- **Database:** `alert_configurations.escalation_recipients`
- **Creates:** `alert_escalations` record + notifications

**Typical Hierarchy:**

```
Primary Recipients (Level 1):
├── Security Manager
├── Transport Manager
└── Floor Safety Officer

↓ (If not acknowledged in 5 minutes)

Escalation Recipients (Level 2):
├── Operations Director
├── HR Head
└── CEO's Office
```

**Example Configuration:**
```json
{
  "primary_recipients": [
    {
      "name": "Security Team Lead",
      "role": "Security",
      "channels": ["SMS", "PUSH"]
    }
  ],
  "escalation_recipients": [
    {
      "name": "Chief Security Officer",
      "role": "CSO",
      "channels": ["SMS", "VOICE", "EMAIL"]
    },
    {
      "name": "CEO",
      "role": "CEO",
      "channels": ["SMS", "VOICE"]
    }
  ]
}
```

**Why Different Channels for Escalations?**
Notice: Escalation recipients have VOICE added
- **More Intrusive:** Voice calls ensure senior management is alerted
- **Urgency Signal:** If it reached escalation, situation is serious

---

## Notification Configuration

### 9. `notification_channels`
**Type:** `array of strings`  
**Required:** Yes (must have at least 1)

**Available Channels:**
- `EMAIL` - Email notifications
- `SMS` - Text messages
- `PUSH` - Mobile app push notifications
- `VOICE` - Automated phone calls
- `WHATSAPP` - WhatsApp messages

**Purpose:** Defines which notification channels are allowed for this configuration.

**Where Used:**
- **Validation:** System checks if recipient's channels are in this list
- **Notification Service:** Only sends through allowed channels
- **Database:** `alert_configurations.notification_channels`

**Example:**
```json
{
  "notification_channels": ["EMAIL", "SMS", "PUSH"],
  "primary_recipients": [
    {
      "name": "Manager",
      "channels": ["EMAIL", "SMS", "VOICE"]
    }
  ]
}
```

**Result:** Manager will receive EMAIL and SMS only (VOICE is not in allowed channels).

**Cost Considerations:**

```json
// Low-cost configuration
{
  "notification_channels": ["EMAIL", "PUSH"]
}
// Cost: Free (email) + Free (push)

// High-cost configuration
{
  "notification_channels": ["EMAIL", "SMS", "VOICE"]
}
// Cost: Free + ₹0.25/SMS + ₹2/Voice call
```

**Best Practices:**
```json
// SOS/Medical (use all channels)
{
  "applicable_alert_types": ["SOS", "MEDICAL"],
  "notification_channels": ["EMAIL", "SMS", "PUSH", "VOICE"]
}

// Routine delays (email only)
{
  "applicable_alert_types": ["DELAYED"],
  "notification_channels": ["EMAIL"]
}
```

---

### 10. `notify_on_status_change`
**Type:** `boolean`  
**Required:** Yes  
**Default:** `true`

**Purpose:** Should recipients be notified when alert status changes?

**Status Changes:**
- TRIGGERED → ACKNOWLEDGED
- ACKNOWLEDGED → IN_PROGRESS
- IN_PROGRESS → RESOLVED
- RESOLVED → CLOSED

**Where Used:**
- **Alert Update Functions:** When status is updated
- **Notification Service:** Checks this flag before sending status updates
- **Database:** `alert_configurations.notify_on_status_change`

**Example Flow:**

**With notify_on_status_change = true:**
```
18:45:00 - Alert triggered
          → Email to Security: "New SOS Alert #101"
          
18:46:00 - Security acknowledges
          → Email to Security: "Alert #101 acknowledged by John"
          → Email to Employee: "Help is on the way"
          
18:55:00 - Status → IN_PROGRESS
          → Email to Security: "Alert #101 in progress"
          
19:00:00 - Status → RESOLVED
          → Email to All: "Alert #101 resolved"
```

**With notify_on_status_change = false:**
```
18:45:00 - Alert triggered
          → Email to Security: "New SOS Alert #101"
          
[No more notifications until closed]
```

**Use Cases:**

**Enable (true):**
- Critical alerts where everyone needs to know progress
- Compliance requirements (audit trail)
- Employee reassurance (they know help is coming)

**Disable (false):**
- High-volume, low-priority alerts
- Internal team communications already handled
- Cost reduction (fewer notifications)

---

### 11. `notify_on_escalation`
**Type:** `boolean`  
**Required:** Yes  
**Default:** `true`

**Purpose:** Should primary recipients be notified when alert escalates?

**Where Used:**
- **Escalation Job:** When creating escalation
- **Notification Service:** Sends escalation notices
- **Database:** `alert_configurations.notify_on_escalation`

**Example:**

**With notify_on_escalation = true:**
```
18:45:00 - Alert triggered
          → SMS to Security Manager
          
18:50:00 - Auto-escalation triggered
          → SMS to Director: "Alert #101 escalated - not acknowledged"
          → SMS to Security Manager: "Alert #101 escalated to director"
          → Email to all primary recipients: "Escalation notice"
```

**With notify_on_escalation = false:**
```
18:45:00 - Alert triggered
          → SMS to Security Manager
          
18:50:00 - Auto-escalation triggered
          → SMS to Director only
          [Security Manager NOT notified about escalation]
```

**Why Disable?**
- Avoid "notification fatigue" for primary recipients
- Senior management prefers discrete handling
- Reduce notification volume

---

## Advanced Settings

### 12. `auto_close_false_alarm_seconds`
**Type:** `integer | null`  
**Required:** No  
**Range:** 60-600 seconds (1-10 minutes)

**Purpose:** Automatically close alerts marked as resolved within X seconds (likely false alarms).

**Logic:**
```
If alert is RESOLVED within auto_close_false_alarm_seconds:
  - Automatically close alert
  - Mark as is_false_alarm = true
  - Send closure notification
```

**Where Used:**
- **Background Job:** Checks resolved alerts
- **Auto-Close Service:** Closes qualifying alerts
- **Database:** `alert_configurations.auto_close_false_alarm_seconds`

**Example:**

**Configuration:**
```json
{
  "auto_close_false_alarm_seconds": 120
}
```

**Scenario 1: Accidental Trigger (Auto-Close)**
```
18:45:00 - Alert triggered
18:45:30 - Employee calls: "Sorry, accident trigger"
18:45:45 - Security marks as RESOLVED (45 seconds)
18:45:45 - System: 45 < 120 → Auto-close as false alarm
```

**Scenario 2: Real Emergency (Manual Close)**
```
18:45:00 - Alert triggered
18:55:00 - Security resolves issue (10 minutes = 600 seconds)
18:55:00 - System: 600 > 120 → Requires manual closure
```

**Why This Matters:**
- **Fast False Alarms:** Accidental button presses are quickly resolved
- **Real Emergencies:** Take longer, need proper closure with notes
- **Reduces Admin Work:** False alarms auto-close without manual intervention

---

### 13. `require_closure_notes`
**Type:** `boolean`  
**Required:** Yes  
**Default:** `true`

**Purpose:** Force responders to provide closure notes when closing alert.

**Where Used:**
- **Alert Close API:** Validates closure_notes field
- **Validation:** Returns 400 error if notes missing and required
- **Database:** `alert_configurations.require_closure_notes`

**API Behavior:**

**With require_closure_notes = true:**
```bash
PUT /api/v1/alerts/101/close
{
  "closed_by": "Security",
  "closure_notes": ""
}
# Response: 400 Bad Request - "Closure notes required"
```

**With require_closure_notes = false:**
```bash
PUT /api/v1/alerts/101/close
{
  "closed_by": "Security"
}
# Response: 200 OK - Closed without notes
```

**Best Practices:**

**Require Notes (true):**
- Critical alerts (SOS, MEDICAL)
- Legal/compliance requirements
- Incident reporting needed
- Pattern analysis for safety improvements

**Optional Notes (false):**
- Minor operational issues
- High-volume, low-impact alerts
- Quick resolutions

---

### 14. `enable_geofencing_alerts`
**Type:** `boolean`  
**Required:** Yes  
**Default:** `false`

**Purpose:** Enable location-based alert features (future feature).

**Planned Features:**
- Alert if employee strays too far from expected location
- Auto-trigger alerts in unsafe zones
- Restrict alert triggering to specific areas

**Where Used:**
- **Future:** Geofencing service
- **Database:** `alert_configurations.enable_geofencing_alerts`

**Example Use Case:**
```json
{
  "enable_geofencing_alerts": true,
  "geofence_radius_meters": 1000
}
```
→ If employee travels >1km from planned route, auto-trigger ROUTE_DEVIATION alert.

---

### 15. `geofence_radius_meters`
**Type:** `integer | null`  
**Required:** No (only if enable_geofencing_alerts is true)  
**Range:** 100-10000 meters (100m to 10km)  
**Default:** 1000 (1 kilometer)

**Purpose:** Defines the acceptable distance from planned route.

**Where Used:**
- **Geofencing Service:** Calculates distance from route
- **Auto-Alert:** Triggers ROUTE_DEVIATION if exceeded
- **Database:** `alert_configurations.geofence_radius_meters`

**Example Values:**

**Tight Monitoring (100-300m):**
```json
{
  "geofence_radius_meters": 200
}
```
→ Strict monitoring, alerts on small deviations
→ Good for high-risk routes

**Normal Monitoring (500-1000m):**
```json
{
  "geofence_radius_meters": 1000
}
```
→ Reasonable flexibility for traffic/detours
→ Standard for most routes

**Loose Monitoring (2000-5000m):**
```json
{
  "geofence_radius_meters": 3000
}
```
→ Allow for major traffic diversions
→ Less critical routes

---

## Emergency Contacts

### 16. `emergency_contacts`
**Type:** `array of contact objects | null`  
**Required:** No

**Purpose:** External emergency services to display or auto-dial.

**Structure:**
```json
{
  "name": "Police",
  "phone": "100",
  "email": "police@gov.in",
  "service_type": "POLICE"
}
```

**Where Used:**
- **Mobile App:** Shows emergency contacts to employee
- **Auto-Dial:** Can trigger automated calls (future)
- **Display:** Shows in alert details
- **Database:** `alert_configurations.emergency_contacts`

**Common Emergency Contacts (India):**
```json
{
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
    },
    {
      "name": "Fire Brigade",
      "phone": "101",
      "service_type": "FIRE"
    },
    {
      "name": "Women Helpline",
      "phone": "1091",
      "service_type": "WOMEN_SAFETY"
    },
    {
      "name": "Company Security Control Room",
      "phone": "+911234567890",
      "email": "security@company.com",
      "service_type": "CORPORATE_SECURITY"
    }
  ]
}
```

**Mobile App Display:**
```
==========================================
SOS ALERT TRIGGERED
==========================================
Alert #101 - TRIGGERED
Your location has been shared.

EMERGENCY CONTACTS:
[📞 Call Police - 100]
[📞 Call Ambulance - 108]
[📞 Call Company Security - +911234567890]
==========================================
```

**Contact Types:**
- `POLICE` - Law enforcement
- `MEDICAL` - Ambulance/medical
- `FIRE` - Fire services
- `WOMEN_SAFETY` - Women's helpline
- `CORPORATE_SECURITY` - Company security
- `ROADSIDE_ASSISTANCE` - Vehicle breakdown
- `OTHER` - Other contacts

---

## Priority Configuration

### 17. `priority`
**Type:** `integer`  
**Required:** Yes  
**Range:** 1-1000  
**Default:** 100

**Purpose:** Determines which configuration to use when multiple configs match.

**Where Used:**
- **Configuration Selection:** When multiple configs apply
- **Sorting:** `ORDER BY priority DESC`
- **Database:** `alert_configurations.priority`

**Example Scenario:**

**Multiple Matching Configs:**
```sql
-- Employee in Team 5 triggers SOS alert

Config A (priority: 200):
- team_id: null (all teams)
- applicable_alert_types: ["SOS", "MEDICAL"]

Config B (priority: 300):
- team_id: 5 (specific team)
- applicable_alert_types: ["SOS"]

→ System selects Config B (higher priority + more specific)
```

**Priority Ranges:**

**Critical Configs (200-1000):**
```json
{
  "config_name": "VIP Employee Protection",
  "team_id": 1,
  "priority": 500
}
```
→ VIP employees get special handling

**Standard Configs (100-199):**
```json
{
  "config_name": "General Emergency",
  "team_id": null,
  "priority": 100
}
```
→ Default configuration

**Fallback Configs (1-99):**
```json
{
  "config_name": "Catch-All",
  "team_id": null,
  "applicable_alert_types": null,
  "priority": 1
}
```
→ Only used if nothing else matches

**Best Practice:**
- Specific configs: Higher priority (200+)
- General configs: Medium priority (100)
- Fallback configs: Low priority (1-50)

---

## Usage Flow Diagram

### Complete Alert Flow with Configuration

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: EMPLOYEE TRIGGERS ALERT                             │
└─────────────────────────────────────────────────────────────┘
  Employee presses SOS button
  ↓
  POST /api/v1/alerts/trigger
  {
    "alert_type": "SOS",
    "severity": "CRITICAL",
    "current_latitude": 12.9716,
    "current_longitude": 77.5946
  }

┌─────────────────────────────────────────────────────────────┐
│ STEP 2: FIND APPLICABLE CONFIGURATION                       │
└─────────────────────────────────────────────────────────────┘
  System Logic:
  1. Get employee's tenant_id and team_id
  2. Search for configuration:
     WHERE tenant_id = employee.tenant_id
     AND (team_id = employee.team_id OR team_id IS NULL)
     AND (alert_type IN applicable_alert_types OR applicable_alert_types IS NULL)
     ORDER BY priority DESC
     LIMIT 1
  
  Found: "Emergency Response Team" config
  
  Config Used:
  {
    "config_name": "Emergency Response Team",
    "primary_recipients": [Security Manager, Transport Manager],
    "notification_channels": ["EMAIL", "SMS", "PUSH"],
    "enable_escalation": true,
    "escalation_threshold_seconds": 300,
    ...
  }

┌─────────────────────────────────────────────────────────────┐
│ STEP 3: CREATE ALERT RECORD                                 │
└─────────────────────────────────────────────────────────────┘
  INSERT INTO alerts (
    tenant_id, employee_id, alert_type, severity, status,
    trigger_latitude, trigger_longitude, triggered_at
  )
  
  Alert #101 created with status: TRIGGERED

┌─────────────────────────────────────────────────────────────┐
│ STEP 4: SEND NOTIFICATIONS TO PRIMARY RECIPIENTS            │
└─────────────────────────────────────────────────────────────┘
  For each recipient in config.primary_recipients:
  
  Recipient 1: Security Manager
  - Channels: ["EMAIL", "SMS", "PUSH"]
  - Send EMAIL to security@company.com ✓
  - Send SMS to +911234567890 ✓
  - Send PUSH notification ✓
  
  Recipient 2: Transport Manager
  - Channels: ["EMAIL", "SMS"]
  - Send EMAIL to transport@company.com ✓
  - Send SMS to +911234567891 ✓
  
  (PUSH not sent - not in their channels)
  
  Creates 5 notification records in database

┌─────────────────────────────────────────────────────────────┐
│ STEP 5: START ESCALATION TIMER                              │
└─────────────────────────────────────────────────────────────┘
  if config.enable_escalation == true:
    escalation_time = triggered_at + escalation_threshold_seconds
    # 18:45:00 + 300 seconds = 18:50:00

┌─────────────────────────────────────────────────────────────┐
│ STEP 6: WAIT FOR ACKNOWLEDGMENT                             │
└─────────────────────────────────────────────────────────────┘
  Background job checks every minute:
  
  18:46:00 - Check: Is alert still TRIGGERED? Yes
             Time: 1 minute < 5 minutes threshold
             Action: Wait
  
  18:47:00 - Check: Is alert still TRIGGERED? Yes
             Time: 2 minutes < 5 minutes threshold
             Action: Wait
  
  ...
  
  18:50:00 - Check: Is alert still TRIGGERED? Yes
             Time: 5 minutes >= 5 minutes threshold
             Action: ESCALATE!

┌─────────────────────────────────────────────────────────────┐
│ STEP 7: AUTO-ESCALATION (if threshold reached)              │
└─────────────────────────────────────────────────────────────┘
  Create escalation record:
  INSERT INTO alert_escalations (
    alert_id, escalation_level, escalated_to,
    escalated_at, is_auto_escalation
  )
  
  For each recipient in config.escalation_recipients:
  
  Recipient 1: Operations Director
  - Channels: ["EMAIL", "SMS", "VOICE"]
  - Send EMAIL to ops-director@company.com ✓
  - Send SMS to +911234567892 ✓
  - Make VOICE call to +911234567892 ✓
  
  if config.notify_on_escalation == true:
    Notify primary recipients too:
    - Email to Security Manager: "Alert #101 escalated"
    - Email to Transport Manager: "Alert #101 escalated"

┌─────────────────────────────────────────────────────────────┐
│ STEP 8: ACKNOWLEDGMENT                                      │
└─────────────────────────────────────────────────────────────┘
  PUT /api/v1/alerts/101/acknowledge
  {
    "acknowledged_by": "Security Manager",
    "notes": "On my way, ETA 10 minutes"
  }
  
  Update alert:
  - status = ACKNOWLEDGED
  - acknowledged_at = NOW()
  - acknowledged_by = "Security Manager"
  - response_time_seconds = (acknowledged_at - triggered_at)
  
  if config.notify_on_status_change == true:
    Send status update notifications:
    - Email to all primary recipients
    - Push to employee: "Security Manager is on the way"

┌─────────────────────────────────────────────────────────────┐
│ STEP 9: RESOLUTION                                           │
└─────────────────────────────────────────────────────────────┘
  PUT /api/v1/alerts/101/status
  {
    "status": "RESOLVED",
    "notes": "Employee safe, situation resolved"
  }
  
  Update alert:
  - status = RESOLVED
  - resolved_at = NOW()
  - resolution_time_seconds = (resolved_at - triggered_at)
  
  Check auto-close:
  resolution_time = 120 seconds
  if config.auto_close_false_alarm_seconds != null
     AND resolution_time <= config.auto_close_false_alarm_seconds:
    # 120 <= 120 → Auto-close as false alarm
    status = CLOSED
    is_false_alarm = true
    closed_at = NOW()
  else:
    # Requires manual closure
    Wait for PUT /close endpoint

┌─────────────────────────────────────────────────────────────┐
│ STEP 10: MANUAL CLOSURE (if not auto-closed)                │
└─────────────────────────────────────────────────────────────┘
  PUT /api/v1/alerts/101/close
  {
    "closed_by": "Security Manager",
    "closure_notes": "Real emergency, provided escort to employee",
    "is_false_alarm": false
  }
  
  if config.require_closure_notes == true:
    Validate: closure_notes must not be empty
    If empty: Return 400 error
  
  Update alert:
  - status = CLOSED
  - closed_at = NOW()
  - closed_by = "Security Manager"
  - closure_notes = "..."
  
  if config.notify_on_status_change == true:
    Send final notifications:
    - Email to all recipients: "Alert #101 closed"
    - Push to employee: "Your alert has been resolved"

┌─────────────────────────────────────────────────────────────┐
│ COMPLETE TIMELINE                                            │
└─────────────────────────────────────────────────────────────┘
18:45:00 - Alert triggered
18:45:05 - Notifications sent (5 notifications)
18:46:30 - Acknowledged (90 seconds response time)
18:46:31 - Status change notifications sent
18:55:00 - Resolved
18:56:00 - Closed (660 seconds total duration)
```

---

## Summary: Where Each Variable is Used

| Variable | Database | CRUD Functions | Notification Service | Background Jobs | API Validation | UI Display |
|----------|----------|----------------|----------------------|-----------------|----------------|------------|
| `team_id` | ✓ | ✓ (filtering) | - | - | - | ✓ |
| `config_name` | ✓ | - | - | - | - | ✓ |
| `description` | ✓ | - | - | - | - | ✓ |
| `applicable_alert_types` | ✓ | ✓ (filtering) | - | - | - | - |
| `primary_recipients` | ✓ | ✓ | ✓ (main use) | - | ✓ (min 1) | ✓ |
| `enable_escalation` | ✓ | ✓ | - | ✓ (checker) | - | - |
| `escalation_threshold_seconds` | ✓ | - | - | ✓ (timer) | ✓ (range) | ✓ |
| `escalation_recipients` | ✓ | ✓ | ✓ (escalation) | ✓ | - | ✓ |
| `notification_channels` | ✓ | - | ✓ (filtering) | - | ✓ | ✓ |
| `notify_on_status_change` | ✓ | - | ✓ (flag) | - | - | - |
| `notify_on_escalation` | ✓ | - | ✓ (flag) | ✓ | - | - |
| `auto_close_false_alarm_seconds` | ✓ | - | - | ✓ (auto-close) | ✓ (range) | - |
| `require_closure_notes` | ✓ | - | - | - | ✓ | ✓ |
| `enable_geofencing_alerts` | ✓ | - | - | ✓ (future) | - | ✓ |
| `geofence_radius_meters` | ✓ | - | - | ✓ (future) | ✓ (range) | ✓ |
| `emergency_contacts` | ✓ | - | - | - | - | ✓ (mobile) |
| `priority` | ✓ | ✓ (sorting) | - | - | - | - |

---

## Real-World Configuration Examples

### Example 1: Startup with Small Team
```json
{
  "team_id": null,
  "config_name": "Company-Wide Alerts",
  "description": "All alerts go to founders",
  "applicable_alert_types": null,
  "primary_recipients": [
    {
      "name": "Founder CEO",
      "email": "ceo@startup.com",
      "phone": "+911234567890",
      "role": "CEO",
      "channels": ["SMS", "EMAIL"]
    }
  ],
  "enable_escalation": false,
  "notification_channels": ["EMAIL", "SMS"],
  "notify_on_status_change": true,
  "notify_on_escalation": false,
  "require_closure_notes": false,
  "priority": 100
}
```

### Example 2: Large Enterprise
```json
{
  "team_id": null,
  "config_name": "Critical Emergency Protocol",
  "description": "SOS and medical emergencies for all employees",
  "applicable_alert_types": ["SOS", "MEDICAL"],
  "primary_recipients": [
    {
      "name": "Security Control Room",
      "email": "security@enterprise.com",
      "phone": "+911234567890",
      "role": "Security",
      "channels": ["SMS", "PUSH", "EMAIL"]
    },
    {
      "name": "Medical Team",
      "email": "medical@enterprise.com",
      "phone": "+911234567891",
      "role": "Medical",
      "channels": ["SMS", "VOICE"]
    }
  ],
  "enable_escalation": true,
  "escalation_threshold_seconds": 120,
  "escalation_recipients": [
    {
      "name": "Chief Security Officer",
      "email": "cso@enterprise.com",
      "phone": "+911234567892",
      "role": "CSO",
      "channels": ["SMS", "VOICE", "EMAIL"]
    },
    {
      "name": "VP Operations",
      "email": "vp-ops@enterprise.com",
      "phone": "+911234567893",
      "role": "VP",
      "channels": ["SMS", "VOICE"]
    }
  ],
  "notification_channels": ["EMAIL", "SMS", "PUSH", "VOICE"],
  "notify_on_status_change": true,
  "notify_on_escalation": true,
  "auto_close_false_alarm_seconds": 90,
  "require_closure_notes": true,
  "enable_geofencing_alerts": true,
  "geofence_radius_meters": 500,
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
    },
    {
      "name": "Corporate Security Hotline",
      "phone": "+911800123456",
      "email": "security@enterprise.com",
      "service_type": "CORPORATE_SECURITY"
    }
  ],
  "priority": 500
}
```

### Example 3: Night Shift Special Configuration
```json
{
  "team_id": 8,
  "config_name": "Night Shift Safety Team",
  "description": "Night shift employees (10 PM - 6 AM) have different responders",
  "applicable_alert_types": ["SOS", "SAFETY_CONCERN"],
  "primary_recipients": [
    {
      "name": "Night Security Supervisor",
      "email": "night-security@company.com",
      "phone": "+911234567894",
      "role": "Night Security",
      "channels": ["SMS", "VOICE"]
    },
    {
      "name": "Night Shift Manager",
      "email": "night-manager@company.com",
      "phone": "+911234567895",
      "role": "Manager",
      "channels": ["SMS", "PUSH"]
    }
  ],
  "enable_escalation": true,
  "escalation_threshold_seconds": 180,
  "escalation_recipients": [
    {
      "name": "On-Call Director",
      "email": "oncall@company.com",
      "phone": "+911234567896",
      "role": "Director",
      "channels": ["VOICE", "SMS"]
    }
  ],
  "notification_channels": ["SMS", "VOICE", "PUSH"],
  "notify_on_status_change": true,
  "notify_on_escalation": true,
  "auto_close_false_alarm_seconds": 60,
  "require_closure_notes": true,
  "enable_geofencing_alerts": true,
  "geofence_radius_meters": 2000,
  "emergency_contacts": [
    {
      "name": "Police Night Patrol",
      "phone": "100",
      "service_type": "POLICE"
    },
    {
      "name": "Night Security Hotline",
      "phone": "+911800NIGHT",
      "service_type": "CORPORATE_SECURITY"
    }
  ],
  "priority": 300
}
```

---

*This document provides comprehensive explanation of all alert configuration variables, their usage, and real-world applications. For API usage examples, see ALERT_API_USAGE_GUIDE.md*
