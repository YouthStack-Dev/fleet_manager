# Audit Logging Implementation Guide

## Completed Modules

### ✅ Employee
- CREATE: ✅ Complete with user details and new values
- UPDATE: ✅ Complete with old/new values comparison
- TOGGLE STATUS: ✅ Complete

### ✅ Driver
- CREATE: ✅ Added audit logging with driver name and code

## Implementation Pattern

### For each CREATE endpoint:
```python
# After successful creation and db.commit()
log_audit(
    db=db,
    entity_type=EntityTypeEnum.{ENTITY},  # DRIVER, VEHICLE, VENDOR, etc.
    entity_id=db_obj.id,
    action=ActionEnum.CREATE,
    user_data=user_data,
    request=request,
    new_data={"key_field1": value1, "key_field2": value2},
    entity_name=name_or_identifier
)
```

### For each UPDATE endpoint:
```python
# Capture old values BEFORE update
old_data = {key: getattr(db_obj, key) for key in update_fields}

# Apply updates...
# db.commit()

# Capture new values AFTER update
new_data = {key: getattr(db_obj, key) for key in update_fields}

# Log audit
log_audit(
    db=db,
    entity_type=EntityTypeEnum.{ENTITY},
    entity_id=entity_id,
    action=ActionEnum.UPDATE,
    user_data=user_data,
    request=request,
    old_data=old_data,
    new_data=new_data,
    entity_name=name_or_identifier
)
```

### For each DELETE endpoint:
```python
# Capture data BEFORE delete
entity_data = {"key_field": db_obj.field}

# Delete...
# db.commit()

# Log audit
log_audit(
    db=db,
    entity_type=EntityTypeEnum.{ENTITY},
    entity_id=entity_id,
    action=ActionEnum.DELETE,
    user_data=user_data,
    request=request,
    old_data=entity_data,
    entity_name=name_or_identifier
)
```

## Modules To Complete

### 🔄 Driver (Partial)
**Files:** `app/routes/driver_router.py`
- ✅ CREATE - Done
- ⏳ UPDATE - Line ~541 `@router.put("/update")`
- ⏳ TOGGLE STATUS - Line ~749 `@router.patch("/{driver_id}/toggle-active")`

### ⏳ Vehicle
**Files:** `app/routes/vehicle_router.py`
- ⏳ CREATE - Line ~29 `@router.post("/")`
- ⏳ UPDATE - Search for `@router.put`
- ⏳ DELETE - Search for `@router.delete`

### ⏳ Vendor
**Files:** `app/routes/vendor_router.py`
- ⏳ CREATE - Line ~21 `@router.post("/")`
- ⏳ UPDATE - Search for `@router.put`
- ⏳ DELETE - Search for `@router.delete`

### ⏳ Cutoff
**Files:** `app/routes/cutoff.py`
- ⏳ UPDATE - Search for update endpoint
- Note: Cutoff uses `ensure_cutoff` which auto-creates, may need special handling

### ⏳ Weekoff Config
**Files:** `app/routes/weekoff_config_router.py`
- ⏳ UPDATE - Search for update endpoint
- Note: Weekoff uses `ensure_weekoff_config` which auto-creates

## Quick Implementation Steps

1. **Add Request import** to function signature:
   ```python
   def create_entity(
       ...,
       request: Request,  # Add this
       db: Session = Depends(get_db),
       user_data=Depends(PermissionChecker(...)),
   ):
   ```

2. **Add audit call** after successful operation:
   ```python
   log_audit(
       db=db,
       entity_type=EntityTypeEnum.DRIVER,  # Change per module
       entity_id=db_obj.driver_id,  # Change per module
       action=ActionEnum.CREATE,  # CREATE/UPDATE/DELETE
       user_data=user_data,
       request=request,
       new_data={"name": name, ...},  # Relevant fields
       entity_name=name  # Optional
   )
   ```

## Testing Checklist

After adding audit logging to each module:

- [ ] Driver CREATE
- [ ] Driver UPDATE
- [ ] Driver DELETE/TOGGLE
- [ ] Vehicle CREATE
- [ ] Vehicle UPDATE
- [ ] Vehicle DELETE
- [ ] Vendor CREATE
- [ ] Vendor UPDATE
- [ ] Vendor DELETE
- [ ] Cutoff UPDATE
- [ ] Weekoff UPDATE

## API Endpoints

Query all audits by module:
```bash
# Driver audits
GET /api/audit-logs/module/driver?page=1&page_size=50

# Vehicle audits
GET /api/audit-logs/module/vehicle

# Vendor audits
GET /api/audit-logs/module/vendor

# Cutoff audits
GET /api/audit-logs/module/cutoff

# Weekoff Config audits
GET /api/audit-logs/module/weekoff_config
```

## Notes

- All imports are already added to the routers
- `log_audit` helper handles user lookup automatically
- Errors in audit logging don't break the main operation
- Audit logs include IP address and user agent from Request object
- Password fields are automatically sanitized
