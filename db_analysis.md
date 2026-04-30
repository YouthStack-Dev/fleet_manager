# Fleet Manager — Database Analysis

**Date:** 2026-04-30  
**Scope:** Schema design, FK integrity, indexing strategy, data type correctness, migration hygiene, connection management  
**Tools referenced:** SQLAlchemy 2.0.25, Alembic 1.13.1, PostgreSQL 15

---

## 1. Schema Inventory

| Table | PK Type | Row Estimate | FK Count | Indexes |
|-------|---------|--------------|----------|---------|
| `tenants` | `String(50)` | Low (hundreds) | 0 FKs in | ~1 |
| `employees` | `Integer` (auto) | Medium (thousands/tenant) | 3 | 3 unique, 1 composite |
| `drivers` | `Integer` (auto) | Medium | 3 | 5 unique, 1 field index |
| `vehicles` | `Integer` (auto) | Medium | 3 | 6 unique |
| `shifts` | `Integer` (auto) | Low | 1 | 1 unique |
| `bookings` | `Integer` (auto) | High (millions over time) | 4 | 1 status, 1 booking_type, 2 FK indexes |
| `route_management` | `Integer` (auto) | High | 1 (escort only) | 1 composite tenant+status |
| `route_management_bookings` | `Integer` (auto) | High | 1 (route_id only) | 1 unique constraint |
| `iam_roles` | `Integer` (auto) | Low | 1 | 1 unique |
| `iam_policies` | `Integer` (auto) | Low | 1 | 1 unique |
| `iam_policy_packages` | `Integer` (auto) | Low | 1 | — |
| `iam_role_policy` | Composite | Low | 2 | — |
| `iam_policy_permission` | Composite | Low | 2 | — |
| `user_sessions` | `Integer` (auto) | Medium | — | — |

---

## 2. Foreign Key Integrity Issues

### DB-001 — `route_management_bookings.booking_id` Has No FK Constraint

**File:** `app/models/route_management.py:66`  
**Severity:** Critical  
**Cross-reference:** `audit_report.md` AUDIT-005

```python
# Current — no FK
booking_id = Column(Integer, nullable=False)
```

**Impact:**
- A booking can be deleted without cascading to `route_management_bookings`. The orphaned row holds a `booking_id` that no longer exists.
- `booking_router.py:580` already logs this as a warning: `"Missing booking or employee data for booking_id={}"`. This is the exact failure this FK would prevent.
- The `UniqueConstraint("route_id", "booking_id")` on this table provides no referential protection — it only prevents duplicates.

**Corrected Schema:**
```python
booking_id = Column(
    Integer,
    ForeignKey("bookings.booking_id", ondelete="CASCADE"),
    nullable=False,
    index=True  # add index for JOIN performance
)
```

**Required Migration:**
```sql
ALTER TABLE route_management_bookings
  ADD CONSTRAINT fk_rmb_booking_id
  FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
  ON DELETE CASCADE;

CREATE INDEX ix_rmb_booking_id ON route_management_bookings(booking_id);
```

---

### DB-002 — `route_management.assigned_vendor_id / vehicle_id / driver_id` Have No FK Constraints

**File:** `app/models/route_management.py:32–34`  
**Severity:** Critical  
**Cross-reference:** `audit_report.md` AUDIT-006

```python
assigned_vendor_id  = Column(Integer, nullable=True)   # no FK → vendors
assigned_vehicle_id = Column(Integer, nullable=True)   # no FK → vehicles
assigned_driver_id  = Column(Integer, nullable=True)   # no FK → drivers
```

**Impact:**
- A vendor, vehicle, or driver can be deleted or deactivated while routes still reference them. The route details endpoint silently returns `null` for these fields with no error.
- Note that `assigned_escort_id` *does* have a FK to `escorts.escort_id` — the pattern was applied inconsistently.

**Corrected Schema:**
```python
assigned_vendor_id  = Column(Integer, ForeignKey("vendors.vendor_id",  ondelete="SET NULL"), nullable=True, index=True)
assigned_vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True, index=True)
assigned_driver_id  = Column(Integer, ForeignKey("drivers.driver_id",  ondelete="SET NULL"), nullable=True, index=True)
```

`SET NULL` (not `CASCADE`) is correct here: deleting a vendor should not delete the route, only clear the assignment so dispatch can re-assign.

---

### DB-003 — `route_management.tenant_id` Has No FK Constraint

**File:** `app/models/route_management.py:27`

```python
tenant_id = Column(String(50), nullable=False)  # no FK → tenants
```

Every other multi-tenant model references `tenants.tenant_id` with `ForeignKey(..., ondelete="CASCADE")`. `RouteManagement` omits this, so routes are not cleaned up when a tenant is deleted.

**Corrected Schema:**
```python
tenant_id = Column(
    String(50),
    ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
    nullable=False,
    index=True
)
```

---

### DB-004 — `route_management.shift_id` Has No FK Constraint

**File:** `app/models/route_management.py:28`

```python
shift_id = Column(Integer, nullable=True)  # no FK → shifts
```

Routes reference a shift for scheduling context, but a deleted shift leaves `shift_id` pointing to a non-existent record. The booking_router tries to fetch shift data for routes (line 543) and silently continues if not found.

**Corrected Schema:**
```python
shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="SET NULL"), nullable=True, index=True)
```

---

## 3. Missing Indexes

### DB-005 — No Index on `bookings.booking_date`

**File:** `app/models/booking.py`  
**Severity:** High — Performance

The most common query pattern throughout `booking_router.py` is:
```python
query.filter(Booking.tenant_id == tenant_id, Booking.booking_date == date)
```

There is no index on `booking_date`. With millions of booking rows, this results in a full table scan filtered only by `tenant_id` (indexed via FK).

**Required Index:**
```sql
CREATE INDEX ix_bookings_tenant_date
  ON bookings(tenant_id, booking_date);
```

This composite index supports both single-tenant queries and tenant+date queries with an index-only scan.

---

### DB-006 — No Index on `route_management_bookings.booking_id`

**File:** `app/models/route_management.py:66`

`booking_router.py:501–503` queries:
```python
db.query(RouteManagementBooking).filter(
    RouteManagementBooking.booking_id.in_(booking_ids)
)
```

`booking_id` has neither a FK constraint nor an index. With a large route_management_bookings table, the `IN (...)` filter requires a sequential scan.

**Required Index:**
```sql
CREATE INDEX ix_rmb_booking_id ON route_management_bookings(booking_id);
```

---

### DB-007 — No Index on `bookings.employee_id` + `booking_date` for Employee Booking Queries

**File:** `app/models/booking.py`, `app/routes/booking_router.py:729–737`

`get_bookings_by_employee` filters by `employee_id` (and optionally `booking_date`). The `employee_id` FK creates a basic index, but a composite `(employee_id, booking_date)` index would eliminate the post-filter sort needed for date-filtered employee lookups.

**Required Index:**
```sql
CREATE INDEX ix_bookings_employee_date
  ON bookings(employee_id, booking_date);
```

---

### DB-008 — No Index on `user_sessions` Lookup Columns

**File:** `app/services/session_manager.py:98–103`

```python
db.query(UserSession).filter_by(
    user_type=user_type, user_id=user_id, platform=platform, is_active=True
)
```

This pattern is called on every login and every token validation. Without a composite index on `(user_type, user_id, platform, is_active)`, this is a full table scan.

**Required Index:**
```sql
CREATE INDEX ix_user_sessions_lookup
  ON user_sessions(user_type, user_id, platform, is_active);
```

---

## 4. Data Type Issues

### DB-009 — Time Fields Stored as `String(10)` Instead of `Time`

**File:** `app/models/route_management.py:69–74`  
**Cross-reference:** `audit_report.md` AUDIT-028

```python
estimated_pick_up_time = Column(String(10), nullable=True)
actual_pick_up_time    = Column(String(10), nullable=True)
estimated_drop_time    = Column(String(10), nullable=True)
actual_drop_time       = Column(String(10), nullable=True)
```

**Problems:**
1. Time comparisons require casting: `CAST(estimated_pick_up_time AS TIME) > '08:00:00'` — cannot use an index.
2. No format validation: `"25:70:99"` is a valid `String(10)`.
3. Time arithmetic (duration calculation) requires manual parsing.

**Corrected Schema:**
```python
from sqlalchemy import Time
estimated_pick_up_time = Column(Time, nullable=True)
actual_pick_up_time    = Column(Time, nullable=True)
estimated_drop_time    = Column(Time, nullable=True)
actual_drop_time       = Column(Time, nullable=True)
```

**Migration Note:** Existing string data must be converted:
```sql
ALTER TABLE route_management_bookings
  ALTER COLUMN estimated_pick_up_time TYPE TIME
  USING estimated_pick_up_time::TIME;
```

---

### DB-010 — OTPs Stored as Plaintext `Integer`

**Files:** `app/models/booking.py:40–41`, `app/models/route_management.py:39`  
**Cross-reference:** `audit_report.md` AUDIT-029

```python
boarding_otp   = Column(Integer, nullable=True)
deboarding_otp = Column(Integer, nullable=True)
escort_otp     = Column(Integer, nullable=True)
```

A database compromise exposes all active OTPs. OTPs should be hashed (SHA-256, not bcrypt — OTPs are short-lived and require fast verification).

**Corrected Schema:**
```python
boarding_otp_hash   = Column(String(64), nullable=True)  # SHA-256 hex digest
deboarding_otp_hash = Column(String(64), nullable=True)
escort_otp_hash     = Column(String(64), nullable=True)
```

**Verification logic:**
```python
import hashlib
def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp(plain: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(plain), stored_hash)
```

---

### DB-011 — `PolicyPackage.permission_ids` Is a JSON Array Without Referential Integrity

**File:** `app/models/iam/policy.py:28`  
**Cross-reference:** `audit_report.md` AUDIT-027

```python
permission_ids = Column(JSON, nullable=False, default=list)
```

**Problems:**
1. A deleted `iam_permissions` row leaves stale IDs in every `iam_policy_packages` record that referenced it.
2. Cannot query "which packages include permission X?" without a JSON array scan (`@>` operator or `json_array_elements`).
3. No uniqueness enforcement within the array.

**Recommended Replacement:** A proper junction table:
```sql
CREATE TABLE iam_package_permissions (
    package_id    INTEGER NOT NULL REFERENCES iam_policy_packages(package_id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES iam_permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (package_id, permission_id)
);
```

This enables: `SELECT permission_id FROM iam_package_permissions WHERE package_id = ?` — a simple PK lookup.

---

### DB-012 — `Tenant.tenant_id` Uses `String(50)` as Primary Key

**File:** `app/models/tenant.py:10`

```python
tenant_id = Column(String(50), primary_key=True)
```

String PKs are valid, but every FK referencing `tenants.tenant_id` stores a `String(50)` value in every row of every child table (`employees`, `drivers`, `shifts`, `bookings`, etc.). For tables with millions of rows, this inflates index size compared to an integer FK. It also makes the tenant identifier part of the query plan rather than a lookup by integer.

**Assessment:** This is an architectural decision rather than a bug. It is acceptable for current scale. Flag for review if row counts exceed 50M in child tables.

---

## 5. Schema Design Issues

### DB-013 — `extend_existing=True` on All Models Masks Schema Divergence

**Files:** All models in `app/models/`  
**Cross-reference:** `audit_report.md` AUDIT-024

`__table_args__ = {"extend_existing": True}` suppresses SQLAlchemy's `InvalidRequestError` when a table is registered twice. This is a workaround for models being imported from multiple places.

**Risk:** Two model definitions with conflicting column types for the same table will silently coexist. SQLAlchemy will use whichever definition was registered last — behavior that depends on import order.

**Correct Fix:** Ensure each model is imported exactly once via `app/models/__init__.py`. Remove `extend_existing=True` once that is done.

---

### DB-014 — `GenderEnum` Defined Three Times (Schema Inconsistency Risk)

**Files:** `app/models/employee.py:10`, `app/models/driver.py:13`, `app/models/shift.py:19`  
**Cross-reference:** `audit_report.md` AUDIT-015

Because `native_enum=False` is used (PostgreSQL `VARCHAR` with Pydantic validation), the three definitions do not cause a database-level conflict. However, if one enum is updated (e.g., `MALE = "male"` vs `MALE = "Male"`), existing data may fail validation in some routes but not others.

**Fix:** Centralize in `app/models/enums.py` and import from all three model files.

---

## 6. Connection Pool Analysis

**File:** `app/database/session.py`, `app/config.py:17–21`

```
Default pool_size     = 10
Default max_overflow  = 20
Default pool_timeout  = 30 seconds
Default pool_recycle  = 3600 seconds (1 hour)
```

**Analysis:**

| Scenario | Workers | Connections per Worker | Max Total DB Connections |
|----------|---------|----------------------|--------------------------|
| Dev (uvicorn 1 worker) | 1 | 30 | **30** |
| Prod (Gunicorn, 4-core) | 9 | 30 | **270** |
| Prod (Gunicorn, 8-core) | 17 | 30 | **510** |

PostgreSQL 15's default `max_connections = 100`. A 4-core production server will exhaust Postgres connections.

**Recommendations:**

1. **Immediate:** Set `DB_MAX_OVERFLOW=5` and `DB_POOL_SIZE=5` to cap at 10 connections/worker.
2. **Short-term:** Deploy PgBouncer in transaction pooling mode. Connection overhead becomes negligible — use `pool_size=2` per worker.
3. **Long-term:** Set `pool_pre_ping=True` ✅ (already set) and `pool_recycle=1800` (30 min) to avoid stale connections behind a load balancer.

---

## 7. Migration History Analysis

**Files:** `migrations/versions/` (22 files, spanning 2025-12-18 to 2026-04-02)

| Observation | File | Risk |
|-------------|------|------|
| Merge migration required | `20260304_1200_merge_escort_password_and_ride_reviews.py` | Indicates diverging feature branches in the past |
| Comprehensive schema fix migration | `20260402_1510_comprehensive_schema_fix.py` | Name suggests a hotfix; review for partial DDL |
| 3 migrations on same day (2026-03-03) | `20260303_*` | Rapid iteration without testing |
| Missing FK migrations | None found for `route_management_bookings.booking_id` | FK was never added via migration |

**Critical Finding:** The missing FK constraints documented in DB-001 through DB-004 have no corresponding migration files. This means these constraints have never been applied to any environment (dev, staging, or production). The schema in `app/models/` is aspirational for some fields, not reflective of the actual database state.

---

## 8. Recommended Migration Plan

The following new migrations are needed (in dependency order):

```
1. add_route_management_fk_constraints.py
   - ADD FK route_management.tenant_id → tenants.tenant_id
   - ADD FK route_management.shift_id → shifts.shift_id
   - ADD FK route_management.assigned_vendor_id → vendors.vendor_id
   - ADD FK route_management.assigned_vehicle_id → vehicles.vehicle_id
   - ADD FK route_management.assigned_driver_id → drivers.driver_id

2. add_route_management_bookings_fk.py
   - ADD FK route_management_bookings.booking_id → bookings.booking_id
   - CREATE INDEX ix_rmb_booking_id

3. add_missing_indexes.py
   - CREATE INDEX ix_bookings_tenant_date ON bookings(tenant_id, booking_date)
   - CREATE INDEX ix_bookings_employee_date ON bookings(employee_id, booking_date)
   - CREATE INDEX ix_user_sessions_lookup ON user_sessions(user_type, user_id, platform, is_active)
   - CREATE INDEX ix_route_management_tenant_date ON route_management(tenant_id, created_at)

4. convert_time_columns.py
   - ALTER COLUMN estimated_pick_up_time TYPE TIME
   - ALTER COLUMN actual_pick_up_time TYPE TIME
   - ALTER COLUMN estimated_drop_time TYPE TIME
   - ALTER COLUMN actual_drop_time TYPE TIME
   (Requires data integrity check: existing values must be valid time strings)

5. hash_otp_columns.py   (requires application-level data migration first)
   - ADD COLUMN boarding_otp_hash VARCHAR(64)
   - Backfill: UPDATE bookings SET boarding_otp_hash = sha256(boarding_otp::text)
   - DROP COLUMN boarding_otp
   - Same for deboarding_otp and escort_otp in route_management

6. add_package_permissions_junction.py  (long-term)
   - CREATE TABLE iam_package_permissions
   - Migrate data from iam_policy_packages.permission_ids JSON array
   - DROP COLUMN permission_ids from iam_policy_packages
```

**Run Order:** All migrations must run against a locked schema (no concurrent application writes). For FK additions on large tables, use `NOT VALID` + `VALIDATE CONSTRAINT` in two steps to avoid long lock holds:

```sql
-- Step 1: Add constraint without validating existing rows (fast)
ALTER TABLE route_management_bookings
  ADD CONSTRAINT fk_rmb_booking_id
  FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
  NOT VALID;

-- Step 2: Validate in background (does not block writes)
ALTER TABLE route_management_bookings
  VALIDATE CONSTRAINT fk_rmb_booking_id;
```
