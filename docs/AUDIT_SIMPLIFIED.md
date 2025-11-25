# Simplified Audit Trail System

## Overview
The audit system has been simplified to use a more flexible JSON-based structure instead of separate columns for each field.

## Database Schema

### New Simplified Structure
```sql
CREATE TABLE audit_logs (
    audit_id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    module VARCHAR(50) NOT NULL,  -- 'employee', 'driver', 'vehicle', etc.
    audit_data JSONB NOT NULL,    -- All audit details in JSON
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_tenant_module ON audit_logs(tenant_id, module);
CREATE INDEX idx_module_created ON audit_logs(module, created_at);
CREATE INDEX idx_tenant_id ON audit_logs(tenant_id);
```

### audit_data JSON Structure
```json
{
  "action": "CREATE",
  "user": {
    "type": "admin",
    "id": 123,
    "name": "John Admin",
    "email": "john@admin.com"
  },
  "description": "Created employee 'Sarah Smith' (sarah@company.com)",
  "new_values": {
    "employee_id": 456,
    "name": "Sarah Smith",
    "email": "sarah@company.com",
    "phone": "+1234567890",
    "employee_code": "EMP001",
    "team_id": 10,
    "is_active": true
  },
  "timestamp": "2025-11-21T10:30:00.000Z",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0..."
}
```

## API Usage

### Query Audit Logs by Module
```http
GET /api/audit-logs/module/employee?page=1&page_size=50&tenant_id=tenant_1
```

**Response:**
```json
{
  "success": true,
  "data": {
    "module": "employee",
    "audit_logs": [
      {
        "audit_id": 1,
        "tenant_id": "tenant_1",
        "module": "employee",
        "audit_data": {
          "action": "CREATE",
          "user": {
            "type": "admin",
            "id": 123,
            "name": "John Admin",
            "email": "john@admin.com"
          },
          "description": "Created employee 'Sarah Smith' (sarah@company.com)",
          "new_values": {...}
        },
        "created_at": "2025-11-21T10:30:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total_count": 1,
      "total_pages": 1
    }
  }
}
```

## Implementation

### Adding Audit Logging to Routes

```python
from app.utils.audit_helper import log_audit

# In your route handler
@router.post("/")
def create_employee(...):
    # ... create employee logic ...
    
    # Log audit
    try:
        log_audit(
            db=db,
            tenant_id=tenant_id,
            module="employee",  # Module name
            action="CREATE",    # Action: CREATE, UPDATE, DELETE
            user_data=user_data,  # From PermissionChecker dependency
            description=f"Created employee '{employee.name}' ({employee.email})",
            new_values={
                "employee_id": employee.employee_id,
                "name": employee.name,
                "email": employee.email,
                # ... other relevant fields
            },
            request=request  # FastAPI Request object
        )
    except Exception as audit_error:
        logger.error(f"Failed to create audit log: {str(audit_error)}")
```

### For UPDATE Operations
```python
# Capture changes
log_audit(
    db=db,
    tenant_id=tenant_id,
    module="employee",
    action="UPDATE",
    user_data=user_data,
    description=f"Updated employee '{employee.name}' - changed fields: name, email",
    new_values={
        "old": {"name": "Old Name", "email": "old@email.com"},
        "new": {"name": "New Name", "email": "new@email.com"}
    },
    request=request
)
```

## Available Modules
- `employee` - Employee management
- `driver` - Driver management
- `vehicle` - Vehicle management
- `vendor` - Vendor management
- `cutoff` - Cutoff time configuration
- `weekoff_config` - Week off configuration
- `team` - Team management
- `admin` - Admin management
- `booking` - Booking management
- `shift` - Shift management
- `tenant` - Tenant management
- `vehicle_type` - Vehicle type management
- `vendor_user` - Vendor user management

## Access Control

### Admin Users
- Must provide `tenant_id` query parameter
- Can view audit logs for any tenant they manage

### Employee Users
- Automatically filtered by their `tenant_id` from token
- Cannot view other tenants' audit logs

### Vendor Users
- Restricted to vendor-related modules only: `driver`, `vehicle`, `vehicle_type`
- Cannot access other modules

### Driver Users
- Forbidden from viewing audit logs

## Benefits of Simplified Structure

1. **Flexibility**: Store any data structure in JSON without schema changes
2. **Simpler Schema**: Only 5 columns instead of 15+
3. **Easy Filtering**: Filter by `module` and `tenant_id` only
4. **Better Performance**: Fewer columns, better index usage
5. **No Enum Management**: Actions are simple strings
6. **Future-Proof**: Add new fields to JSON without migrations

## Migration from Old System

To migrate from the old audit system:

1. **Backup existing data**:
   ```sql
   CREATE TABLE audit_logs_backup AS SELECT * FROM audit_logs;
   ```

2. **Drop old table**:
   ```sql
   DROP TABLE audit_logs CASCADE;
   ```

3. **Create new table** (Alembic migration):
   ```bash
   alembic revision --autogenerate -m "simplify audit log schema"
   alembic upgrade head
   ```

4. **(Optional) Migrate old data**:
   ```sql
   INSERT INTO audit_logs (tenant_id, module, audit_data, created_at)
   SELECT 
       tenant_id,
       LOWER(entity_type::text) as module,
       jsonb_build_object(
           'action', action::text,
           'user', jsonb_build_object(
               'type', performed_by_type,
               'id', performed_by_id,
               'name', performed_by_name,
               'email', performed_by_email
           ),
           'description', description,
           'new_values', new_values,
           'old_values', old_values,
           'ip_address', ip_address,
           'user_agent', user_agent
       ) as audit_data,
       created_at
   FROM audit_logs_backup;
   ```

## Database Indexes

The system uses composite indexes for optimal query performance:
- `(tenant_id, module)` - For module-specific queries per tenant
- `(module, created_at)` - For time-based queries per module
- `tenant_id` - For tenant-wide audit queries

## Code Files Modified

### Models
- `app/models/audit_log.py` - Simplified to 5 columns with JSON

### Schemas
- `app/schemas/audit_log.py` - Removed enums, simplified structure

### CRUD
- `app/crud/audit_log.py` - Updated to query by module/tenant

### Services
- `app/services/audit_service.py` - Simplified to one `log_audit()` method
- `app/utils/audit_helper.py` - Updated helper function

### Routes
- `app/routes/audit_log_router.py` - Updated query endpoint
- `app/routes/employee_router.py` - Updated to use simplified audit
- `app/routes/driver_router.py` - Updated to use simplified audit
- `app/routes/cutoff.py` - Updated to use simplified audit

## Future Enhancements

1. **Search within JSON**: Use PostgreSQL JSONB operators
   ```sql
   SELECT * FROM audit_logs 
   WHERE audit_data->'user'->>'name' ILIKE '%john%';
   ```

2. **Date Range Filtering**: Add to API endpoint
3. **Export to CSV/Excel**: For compliance reporting
4. **Audit Log Retention**: Auto-archive old logs
5. **Real-time Notifications**: WebSocket for live audit feed
