# Alert Configuration API Testing Guide

## Summary of Changes

### Fixed Issues
1. ✅ Fixed `tenant_id` duplicate argument error - excluded from config_data
2. ✅ Fixed `ResponseWrapper()` → `ResponseWrapper.success()` 
3. ✅ Fixed `get_applicable_configuration()` missing `alert_type` parameter
4. ✅ All error responses now use `ResponseWrapper.error()` with consistent structure

### Response Structure
**Success Response:**
```json
{
  "success": true,
  "message": "Alert configuration created successfully",
  "data": { /* configuration object */ },
  "timestamp": "2025-12-31T08:00:00Z"
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Configuration not found",
  "error_code": "CONFIG_NOT_FOUND",
  "details": { /* optional error details */ },
  "timestamp": "2025-12-31T08:00:00Z"
}
```

## Manual Testing Steps

### Prerequisites
- Valid employee or admin token with `tenant_config.read` and `tenant_config.write` permissions
- For admin operations: Role must be `TRANSPORT_MANAGER` or `ADMIN`
- For delete operations: Role must be `ADMIN`

### 1. Create Alert Configuration (POST /api/v1/alert-config)

**As Employee:**
```bash
curl -X POST "http://localhost:8000/api/v1/alert-config" \
  -H "Authorization: Bearer YOUR_EMPLOYEE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_name": "Emergency Response Team",
    "priority": 1,
    "applicable_alert_types": ["SOS", "EMERGENCY"],
    "primary_recipients": [
      {
        "name": "Control Room",
        "contact_type": "PHONE",
        "contact_value": "+919876543210",
        "notification_methods": ["SMS", "WHATSAPP"]
      }
    ],
    "escalation_recipients": [
      {
        "name": "Manager",
        "contact_type": "PHONE",
        "contact_value": "+919876543211",
        "notification_methods": ["CALL", "SMS"]
      }
    ],
    "escalation_delay_minutes": 5,
    "emergency_contacts": [
      {
        "name": "Police",
        "contact_number": "100",
        "contact_type": "EMERGENCY_SERVICE"
      }
    ],
    "is_active": true
  }'
```

**Expected Response:**
- Status: 200
- Body: Success response with created configuration including `config_id`

**Error Cases to Test:**
- Without auth: Status 401
- Duplicate config: Status 400, error_code: `CONFIG_ALREADY_EXISTS`
- Missing tenant_id (admin): Status 400, error_code: `TENANT_ID_REQUIRED`

### 2. Get All Configurations (GET /api/v1/alert-config)

```bash
curl -X GET "http://localhost:8000/api/v1/alert-config" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Optional Query Parameters:**
- `team_id` - Filter by specific team

**Expected Response:**
- Status: 200
- Body: List of configurations

### 3. Get Single Configuration (GET /api/v1/alert-config/{config_id})

```bash
curl -X GET "http://localhost:8000/api/v1/alert-config/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected Response:**
- Status: 200
- Body: Single configuration object

**Error Cases:**
- Non-existent ID: Status 404, error_code: `CONFIG_NOT_FOUND`

### 4. Update Configuration (PUT /api/v1/alert-config/{config_id})

**Requires Role:** `TRANSPORT_MANAGER` or `ADMIN`

```bash
curl -X PUT "http://localhost:8000/api/v1/alert-config/1" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_name": "Updated Emergency Team",
    "priority": 2,
    "escalation_delay_minutes": 10
  }'
```

**Expected Response:**
- Status: 200
- Body: Updated configuration

**Error Cases:**
- Insufficient role: Status 403, error_code: `ADMIN_ACCESS_REQUIRED`
- Non-existent ID: Status 404, error_code: `CONFIG_NOT_FOUND`

### 5. Delete Configuration (DELETE /api/v1/alert-config/{config_id})

**Requires Role:** `ADMIN` only

```bash
curl -X DELETE "http://localhost:8000/api/v1/alert-config/1" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Expected Response:**
- Status: 200
- Body: Success with `deleted_config_id`

**Error Cases:**
- Insufficient role (non-ADMIN): Status 403, error_code: `ADMIN_ACCESS_REQUIRED`
- Non-existent ID: Status 404, error_code: `CONFIG_NOT_FOUND`

### 6. Test Notification (POST /api/v1/alert-config/{config_id}/test-notification)

**Requires Role:** `TRANSPORT_MANAGER` or `ADMIN`

```bash
curl -X POST "http://localhost:8000/api/v1/alert-config/1/test-notification" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Expected Response:**
- Status: 200
- Body: Success with number of notifications sent and recipient list

**Error Cases:**
- Insufficient role: Status 403, error_code: `ADMIN_ACCESS_REQUIRED`
- Non-existent config: Status 404, error_code: `CONFIG_NOT_FOUND`

### 7. Get Applicable Configuration (GET /api/v1/alert-config/applicable/current)

**Required Query Parameter:** `alert_type`

```bash
curl -X GET "http://localhost:8000/api/v1/alert-config/applicable/current?alert_type=SOS" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Valid Alert Types:**
- SOS
- SAFETY_CONCERN
- ROUTE_DEVIATION
- DELAYED
- ACCIDENT
- MEDICAL
- OTHER

**Expected Response:**
- Status: 200
- Body: Most applicable configuration for the alert type (team-specific if exists, otherwise tenant-wide)
- If no config: Returns success with `data: null`

**Error Cases:**
- Invalid alert_type: Status 400, error_code: `INVALID_ALERT_TYPE`
- Missing alert_type: Status 422 (Validation Error)

## Error Codes Reference

| Error Code | Description | HTTP Status |
|------------|-------------|-------------|
| `ACCESS_FORBIDDEN` | Employee access only | 403 |
| `TENANT_ID_MISSING` | Tenant ID missing in token for employee | 400 |
| `TENANT_ID_REQUIRED` | Admin must provide tenant_id in request | 400 |
| `INVALID_USER_TYPE` | Invalid user type | 403 |
| `CONFIG_ALREADY_EXISTS` | Configuration already exists for tenant/team | 400 |
| `CONFIG_NOT_FOUND` | Configuration not found | 404 |
| `ADMIN_ACCESS_REQUIRED` | Admin/Transport Manager access required | 403 |
| `INVALID_ALERT_TYPE` | Invalid alert type provided | 400 |
| `CREATE_FAILED` | Failed to create configuration | 500 |
| `RETRIEVE_FAILED` | Failed to retrieve configuration | 500 |
| `UPDATE_FAILED` | Failed to update configuration | 500 |
| `DELETE_FAILED` | Failed to delete configuration | 500 |
| `TEST_NOTIFICATION_FAILED` | Failed to send test notifications | 500 |

## Automated Tests

Run the test suite:
```bash
cd c:\projects\fleet_manager\fleet_manager
python -m pytest tests/test_alert_config_router.py -v
```

The test suite includes:
- ✅ Create configuration (employee & admin)
- ✅ Duplicate configuration check
- ✅ Get all configurations
- ✅ Get single configuration
- ✅ Update configuration
- ✅ Delete configuration
- ✅ Test notifications
- ✅ Get applicable configuration
- ✅ Permission checks
- ✅ Role-based access control
- ✅ Response structure validation
- ✅ Full CRUD lifecycle test

## Configuration Priority System

The system uses priority levels to determine which configuration applies:

1. **Team-specific** configuration takes priority over tenant-wide
2. Higher `priority` number = higher priority
3. `applicable_alert_types` filters which alerts use the config
4. If no match, falls back to tenant-wide config

## Next Steps

1. Test all endpoints with valid authentication tokens
2. Verify error responses follow the consistent structure
3. Check that all error_codes are present in error responses
4. Validate permission and role-based access control
5. Test edge cases (missing fields, invalid data, etc.)

## Status: ✅ READY FOR TESTING

All endpoints have been updated with:
- ✅ Consistent response structure  
- ✅ Proper error handling
- ✅ Error codes for programmatic handling
- ✅ Fixed argument passing issues
- ✅ Comprehensive test coverage
