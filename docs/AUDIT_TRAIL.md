# Audit Trail Feature Documentation

## Overview
The audit trail feature provides comprehensive logging of all operations performed in the Fleet Manager system. It tracks who performed what action, when, and what changed, providing full accountability and compliance tracking.

## Features

### 1. Comprehensive Logging
- **Entity Types Tracked**: Employee, Admin, Driver, Vehicle, Vendor, Vendor User, Booking, Team, Tenant, Shift, Cutoff, Vehicle Type, Weekoff Config
- **Actions Logged**: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, EXPORT, IMPORT
- **Metadata Captured**:
  - Who performed the action (type, ID, name, email)
  - When it was performed (timestamp)
  - What entity was affected (type and ID)
  - What changed (old values vs new values)
  - Where it came from (IP address and user agent)
  - Which tenant it belongs to

### 2. Security Features
- **Password Sanitization**: Sensitive fields like passwords are automatically redacted in audit logs
- **Tenant Isolation**: Employees can only view audit logs within their tenant
- **Role-Based Access**: Different permissions for admins, employees, and other users

### 3. Query Capabilities
- Filter by entity type, entity ID, action, performer, tenant, and date range
- Pagination support for large datasets
- Retrieve audit history for specific entities
- Search by user actions

## Database Schema

### AuditLog Table
```sql
CREATE TABLE audit_logs (
    audit_id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    performed_by_type VARCHAR(50) NOT NULL,
    performed_by_id INTEGER NOT NULL,
    performed_by_name VARCHAR(150) NOT NULL,
    performed_by_email VARCHAR(150),
    tenant_id VARCHAR(50),
    old_values JSON,
    new_values JSON,
    description TEXT,
    ip_address VARCHAR(50),
    user_agent VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity_type ON audit_logs(entity_type);
CREATE INDEX idx_audit_entity_id ON audit_logs(entity_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
```

## API Endpoints

### 1. Get All Audit Logs (with filters)
**GET** `/api/audit-logs/`

**Query Parameters:**
- `entity_type`: Filter by entity type (optional)
- `entity_id`: Filter by entity ID (optional)
- `action`: Filter by action type (optional)
- `performed_by_type`: Filter by performer type (optional)
- `performed_by_id`: Filter by performer ID (optional)
- `tenant_id`: Filter by tenant ID (optional)
- `start_date`: Filter by start date (optional)
- `end_date`: Filter by end date (optional)
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 50, max: 200)

**Permissions:**
- Admins: Can view all audit logs
- Employees: Can only view logs within their tenant
- Vendors/Drivers: Forbidden

**Example Response:**
```json
{
  "success": true,
  "data": {
    "audit_logs": [
      {
        "audit_id": 1,
        "entity_type": "EMPLOYEE",
        "entity_id": "123",
        "action": "CREATE",
        "performed_by_type": "admin",
        "performed_by_id": 1,
        "performed_by_name": "Admin User",
        "performed_by_email": "admin@example.com",
        "tenant_id": "tenant_001",
        "old_values": null,
        "new_values": {
          "name": "John Doe",
          "email": "john@example.com",
          "phone": "1234567890"
        },
        "description": "Employee 'John Doe' created",
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "created_at": "2025-11-20T10:30:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total_count": 1,
      "total_pages": 1
    }
  },
  "message": "Audit logs retrieved successfully"
}
```

### 2. Get Specific Audit Log by ID
**GET** `/api/audit-logs/{audit_id}`

**Permissions:**
- Admins: Can view any audit log
- Employees: Can only view logs within their tenant
- Vendors/Drivers: Forbidden

### 3. Get Audit Logs for Specific Entity
**GET** `/api/audit-logs/entity/{entity_type}/{entity_id}`

**Query Parameters:**
- `skip`: Number of records to skip (default: 0)
- `limit`: Maximum records to return (default: 100, max: 200)

**Example:**
```
GET /api/audit-logs/entity/EMPLOYEE/123
```

This returns all audit history for employee with ID 123.

## Usage Examples

### 1. Logging an Action (Internal Use)

The audit service provides convenient methods for logging actions:

```python
from app.services.audit_service import audit_service
from app.models.audit_log import EntityTypeEnum, ActionEnum

# Log employee creation
audit_service.log_employee_created(
    db=db,
    employee_id=employee.employee_id,
    employee_data={
        "name": employee.name,
        "email": employee.email,
        "phone": employee.phone
    },
    performed_by={
        "type": "admin",
        "id": 1,
        "name": "Admin User",
        "email": "admin@example.com"
    },
    request=request,
    tenant_id="tenant_001"
)

# Log custom action
audit_service.log_action(
    db=db,
    entity_type=EntityTypeEnum.VEHICLE,
    entity_id=vehicle_id,
    action=ActionEnum.DELETE,
    performed_by=performer_info,
    old_values={"license_plate": "ABC123"},
    description="Vehicle deleted",
    request=request
)
```

### 2. Querying Audit Logs

#### Get all employee creation logs for a tenant:
```bash
GET /api/audit-logs/?entity_type=EMPLOYEE&action=CREATE&tenant_id=tenant_001&page=1&page_size=50
```

#### Get audit history for specific employee:
```bash
GET /api/audit-logs/entity/EMPLOYEE/123
```

#### Get all actions performed by a specific user:
```bash
GET /api/audit-logs/?performed_by_id=5&performed_by_type=admin
```

#### Get audit logs within a date range:
```bash
GET /api/audit-logs/?start_date=2025-11-01T00:00:00&end_date=2025-11-20T23:59:59
```

## Implementation in Routes

The employee router has been updated with audit logging:

### Employee Creation
```python
@router.post("/")
def create_employee(
    employee: EmployeeCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.create"])),
):
    # ... create employee logic ...
    
    # Log audit trail
    audit_service.log_employee_created(
        db=db,
        employee_id=db_employee.employee_id,
        employee_data=sanitized_data,
        performed_by=performer_info,
        request=request,
        tenant_id=tenant_id
    )
```

### Employee Update
```python
@router.put("/{employee_id}")
def update_employee(
    employee_id: int,
    employee_update: EmployeeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.update"])),
):
    # Capture old values
    old_values = {...}
    
    # ... update logic ...
    
    # Capture new values
    new_values = {...}
    
    # Log audit trail
    audit_service.log_employee_updated(
        db=db,
        employee_id=employee_id,
        old_data=old_values,
        new_data=new_values,
        performed_by=performer_info,
        request=request,
        tenant_id=tenant_id
    )
```

## Extending to Other Entities

To add audit logging to other entities (drivers, vehicles, bookings, etc.):

### 1. Add convenience methods to `audit_service.py`:
```python
@staticmethod
def log_vehicle_created(
    db: Session,
    vehicle_id: int,
    vehicle_data: Dict[str, Any],
    performed_by: Dict[str, Any],
    request: Optional[Request] = None,
    tenant_id: Optional[str] = None
) -> AuditLog:
    return AuditService.log_action(
        db=db,
        entity_type=EntityTypeEnum.VEHICLE,
        entity_id=vehicle_id,
        action=ActionEnum.CREATE,
        performed_by=performed_by,
        new_values=vehicle_data,
        description=f"Vehicle '{vehicle_data.get('license_plate')}' created",
        request=request,
        tenant_id=tenant_id
    )
```

### 2. Update the route handlers:
```python
# In vehicle_router.py
from app.services.audit_service import audit_service
from app.models.audit_log import EntityTypeEnum, ActionEnum

@router.post("/")
def create_vehicle(
    vehicle: VehicleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(...),
):
    # ... vehicle creation logic ...
    
    # Add audit logging
    audit_service.log_vehicle_created(
        db=db,
        vehicle_id=db_vehicle.vehicle_id,
        vehicle_data=sanitized_data,
        performed_by=performer_info,
        request=request
    )
```

## Setup Instructions

### 1. Create Database Tables
Run the database initialization script:
```bash
python app/database/create_tables.py
```

This will automatically create the `audit_logs` table along with all necessary indexes.

### 2. Add Permissions
Ensure the IAM system includes the `audit_log.read` permission for roles that should access audit logs.

### 3. Test the Feature
```bash
# Create an employee (should generate audit log)
POST /api/employees/

# View the audit log
GET /api/audit-logs/?entity_type=EMPLOYEE&action=CREATE
```

## Best Practices

1. **Always sanitize sensitive data**: Use `audit_service.sanitize_data()` to remove passwords and tokens
2. **Handle audit failures gracefully**: Wrap audit logging in try-catch to prevent audit failures from breaking business logic
3. **Be specific with descriptions**: Provide meaningful descriptions for better audit trails
4. **Use entity-specific methods**: Prefer `log_employee_created()` over generic `log_action()` for consistency
5. **Include request context**: Always pass the `Request` object to capture IP and user agent

## Security Considerations

- Audit logs are **append-only** (no update/delete endpoints provided)
- Sensitive data is automatically redacted
- Tenant isolation is strictly enforced
- All queries are logged and can be audited themselves
- Database-level constraints prevent orphaned audit records

## Compliance

This audit trail implementation supports:
- **SOC 2 Type II**: Complete activity logging
- **GDPR**: Data change tracking for compliance
- **HIPAA**: Audit trail requirements
- **ISO 27001**: Information security management
- **General Compliance**: Who, what, when, where tracking

## Future Enhancements

1. Add audit log retention policies
2. Implement audit log export functionality
3. Add real-time audit log streaming
4. Create audit log dashboards and analytics
5. Add tamper-detection mechanisms
6. Implement audit log archival for older records
