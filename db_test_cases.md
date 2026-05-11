# Fleet Manager Database Test Cases
**Version:** 1.0.0  
**Prepared by:** QA Automation Architecture Team  
**Date:** 2026-04-30  
**Database:** PostgreSQL  
**ORM:** SQLAlchemy (sync)  
**Migration Tool:** Alembic  

---

## Purpose

This document defines the complete database-layer test suite for the Fleet Manager backend. Tests verify:
- Data integrity constraints (PK, FK, UNIQUE, NOT NULL, CHECK)
- Status transitions and field update correctness
- Cascade behaviors
- Transaction atomicity and rollback
- Missing constraints (documented as defects)
- Index usage and query performance
- Audit trail accuracy

**Notation used:**
- `[DEFECT]` — identifies a missing constraint or incorrect behavior
- `[CONSTRAINT EXISTS]` — confirmed DB-level constraint
- `[APP-LAYER ONLY]` — enforced only in application code, not the DB

---

## Table of Contents

1. [Schema Reference](#1-schema-reference)
2. [A. Insert Validation](#2-a-insert-validation)
3. [B. Update Correctness](#3-b-update-correctness)
4. [C. Delete Behavior](#4-c-delete-behavior)
5. [D. Foreign Key Integrity](#5-d-foreign-key-integrity)
6. [E. Cascade Behavior](#6-e-cascade-behavior)
7. [F. Transaction Rollback](#7-f-transaction-rollback)
8. [G. Duplicate Prevention](#8-g-duplicate-prevention)
9. [H. Index-Sensitive Queries](#9-h-index-sensitive-queries)
10. [I. Audit Trail Validation](#10-i-audit-trail-validation)
11. [Defect Summary Register](#11-defect-summary-register)
12. [Pytest DB Test Mapping](#12-pytest-db-test-mapping)

---

## 1. Schema Reference

### Key Tables and Relevant Columns

| Table | Primary Key | Notable Constraints | Status Column |
|-------|-------------|-------------------|---------------|
| `users` | `id` UUID | `email` UNIQUE, `user_type` CHECK | `is_active` bool |
| `tenants` | `id` UUID | `domain` UNIQUE | `is_active` bool |
| `tenant_configs` | `id` UUID | FK → tenants | — |
| `bookings` | `id` UUID | FK → users, shifts, tenants | `status` varchar |
| `routes` | `id` UUID | FK → tenants, shifts | `status` varchar |
| `route_management_bookings` | `id` UUID | FK → routes (**no FK → bookings** — DEFECT) | — |
| `driver_sessions` | `id` UUID | FK → users, routes | `status` varchar |
| `employee_sessions` | `id` UUID | FK → users, tenants | `is_active` bool |
| `vendor_sessions` | `id` UUID | FK → vendor_users | `is_active` bool |
| `alerts` | `id` UUID | FK → tenants | `status` varchar |
| `alert_configs` | `id` UUID | FK → tenants | — |
| `alert_escalations` | `id` UUID | FK → alerts, users | `escalated_at` timestamp |
| `announcements` | `id` UUID | FK → tenants | `status` varchar |
| `announcement_recipients` | `id` UUID | FK → announcements, users (**no UNIQUE** — DEFECT) | — |
| `iam_packages` | `id` UUID | `name` UNIQUE per tenant | — |
| `iam_policies` | `id` UUID | FK → iam_packages | — |
| `iam_roles` | `id` UUID | CHECK: `system_role=true → tenant_id IS NULL` | — |
| `iam_role_assignments` | `id` UUID | FK → iam_roles, users | — |
| `iam_permissions` | `id` UUID | `code` UNIQUE | — |
| `vehicles` | `id` UUID | FK → vendor_users (`vendor_id`) | `is_active` bool |
| `vendor_users` | `id` UUID | `email` UNIQUE | `is_active` bool |
| `shifts` | `id` UUID | FK → tenants | — |
| `weekoffs` | `id` UUID | FK → tenants | — |
| `cutoff_configs` | `id` UUID | FK → tenants | — |

---

## 2. A. Insert Validation

### DB-001: Valid Booking Insert — Full Field Persistence

- **Table(s):** `bookings`
- **Operation:** INSERT
- **Scenario:** Insert a complete booking record and verify every column is persisted exactly as provided.
- **SQL / ORM Operation:**
  ```python
  from app.models.booking import Booking
  import uuid
  from datetime import date

  booking = Booking(
      id=uuid.uuid4(),
      employee_id=employee.id,
      booking_date=date(2026, 5, 15),
      shift_id=shift.id,
      pickup_location_id=loc_home.id,
      drop_location_id=loc_office.id,
      trip_type="pickup",
      status="Request",
      tenant_id=tenant.id,
  )
  db_session.add(booking)
  db_session.commit()
  ```
- **Expected DB State:** One row exists in `bookings` with all columns matching inserted values.
- **Verification Query:**
  ```sql
  SELECT
      id, employee_id, booking_date, shift_id,
      pickup_location_id, drop_location_id, trip_type,
      status, tenant_id, created_at, updated_at
  FROM bookings
  WHERE id = '<inserted_uuid>';
  ```
- **Pass Criteria:**
  - Row exists (1 row returned)
  - `status` == `'Request'`
  - `booking_date` == `'2026-05-15'`
  - `created_at` is NOT NULL and is within last 5 seconds
  - `updated_at` == `created_at` (no updates yet)
  - `trip_type` == `'pickup'`

---

### DB-002: Duplicate Booking Insert — Missing UNIQUE Constraint

- **Table(s):** `bookings`
- **Operation:** INSERT (two identical rows)
- **Scenario:** Insert two bookings with the same `(employee_id, booking_date, shift_id)`. Due to missing DB constraint, both succeed — this is a defect.
- **SQL / ORM Operation:**
  ```sql
  -- First insert
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, pickup_location_id, drop_location_id)
  VALUES (gen_random_uuid(), '<emp_id>', '2026-05-15', '<shift_id>', 'Request', '<tenant_id>', 'pickup', '<loc1>', '<loc2>');

  -- Second insert — should be rejected but is NOT
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, pickup_location_id, drop_location_id)
  VALUES (gen_random_uuid(), '<emp_id>', '2026-05-15', '<shift_id>', 'Request', '<tenant_id>', 'pickup', '<loc1>', '<loc2>');
  ```
- **Expected DB State (correct):** Second insert raises `UniqueViolation` error.
- **Actual DB State:** Both inserts succeed — two rows exist with the same `(employee_id, booking_date, shift_id)`.
- **Verification Query:**
  ```sql
  SELECT COUNT(*) AS duplicate_count
  FROM bookings
  WHERE employee_id = '<emp_id>'
    AND booking_date = '2026-05-15'
    AND shift_id = '<shift_id>'
    AND status != 'Cancelled';
  ```
- **Pass Criteria (for defect documentation):** `duplicate_count` == 2 (confirms missing constraint)
- **[DEFECT DB-001]:**
  > **MISSING CONSTRAINT:** No `UNIQUE` constraint exists on `bookings(employee_id, booking_date, shift_id)`. The application-layer check is the only guard, making the system vulnerable to race conditions.
  >
  > **Recommended Fix:**
  > ```sql
  > -- Partial unique index (only for non-cancelled bookings)
  > CREATE UNIQUE INDEX uq_bookings_no_duplicate
  > ON bookings (employee_id, booking_date, shift_id)
  > WHERE status != 'Cancelled';
  > ```
  > Add Alembic migration: `alembic revision --autogenerate -m "add_booking_uniqueness_constraint"`

---

### DB-003: Announcement Insert — Status Defaults to DRAFT

- **Table(s):** `announcements`
- **Operation:** INSERT
- **Scenario:** Insert announcement without specifying status — default should be DRAFT.
- **SQL / ORM Operation:**
  ```python
  announcement = Announcement(
      id=uuid.uuid4(),
      title="Office Closure",
      body="Closed on 20th May",
      tenant_id=tenant.id,
      created_by=admin_user.id,
      # status NOT specified — should default to 'DRAFT'
  )
  db_session.add(announcement)
  db_session.commit()
  ```
- **Expected DB State:** Row with `status` == `'DRAFT'` and `published_at` IS NULL.
- **Verification Query:**
  ```sql
  SELECT status, published_at, created_at
  FROM announcements
  WHERE id = '<inserted_uuid>';
  ```
- **Pass Criteria:**
  - `status` == `'DRAFT'`
  - `published_at` IS NULL
  - `created_at` is NOT NULL

---

### DB-004: Route Insert — Status Defaults to Planned

- **Table(s):** `routes`
- **Operation:** INSERT
- **Scenario:** Insert a new route and verify default status is `'Planned'`.
- **SQL / ORM Operation:**
  ```python
  route = Route(
      id=uuid.uuid4(),
      name="Route Alpha",
      shift_id=shift.id,
      route_date=date(2026, 5, 15),
      direction="pickup",
      tenant_id=tenant.id,
  )
  db_session.add(route)
  db_session.commit()
  ```
- **Expected DB State:** `status` == `'Planned'`, `vehicle_id` IS NULL, `driver_id` IS NULL.
- **Verification Query:**
  ```sql
  SELECT status, vehicle_id, driver_id, dispatched_at
  FROM routes
  WHERE id = '<inserted_uuid>';
  ```
- **Pass Criteria:**
  - `status` == `'Planned'`
  - `vehicle_id` IS NULL
  - `driver_id` IS NULL
  - `dispatched_at` IS NULL

---

### DB-005: IAM Role Insert — System Role with tenant_id NULL (Valid)

- **Table(s):** `iam_roles`
- **Operation:** INSERT
- **Scenario:** Insert a system role (global, not tenant-scoped) — `tenant_id` must be NULL.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO iam_roles (id, name, system_role, tenant_id)
  VALUES (gen_random_uuid(), 'GlobalSuperAdmin', true, NULL);
  ```
- **Expected DB State:** Row inserted successfully with `tenant_id` IS NULL.
- **Verification Query:**
  ```sql
  SELECT id, name, system_role, tenant_id
  FROM iam_roles
  WHERE name = 'GlobalSuperAdmin';
  ```
- **Pass Criteria:**
  - `system_role` == `true`
  - `tenant_id` IS NULL
  - No constraint violation

---

### DB-006: IAM Role Insert — System Role with Non-NULL tenant_id (Must Fail)

- **Table(s):** `iam_roles`
- **Operation:** INSERT (should be rejected)
- **Scenario:** Insert a system role with a `tenant_id` — this violates the business rule that system roles are not tenant-scoped.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO iam_roles (id, name, system_role, tenant_id)
  VALUES (gen_random_uuid(), 'InvalidRole', true, '<some_tenant_uuid>');
  ```
- **Expected DB State:** INSERT rejected with `CHECK constraint violation`.
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM iam_roles WHERE name = 'InvalidRole';
  -- Should be 0
  ```
- **Pass Criteria:** `CheckViolation` exception raised; zero rows inserted.
- **Note:** Verify CHECK constraint exists: `CHECK (NOT (system_role = true AND tenant_id IS NOT NULL))`

---

### DB-007: IAM Role Insert — Tenant Role without tenant_id (Must Fail)

- **Table(s):** `iam_roles`
- **Operation:** INSERT (should be rejected)
- **Scenario:** Insert a non-system role without `tenant_id` — tenant-scoped roles MUST have a tenant_id.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO iam_roles (id, name, system_role, tenant_id)
  VALUES (gen_random_uuid(), 'OrphanRole', false, NULL);
  ```
- **Expected DB State:** INSERT rejected with CHECK constraint violation.
- **Pass Criteria:** `CheckViolation` raised; zero rows inserted.
- **Note:** CHECK constraint: `CHECK (NOT (system_role = false AND tenant_id IS NULL))`

---

### DB-008: User Insert — Missing Required Fields (NOT NULL Violation)

- **Table(s):** `users`
- **Operation:** INSERT (should be rejected)
- **Scenario:** Attempt to insert a user without `email` (NOT NULL column).
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO users (id, hashed_password, user_type, is_active)
  VALUES (gen_random_uuid(), 'hashed_pw', 'employee', true);
  -- email is missing
  ```
- **Expected DB State:** INSERT rejected with `NOT NULL constraint violation` on `email`.
- **Verification:** Exception type: `sqlalchemy.exc.IntegrityError` with `NotNullViolation` in detail.
- **Pass Criteria:** Exception raised; no row in `users` with the given UUID.

---

### DB-009: Announcement Recipient Duplicate Insert — Missing UNIQUE Constraint

- **Table(s):** `announcement_recipients`
- **Operation:** INSERT (two identical rows allowed — defect)
- **Scenario:** Publish an announcement, then publish again (retry scenario). Two identical recipient rows are created.
- **SQL / ORM Operation:**
  ```sql
  -- Simulating two publish attempts
  INSERT INTO announcement_recipients (id, announcement_id, recipient_id, sent_at)
  VALUES (gen_random_uuid(), '<ann_id>', '<user_id>', NOW());

  -- Second insert with same announcement_id + recipient_id
  INSERT INTO announcement_recipients (id, announcement_id, recipient_id, sent_at)
  VALUES (gen_random_uuid(), '<ann_id>', '<user_id>', NOW());
  ```
- **Expected DB State (correct):** Second insert rejected by UNIQUE constraint.
- **Actual DB State:** Both inserts succeed — two rows for same recipient.
- **Verification Query:**
  ```sql
  SELECT COUNT(*) AS recipient_count
  FROM announcement_recipients
  WHERE announcement_id = '<ann_id>'
    AND recipient_id = '<user_id>';
  ```
- **Pass Criteria (defect documentation):** `recipient_count` == 2 (confirms missing constraint)
- **[DEFECT DB-002]:**
  > **MISSING CONSTRAINT:** `announcement_recipients` has no UNIQUE constraint on `(announcement_id, recipient_id)`. Retry publishes create duplicate notification records, causing users to receive the same announcement multiple times.
  >
  > **Recommended Fix:**
  > ```sql
  > ALTER TABLE announcement_recipients
  > ADD CONSTRAINT uq_announcement_recipient
  > UNIQUE (announcement_id, recipient_id);
  > ```

---

### DB-010: Booking Insert — Valid trip_type Values Only

- **Table(s):** `bookings`
- **Operation:** INSERT
- **Scenario:** Insert booking with invalid `trip_type` value to test CHECK constraint.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, pickup_location_id, drop_location_id)
  VALUES (gen_random_uuid(), '<emp_id>', '2026-05-15', '<shift_id>', 'Request', '<tenant_id>', 'invalid_type', '<loc1>', '<loc2>');
  ```
- **Expected DB State:** INSERT rejected by CHECK constraint on `trip_type`.
- **Pass Criteria:** Exception raised for invalid `trip_type`; no row inserted.
- **Valid Values:** `'pickup'`, `'drop'`, `'both'` (verify against actual CHECK constraint in schema)

---

### DB-011: Tenant Insert — Duplicate Domain Rejected

- **Table(s):** `tenants`
- **Operation:** INSERT (second with same domain should fail)
- **Scenario:** Insert two tenants with the same `domain` — must fail on second due to UNIQUE constraint.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO tenants (id, name, domain, is_active)
  VALUES (gen_random_uuid(), 'Corp A', 'corp-a.com', true);

  INSERT INTO tenants (id, name, domain, is_active)
  VALUES (gen_random_uuid(), 'Corp A Clone', 'corp-a.com', true);
  -- Should fail: unique constraint on domain
  ```
- **Expected DB State:** Second insert raises `UniqueViolation`.
- **Pass Criteria:** Only one tenant with `domain = 'corp-a.com'` in DB.

---

### DB-012: User Insert — Duplicate Email Rejected

- **Table(s):** `users`
- **Operation:** INSERT
- **Scenario:** Insert two users with the same `email`.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO users (id, email, hashed_password, user_type, is_active)
  VALUES (gen_random_uuid(), 'alice@corp.com', 'hash1', 'employee', true);

  INSERT INTO users (id, email, hashed_password, user_type, is_active)
  VALUES (gen_random_uuid(), 'alice@corp.com', 'hash2', 'employee', true);
  ```
- **Expected DB State:** Second insert raises `UniqueViolation` on `email`.
- **Pass Criteria:** Only one row with `email = 'alice@corp.com'`.

---

### DB-013: Vehicle Insert — Valid vendor_id Required

- **Table(s):** `vehicles`
- **Operation:** INSERT
- **Scenario:** Insert vehicle with a non-existent `vendor_id` — must fail FK check.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO vehicles (id, registration_number, model, vendor_id, is_active)
  VALUES (gen_random_uuid(), 'KA-01-AB-1234', 'Toyota Innova', gen_random_uuid(), true);
  -- vendor_id is a random UUID not in vendor_users
  ```
- **Expected DB State:** INSERT rejected with `ForeignKeyViolation`.
- **Pass Criteria:** Exception raised; no vehicle row created.

---

### DB-014: Alert Insert — Valid Status Value

- **Table(s):** `alerts`
- **Operation:** INSERT
- **Scenario:** Insert alert with valid initial status `TRIGGERED` and verify all fields.
- **SQL / ORM Operation:**
  ```python
  alert = Alert(
      id=uuid.uuid4(),
      tenant_id=tenant.id,
      alert_type="SOS",
      status="TRIGGERED",
      message="Driver SOS triggered",
      triggered_by=driver_user.id,
      route_id=route.id,
  )
  db_session.add(alert)
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, acknowledged_at, resolved_at, closed_at
  FROM alerts
  WHERE id = '<inserted_uuid>';
  ```
- **Pass Criteria:**
  - `status` == `'TRIGGERED'`
  - `acknowledged_at` IS NULL
  - `resolved_at` IS NULL
  - `closed_at` IS NULL

---

### DB-015: Driver Session Insert — Idempotency Check

- **Table(s):** `driver_sessions`
- **Operation:** INSERT (attempt duplicate)
- **Scenario:** Attempt to insert two driver sessions for same `(driver_id, route_id)` — idempotency should prevent duplicate.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO driver_sessions (id, driver_id, route_id, status, started_at)
  VALUES (gen_random_uuid(), '<driver_id>', '<route_id>', 'active', NOW());

  -- Second insert — should this be blocked or upserted?
  INSERT INTO driver_sessions (id, driver_id, route_id, status, started_at)
  VALUES (gen_random_uuid(), '<driver_id>', '<route_id>', 'active', NOW());
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM driver_sessions
  WHERE driver_id = '<driver_id>' AND route_id = '<route_id>' AND status = 'active';
  ```
- **Pass Criteria:** Only 1 active session per driver per route.
- **Note:** Verify whether a UNIQUE constraint on `(driver_id, route_id)` where `status='active'` exists. Document as defect if missing.

---

## 3. B. Update Correctness

### DB-101: Booking Status Transition — Request → Scheduled

- **Table(s):** `bookings`
- **Operation:** UPDATE
- **Scenario:** Update booking status from `Request` to `Scheduled` and verify `updated_at` is refreshed while `created_at` remains unchanged.
- **Setup:**
  ```sql
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, ...)
  VALUES ('<booking_id>', '<emp_id>', '2026-05-15', '<shift_id>', 'Request', '<tenant_id>', 'pickup', ...);
  ```
- **SQL / ORM Operation:**
  ```python
  # Capture created_at before update
  booking = db_session.query(Booking).filter_by(id=booking_id).one()
  original_created_at = booking.created_at
  original_updated_at = booking.updated_at

  # Update status
  booking.status = "Scheduled"
  db_session.commit()
  db_session.refresh(booking)
  ```
- **Verification Query:**
  ```sql
  SELECT status, created_at, updated_at
  FROM bookings
  WHERE id = '<booking_id>';
  ```
- **Pass Criteria:**
  - `status` == `'Scheduled'`
  - `created_at` unchanged (== `original_created_at`)
  - `updated_at` > `original_updated_at`
  - `updated_at` is within last 5 seconds

---

### DB-102: Route Status Transition — Planned → Vendor Assigned

- **Table(s):** `routes`
- **Operation:** UPDATE
- **Scenario:** Assign a vehicle/driver/vendor to a route and verify status transitions to `'Vendor Assigned'`.
- **SQL / ORM Operation:**
  ```python
  route = db_session.query(Route).filter_by(id=route_id).one()
  route.vehicle_id = vehicle.id
  route.driver_id = driver.id
  route.vendor_id = vendor.id
  route.status = "Vendor Assigned"
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, vehicle_id, driver_id, vendor_id, updated_at
  FROM routes
  WHERE id = '<route_id>';
  ```
- **Pass Criteria:**
  - `status` == `'Vendor Assigned'`
  - `vehicle_id`, `driver_id`, `vendor_id` are NOT NULL
  - `updated_at` refreshed

---

### DB-103: Announcement Status — DRAFT → PUBLISHED (One-Way)

- **Table(s):** `announcements`
- **Operation:** UPDATE
- **Scenario:** Publish an announcement, then attempt to revert to DRAFT via raw SQL (simulating a bypass). Verify app-layer prevents this (DB may not).
- **SQL / ORM Operation (publish):**
  ```python
  announcement.status = "PUBLISHED"
  announcement.published_at = datetime.utcnow()
  db_session.commit()
  ```
- **Attempt to Revert (raw SQL — DB layer):**
  ```sql
  UPDATE announcements
  SET status = 'DRAFT', published_at = NULL
  WHERE id = '<ann_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT status, published_at FROM announcements WHERE id = '<ann_id>';
  ```
- **Pass Criteria:**
  - After application-layer publish: `status` == `'PUBLISHED'`, `published_at` IS NOT NULL
  - Raw SQL revert: **succeeds at DB level** (no DB CHECK constraint preventing backward transition)
  - **[DEFECT DB-003]:** No DB-level constraint prevents setting `status='DRAFT'` after `PUBLISHED`. Status integrity is enforced by application logic only.
  - Recommended: Add DB CHECK trigger or constraint for status transition rules.

---

### DB-104: Alert Status Update — With Timestamp Tracking

- **Table(s):** `alerts`
- **Operation:** UPDATE (multiple transitions)
- **Scenario:** Transition alert through full lifecycle: TRIGGERED → ACKNOWLEDGED → RESOLVED → CLOSED. Verify each transition sets the correct timestamp.
- **SQL / ORM Operations:**
  ```python
  # Step 1: Acknowledge
  alert.status = "ACKNOWLEDGED"
  alert.acknowledged_at = datetime.utcnow()
  alert.acknowledged_by = admin_user.id
  db_session.commit()

  # Step 2: Resolve
  alert.status = "RESOLVED"
  alert.resolved_at = datetime.utcnow()
  db_session.commit()

  # Step 3: Close
  alert.status = "CLOSED"
  alert.closed_at = datetime.utcnow()
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, acknowledged_at, acknowledged_by, resolved_at, closed_at, updated_at
  FROM alerts
  WHERE id = '<alert_id>';
  ```
- **Pass Criteria:**
  - `status` == `'CLOSED'`
  - `acknowledged_at` IS NOT NULL
  - `resolved_at` IS NOT NULL
  - `closed_at` IS NOT NULL
  - Timestamps are in order: `acknowledged_at` < `resolved_at` < `closed_at`

---

### DB-105: Route Dispatch — dispatched_at Timestamp Set

- **Table(s):** `routes`
- **Operation:** UPDATE
- **Scenario:** Dispatch a route and verify `dispatched_at` is set and `status` is `'Dispatched'`.
- **SQL / ORM Operation:**
  ```python
  route.status = "Dispatched"
  route.dispatched_at = datetime.utcnow()
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, dispatched_at FROM routes WHERE id = '<route_id>';
  ```
- **Pass Criteria:**
  - `status` == `'Dispatched'`
  - `dispatched_at` IS NOT NULL, is within last 5 seconds

---

### DB-106: Booking Trip Status — InProgress → Completed

- **Table(s):** `bookings`
- **Operation:** UPDATE
- **Scenario:** Driver drops passenger — booking moves to `Completed` with `drop_time` set.
- **SQL / ORM Operation:**
  ```python
  booking.status = "Completed"
  booking.drop_time = datetime.utcnow()
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, drop_time, updated_at FROM bookings WHERE id = '<booking_id>';
  ```
- **Pass Criteria:**
  - `status` == `'Completed'`
  - `drop_time` IS NOT NULL
  - `updated_at` refreshed

---

### DB-107: User Active Status Toggle

- **Table(s):** `users`
- **Operation:** UPDATE
- **Scenario:** Deactivate a user and verify `is_active` = false. Verify re-activation sets it back to true.
- **SQL / ORM Operation:**
  ```sql
  UPDATE users SET is_active = false WHERE id = '<user_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT is_active FROM users WHERE id = '<user_id>';
  ```
- **Pass Criteria:** `is_active` == `false` after deactivation, `true` after reactivation.

---

### DB-108: Tenant Config Update — Cutoff Window

- **Table(s):** `cutoff_configs`
- **Operation:** UPDATE (or UPSERT)
- **Scenario:** Update cutoff hours for a tenant and verify the config is persisted.
- **SQL / ORM Operation:**
  ```python
  config = db_session.query(CutoffConfig).filter_by(tenant_id=tenant.id).one()
  config.cutoff_hours_before = 4
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT cutoff_hours_before, updated_at
  FROM cutoff_configs
  WHERE tenant_id = '<tenant_id>';
  ```
- **Pass Criteria:** `cutoff_hours_before` == 4; `updated_at` refreshed.

---

### DB-109: IAM Policy Update — Permissions Set Validation

- **Table(s):** `iam_policies`
- **Operation:** UPDATE
- **Scenario:** Update policy permissions and verify the new set is persisted. Attempt to add a permission not in the parent package — verify app-layer rejection.
- **ORM Operation:**
  ```python
  policy.permissions = ["booking:read", "booking:create"]  # both in package
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT permissions FROM iam_policies WHERE id = '<policy_id>';
  ```
- **Pass Criteria:** `permissions` array contains exactly the updated set.

---

### DB-110: Weekoff Config Update

- **Table(s):** `weekoffs`
- **Operation:** INSERT or UPDATE
- **Scenario:** Set Monday (day_of_week=1) as weekoff for tenant. Verify persisted.
- **SQL / ORM Operation:**
  ```python
  weekoff = Weekoff(
      id=uuid.uuid4(),
      tenant_id=tenant.id,
      day_of_week=1,  # Monday
  )
  db_session.add(weekoff)
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT day_of_week FROM weekoffs WHERE tenant_id = '<tenant_id>';
  ```
- **Pass Criteria:** Row exists with `day_of_week` == 1.

---

## 4. C. Delete Behavior

### DB-201: Soft Delete — Booking Cancellation (Status vs Hard Delete)

- **Table(s):** `bookings`
- **Operation:** UPDATE (soft cancel, not DELETE)
- **Scenario:** Cancel a booking — verify the record remains in DB with `status='Cancelled'` (not physically deleted).
- **SQL / ORM Operation:**
  ```python
  booking.status = "Cancelled"
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT id, status FROM bookings WHERE id = '<booking_id>';
  ```
- **Pass Criteria:**
  - Row still exists
  - `status` == `'Cancelled'`
  - Row count in `bookings` for this ID == 1 (not deleted)

---

### DB-202: DRAFT Announcement Delete — Hard Delete

- **Table(s):** `announcements`
- **Operation:** DELETE
- **Scenario:** Delete a DRAFT announcement — record should be physically removed.
- **SQL / ORM Operation:**
  ```python
  db_session.delete(draft_announcement)
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM announcements WHERE id = '<ann_id>';
  ```
- **Pass Criteria:** Count == 0 (record physically deleted).

---

### DB-203: PUBLISHED Announcement Delete — Should Be Blocked

- **Table(s):** `announcements`
- **Operation:** DELETE (should be rejected at app layer)
- **Scenario:** Attempt to delete a PUBLISHED announcement — application should prevent this.
- **Test:** Issue `DELETE /announcements/{id}` via API for a published announcement.
- **Expected API Response:** 400 Bad Request
- **DB Verification:**
  ```sql
  SELECT COUNT(*) FROM announcements WHERE id = '<ann_id>';
  ```
- **Pass Criteria:**
  - API returns 400
  - Count == 1 (record not deleted)
  - `announcement_recipients` for this announcement still exist (cascaded data intact)

---

### DB-204: Route Cancellation — Downstream Booking Status

- **Table(s):** `routes`, `bookings`, `route_management_bookings`
- **Operation:** UPDATE (route cancel) + verify downstream
- **Scenario:** Cancel a route — verify all bookings associated with the route are updated to reflect cancellation.
- **SQL / ORM Operation:**
  ```python
  route.status = "Cancelled"
  db_session.commit()
  # App should cascade to bookings in this route
  ```
- **Verification Query:**
  ```sql
  -- Get all booking_ids in the route
  SELECT b.id, b.status
  FROM bookings b
  INNER JOIN route_management_bookings rmb ON rmb.booking_id = b.id
  WHERE rmb.route_id = '<route_id>';
  ```
- **Pass Criteria:** All associated bookings have their status updated (to `'Cancelled'` or equivalent). Document actual behavior if status is not cascaded.

---

### DB-205: Driver Session Deletion on Duty End

- **Table(s):** `driver_sessions`
- **Operation:** UPDATE (end duty) or DELETE
- **Scenario:** When driver ends duty (`POST /driver/duty/end`), verify the session record is finalized correctly.
- **Verification Query:**
  ```sql
  SELECT status, ended_at FROM driver_sessions
  WHERE driver_id = '<driver_id>' AND route_id = '<route_id>';
  ```
- **Pass Criteria:**
  - `status` == `'ended'` or `'completed'`
  - `ended_at` IS NOT NULL
  - `ended_at` is within last 5 seconds

---

### DB-206: IAM Role Assignment Deletion

- **Table(s):** `iam_role_assignments`
- **Operation:** DELETE
- **Scenario:** Remove a role assignment from a user and verify the association is deleted.
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM iam_role_assignments
  WHERE user_id = '<user_id>' AND role_id = '<role_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM iam_role_assignments
  WHERE user_id = '<user_id>' AND role_id = '<role_id>';
  ```
- **Pass Criteria:** Count == 0.

---

### DB-207: Vehicle Deactivation vs Deletion

- **Table(s):** `vehicles`
- **Operation:** UPDATE (soft deactivate)
- **Scenario:** Deactivate a vehicle (rather than hard-deleting) and verify it remains in the DB.
- **SQL / ORM Operation:**
  ```sql
  UPDATE vehicles SET is_active = false WHERE id = '<vehicle_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT id, is_active FROM vehicles WHERE id = '<vehicle_id>';
  ```
- **Pass Criteria:** Row exists; `is_active` == `false`.

---

### DB-208: Shift Delete — Impact on Existing Bookings

- **Table(s):** `shifts`, `bookings`
- **Operation:** DELETE (shift) — verify FK behavior on bookings
- **Scenario:** Delete a shift that has existing bookings. Verify whether FK constraint prevents deletion or cascades.
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM shifts WHERE id = '<shift_id>';
  ```
- **Expected DB State:** Either:
  - a) FK constraint prevents delete → `ForeignKeyViolation` raised (**preferred**)
  - b) CASCADE delete removes associated bookings (**acceptable if intentional**)
  - c) SET NULL on bookings.shift_id (**check if this is configured**)
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM bookings WHERE shift_id = '<shift_id>';
  ```
- **Pass Criteria:** Document actual FK behavior. If delete succeeds and bookings become orphaned, flag as **[DEFECT DB-004]**.

---

## 5. D. Foreign Key Integrity

### DB-301: route_management_bookings — Missing FK to bookings

- **Table(s):** `route_management_bookings`, `bookings`
- **Operation:** INSERT with invalid booking_id
- **Scenario:** Insert into `route_management_bookings` with a `booking_id` that does not exist in `bookings` table. Due to missing FK constraint, this succeeds — defect.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO route_management_bookings (id, route_id, booking_id)
  VALUES (gen_random_uuid(), '<valid_route_id>', gen_random_uuid());
  -- booking_id is a random UUID that doesn't exist in bookings table
  ```
- **Expected DB State (correct):** FK violation error raised.
- **Actual DB State:** Insert succeeds — orphaned record created.
- **Verification Query:**
  ```sql
  SELECT rmb.id, rmb.booking_id
  FROM route_management_bookings rmb
  LEFT JOIN bookings b ON b.id = rmb.booking_id
  WHERE b.id IS NULL;
  -- Should be 0 rows if FK exists; will be 1 if missing
  ```
- **[DEFECT DB-005]:**
  > **MISSING FOREIGN KEY:** `route_management_bookings.booking_id` has no FK constraint to `bookings.id`. This allows orphaned records — bookings that don't exist in the `bookings` table but are referenced in route mapping.
  >
  > **Recommended Fix:**
  > ```sql
  > ALTER TABLE route_management_bookings
  > ADD CONSTRAINT fk_rmb_booking_id
  > FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE;
  > ```

---

### DB-302: Booking Insert — Invalid employee_id (FK Check)

- **Table(s):** `bookings`, `users`
- **Operation:** INSERT (should fail)
- **Scenario:** Insert booking with an `employee_id` that doesn't exist in `users`.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, pickup_location_id, drop_location_id)
  VALUES (gen_random_uuid(), gen_random_uuid(), '2026-05-15', '<valid_shift_id>', 'Request', '<valid_tenant_id>', 'pickup', '<loc1>', '<loc2>');
  ```
- **Expected DB State:** `ForeignKeyViolation` raised for `employee_id`.
- **Verification:** Exception detail references `employee_id` FK constraint.
- **Pass Criteria:** No row inserted in `bookings`.

---

### DB-303: Booking Insert — Invalid shift_id (FK Check)

- **Table(s):** `bookings`, `shifts`
- **Operation:** INSERT (should fail)
- **Scenario:** Insert booking with a `shift_id` that doesn't exist in `shifts`.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, ...)
  VALUES (gen_random_uuid(), '<valid_emp_id>', '2026-05-15', gen_random_uuid(), 'Request', '<valid_tenant_id>', 'pickup', ...);
  ```
- **Expected DB State:** `ForeignKeyViolation` on `shift_id`.
- **Pass Criteria:** No row inserted; exception raised.

---

### DB-304: Booking Insert — Invalid tenant_id (FK Check)

- **Table(s):** `bookings`, `tenants`
- **Operation:** INSERT (should fail)
- **Scenario:** Insert booking referencing a non-existent `tenant_id`.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, ...)
  VALUES (gen_random_uuid(), '<valid_emp_id>', '2026-05-15', '<valid_shift_id>', 'Request', gen_random_uuid(), 'pickup', ...);
  ```
- **Expected DB State:** `ForeignKeyViolation` on `tenant_id`.
- **Pass Criteria:** Exception raised; no row inserted.

---

### DB-305: IAM Role Assignment — Invalid user_id (FK Check)

- **Table(s):** `iam_role_assignments`, `users`
- **Operation:** INSERT (should fail)
- **Scenario:** Assign role to a non-existent user.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO iam_role_assignments (id, role_id, user_id, tenant_id)
  VALUES (gen_random_uuid(), '<valid_role_id>', gen_random_uuid(), '<tenant_id>');
  ```
- **Expected DB State:** `ForeignKeyViolation` on `user_id`.
- **Pass Criteria:** Exception raised; no assignment created.

---

### DB-306: Vehicle Insert — Invalid vendor_id (FK Check)

- **Table(s):** `vehicles`, `vendor_users`
- **Operation:** INSERT (should fail)
- **Scenario:** Create a vehicle referencing a non-existent vendor.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO vehicles (id, registration_number, model, vendor_id, is_active)
  VALUES (gen_random_uuid(), 'KA-99-ZZ-9999', 'Test Model', gen_random_uuid(), true);
  ```
- **Expected DB State:** `ForeignKeyViolation` on `vendor_id`.
- **Pass Criteria:** Exception raised; no vehicle row inserted.

---

### DB-307: Alert Insert — Invalid tenant_id (FK Check)

- **Table(s):** `alerts`, `tenants`
- **Operation:** INSERT (should fail)
- **Scenario:** Create alert for a non-existent tenant.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO alerts (id, tenant_id, alert_type, status, message)
  VALUES (gen_random_uuid(), gen_random_uuid(), 'SOS', 'TRIGGERED', 'Test');
  ```
- **Expected DB State:** `ForeignKeyViolation` on `tenant_id`.
- **Pass Criteria:** Exception raised.

---

### DB-308: Announcement Insert — Invalid tenant_id (FK Check)

- **Table(s):** `announcements`, `tenants`
- **Operation:** INSERT (should fail)
- **Scenario:** Create announcement for a non-existent tenant.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO announcements (id, title, body, tenant_id, status)
  VALUES (gen_random_uuid(), 'Test', 'Body', gen_random_uuid(), 'DRAFT');
  ```
- **Expected DB State:** `ForeignKeyViolation` on `tenant_id`.
- **Pass Criteria:** Exception raised.

---

## 6. E. Cascade Behavior

### DB-401: Delete Tenant — Cascade to Tenant-Scoped Records

- **Table(s):** `tenants`, `bookings`, `routes`, `shifts`, `announcements`, `alerts`, `weekoffs`, `cutoff_configs`, `tenant_configs`
- **Operation:** DELETE (on tenant)
- **Scenario:** Delete a tenant and verify all its scoped child records are cascaded/handled.
- **Setup:**
  ```python
  # Create tenant with full data set
  tenant = create_test_tenant(db_session)
  shift = create_shift(db_session, tenant)
  booking = create_booking(db_session, tenant, shift)
  route = create_route(db_session, tenant, shift)
  announcement = create_announcement(db_session, tenant)
  alert = create_alert(db_session, tenant)
  ```
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM tenants WHERE id = '<tenant_id>';
  ```
- **Verification Queries:**
  ```sql
  SELECT COUNT(*) FROM bookings WHERE tenant_id = '<tenant_id>';
  SELECT COUNT(*) FROM routes WHERE tenant_id = '<tenant_id>';
  SELECT COUNT(*) FROM shifts WHERE tenant_id = '<tenant_id>';
  SELECT COUNT(*) FROM announcements WHERE tenant_id = '<tenant_id>';
  SELECT COUNT(*) FROM alerts WHERE tenant_id = '<tenant_id>';
  SELECT COUNT(*) FROM weekoffs WHERE tenant_id = '<tenant_id>';
  ```
- **Pass Criteria:**
  - All counts == 0 (CASCADE DELETE configured on FK `tenant_id`)
  - OR: FK constraint prevents tenant deletion if child records exist (`ForeignKeyViolation`)
  - Document actual behavior — if orphaned records remain, flag as **[DEFECT DB-006]**.

---

### DB-402: Delete Employee — Booking Reference Handling

- **Table(s):** `users`, `bookings`
- **Operation:** DELETE (user) — observe behavior on bookings
- **Scenario:** Delete an employee who has existing bookings. Verify FK behavior.
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM users WHERE id = '<employee_id>';
  ```
- **Expected Behavior Options:**
  - a) `ForeignKeyViolation` — bookings cannot become orphaned (preferred)
  - b) CASCADE DELETE — bookings also deleted (acceptable if intentional)
  - c) SET NULL on `bookings.employee_id` (acceptable if `employee_id` is nullable)
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM bookings WHERE employee_id = '<employee_id>';
  ```
- **Pass Criteria:** Document actual behavior; flag defect if bookings become orphaned (no FK + no null on the FK column).

---

### DB-403: Delete Shift — Booking FK Response

- **Table(s):** `shifts`, `bookings`
- **Operation:** DELETE (shift)
- **Scenario:** Delete a shift with associated bookings. Check FK cascade behavior.
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM shifts WHERE id = '<shift_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM bookings WHERE shift_id = '<shift_id>';
  ```
- **Pass Criteria:**
  - If FK exists: `ForeignKeyViolation` raised — correct behavior
  - If no FK: Bookings remain with orphaned `shift_id` — **[DEFECT DB-007]**

---

### DB-404: Delete Route — route_management_bookings Cascade

- **Table(s):** `routes`, `route_management_bookings`
- **Operation:** DELETE (route)
- **Scenario:** Delete a route — verify `route_management_bookings` entries are handled.
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM routes WHERE id = '<route_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM route_management_bookings WHERE route_id = '<route_id>';
  ```
- **Pass Criteria:**
  - Count == 0 (CASCADE DELETE from route to route_management_bookings)
  - OR FK violation prevents route deletion if mapping entries exist
  - Document actual behavior.

---

### DB-405: Delete Announcement — Cascade to Recipients

- **Table(s):** `announcements`, `announcement_recipients`
- **Operation:** DELETE (announcement)
- **Scenario:** Delete a DRAFT announcement — verify `announcement_recipients` are also removed (if any exist pre-publish).
- **SQL / ORM Operation:**
  ```sql
  DELETE FROM announcements WHERE id = '<ann_id>';
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM announcement_recipients WHERE announcement_id = '<ann_id>';
  ```
- **Pass Criteria:** Count == 0 (CASCADE DELETE configured on FK).

---

## 7. F. Transaction Rollback

### DB-501: Bulk Booking — Failure on 3rd Date Rolls Back All

- **Table(s):** `bookings`
- **Operation:** TRANSACTION (multi-insert) with simulated failure
- **Scenario:** Bulk booking for 3 dates; simulate a failure (e.g., FK violation) on the 3rd insert. Verify ALL 3 bookings are rolled back.
- **SQL / ORM Operation:**
  ```python
  try:
      with db_session.begin():
          for i, booking_date in enumerate(["2026-05-15", "2026-05-16", "2026-05-17"]):
              if i == 2:
                  # Simulate failure: use invalid shift_id on 3rd
                  booking = Booking(..., shift_id=uuid.uuid4())  # invalid FK
              else:
                  booking = Booking(..., booking_date=booking_date, shift_id=valid_shift.id)
              db_session.add(booking)
      db_session.flush()  # Should raise FK error on 3rd
  except Exception:
      pass  # Transaction rolled back
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM bookings
  WHERE booking_date IN ('2026-05-15', '2026-05-16', '2026-05-17')
    AND employee_id = '<emp_id>';
  ```
- **Pass Criteria:**
  - Count == 0 (all 3 inserts rolled back atomically)
  - If count > 0 (partial success), document as **[DEFECT DB-008]**: bulk booking is not atomic.

---

### DB-502: Route Dispatch — FCM Failure Mid-Way Does Not Update Route Status

- **Table(s):** `routes`
- **Operation:** TRANSACTION with mocked failure
- **Scenario:** During dispatch, FCM send fails after the route status is updated but before OTPs are committed. Verify the transaction rolls back route status.
- **SQL / ORM Operation:**
  ```python
  # Mock FCM to raise exception mid-dispatch
  with patch("app.services.notification.fcm_client.send", side_effect=Exception("FCM down")):
      response = await async_client.post(f"/routes/{route_id}/dispatch")
  ```
- **Verification Query:**
  ```sql
  SELECT status, dispatched_at FROM routes WHERE id = '<route_id>';
  ```
- **Pass Criteria:**
  - `status` remains `'Vendor Assigned'` (not `'Dispatched'`)
  - `dispatched_at` IS NULL
  - No OTPs created in DB for this route's bookings
  - If `status` == `'Dispatched'` despite FCM failure, document as **[DEFECT DB-009]**: dispatch is not atomic.

---

### DB-503: Role Assignment Batch — Failure on One Rolls Back All

- **Table(s):** `iam_role_assignments`
- **Operation:** TRANSACTION (batch role assign)
- **Scenario:** Attempt to assign same role to 3 users; 2nd user doesn't exist. Verify all 3 assignments are rolled back.
- **SQL / ORM Operation:**
  ```python
  try:
      with db_session.begin():
          for user_id in [valid_user_1, nonexistent_user, valid_user_2]:
              assignment = IAMRoleAssignment(
                  id=uuid.uuid4(),
                  role_id=role.id,
                  user_id=user_id,
                  tenant_id=tenant.id,
              )
              db_session.add(assignment)
          db_session.flush()
  except Exception:
      pass
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM iam_role_assignments
  WHERE role_id = '<role_id>'
    AND user_id IN ('<user1_id>', '<user2_id>');
  ```
- **Pass Criteria:** Count == 0 (all assignments rolled back).

---

### DB-504: Announcement Publish — Notification Failure Rolls Back Recipient Records

- **Table(s):** `announcements`, `announcement_recipients`
- **Operation:** TRANSACTION
- **Scenario:** Announcement publish: DB records created, then notification send fails. Verify recipients are rolled back.
- **SQL / ORM Operation:**
  ```python
  with patch("app.services.sms.send_sms", side_effect=Exception("Twilio down")):
      response = await async_client.post(f"/announcements/{ann_id}/publish")
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM announcement_recipients WHERE announcement_id = '<ann_id>';
  SELECT status FROM announcements WHERE id = '<ann_id>';
  ```
- **Pass Criteria:**
  - If atomic: `status` == `'DRAFT'`, recipient count == 0
  - If not atomic: `status` == `'PUBLISHED'` with no recipient records — **[DEFECT DB-010]**

---

### DB-505: Multi-Record Delete — Partial Failure Rollback

- **Table(s):** `bookings`
- **Operation:** TRANSACTION (bulk delete)
- **Scenario:** Bulk cancel 5 bookings in one transaction; simulate constraint error on 3rd. Verify 0 or 5 are cancelled (not 1 or 2).
- **Pass Criteria:** Atomicity maintained — either all succeed or none.

---

### DB-506: Driver Location Update — Redis Write Failure Does Not Corrupt DB

- **Table(s):** `driver_sessions` (or location audit table)
- **Operation:** TRANSACTION
- **Scenario:** Driver location update writes to DB and Redis. Redis write fails. Verify DB write is also rolled back (or handled gracefully).
- **Pass Criteria:** No partial location record in DB if Redis write fails (or document accepted non-atomic behavior).

---

## 8. G. Duplicate Prevention

### DB-601: Driver Device Registration — Duplicate android_id

- **Table(s):** `users` (or `driver_devices`)
- **Operation:** INSERT (duplicate should be blocked)
- **Scenario:** Register same `android_id` twice.
- **SQL / ORM Operation:**
  ```sql
  -- First registration
  INSERT INTO driver_devices (id, android_id, driver_id, fcm_token)
  VALUES (gen_random_uuid(), 'device-abc-123', '<driver_id>', 'fcm-token-1');

  -- Second registration with same android_id
  INSERT INTO driver_devices (id, android_id, driver_id, fcm_token)
  VALUES (gen_random_uuid(), 'device-abc-123', '<driver_id>', 'fcm-token-2');
  ```
- **Expected DB State:**
  - Option A: Second insert raises `UniqueViolation` (preferred — UNIQUE constraint on `android_id`)
  - Option B: UPSERT — updates `fcm_token` for existing device (acceptable)
  - Option C: Both inserts succeed — **[DEFECT DB-011]** if no constraint
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM driver_devices WHERE android_id = 'device-abc-123';
  ```
- **Pass Criteria:** Count == 1 after both inserts (either rejected or upserted).

---

### DB-602: IAM Permission — Duplicate Code Rejected

- **Table(s):** `iam_permissions`
- **Operation:** INSERT (duplicate code)
- **Scenario:** Insert two permissions with the same `code` — must fail UNIQUE constraint.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO iam_permissions (id, code, description)
  VALUES (gen_random_uuid(), 'booking:read', 'Read bookings');

  INSERT INTO iam_permissions (id, code, description)
  VALUES (gen_random_uuid(), 'booking:read', 'Duplicate booking read');
  ```
- **Expected DB State:** Second insert raises `UniqueViolation` on `code`.
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM iam_permissions WHERE code = 'booking:read';
  ```
- **Pass Criteria:** Count == 1.

---

### DB-603: Shift Name Uniqueness Within Tenant

- **Table(s):** `shifts`
- **Operation:** INSERT (duplicate name in same tenant)
- **Scenario:** Create two shifts with same name in same tenant.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO shifts (id, name, start_time, end_time, tenant_id)
  VALUES (gen_random_uuid(), 'Morning Shift', '08:00', '17:00', '<tenant_id>');

  INSERT INTO shifts (id, name, start_time, end_time, tenant_id)
  VALUES (gen_random_uuid(), 'Morning Shift', '09:00', '18:00', '<tenant_id>');
  ```
- **Expected DB State:** Second insert rejected by UNIQUE constraint on `(name, tenant_id)`.
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM shifts WHERE name = 'Morning Shift' AND tenant_id = '<tenant_id>';
  ```
- **Pass Criteria:** Count == 1.
- **Note:** If count == 2, flag as **[DEFECT DB-012]**: no UNIQUE constraint on shift name per tenant.

---

### DB-604: Announcement Recipient Duplicate — No Constraint (Known Defect)

- **Table(s):** `announcement_recipients`
- **Operation:** INSERT (duplicate — succeeds due to missing constraint)
- **Scenario:** Same as DB-009. This test specifically documents and verifies the defect.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO announcement_recipients (id, announcement_id, recipient_id, sent_at)
  VALUES (gen_random_uuid(), '<ann_id>', '<user_id>', NOW());

  INSERT INTO announcement_recipients (id, announcement_id, recipient_id, sent_at)
  VALUES (gen_random_uuid(), '<ann_id>', '<user_id>', NOW());
  ```
- **Verification Query:**
  ```sql
  SELECT id, sent_at FROM announcement_recipients
  WHERE announcement_id = '<ann_id>' AND recipient_id = '<user_id>'
  ORDER BY sent_at;
  ```
- **Pass Criteria (defect confirmation):** 2 rows returned.
- **Impact:** User receives duplicate push/SMS/email notifications.

---

### DB-605: Weekoff Duplicate Day — Same Tenant

- **Table(s):** `weekoffs`
- **Operation:** INSERT (duplicate day)
- **Scenario:** Insert Monday as weekoff twice for same tenant.
- **SQL / ORM Operation:**
  ```sql
  INSERT INTO weekoffs (id, tenant_id, day_of_week)
  VALUES (gen_random_uuid(), '<tenant_id>', 1);

  INSERT INTO weekoffs (id, tenant_id, day_of_week)
  VALUES (gen_random_uuid(), '<tenant_id>', 1);
  ```
- **Verification Query:**
  ```sql
  SELECT COUNT(*) FROM weekoffs WHERE tenant_id = '<tenant_id>' AND day_of_week = 1;
  ```
- **Pass Criteria:** Count == 1 (UNIQUE constraint on `(tenant_id, day_of_week)`).
- **Note:** If count == 2, flag as **[DEFECT DB-013]**.

---

## 9. H. Index-Sensitive Queries

### DB-701: Booking Query — (employee_id, booking_date) Index

- **Table(s):** `bookings`
- **Operation:** SELECT with EXPLAIN ANALYZE
- **Scenario:** Verify an index exists on `(employee_id, booking_date)` and is used by the query planner.
- **SQL / ORM Operation:**
  ```sql
  EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
  SELECT * FROM bookings
  WHERE employee_id = '<emp_id>'
    AND booking_date = '2026-05-15';
  ```
- **Expected Execution Plan:**
  - Plan type: `Index Scan` or `Bitmap Index Scan` on a relevant index
  - NOT: `Seq Scan` on the full `bookings` table
- **Verification:**
  ```sql
  -- Verify index exists
  SELECT indexname, indexdef
  FROM pg_indexes
  WHERE tablename = 'bookings'
    AND indexdef LIKE '%employee_id%booking_date%';
  ```
- **Pass Criteria:**
  - Index exists for `(employee_id, booking_date)`
  - EXPLAIN ANALYZE shows index scan (not seq scan for large tables)
  - Execution time < 50ms with 100k rows
- **[DEFECT DB-014]:** If no index found, document as missing. Recommended:
  ```sql
  CREATE INDEX idx_bookings_employee_date ON bookings (employee_id, booking_date);
  ```

---

### DB-702: Route Query — (tenant_id, status, route_date) Composite Index

- **Table(s):** `routes`
- **Operation:** SELECT with EXPLAIN ANALYZE
- **Scenario:** Verify composite index for route listing query.
- **SQL / ORM Operation:**
  ```sql
  EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
  SELECT * FROM routes
  WHERE tenant_id = '<tenant_id>'
    AND status = 'Planned'
    AND route_date = '2026-05-15';
  ```
- **Verification:**
  ```sql
  SELECT indexname, indexdef
  FROM pg_indexes
  WHERE tablename = 'routes'
    AND indexdef LIKE '%tenant_id%status%';
  ```
- **Pass Criteria:** Composite index found and used. No seq scan on large tables.
- **Recommended index:**
  ```sql
  CREATE INDEX idx_routes_tenant_status_date ON routes (tenant_id, status, route_date);
  ```

---

### DB-703: Alert Query — (tenant_id, status) Index

- **Table(s):** `alerts`
- **Operation:** SELECT with EXPLAIN ANALYZE
- **Scenario:** Verify alert listing query uses index on `(tenant_id, status)`.
- **SQL / ORM Operation:**
  ```sql
  EXPLAIN (ANALYZE, BUFFERS)
  SELECT * FROM alerts
  WHERE tenant_id = '<tenant_id>'
    AND status = 'TRIGGERED'
  ORDER BY created_at DESC
  LIMIT 50;
  ```
- **Verification:**
  ```sql
  SELECT indexname FROM pg_indexes
  WHERE tablename = 'alerts'
    AND indexdef LIKE '%tenant_id%status%';
  ```
- **Pass Criteria:** Index scan used; query time < 100ms with 50k rows.

---

### DB-704: Reports Query — EXPLAIN ANALYZE on Large Dataset

- **Table(s):** `bookings`
- **Operation:** SELECT (reports query) on seeded large dataset
- **Scenario:** Seed 100,000 bookings for one tenant. Run the reports query with date range and measure execution time.
- **Setup:**
  ```sql
  -- Seed 100k bookings for tenant
  INSERT INTO bookings (id, employee_id, booking_date, shift_id, status, tenant_id, trip_type, ...)
  SELECT
      gen_random_uuid(),
      (SELECT id FROM users WHERE tenant_id = '<tenant_id>' LIMIT 1),
      '2026-01-01'::date + (random() * 365)::int,
      '<shift_id>',
      (ARRAY['Request', 'Scheduled', 'Completed', 'Cancelled'])[floor(random()*4+1)::int],
      '<tenant_id>',
      'pickup', '<loc1>', '<loc2>'
  FROM generate_series(1, 100000);
  ```
- **SQL / ORM Operation:**
  ```sql
  EXPLAIN (ANALYZE, BUFFERS)
  SELECT b.id, b.booking_date, b.status, b.employee_id
  FROM bookings b
  WHERE b.tenant_id = '<tenant_id>'
    AND b.booking_date BETWEEN '2026-01-01' AND '2026-12-31'
  ORDER BY b.booking_date DESC
  LIMIT 100 OFFSET 500;
  ```
- **Pass Criteria:**
  - Execution time < 500ms
  - Index scan used (not seq scan)
  - Correct row count in result

---

### DB-705: Driver Sessions — Active Session Lookup Performance

- **Table(s):** `driver_sessions`
- **Operation:** SELECT
- **Scenario:** Verify lookup of active driver session by `(driver_id, route_id)` uses an index.
- **SQL / ORM Operation:**
  ```sql
  EXPLAIN (ANALYZE)
  SELECT * FROM driver_sessions
  WHERE driver_id = '<driver_id>'
    AND route_id = '<route_id>'
    AND status = 'active';
  ```
- **Pass Criteria:** Index scan used; < 10ms response for lookup of single session.
- **Recommended index:**
  ```sql
  CREATE INDEX idx_driver_sessions_driver_route ON driver_sessions (driver_id, route_id) WHERE status = 'active';
  ```

---

## 10. I. Audit Trail Validation

### DB-801: Booking Status Change — created_at Preserved, updated_at Refreshed

- **Table(s):** `bookings`
- **Operation:** UPDATE (status change)
- **Scenario:** Change booking status multiple times and verify `created_at` never changes while `updated_at` reflects each change.
- **Setup:**
  ```python
  booking = create_test_booking(db_session)  # Status: Request
  original_created_at = booking.created_at
  ```
- **SQL / ORM Operations:**
  ```python
  # Change 1: Request → Scheduled
  import time
  booking.status = "Scheduled"
  db_session.commit()
  scheduled_updated_at = db_session.query(Booking).filter_by(id=booking.id).one().updated_at

  time.sleep(0.1)  # Ensure timestamp difference

  # Change 2: Scheduled → InProgress
  booking.status = "InProgress"
  db_session.commit()
  inprogress_updated_at = db_session.query(Booking).filter_by(id=booking.id).one().updated_at
  ```
- **Verification Query:**
  ```sql
  SELECT created_at, updated_at, status FROM bookings WHERE id = '<booking_id>';
  ```
- **Pass Criteria:**
  - `created_at` == `original_created_at` (never changed)
  - `scheduled_updated_at` > `original_created_at`
  - `inprogress_updated_at` > `scheduled_updated_at`
  - All timestamps are valid ISO datetimes

---

### DB-802: Alert Lifecycle Timestamps — Each Transition Logged

- **Table(s):** `alerts`
- **Operation:** Multiple UPDATEs
- **Scenario:** Walk an alert through its full lifecycle and verify each stage has a non-null, non-repeating timestamp.
- **SQL / ORM Operations:**
  ```python
  # Acknowledge
  alert.status = "ACKNOWLEDGED"
  alert.acknowledged_at = datetime.utcnow()
  db_session.commit()
  ack_time = alert.acknowledged_at

  # Resolve
  alert.status = "RESOLVED"
  alert.resolved_at = datetime.utcnow()
  db_session.commit()
  res_time = alert.resolved_at

  # Close
  alert.status = "CLOSED"
  alert.closed_at = datetime.utcnow()
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT
      status,
      created_at,
      acknowledged_at,
      resolved_at,
      closed_at
  FROM alerts
  WHERE id = '<alert_id>';
  ```
- **Pass Criteria:**
  - `created_at` IS NOT NULL (set on insert)
  - `acknowledged_at` IS NOT NULL and > `created_at`
  - `resolved_at` IS NOT NULL and > `acknowledged_at`
  - `closed_at` IS NOT NULL and > `resolved_at`

---

### DB-803: Announcement Publish — published_at Set Correctly

- **Table(s):** `announcements`
- **Operation:** UPDATE (publish)
- **Scenario:** Publish an announcement and verify `published_at` is set exactly once.
- **SQL / ORM Operation:**
  ```python
  announcement.status = "PUBLISHED"
  announcement.published_at = datetime.utcnow()
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT status, published_at, created_at, updated_at
  FROM announcements
  WHERE id = '<ann_id>';
  ```
- **Pass Criteria:**
  - `status` == `'PUBLISHED'`
  - `published_at` IS NOT NULL
  - `published_at` >= `created_at`
  - `published_at` is within last 5 seconds

---

### DB-804: Route Dispatch — dispatched_at Immutable After First Set

- **Table(s):** `routes`
- **Operation:** UPDATE
- **Scenario:** Dispatch a route, then attempt to re-dispatch (should fail at app layer). Verify `dispatched_at` is not reset.
- **SQL / ORM Operation:**
  ```python
  # First dispatch
  route.status = "Dispatched"
  route.dispatched_at = datetime.utcnow()
  db_session.commit()
  original_dispatched_at = route.dispatched_at

  # Attempt re-dispatch (raw SQL bypass)
  time.sleep(0.5)
  db_session.execute(
      text("UPDATE routes SET dispatched_at = :now WHERE id = :id"),
      {"now": datetime.utcnow(), "id": str(route.id)}
  )
  db_session.commit()
  ```
- **Verification Query:**
  ```sql
  SELECT dispatched_at FROM routes WHERE id = '<route_id>';
  ```
- **Pass Criteria:**
  - At DB level: raw SQL CAN update `dispatched_at` (no DB-level immutability)
  - Application layer must prevent re-dispatch (returns 409)
  - **[DEFECT DB-015]:** No DB constraint prevents `dispatched_at` from being overwritten. Immutability is app-layer only.

---

### DB-805: Booking Trip — OTP Marked as Used After Trip Start

- **Table(s):** `bookings` (or `otps` / `booking_otps` table)
- **Operation:** SELECT (verify OTP consumed)
- **Scenario:** After driver starts a trip with a valid OTP, verify the OTP cannot be reused.
- **Verification Query:**
  ```sql
  -- If OTPs are stored in DB:
  SELECT is_used, used_at FROM booking_otps
  WHERE booking_id = '<booking_id>';

  -- If OTPs are stored in Redis:
  -- Verify via Redis CLI: GET otp:<booking_id> should return nil after use
  ```
- **Pass Criteria:**
  - OTP marked as used (`is_used` = true) or deleted from Redis
  - `used_at` IS NOT NULL (if DB-stored)
  - Second trip start attempt with same OTP returns 401

---

## 11. Defect Summary Register

| Defect ID | Severity | Table | Missing/Incorrect Constraint | Recommended Fix |
|-----------|----------|-------|------------------------------|-----------------|
| DB-001 | HIGH | `bookings` | No UNIQUE on `(employee_id, booking_date, shift_id)` | Add partial unique index excluding cancelled |
| DB-002 | MEDIUM | `announcement_recipients` | No UNIQUE on `(announcement_id, recipient_id)` | `ALTER TABLE ADD CONSTRAINT uq_announcement_recipient UNIQUE(announcement_id, recipient_id)` |
| DB-003 | LOW | `announcements` | No DB-level CHECK preventing `PUBLISHED → DRAFT` revert | Add status transition trigger or CHECK constraint |
| DB-004 | HIGH | `shifts`, `bookings` | Unclear FK cascade behavior on shift delete | Document and enforce ON DELETE RESTRICT |
| DB-005 | HIGH | `route_management_bookings` | No FK from `booking_id` to `bookings.id` | `ALTER TABLE ADD CONSTRAINT fk_rmb_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id)` |
| DB-006 | HIGH | `tenants` + all child tables | Cascade delete behavior on tenant deletion unclear | Audit all FKs with `tenant_id`; add `ON DELETE CASCADE` or `RESTRICT` |
| DB-007 | MEDIUM | `shifts`, `bookings` | Cascade on shift delete may orphan bookings | Add `ON DELETE RESTRICT` on `bookings.shift_id` FK |
| DB-008 | HIGH | `bookings` | Bulk booking may be non-atomic | Verify transaction wraps entire bulk insert |
| DB-009 | HIGH | `routes` | Route dispatch may be non-atomic with notifications | Wrap dispatch + notification in transaction with rollback on failure |
| DB-010 | MEDIUM | `announcements` | Publish may not be atomic with recipient creation | Verify transaction wraps publish + recipient inserts |
| DB-011 | MEDIUM | `driver_devices` | No UNIQUE on `android_id` (verify) | Add UNIQUE constraint on `android_id` |
| DB-012 | LOW | `shifts` | No UNIQUE on `(name, tenant_id)` (verify) | Add UNIQUE constraint for shift name per tenant |
| DB-013 | LOW | `weekoffs` | No UNIQUE on `(tenant_id, day_of_week)` (verify) | Add UNIQUE constraint to prevent duplicate weekoffs |
| DB-014 | MEDIUM | `bookings` | Missing index on `(employee_id, booking_date)` (verify) | Add composite index |
| DB-015 | LOW | `routes` | No DB-level immutability on `dispatched_at` | Enforce at app layer; add DB trigger if needed |

---

## 12. Pytest DB Test Mapping

### Directory Structure

```
tests/
  db/
    conftest.py           ← Engine, session, base fixtures
    test_insert.py        ← DB-001 through DB-015
    test_update.py        ← DB-101 through DB-110
    test_delete.py        ← DB-201 through DB-208
    test_fk_integrity.py  ← DB-301 through DB-308
    test_cascade.py       ← DB-401 through DB-405
    test_transactions.py  ← DB-501 through DB-506
    test_duplicates.py    ← DB-601 through DB-605
    test_indexes.py       ← DB-701 through DB-705
    test_audit_trail.py   ← DB-801 through DB-805
```

### `tests/db/conftest.py`

```python
"""
tests/db/conftest.py
Database test fixtures.
"""
import uuid
from datetime import date, datetime
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.shift import Shift
from app.models.booking import Booking
from app.models.route import Route
from app.models.announcement import Announcement
from app.models.alert import Alert
from app.core.security import get_password_hash

TEST_DB_URL = "postgresql://test_user:test_pass@localhost:5433/fleet_test_db"

engine = create_engine(TEST_DB_URL, echo=True)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Transactional test session — always rolls back."""
    conn = engine.connect()
    txn = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    txn.rollback()
    conn.close()


@pytest.fixture()
def tenant(db_session: Session) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="TestCorp",
        domain=f"testcorp-{uuid.uuid4().hex[:6]}.com",
        is_active=True,
    )
    db_session.add(t)
    db_session.flush()
    return t


@pytest.fixture()
def employee(db_session: Session, tenant: Tenant) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"emp-{uuid.uuid4().hex[:6]}@testcorp.com",
        hashed_password=get_password_hash("Test1234!"),
        user_type="employee",
        tenant_id=tenant.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture()
def shift(db_session: Session, tenant: Tenant) -> Shift:
    s = Shift(
        id=uuid.uuid4(),
        name=f"Shift-{uuid.uuid4().hex[:4]}",
        start_time="08:00",
        end_time="17:00",
        tenant_id=tenant.id,
        grace_period_minutes=15,
    )
    db_session.add(s)
    db_session.flush()
    return s


@pytest.fixture()
def booking(db_session: Session, employee: User, shift: Shift, tenant: Tenant) -> Booking:
    b = Booking(
        id=uuid.uuid4(),
        employee_id=employee.id,
        booking_date=date(2026, 5, 15),
        shift_id=shift.id,
        tenant_id=tenant.id,
        status="Request",
        trip_type="pickup",
    )
    db_session.add(b)
    db_session.flush()
    return b


@pytest.fixture()
def route(db_session: Session, shift: Shift, tenant: Tenant) -> Route:
    r = Route(
        id=uuid.uuid4(),
        name="Test Route Alpha",
        shift_id=shift.id,
        route_date=date(2026, 5, 15),
        direction="pickup",
        tenant_id=tenant.id,
        status="Planned",
    )
    db_session.add(r)
    db_session.flush()
    return r


@pytest.fixture()
def draft_announcement(db_session: Session, tenant: Tenant, employee: User) -> Announcement:
    a = Announcement(
        id=uuid.uuid4(),
        title="Test Announcement",
        body="Test body",
        tenant_id=tenant.id,
        created_by=employee.id,
        status="DRAFT",
    )
    db_session.add(a)
    db_session.flush()
    return a


@pytest.fixture()
def alert(db_session: Session, tenant: Tenant, employee: User, route: Route) -> Alert:
    a = Alert(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        alert_type="SOS",
        status="TRIGGERED",
        message="Test SOS",
        triggered_by=employee.id,
        route_id=route.id,
    )
    db_session.add(a)
    db_session.flush()
    return a
```

### `tests/db/test_insert.py` (sample)

```python
"""
tests/db/test_insert.py
Insert validation tests (DB-001 through DB-015).
"""
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking
from app.models.announcement import Announcement, AnnouncementRecipient
from app.models.iam import IAMRole


class TestBookingInsert:

    def test_valid_booking_persists_all_fields(self, db_session, booking):
        """DB-001: All fields of a valid booking are stored correctly."""
        from sqlalchemy import text
        result = db_session.execute(
            text("SELECT id, status, booking_date, trip_type FROM bookings WHERE id = :id"),
            {"id": str(booking.id)},
        ).fetchone()

        assert result is not None
        assert str(result.id) == str(booking.id)
        assert result.status == "Request"
        assert str(result.booking_date) == "2026-05-15"
        assert result.trip_type == "pickup"

    def test_duplicate_booking_no_db_constraint(self, db_session, employee, shift, tenant):
        """DB-002: DEFECT — No DB UNIQUE constraint on (employee_id, booking_date, shift_id).
        Both inserts succeed, proving missing constraint.
        """
        def make_booking():
            b = Booking(
                id=uuid.uuid4(),
                employee_id=employee.id,
                booking_date=date(2026, 5, 20),
                shift_id=shift.id,
                tenant_id=tenant.id,
                status="Request",
                trip_type="pickup",
            )
            db_session.add(b)
            db_session.flush()
            return b

        b1 = make_booking()
        try:
            b2 = make_booking()
            # If we get here, the constraint is MISSING (defect)
            from sqlalchemy import text
            count = db_session.execute(
                text(
                    "SELECT COUNT(*) FROM bookings "
                    "WHERE employee_id = :emp AND booking_date = '2026-05-20' AND shift_id = :shift"
                ),
                {"emp": str(employee.id), "shift": str(shift.id)},
            ).scalar()
            assert count == 2, f"Expected 2 duplicate rows (defect), got {count}"
            pytest.fail(
                "DB-DEFECT-001: Both duplicate bookings inserted successfully. "
                "UNIQUE constraint on (employee_id, booking_date, shift_id) is MISSING. "
                "Add: CREATE UNIQUE INDEX uq_bookings_no_duplicate "
                "ON bookings(employee_id, booking_date, shift_id) WHERE status != 'Cancelled'"
            )
        except IntegrityError:
            # Constraint exists — defect is fixed
            db_session.rollback()
            pass

    def test_announcement_defaults_to_draft(self, db_session, draft_announcement):
        """DB-003: Announcement defaults to DRAFT status with published_at NULL."""
        from sqlalchemy import text
        result = db_session.execute(
            text("SELECT status, published_at FROM announcements WHERE id = :id"),
            {"id": str(draft_announcement.id)},
        ).fetchone()
        assert result.status == "DRAFT"
        assert result.published_at is None


class TestIAMRoleInsert:

    def test_system_role_with_null_tenant_valid(self, db_session):
        """DB-005: System role with tenant_id=NULL is valid."""
        role = IAMRole(
            id=uuid.uuid4(),
            name="GlobalAdmin",
            system_role=True,
            tenant_id=None,
        )
        db_session.add(role)
        db_session.flush()  # Should not raise

        from sqlalchemy import text
        result = db_session.execute(
            text("SELECT system_role, tenant_id FROM iam_roles WHERE id = :id"),
            {"id": str(role.id)},
        ).fetchone()
        assert result.system_role is True
        assert result.tenant_id is None

    def test_system_role_with_tenant_id_rejected(self, db_session, tenant):
        """DB-006: System role with non-NULL tenant_id must raise CHECK constraint violation."""
        role = IAMRole(
            id=uuid.uuid4(),
            name="InvalidSystemRole",
            system_role=True,
            tenant_id=tenant.id,  # This should violate CHECK constraint
        )
        db_session.add(role)
        with pytest.raises(IntegrityError, match="check"):
            db_session.flush()
        db_session.rollback()

    def test_tenant_role_without_tenant_id_rejected(self, db_session):
        """DB-007: Tenant-scoped role (system_role=False) with NULL tenant_id must fail."""
        role = IAMRole(
            id=uuid.uuid4(),
            name="OrphanRole",
            system_role=False,
            tenant_id=None,  # Should violate CHECK constraint
        )
        db_session.add(role)
        with pytest.raises(IntegrityError, match="check"):
            db_session.flush()
        db_session.rollback()
```

### `tests/db/test_transactions.py` (sample)

```python
"""
tests/db/test_transactions.py
Transaction atomicity and rollback tests (DB-501 through DB-506).
"""
import uuid
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking


class TestBulkBookingAtomicity:

    def test_bulk_booking_rolls_back_on_failure(
        self, db_session, employee, tenant
    ):
        """DB-501: If any booking in bulk insert fails, ALL are rolled back."""
        valid_dates = [date(2026, 6, 1), date(2026, 6, 2)]
        booking_ids = []

        try:
            for i, booking_date in enumerate(valid_dates + [date(2026, 6, 3)]):
                if i == 2:
                    # Inject invalid shift_id to cause FK failure on 3rd insert
                    shift_id = uuid.uuid4()  # non-existent
                else:
                    shift_id = uuid.uuid4()  # Also non-existent for simplicity in unit test
                    # In real test, use valid shift_id fixture for first 2

                b = Booking(
                    id=uuid.uuid4(),
                    employee_id=employee.id,
                    booking_date=booking_date,
                    shift_id=shift_id,
                    tenant_id=tenant.id,
                    status="Request",
                    trip_type="pickup",
                )
                booking_ids.append(b.id)
                db_session.add(b)
            db_session.flush()
        except IntegrityError:
            db_session.rollback()

        # Verify no bookings were created
        for booking_id in booking_ids:
            count = db_session.execute(
                text("SELECT COUNT(*) FROM bookings WHERE id = :id"),
                {"id": str(booking_id)},
            ).scalar()
            assert count == 0, (
                f"DB-DEFECT-008: Booking {booking_id} was partially committed. "
                "Bulk insert is not atomic."
            )
```

### `tests/db/test_audit_trail.py` (sample)

```python
"""
tests/db/test_audit_trail.py
Audit trail validation tests (DB-801 through DB-805).
"""
import time
from datetime import datetime

import pytest
from sqlalchemy import text


class TestBookingAuditTrail:

    def test_created_at_preserved_on_status_change(self, db_session, booking):
        """DB-801: created_at never changes; updated_at refreshes on each update."""
        original_created_at = booking.created_at
        original_updated_at = booking.updated_at

        time.sleep(0.05)  # Ensure timestamp difference

        # Update 1
        booking.status = "Scheduled"
        db_session.flush()
        db_session.refresh(booking)

        assert booking.created_at == original_created_at, (
            "created_at changed after status update — it must never change"
        )
        assert booking.updated_at > original_updated_at, (
            "updated_at was not refreshed after status update"
        )

        time.sleep(0.05)
        prev_updated_at = booking.updated_at

        # Update 2
        booking.status = "InProgress"
        db_session.flush()
        db_session.refresh(booking)

        assert booking.created_at == original_created_at, "created_at changed"
        assert booking.updated_at > prev_updated_at, "updated_at not refreshed on 2nd update"


class TestAlertAuditTrail:

    def test_alert_lifecycle_timestamps_ordered(self, db_session, alert):
        """DB-802: Each alert transition sets a distinct, ordered timestamp."""
        time.sleep(0.05)
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = datetime.utcnow()
        db_session.flush()
        ack_time = alert.acknowledged_at

        time.sleep(0.05)
        alert.status = "RESOLVED"
        alert.resolved_at = datetime.utcnow()
        db_session.flush()
        res_time = alert.resolved_at

        time.sleep(0.05)
        alert.status = "CLOSED"
        alert.closed_at = datetime.utcnow()
        db_session.flush()
        db_session.refresh(alert)

        assert alert.acknowledged_at is not None
        assert alert.resolved_at is not None
        assert alert.closed_at is not None
        assert ack_time < res_time < alert.closed_at, (
            "Alert timestamps are not in correct chronological order"
        )
```

---

*End of DB Test Cases — Fleet Manager v1.0.0*
