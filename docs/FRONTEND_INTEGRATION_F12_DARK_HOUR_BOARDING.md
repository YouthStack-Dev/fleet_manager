# Frontend Integration Guide — Feature 12: Female Employee Dark-Hour Boarding Block

## Overview

Feature 12 adds a safety enforcement layer to `POST /driver/trip/start`.  
When a **female employee** attempts to board during the tenant's configured dark-hour window and **no escort has boarded the vehicle**, the system can either:

| Mode | Behaviour |
|------|-----------|
| `off`   | Feature disabled — boarding proceeds normally (default, zero impact on existing tenants) |
| `warn`  | Boarding proceeds — response includes `"dark_hour_no_escort"` in `data.warnings` |
| `block` | Boarding is **rejected** with `HTTP 423 Locked` + security push to all admins |

---

## Tenant Configuration

Manage via `PUT /api/v1/tenant-config/` (admin only).

### New field

| Field | Type | Allowed values | Default |
|-------|------|----------------|---------|
| `dark_hour_boarding_mode` | `string` | `"off"`, `"warn"`, `"block"` | `"off"` |

### Related existing fields

| Field | Type | Description |
|-------|------|-------------|
| `escort_required_for_women` | `bool` | Must be `true` for F12 to apply |
| `escort_required_start_time` | `time` | Dark-window start (e.g. `"22:00:00"`) |
| `escort_required_end_time`   | `time` | Dark-window end   (e.g. `"06:00:00"`) |

> **Overnight window**: if `start_time > end_time` (e.g. 22:00 → 06:00) the system
> correctly handles the midnight crossing.  
> **All-day window**: set `start_time = "00:00:00"` and `end_time = "23:59:00"` to
> apply the rule 24 hours a day.

### Example config update request

```json
PATCH /api/v1/tenant-config/
{
  "escort_required_for_women": true,
  "escort_required_start_time": "22:00:00",
  "escort_required_end_time": "06:00:00",
  "dark_hour_boarding_mode": "warn"
}
```

### GET /api/v1/tenant-config/ response (new field included)

```json
{
  "tenant_id": "ACME001",
  ...
  "escort_required_for_women": true,
  "escort_required_start_time": "22:00:00",
  "escort_required_end_time": "06:00:00",
  "dark_hour_boarding_mode": "warn"
}
```

---

## POST /api/v1/driver/trip/start — behavioural changes

### Trigger conditions (ALL must be true)

1. `dark_hour_boarding_mode` ≠ `"off"`
2. Employee gender = `"Female"`
3. `escort_required_for_women` = `true`
4. Both `escort_required_start_time` and `escort_required_end_time` are set
5. Current IST time falls inside the configured dark window
6. No escort is assigned to the route **or** assigned escort has **not** boarded

> If an escort is assigned **and** has boarded (`escort_boarded = true`), the
> employee is considered safe and boarding is always allowed regardless of mode.

### Mode = `warn` — success response with warning

**HTTP 200 OK**

```json
{
  "success": true,
  "message": "Trip started successfully",
  "data": {
    "route_id": 42,
    "route_status": "Ongoing",
    "started_at": "22:15",
    "current_booking_id": 101,
    "current_status": "Ongoing",
    "actual_pick_up_time": "22:15",
    "next_stop": { ... },
    "warnings": ["dark_hour_no_escort"]
  }
}
```

**Driver app recommendation**: display an amber/yellow banner to the driver:  
> "Safety notice: Female passenger boarded without escort during restricted hours."

**No warnings (normal boarding)**:

```json
{
  "data": {
    ...
    "warnings": []
  }
}
```

### Mode = `block` — hard rejection

**HTTP 423 Locked**

```json
{
  "success": false,
  "error_code": "DARK_HOUR_NO_ESCORT",
  "message": "Boarding blocked: female employee in dark hours without a boarded escort.",
  "details": {
    "booking_id": 101,
    "route_id": 42
  }
}
```

**Driver app recommendation**: show a red blocking modal:  
> "Boarding blocked by safety policy. Please ensure an escort has boarded before
> picking up this passenger. Contact your supervisor if needed."

### Security push notification (mode = `block` only)

When boarding is blocked, the backend fires a push notification to all active
admin sessions for the tenant (non-blocking background task).  
The notification payload:

```json
{
  "title": "Security Alert: Dark-Hour Boarding Blocked",
  "body": "<Employee Name> attempted to board without a safety escort during restricted hours (booking #<id>). Boarding was blocked by system policy.",
  "data": {
    "type": "dark_hour_block",
    "booking_id": "101",
    "tenant_id": "ACME001",
    "employee_name": "Jane Doe"
  }
}
```

**Admin panel recommendation**: show an actionable alert card under "Security Alerts"
with options: _Acknowledge_ / _Dispatch Escort_ / _Call Driver_.

---

## Settings UI — Tenant Config Page

Add a new section **"Female Employee Safety (Dark Hours)"**:

### Controls

| UI Element | Maps to | Notes |
|------------|---------|-------|
| Toggle: "Enable dark-hour boarding restriction" | `dark_hour_boarding_mode != 'off'` | Disabled → mode stays `'off'` |
| Radio: "Warn only" / "Hard block" | `dark_hour_boarding_mode` = `"warn"` / `"block"` | Visible only when toggle is on |
| Toggle: "Require escort for female employees" | `escort_required_for_women` | |
| Time picker: "Restriction window start" | `escort_required_start_time` | HH:MM format |
| Time picker: "Restriction window end" | `escort_required_end_time` | Shows "(next day)" hint when start > end |

### Validation rules

- If mode ≠ `"off"` and `escort_required_for_women` is `false`: show warning
  _"The dark-hour block has no effect unless 'Require escort for female employees' is enabled."_
- If one time is set but not the other: block save with error
  _"Both window start and end times must be set."_
- Overnight window label: when start > end, display
  _"Window: HH:MM → HH:MM (next day)"_

---

## Error Codes Reference

| Code | HTTP Status | Trigger |
|------|-------------|---------|
| `DARK_HOUR_NO_ESCORT` | 423 Locked | Female employee, dark window active, mode=block, no boarded escort |

---

## Checklist for Driver App

- [ ] Read `data.warnings` in every `POST /driver/trip/start` 200 response
- [ ] If `"dark_hour_no_escort"` is in warnings → display amber safety banner
- [ ] Handle `HTTP 423` with `error_code == "DARK_HOUR_NO_ESCORT"` → show blocking modal
- [ ] Do not retry automatically on 423 — require driver action

## Checklist for Admin Panel

- [ ] Add dark-hour configuration controls to Tenant Settings page
- [ ] Subscribe to push notifications with `type = "dark_hour_block"` → show alert card
- [ ] Display `dark_hour_boarding_mode` in tenant config read view
