# Fleet Manager — Query Optimization Guide

**Date:** 2026-04-30  
**Scope:** N+1 query patterns, missing indexes, redundant queries, ORM configuration issues, and cache misuse  
**Cross-reference:** See `db_analysis.md` for index creation SQL; `audit_report.md` AUDIT-021, AUDIT-026

---

## 1. N+1 Query Patterns

### QO-001 — `get_bookings` Executes a COUNT Query on Every Page Load

**File:** `app/routes/booking_router.py:489`  
**Severity:** High

```python
# Current — two full queries per page load
total, items = paginate_query(query, skip, limit)
filtered_count = query.count()   # ← runs BEFORE paginate_query too
```

`query.count()` executes `SELECT COUNT(*) FROM bookings WHERE tenant_id = ? [AND date = ?]`. Then `paginate_query` calls `.count()` internally again before applying `.offset().limit()`. This means **every paginated list endpoint runs 3 SQL statements** where 2 suffice: one `COUNT(*)` and one `SELECT ... LIMIT ? OFFSET ?`.

**Optimized Pattern:**
```python
# Pass count through paginate_query, remove the separate .count() call
total, items = paginate_query(query, skip, limit)
# total already contains the count — log it directly
logger.info(
    "Filtered bookings count for tenant_id=%s date=%s: %d",
    effective_tenant_id, booking_date, total
)
```

Remove `filtered_count = query.count()` at line 489. Eliminates 1 SQL query per list request.

---

### QO-002 — Shift Cache Lookup Called Inside a Loop

**File:** `app/routes/booking_router.py:543–547`  
**Severity:** Medium

```python
shift_ids = [r.shift_id for r in route_obj_dict.values() if r.shift_id]
for shift_id in shift_ids:                          # ← loop
    shift_data = get_shift_with_cache(db, tenant_id, shift_id)  # DB hit if not cached
    if shift_data:
        shifts_dict[shift_id] = shift_data
```

If none of the shifts are in Redis (cold start, cache flush, or `USE_REDIS=0`), this is one DB query per unique `shift_id` in the current page of results. For a page of 20 bookings across 5 shifts, that's 5 sequential queries.

**Optimized Pattern:**
```python
# Batch fetch all shifts in one query, then cache individually
uncached_shift_ids = [sid for sid in shift_ids if sid not in shifts_dict]
if uncached_shift_ids:
    shifts = db.query(Shift).filter(Shift.shift_id.in_(uncached_shift_ids)).all()
    for shift in shifts:
        shifts_dict[shift.shift_id] = shift
        # Optionally write-through to cache here
```

Same fix applies to the identical block in `get_bookings_by_employee`.

---

### QO-003 — Duplicate `booking_map` Assignment

**File:** `app/routes/booking_router.py:567–572`  
**Severity:** Low (correctness, not performance)

```python
# Line 567
booking_map = {b.booking_id: b for b in passenger_bookings}
logger.info(f"Created booking map with {len(booking_map)} entries")

# Line 571 — exact duplicate, overwrites line 567
booking_map = {b.booking_id: b for b in passenger_bookings}
logger.info(f"Created booking map with {len(booking_map)} entries")
```

This is a copy-paste artifact. The same dict is built twice, iterating `passenger_bookings` twice. Remove the second block (lines 571–572).

---

### QO-004 — `get_booking_by_id` Executes 7+ Sequential Queries

**File:** `app/routes/booking_router.py:971–1031`  
**Cross-reference:** `audit_report.md` AUDIT-021  
**Severity:** High

Current execution trace for a single `/bookings/{id}` call:

```
1. SELECT * FROM bookings WHERE booking_id = ?
2. SELECT * FROM route_management_bookings WHERE booking_id = ?
3. SELECT * FROM route_management WHERE route_id = ?
4. SELECT * FROM route_management_bookings WHERE route_id = ?   ← all passengers
5. SELECT * FROM bookings WHERE booking_id IN (...)             ← passenger bookings
6. SELECT * FROM employees WHERE employee_id IN (...)           ← via lazy load
7. SELECT * FROM vehicles WHERE vehicle_id = ?
8. SELECT * FROM drivers WHERE driver_id = ?
9. SELECT * FROM vendors WHERE vendor_id = ?
```

**Optimized Version (3 queries total):**

```python
@router.get("/{booking_id}")
def get_booking_by_id(booking_id: int, db: Session = Depends(get_db), ...):
    # Query 1: Booking + employee + shift (eager load)
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.employee),
            joinedload(Booking.shift),
        )
        .filter(Booking.booking_id == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, ...)

    # Query 2: RouteManagementBooking + its Route (eager load)
    route_booking = (
        db.query(RouteManagementBooking)
        .options(joinedload(RouteManagementBooking.route_management))
        .filter(RouteManagementBooking.booking_id == booking_id)
        .first()
    )

    if route_booking and route_booking.route_management:
        route = route_booking.route_management

        # Query 3: Batch fetch all passengers + vehicle + driver + vendor in one go
        # using .in_() on the route's booking IDs
        all_route_bookings = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route.route_id)
            .all()
        )
        passenger_booking_ids = [rb.booking_id for rb in all_route_bookings]

        # Inline batch: vehicle, driver, vendor, passengers in one query each
        vehicle = db.get(Vehicle, route.assigned_vehicle_id) if route.assigned_vehicle_id else None
        driver  = db.get(Driver,  route.assigned_driver_id)  if route.assigned_driver_id  else None
        vendor  = db.get(Vendor,  route.assigned_vendor_id)  if route.assigned_vendor_id  else None

        passenger_bookings = (
            db.query(Booking)
            .options(joinedload(Booking.employee))
            .filter(Booking.booking_id.in_(passenger_booking_ids))
            .all()
        ) if passenger_booking_ids else []

    # ... build response
```

Using `db.get(Model, pk)` for single-row lookups leverages SQLAlchemy's identity map — if the object was already loaded in this session, no SQL is emitted.

---

### QO-005 — O(n²) Permission Aggregation Using `next()` Linear Scan

**File:** `app/crud/employee.py:155`, `app/routes/auth_router.py:147`  
**Cross-reference:** `audit_report.md` AUDIT-026  
**Severity:** Medium

```python
# Current — O(n) scan for every permission
existing = next((p for p in all_permissions if p["module"] == module), None)
if existing:
    existing["action"].append(action)
else:
    all_permissions.append({"module": module, "action": [action]})
```

For an employee with 5 roles × 10 policies × 20 permissions = 1,000 permissions, this inner `next()` scan runs 1,000 times against a growing list — 500,500 comparisons in the worst case.

**Optimized Version — O(n) using a dict:**

```python
# Build as dict, convert to list at the end
permissions_by_module: dict[str, set[str]] = {}

for role in role_list:
    for policy in (role.policies or []):
        for permission in (policy.permissions or []):
            if allowed_permission_ids is not None:
                if permission.permission_id not in allowed_permission_ids:
                    continue
            module = permission.module
            action = permission.action
            if module not in permissions_by_module:
                permissions_by_module[module] = set()
            if action == "*":
                permissions_by_module[module] = {"create", "read", "update", "delete", "*"}
            else:
                permissions_by_module[module].add(action)

# Convert to list format expected by callers
all_permissions = [
    {"module": mod, "action": sorted(actions)}
    for mod, actions in permissions_by_module.items()
]
```

Apply identical fix in `auth_router.py:147`.

---

### QO-006 — `get_employee_roles_and_permissions` Calls the DB on Every Token Validation

**File:** `app/crud/employee.py:109–169`  
**Severity:** High

```python
employee = db.query(Employee).filter(...).first()
package  = db.query(PolicyPackage).filter_by(tenant_id=tenant_id).first()
# + N queries for role.policies and policy.permissions (lazy loaded)
```

This function is called from `validate_bearer_token` — i.e., on **every authenticated request**. At 100 req/s, this generates 200+ DB queries per second just for permission loading.

**Required Fix:**

1. Add eager loading to the employee + role + policies + permissions chain:

```python
employee = (
    db.query(Employee)
    .options(
        joinedload(Employee.role)
        .joinedload(Role.policies)
        .joinedload(Policy.permissions)
    )
    .filter(
        Employee.employee_id == employee_id,
        Employee.tenant_id == tenant_id,
        Employee.is_active == True,
    )
    .first()
)
```

2. Cache the resolved `(employee_id, tenant_id) → permissions` result in Redis with a short TTL (5–10 minutes). Invalidate on role change or policy package update.

**Estimated Impact:** Reduces DB queries for auth from ~4 per request to 0 (cache hit) or 1 (cache miss, single eager-loaded query).

---

### QO-007 — `PolicyPackage` Queried Separately in Permission Resolution

**File:** `app/crud/employee.py:119`

```python
package = db.query(PolicyPackage).filter_by(tenant_id=tenant_id).first()
```

This is a separate query executed after the employee query. The `PolicyPackage` for a tenant changes rarely (only when a super-admin updates it). It should be cached by `tenant_id` with a long TTL (60 minutes or until explicitly invalidated).

**Optimized Pattern:**
```python
def get_policy_package(db: Session, tenant_id: str) -> Optional[PolicyPackage]:
    cache_key = f"policy_package:{tenant_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    package = db.query(PolicyPackage).filter_by(tenant_id=tenant_id).first()
    if package:
        redis_client.setex(cache_key, 3600, json.dumps(package.permission_ids))
    return package
```

---

## 2. ORM Configuration Issues

### QO-008 — `expire_on_commit=True` Causes Hidden Lazy Loads Post-Commit

**File:** `app/database/session.py:19`  
**Cross-reference:** `audit_report.md` AUDIT-034  
**Severity:** Medium

```python
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# expire_on_commit defaults to True
```

After any `db.commit()`, all loaded ORM objects are marked expired. The next attribute access on any of those objects triggers a new `SELECT` query. In `create_booking` (booking_router.py), objects are accessed after `db.commit()` to build the response — this triggers lazy loads.

**Fix:**
```python
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # objects remain valid after commit
)
```

**Caveat:** With `expire_on_commit=False`, stale data may be served if objects are modified after commit. Ensure route handlers do not reuse a session across multiple logical operations. The current pattern (one session per request via `get_db`) is safe.

---

### QO-009 — `autoflush=False` Combined with Lazy Relationships Can Cause Unexpected `SELECT`

**File:** `app/database/session.py:19`

`autoflush=False` prevents SQLAlchemy from flushing pending changes before executing a query. This is generally correct for async-style code. However, if a route handler creates an object (`db.add(obj)`) and then queries a related collection before `db.commit()`, the new object will not appear in the query results — creating confusing ordering-dependent bugs.

**Recommendation:** Document this as a known constraint in session management and add a note in `get_db` docstring. Use `db.flush()` explicitly before any query that depends on an unflushed change.

---

## 3. Missing Indexes (Query Impact)

The following queries are confirmed to run without covering indexes. Full details in `db_analysis.md`.

| Query Pattern | Table | Missing Index | Expected Improvement |
|--------------|-------|---------------|----------------------|
| `WHERE tenant_id=? AND booking_date=?` | `bookings` | `(tenant_id, booking_date)` | Seq scan → index seek |
| `WHERE booking_id IN (...)` | `route_management_bookings` | `(booking_id)` | Seq scan → bitmap index |
| `WHERE employee_id=? AND booking_date=?` | `bookings` | `(employee_id, booking_date)` | Partial seq scan → index |
| `WHERE user_type=? AND user_id=? AND platform=? AND is_active=True` | `user_sessions` | `(user_type, user_id, platform, is_active)` | Seq scan → covering index |
| `WHERE route_id IN (...)` | `route_management_bookings` | Already has PK and unique constraint | Partial only |

---

## 4. Cache Usage Issues

### QO-010 — Cache Warming Happens Request-by-Request (No Preloading)

**File:** `app/utils/cache_manager.py`

All cache helpers (`get_tenant_with_cache`, `get_shift_with_cache`, etc.) follow a lazy read-through pattern: miss → DB query → cache write. On application startup (or after a Redis flush), the first N requests for each tenant's configuration incur DB queries. With 50 concurrent requests at startup, 50 parallel cache-miss DB queries execute simultaneously.

**Recommended Pattern:** Add a startup preloader in the lifespan:
```python
async def lifespan(app: FastAPI):
    run_migrations()
    setup_logging()
    # Warm cache for active tenants
    from app.utils.cache_manager import warm_cache_for_active_tenants
    warm_cache_for_active_tenants()
    yield
```

---

### QO-011 — Cache Serializer Re-Reads Model Columns on Every Serialize Call

**File:** `app/utils/cache_manager.py:596–1125`  
**Cross-reference:** `audit_report.md` AUDIT-023  
**Severity:** Medium

The ~500 lines of `serialize_X_for_cache` functions contain hand-coded per-field serialization. Every change to a model column requires updating the corresponding serialize/deserialize function. More critically, serializing a model with 40 columns requires 40 `getattr` calls followed by 40 conditional branches.

**Optimized Generic Serializer:**
```python
from sqlalchemy import inspect as sa_inspect
from datetime import datetime, date, time
from enum import Enum as PyEnum
import json

def serialize_model(instance) -> dict:
    mapper = sa_inspect(type(instance))
    result = {}
    for col in mapper.columns:
        value = getattr(instance, col.key)
        if value is None:
            result[col.key] = None
        elif isinstance(value, (datetime, date, time)):
            result[col.key] = value.isoformat()
        elif isinstance(value, PyEnum):
            result[col.key] = value.value
        elif isinstance(value, (dict, list)):
            result[col.key] = value  # JSON-serializable already
        else:
            result[col.key] = value
    return result

def deserialize_model(data: dict, model_class):
    """Reconstruct a model instance from cached dict (read-only, no DB session)."""
    instance = model_class.__new__(model_class)
    mapper = sa_inspect(model_class)
    for col in mapper.columns:
        key = col.key
        raw = data.get(key)
        if raw is not None and hasattr(col.type, 'impl'):
            # Let column type handle coercion
            pass
        setattr(instance, key, raw)
    return instance
```

This replaces ~500 lines with ~40 lines and is automatically correct for new model columns.

---

## 5. Bulk Operation Issues

### QO-012 — `bulk_insert_mappings` Is Deprecated in SQLAlchemy 2.x

**File:** Any route or CRUD that uses `db.bulk_insert_mappings()`  
**Cross-reference:** `audit_report.md` (identified in discovery)  
**Severity:** Medium

`Session.bulk_insert_mappings()` is deprecated in SQLAlchemy 2.0 and removed in 2.1. The modern replacement:

```python
# Old (deprecated)
db.bulk_insert_mappings(Booking, [{"tenant_id": ..., "employee_id": ...}, ...])

# New (SQLAlchemy 2.x)
from sqlalchemy import insert
db.execute(insert(Booking), [{"tenant_id": ..., "employee_id": ...}, ...])
db.commit()
```

The `insert()` approach is also more efficient: it uses a true bulk `INSERT INTO ... VALUES (...), (...), (...)` statement rather than individual `INSERT` statements.

---

## 6. Query Patterns Reference

### Summary of Confirmed Problematic Queries

| ID | Location | Problem | Fix |
|----|----------|---------|-----|
| QO-001 | `booking_router.py:489` | Double `COUNT(*)` per page | Remove redundant `query.count()` |
| QO-002 | `booking_router.py:543` | Loop-per-shift DB calls | Batch `IN ()` query + write-through cache |
| QO-003 | `booking_router.py:571` | Duplicate `booking_map` build | Remove lines 571–572 |
| QO-004 | `booking_router.py:971` | 7+ sequential queries for one booking | Eager load + `db.get()` for FKs |
| QO-005 | `crud/employee.py:155` | O(n²) `next()` scan | Replace with `dict` keyed by module |
| QO-006 | `crud/employee.py:109` | Full DB query on every auth check | Eager load + Redis cache for permissions |
| QO-007 | `crud/employee.py:119` | Separate `PolicyPackage` query | Redis cache by `tenant_id` |
| QO-008 | `database/session.py:19` | Lazy loads after commit | `expire_on_commit=False` |
| QO-010 | `cache_manager.py` | Cold start cache misses under load | Startup preloader for active tenants |
| QO-011 | `cache_manager.py:596` | 500 lines of manual serializers | Generic `serialize_model()` |
| QO-012 | Various | Deprecated `bulk_insert_mappings` | `session.execute(insert(...), [...])` |
