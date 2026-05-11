# RBAC Test Matrix — Fleet Manager Backend API

**Document Version:** 1.0  
**Last Updated:** 2026-04-30  
**Author:** QA Automation Architect  
**Stack:** FastAPI + SQLAlchemy + PostgreSQL + Redis  
**Scope:** Role-Based Access Control validation, privilege escalation, and token manipulation

---

## Table of Contents

1. [Role Definitions & Assumptions](#role-definitions--assumptions)
2. [Part 1: Full RBAC Permission Matrix](#part-1-full-rbac-permission-matrix)
3. [Part 2: RBAC Test Cases (60+)](#part-2-rbac-test-cases)
4. [Part 3: Privilege Escalation Scenarios (15)](#part-3-privilege-escalation-scenarios)
5. [Part 4: Token Manipulation Checks (10)](#part-4-token-manipulation-checks)
6. [Footnotes & Security Notes](#footnotes--security-notes)

---

## Role Definitions & Assumptions

| Role | JWT Claims Present | Scope |
|------|--------------------|-------|
| Admin | `admin_id`, no `tenant_id` | Global — all tenants |
| SubAdmin | `user_id`, `tenant_id`, `role=subadmin`, IAM policy attached | Tenant-scoped, permissions from IAM policy |
| Vendor | `user_id`, `tenant_id`, `vendor_id`, `role=vendor` | Tenant + Vendor scoped |
| Driver | `user_id`, `tenant_id`, `driver_id`, `role=driver` | Tenant + Driver scoped |
| Employee | `user_id`, `tenant_id`, `employee_id`, `role=employee` | Tenant + Employee scoped |
| Escort | `user_id`, `tenant_id`, `role=escort` | Tenant-scoped, user_type check only |
| Guest | No token | Unauthenticated |

**Permission Notation:**
- ✅ ALLOWED — Role has required permission and access is granted
- ❌ DENIED — Role lacks permission; API must return HTTP 403
- ⚠️ PARTIAL — Allowed with scope restrictions (see footnotes)
- 🔓 UNAUTHENTICATED — Security bug: no auth enforced; anyone can call this endpoint
- 🚫 401 — No/invalid token; API must return HTTP 401

---

## Part 1: Full RBAC Permission Matrix

### 1.1 Authentication Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Auth | login | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auth | logout | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚫 401 |
| Auth | refresh_token | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚫 401 |
| Auth | reset_password | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [^1] |
| Auth | introspect | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚫 401 |

[^1]: `reset_password` is a stub — no auth required, always returns 200. **Known security defect.**

---

### 1.2 Booking Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Booking | create | ✅ | ⚠️ [^2] | ❌ | ❌ | ✅ [^3] | ❌ | 🚫 401 |
| Booking | read | ✅ | ⚠️ [^4] | ❌ | ❌ | ⚠️ [^5] | ❌ | 🚫 401 |
| Booking | update | ✅ | ⚠️ [^6] | ❌ | ❌ | ⚠️ [^7] | ❌ | 🚫 401 |
| Booking | delete | ✅ | ⚠️ [^8] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Booking | bulk_create | ✅ | ⚠️ [^9] | ❌ | ❌ | ✅ [^10] | ❌ | 🚫 401 |

[^2]: SubAdmin can create bookings only if `booking.create` is in their IAM policy.
[^3]: Employee can only create bookings for themselves (own `employee_id`).
[^4]: SubAdmin can read all bookings within their tenant only.
[^5]: Employee can only read their own bookings.
[^6]: SubAdmin can update bookings only if `booking.update` is in their IAM policy.
[^7]: Employee can only cancel/update their own bookings before cutoff.
[^8]: SubAdmin can delete bookings only if `booking.delete` is in IAM policy.
[^9]: SubAdmin can bulk_create if `booking.create` is in policy.
[^10]: Employee can bulk_create only for their own `employee_id` across multiple dates.

---

### 1.3 Route Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Route | create | ✅ | ⚠️ [^11] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Route | read | ✅ | ⚠️ [^12] | ❌ | ⚠️ [^13] | ❌ | ❌ | 🚫 401 |
| Route | update | ✅ | ⚠️ [^14] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Route | delete | ✅ | ⚠️ [^15] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Route | assign_vehicle | ✅ | ⚠️ [^16] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Route | dispatch | ✅ | ⚠️ [^17] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Route | cancel | ✅ | ⚠️ [^18] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^11]: SubAdmin needs `route.create` in IAM policy.
[^12]: SubAdmin can read routes within their tenant only.
[^13]: Driver can read only routes they are assigned to.
[^14]: SubAdmin needs `route.update` in IAM policy.
[^15]: SubAdmin needs `route.delete` in IAM policy.
[^16]: SubAdmin needs `route.assign_vehicle` in IAM policy.
[^17]: SubAdmin needs `route.dispatch` in IAM policy.
[^18]: SubAdmin needs `route.update` or `route.delete` in IAM policy (depends on implementation).

---

### 1.4 Driver App Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Driver App | duty_start | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | duty_end | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | trip_start | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | trip_drop | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | trip_no_show | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | location_update | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |
| Driver App | sos | ❌ | ❌ | ❌ | ✅ [^19] | ❌ | ❌ | 🚫 401 |

[^19]: Driver can only perform actions on routes/trips assigned to their own `driver_id`.

---

### 1.5 Alert Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Alert | create | ✅ | ⚠️ [^20] | ❌ | ✅ [^21] | ❌ | ❌ | 🚫 401 |
| Alert | read | ✅ | ⚠️ [^22] | ❌ | ⚠️ [^23] | ❌ | ❌ | 🚫 401 |
| Alert | update (ack/resolve/close) | ✅ | ⚠️ [^24] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Alert | escalate | ✅ | ⚠️ [^25] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^20]: SubAdmin needs `alert.create` in IAM policy.
[^21]: Driver can only create SOS alerts tied to their active route.
[^22]: SubAdmin can read all alerts within their tenant.
[^23]: Driver can only read alerts they triggered.
[^24]: SubAdmin needs `alert.update` in IAM policy.
[^25]: SubAdmin needs `alert.update` in IAM policy to escalate.

---

### 1.6 Announcement Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Announcement | create | ✅ | ⚠️ [^26] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Announcement | read | ✅ | ⚠️ [^27] | ❌ | ✅ [^28] | ✅ [^28] | ✅ [^28] | 🚫 401 |
| Announcement | update | ✅ | ⚠️ [^29] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Announcement | publish | ✅ | ⚠️ [^30] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Announcement | delete | ✅ | ⚠️ [^31] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^26]: SubAdmin needs `announcement.create` in IAM policy.
[^27]: SubAdmin can read all announcements in their tenant.
[^28]: Driver/Employee/Escort can only read PUBLISHED announcements targeted to their tenant.
[^29]: SubAdmin needs `announcement.update` in IAM policy; update blocked after PUBLISHED.
[^30]: SubAdmin needs `announcement.publish` in IAM policy.
[^31]: SubAdmin needs `announcement.delete` in IAM policy; delete blocked after PUBLISHED.

---

### 1.7 IAM Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| IAM | package_create | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | package_read | ✅ | ⚠️ [^32] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | policy_create | ✅ | ⚠️ [^33] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | policy_read | ✅ | ⚠️ [^34] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | role_create | ✅ | ⚠️ [^35] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | role_read | ✅ | ⚠️ [^36] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| IAM | role_assign | ✅ | ⚠️ [^37] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^32]: SubAdmin needs `iam.read` in IAM policy; can only read packages assigned to their tenant.
[^33]: SubAdmin needs `iam.write` in IAM policy; cannot create packages (Admin-only).
[^34]: SubAdmin needs `iam.read` in IAM policy; can only read policies under their tenant package.
[^35]: SubAdmin needs `iam.write` in IAM policy; cannot create system-level roles.
[^36]: SubAdmin needs `iam.read` in IAM policy.
[^37]: SubAdmin needs `iam.write` in IAM policy; can only assign roles within their tenant.

---

### 1.8 Employee Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Employee | create | ✅ | ⚠️ [^38] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Employee | read | ✅ | ⚠️ [^39] | ❌ | ❌ | ⚠️ [^40] | ❌ | 🚫 401 |
| Employee | update | ✅ | ⚠️ [^41] | ❌ | ❌ | ⚠️ [^42] | ❌ | 🚫 401 |
| Employee | delete | ✅ | ⚠️ [^43] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Employee | bulk_import | ✅ | ⚠️ [^44] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^38]: SubAdmin needs `employee.create` in IAM policy.
[^39]: SubAdmin needs `employee.read`; can read employees in their tenant only.
[^40]: Employee can read their own profile only.
[^41]: SubAdmin needs `employee.update` in IAM policy.
[^42]: Employee can update limited fields of their own profile (e.g., contact info), not role or permissions.
[^43]: SubAdmin needs `employee.delete` in IAM policy.
[^44]: SubAdmin needs `employee.create` in IAM policy.

---

### 1.9 Vendor Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Vendor | create | ✅ | ⚠️ [^45] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Vendor | read | ✅ | ⚠️ [^46] | ⚠️ [^47] | ❌ | ❌ | ❌ | 🚫 401 |
| Vendor | update | ✅ | ⚠️ [^48] | ⚠️ [^49] | ❌ | ❌ | ❌ | 🚫 401 |
| Vendor | delete | ✅ | ⚠️ [^50] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Vendor | vehicle_create | ✅ | ⚠️ [^51] | ⚠️ [^52] | ❌ | ❌ | ❌ | 🚫 401 |
| Vendor | vehicle_read | ✅ | ⚠️ [^53] | ⚠️ [^54] | ❌ | ❌ | ❌ | 🚫 401 |

[^45]: SubAdmin needs `vendor.create` in IAM policy.
[^46]: SubAdmin needs `vendor.read`; can read vendors in their tenant only.
[^47]: Vendor can only read their own vendor profile.
[^48]: SubAdmin needs `vendor.update` in IAM policy.
[^49]: Vendor can only update their own vendor profile.
[^50]: SubAdmin needs `vendor.delete` in IAM policy.
[^51]: SubAdmin needs `vendor.create` in IAM policy.
[^52]: Vendor can only create vehicles under their own `vendor_id`.
[^53]: SubAdmin needs `vendor.read` in IAM policy.
[^54]: Vendor can only read vehicles under their own `vendor_id`.

---

### 1.10 Report Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Report | read_booking_report | ✅ | ⚠️ [^55] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Report | read_route_report | ✅ | ⚠️ [^55] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Report | read_driver_report | ✅ | ⚠️ [^55] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^55]: SubAdmin needs `report.read` in IAM policy; data is scoped to their tenant only.

---

### 1.11 Tenant Config Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Tenant Config | create_tenant | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Tenant Config | read_tenant | ✅ | ⚠️ [^56] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Tenant Config | update_tenant | ✅ | ⚠️ [^57] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Tenant Config | shift_create | ✅ | ⚠️ [^58] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Tenant Config | weekoff_create | ✅ | ⚠️ [^58] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |
| Tenant Config | cutoff_create | ✅ | ⚠️ [^58] | ❌ | ❌ | ❌ | ❌ | 🚫 401 |

[^56]: SubAdmin needs `tenant_config.read`; can only read their own tenant config.
[^57]: SubAdmin needs `tenant_config.write`; can only update their own tenant config.
[^58]: SubAdmin needs `tenant_config.write`; can only create configs for their own tenant.

---

### 1.12 Push Notification Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Push Notification | send | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^59] |
| Push Notification | send_batch | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^59] |

[^59]: **CRITICAL SECURITY BUG:** `/push-notifications/send` and `/push-notifications/send-batch` have NO auth dependency. Any unauthenticated caller can send push notifications to any device token. This must be treated as a P0 security vulnerability.

---

### 1.13 Route Grouping Module

| Module | Action | Admin | SubAdmin | Vendor | Driver | Employee | Escort | Guest |
|--------|--------|-------|----------|--------|--------|----------|--------|-------|
| Route Grouping | create_group | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^60] |
| Route Grouping | read_group | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^60] |
| Route Grouping | update_group | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^60] |
| Route Grouping | delete_group | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 | 🔓 [^60] |

[^60]: **CRITICAL SECURITY BUG:** All permission checks in `route_grouping.py` are commented out. Any unauthenticated caller can create, read, update, and delete route groups. This is a P0 security vulnerability.

---

## Part 2: RBAC Test Cases

---

### RBAC-001: Admin Can Create a Booking
- **Module:** Booking
- **Action:** create
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/bookings
- **Token:** Valid Admin JWT (contains `admin_id`, no `tenant_id`)
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin, obtain JWT.
  2. POST /api/v1/bookings with valid payload: `{ "employee_id": "emp_001", "tenant_id": "tenant_A", "shift_id": "shift_001", "booking_date": "2026-05-01", "trip_type": "pickup" }`
  3. Verify response status 201 and booking object in response body.
- **Expected Response:** `{ "id": "<uuid>", "status": "Pending", ... }`
- **Security Note:** Admin acts globally; no tenant check needed in token.

---

### RBAC-002: Guest Cannot Create a Booking
- **Module:** Booking
- **Action:** create
- **Actor Role:** Guest (Unauthenticated)
- **Endpoint:** POST /api/v1/bookings
- **Token:** None
- **Expected Status:** 401
- **Test Type:** Negative
- **Steps:**
  1. Send POST /api/v1/bookings without any Authorization header.
  2. Payload: `{ "employee_id": "emp_001", "tenant_id": "tenant_A", ... }`
  3. Verify response is 401.
- **Expected Response:** `{ "detail": "Not authenticated" }`
- **Security Note:** All booking endpoints must require authentication.

---

### RBAC-003: Employee Can Create Their Own Booking
- **Module:** Booking
- **Action:** create
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/bookings
- **Token:** Valid Employee JWT (`tenant_id=tenant_A`, `employee_id=emp_001`)
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Employee (emp_001 in tenant_A).
  2. POST /api/v1/bookings with payload where `employee_id=emp_001`.
  3. Verify 201 response and booking scoped to emp_001.
- **Expected Response:** `{ "id": "<uuid>", "employee_id": "emp_001", "status": "Pending" }`

---

### RBAC-004: Employee Cannot Create Booking for Another Employee
- **Module:** Booking
- **Action:** create
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/bookings
- **Token:** Valid Employee JWT (`employee_id=emp_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as Employee emp_001.
  2. POST /api/v1/bookings with `"employee_id": "emp_002"` (another employee).
  3. Verify 403 response.
- **Expected Response:** `{ "detail": "Forbidden: Cannot create booking for another employee" }`
- **Security Note:** Handler must validate that token's `employee_id` matches payload's `employee_id`.

---

### RBAC-005: Driver Cannot Access Booking Management Endpoints
- **Module:** Booking
- **Action:** create
- **Actor Role:** Driver
- **Endpoint:** POST /api/v1/bookings
- **Token:** Valid Driver JWT (`driver_id=drv_001`, `tenant_id=tenant_A`)
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Driver (drv_001).
  2. POST /api/v1/bookings with any payload.
  3. Verify 403 response.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-006: Vendor Cannot Access Booking Management Endpoints
- **Module:** Booking
- **Action:** create
- **Actor Role:** Vendor
- **Endpoint:** POST /api/v1/bookings
- **Token:** Valid Vendor JWT (`vendor_id=vnd_001`, `tenant_id=tenant_A`)
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Vendor.
  2. POST /api/v1/bookings.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-007: SubAdmin WITH booking.read Can List Bookings
- **Module:** Booking
- **Action:** read
- **Actor Role:** SubAdmin
- **Endpoint:** GET /api/v1/bookings
- **Token:** SubAdmin JWT with IAM policy containing `booking.read`
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Create SubAdmin in tenant_A with IAM policy that includes `booking.read`.
  2. Authenticate as SubAdmin, obtain JWT.
  3. GET /api/v1/bookings.
  4. Verify 200 and results are scoped to tenant_A only.
- **Expected Response:** `{ "items": [...], "total": N, "page": 1 }`

---

### RBAC-008: SubAdmin WITHOUT booking.create Cannot Create Booking
- **Module:** Booking
- **Action:** create
- **Actor Role:** SubAdmin
- **Endpoint:** POST /api/v1/bookings
- **Token:** SubAdmin JWT with IAM policy containing ONLY `booking.read` (no `booking.create`)
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Create SubAdmin with policy limited to `booking.read`.
  2. Authenticate as SubAdmin.
  3. POST /api/v1/bookings.
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Missing permission booking.create" }`

---

### RBAC-009: Escort Cannot Access Route Management
- **Module:** Route
- **Action:** create
- **Actor Role:** Escort
- **Endpoint:** POST /api/v1/routes
- **Token:** Valid Escort JWT (`tenant_id=tenant_A`, `role=escort`)
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Escort.
  2. POST /api/v1/routes with route payload.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-010: Admin Can Dispatch a Route
- **Module:** Route
- **Action:** dispatch
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/routes/{route_id}/dispatch
- **Token:** Valid Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. Create a route, assign a vehicle and driver (route in DriverAssigned status).
  3. POST /api/v1/routes/{route_id}/dispatch.
  4. Verify 200 and route status = Dispatched.
- **Expected Response:** `{ "id": "<route_id>", "status": "Dispatched" }`

---

### RBAC-011: Driver Can Start Duty
- **Module:** Driver App
- **Action:** duty_start
- **Actor Role:** Driver
- **Endpoint:** POST /api/v1/driver/duty/start
- **Token:** Valid Driver JWT (`driver_id=drv_001`)
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Driver drv_001.
  2. POST /api/v1/driver/duty/start with `{ "route_id": "rte_001" }`.
  3. Verify 200 and duty status updated.
- **Expected Response:** `{ "duty_id": "<uuid>", "status": "OnDuty" }`

---

### RBAC-012: Employee Cannot Start Driver Duty
- **Module:** Driver App
- **Action:** duty_start
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/driver/duty/start
- **Token:** Valid Employee JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/driver/duty/start.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Driver role required" }`

---

### RBAC-013: Admin Cannot Start Driver Duty (Role Check)
- **Module:** Driver App
- **Action:** duty_start
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/driver/duty/start
- **Token:** Valid Admin JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Admin.
  2. POST /api/v1/driver/duty/start.
  3. Verify 403 — Admin is not a driver, should not be allowed.
- **Expected Response:** `{ "detail": "Forbidden: Driver role required" }`
- **Security Note:** Role-specific endpoints should check role type, not just permissions.

---

### RBAC-014: Admin Can Publish Announcement
- **Module:** Announcement
- **Action:** publish
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/announcements/{id}/publish
- **Token:** Valid Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. Create a DRAFT announcement.
  3. POST /api/v1/announcements/{id}/publish.
  4. Verify status = Published.
- **Expected Response:** `{ "id": "<uuid>", "status": "Published" }`

---

### RBAC-015: Employee Cannot Publish Announcement
- **Module:** Announcement
- **Action:** publish
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/announcements/{id}/publish
- **Token:** Valid Employee JWT
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/announcements/{id}/publish.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-016: Route Grouping Accessible Without Token (Security Bug)
- **Module:** Route Grouping
- **Action:** create_group
- **Actor Role:** Guest (Unauthenticated)
- **Endpoint:** POST /api/v1/route-groupings
- **Token:** None
- **Expected Status:** 🔓 200 (BUG — should be 401)
- **Test Type:** Negative (exploiting known bug)
- **Steps:**
  1. Send POST /api/v1/route-groupings WITHOUT any Authorization header.
  2. Provide a valid route grouping payload.
  3. Document that API returns 200/201 instead of 401.
- **Expected Response (Actual):** `{ "id": "<uuid>", ... }` — **BUG: Auth bypass**
- **Expected Response (Desired):** `{ "detail": "Not authenticated" }` with status 401
- **Security Note:** All permission checks in `route_grouping.py` are commented out. Must be fixed before production.

---

### RBAC-017: Route Grouping Read Without Token (Security Bug)
- **Module:** Route Grouping
- **Action:** read_group
- **Actor Role:** Guest
- **Endpoint:** GET /api/v1/route-groupings
- **Token:** None
- **Expected Status:** 🔓 200 (BUG)
- **Test Type:** Negative (exploiting known bug)
- **Steps:**
  1. Send GET /api/v1/route-groupings without Authorization header.
  2. Observe response — should return 401 but currently returns data.
- **Security Note:** P0 — all route grouping endpoints are fully unauthenticated.

---

### RBAC-018: Push Notification Send Without Token (Security Bug)
- **Module:** Push Notification
- **Action:** send
- **Actor Role:** Guest
- **Endpoint:** POST /api/v1/push-notifications/send
- **Token:** None
- **Expected Status:** 🔓 200 (BUG — should be 401)
- **Test Type:** Negative (exploiting known bug)
- **Steps:**
  1. POST /api/v1/push-notifications/send without Authorization header.
  2. Payload: `{ "device_token": "any_token", "title": "Test", "body": "Spam" }`
  3. Observe that notification is sent without authentication.
- **Security Note:** P0 — this allows anyone to send arbitrary push notifications to any device token. Can be abused for phishing, spam, or denial-of-service.

---

### RBAC-019: Push Notification Batch Send Without Token (Security Bug)
- **Module:** Push Notification
- **Action:** send_batch
- **Actor Role:** Guest
- **Endpoint:** POST /api/v1/push-notifications/send-batch
- **Token:** None
- **Expected Status:** 🔓 200 (BUG)
- **Test Type:** Negative (exploiting known bug)
- **Steps:**
  1. POST /api/v1/push-notifications/send-batch without Authorization header.
  2. Payload: `{ "device_tokens": ["tok1", "tok2"], "title": "Spam", "body": "..." }`
  3. Observe unauthenticated batch notification delivery.
- **Security Note:** P0 — batch endpoint amplifies the impact of the auth bypass.

---

### RBAC-020: Cross-Tenant Booking Read — Employee Tenant A Reads Tenant B
- **Module:** Booking
- **Action:** read
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/bookings/{booking_id}
- **Token:** Employee JWT with `tenant_id=tenant_A`
- **Expected Status:** 403
- **Test Type:** Cross-Tenant Isolation
- **Steps:**
  1. Create a booking in tenant_B.
  2. Authenticate as Employee in tenant_A.
  3. GET /api/v1/bookings/{booking_id_from_tenant_B}.
  4. Verify 403 — cannot access cross-tenant data.
- **Expected Response:** `{ "detail": "Forbidden: Cross-tenant access denied" }`
- **Security Note:** `check_tenant` in PermissionChecker is non-functional. Handler code MUST enforce tenant isolation manually.

---

### RBAC-021: Cross-Tenant Route Read — SubAdmin Tenant A Reads Tenant B
- **Module:** Route
- **Action:** read
- **Actor Role:** SubAdmin
- **Endpoint:** GET /api/v1/routes/{route_id}
- **Token:** SubAdmin JWT with `tenant_id=tenant_A`
- **Expected Status:** 403
- **Test Type:** Cross-Tenant Isolation
- **Steps:**
  1. Create a route in tenant_B.
  2. Authenticate as SubAdmin in tenant_A.
  3. GET /api/v1/routes/{route_id_from_tenant_B}.
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Resource belongs to different tenant" }`
- **Security Note:** Since check_tenant is commented out, handler logic is the only safeguard.

---

### RBAC-022: Driver Accessing Another Driver's Route
- **Module:** Driver App
- **Action:** duty_start
- **Actor Role:** Driver
- **Endpoint:** POST /api/v1/driver/duty/start
- **Token:** Driver JWT with `driver_id=drv_001`
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as drv_001.
  2. POST /api/v1/driver/duty/start with `route_id` assigned to drv_002.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Route not assigned to this driver" }`

---

### RBAC-023: Vendor Reads Another Vendor's Vehicles
- **Module:** Vendor
- **Action:** vehicle_read
- **Actor Role:** Vendor
- **Endpoint:** GET /api/v1/vendors/{vendor_id}/vehicles
- **Token:** Vendor JWT (`vendor_id=vnd_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as vnd_001.
  2. GET /api/v1/vendors/vnd_002/vehicles.
  3. Verify 403 — cannot access another vendor's fleet.
- **Expected Response:** `{ "detail": "Forbidden: Vendor ID mismatch" }`

---

### RBAC-024: Vendor Reads Own Vehicles
- **Module:** Vendor
- **Action:** vehicle_read
- **Actor Role:** Vendor
- **Endpoint:** GET /api/v1/vendors/{vendor_id}/vehicles
- **Token:** Vendor JWT (`vendor_id=vnd_001`)
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as vnd_001.
  2. GET /api/v1/vendors/vnd_001/vehicles.
  3. Verify 200 with own vehicles.
- **Expected Response:** `{ "items": [...] }`

---

### RBAC-025: Employee Cannot Read All Employees
- **Module:** Employee
- **Action:** read
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/employees
- **Token:** Employee JWT (`employee_id=emp_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as emp_001.
  2. GET /api/v1/employees (list all employees).
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Cannot list all employees" }`

---

### RBAC-026: Employee Can Read Own Profile
- **Module:** Employee
- **Action:** read
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/employees/{employee_id}
- **Token:** Employee JWT (`employee_id=emp_001`)
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as emp_001.
  2. GET /api/v1/employees/emp_001.
  3. Verify 200 with own profile.
- **Expected Response:** `{ "id": "emp_001", "name": "...", ... }`

---

### RBAC-027: Employee Cannot Read Another Employee's Profile
- **Module:** Employee
- **Action:** read
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/employees/{employee_id}
- **Token:** Employee JWT (`employee_id=emp_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as emp_001.
  2. GET /api/v1/employees/emp_002.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Cannot access another employee's profile" }`

---

### RBAC-028: Admin Can Create IAM Package
- **Module:** IAM
- **Action:** package_create
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/iam/packages
- **Token:** Valid Admin JWT
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. POST /api/v1/iam/packages with `{ "name": "enterprise_plan", "permissions": ["booking.create", "booking.read", ...] }`
  3. Verify 201.
- **Expected Response:** `{ "id": "<uuid>", "name": "enterprise_plan", "permissions": [...] }`

---

### RBAC-029: SubAdmin Cannot Create IAM Package
- **Module:** IAM
- **Action:** package_create
- **Actor Role:** SubAdmin
- **Endpoint:** POST /api/v1/iam/packages
- **Token:** SubAdmin JWT (even with `iam.write` in policy)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as SubAdmin with `iam.write` permission.
  2. POST /api/v1/iam/packages.
  3. Verify 403 — package creation is Admin-only.
- **Expected Response:** `{ "detail": "Forbidden: Admin-only operation" }`

---

### RBAC-030: SubAdmin Can Create IAM Policy (Within Their Tenant Package)
- **Module:** IAM
- **Action:** policy_create
- **Actor Role:** SubAdmin
- **Endpoint:** POST /api/v1/iam/policies
- **Token:** SubAdmin JWT with `iam.write`
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as SubAdmin with `iam.write`.
  2. POST /api/v1/iam/policies with `{ "name": "booking_manager", "permissions": ["booking.read", "booking.create"] }`
  3. Verify 201 and policy is scoped to SubAdmin's tenant.
- **Expected Response:** `{ "id": "<uuid>", "tenant_id": "tenant_A", ... }`

---

### RBAC-031: SubAdmin Cannot Create Policy Exceeding Package Permissions
- **Module:** IAM
- **Action:** policy_create
- **Actor Role:** SubAdmin
- **Endpoint:** POST /api/v1/iam/policies
- **Token:** SubAdmin JWT with `iam.write`; tenant package does NOT include `driver.delete`
- **Expected Status:** 422 or 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as SubAdmin with `iam.write`.
  2. POST /api/v1/iam/policies with permissions EXCEEDING the PolicyPackage ceiling (e.g., include `driver.delete` when package doesn't allow it).
  3. Verify request is rejected.
- **Expected Response:** `{ "detail": "Policy permissions exceed the allowed PolicyPackage ceiling" }`

---

### RBAC-032: Employee Cannot Manage IAM Roles
- **Module:** IAM
- **Action:** role_create
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/iam/roles
- **Token:** Employee JWT
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/iam/roles.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-033: Driver Cannot Read All Employees
- **Module:** Employee
- **Action:** read
- **Actor Role:** Driver
- **Endpoint:** GET /api/v1/employees
- **Token:** Driver JWT
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Authenticate as Driver.
  2. GET /api/v1/employees.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-034: Escort Cannot Create Announcement
- **Module:** Announcement
- **Action:** create
- **Actor Role:** Escort
- **Endpoint:** POST /api/v1/announcements
- **Token:** Escort JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Escort.
  2. POST /api/v1/announcements.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-035: Escort Can Read Published Announcements
- **Module:** Announcement
- **Action:** read
- **Actor Role:** Escort
- **Endpoint:** GET /api/v1/announcements
- **Token:** Escort JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Create and publish an announcement targeted to tenant_A.
  2. Authenticate as Escort (tenant_A).
  3. GET /api/v1/announcements.
  4. Verify 200 and only PUBLISHED announcements returned.
- **Expected Response:** `{ "items": [{ "status": "Published", ... }] }`

---

### RBAC-036: Admin Can Read Reports
- **Module:** Report
- **Action:** read_booking_report
- **Actor Role:** Admin
- **Endpoint:** GET /api/v1/reports/bookings
- **Token:** Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. GET /api/v1/reports/bookings?start_date=2026-04-01&end_date=2026-04-30.
  3. Verify 200 with booking data from ALL tenants.
- **Expected Response:** `{ "items": [...], "total": N }`

---

### RBAC-037: Employee Cannot Read Reports
- **Module:** Report
- **Action:** read_booking_report
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/reports/bookings
- **Token:** Employee JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Employee.
  2. GET /api/v1/reports/bookings.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-038: Driver Cannot Read Reports
- **Module:** Report
- **Action:** read_booking_report
- **Actor Role:** Driver
- **Endpoint:** GET /api/v1/reports/bookings
- **Token:** Driver JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Driver.
  2. GET /api/v1/reports/bookings.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-039: Admin Can Update Tenant Config
- **Module:** Tenant Config
- **Action:** update_tenant
- **Actor Role:** Admin
- **Endpoint:** PUT /api/v1/tenants/{tenant_id}
- **Token:** Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. PUT /api/v1/tenants/tenant_A with config payload.
  3. Verify 200.
- **Expected Response:** `{ "id": "tenant_A", ... }`

---

### RBAC-040: Employee Cannot Modify Tenant Config
- **Module:** Tenant Config
- **Action:** update_tenant
- **Actor Role:** Employee
- **Endpoint:** PUT /api/v1/tenants/{tenant_id}
- **Token:** Employee JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Employee.
  2. PUT /api/v1/tenants/tenant_A.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-041: Admin Can Delete a Booking
- **Module:** Booking
- **Action:** delete
- **Actor Role:** Admin
- **Endpoint:** DELETE /api/v1/bookings/{booking_id}
- **Token:** Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. Create a booking.
  3. DELETE /api/v1/bookings/{booking_id}.
  4. Verify 200 or 204.
- **Expected Response:** `{ "detail": "Booking deleted" }` or 204 No Content.

---

### RBAC-042: Employee Cannot Delete Another Employee's Booking
- **Module:** Booking
- **Action:** delete
- **Actor Role:** Employee
- **Endpoint:** DELETE /api/v1/bookings/{booking_id}
- **Token:** Employee JWT (`employee_id=emp_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Create a booking for emp_002.
  2. Authenticate as emp_001.
  3. DELETE /api/v1/bookings/{booking_id_of_emp_002}.
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Cannot delete another employee's booking" }`

---

### RBAC-043: Vendor Cannot Dispatch a Route
- **Module:** Route
- **Action:** dispatch
- **Actor Role:** Vendor
- **Endpoint:** POST /api/v1/routes/{route_id}/dispatch
- **Token:** Vendor JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Vendor.
  2. POST /api/v1/routes/{route_id}/dispatch.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-044: Driver Triggers SOS Alert
- **Module:** Alert
- **Action:** create (SOS)
- **Actor Role:** Driver
- **Endpoint:** POST /api/v1/driver/sos
- **Token:** Driver JWT
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Driver with an active route.
  2. POST /api/v1/driver/sos with `{ "route_id": "...", "location": { "lat": ..., "lng": ... } }`.
  3. Verify 201 and alert with type=SOS, status=TRIGGERED.
- **Expected Response:** `{ "alert_id": "<uuid>", "type": "SOS", "status": "TRIGGERED" }`

---

### RBAC-045: Employee Cannot Create SOS Alert
- **Module:** Alert
- **Action:** create (SOS)
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/driver/sos
- **Token:** Employee JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/driver/sos.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Driver role required" }`

---

### RBAC-046: SubAdmin WITH alert.update Can Acknowledge Alert
- **Module:** Alert
- **Action:** update (acknowledge)
- **Actor Role:** SubAdmin
- **Endpoint:** PATCH /api/v1/alerts/{alert_id}/acknowledge
- **Token:** SubAdmin JWT with `alert.update` in policy
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Create an alert with TRIGGERED status.
  2. Authenticate as SubAdmin with `alert.update`.
  3. PATCH /api/v1/alerts/{alert_id}/acknowledge.
  4. Verify 200 and status = ACKNOWLEDGED.
- **Expected Response:** `{ "id": "<alert_id>", "status": "ACKNOWLEDGED" }`

---

### RBAC-047: Escort Cannot Acknowledge Alert
- **Module:** Alert
- **Action:** update (acknowledge)
- **Actor Role:** Escort
- **Endpoint:** PATCH /api/v1/alerts/{alert_id}/acknowledge
- **Token:** Escort JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Create an alert.
  2. Authenticate as Escort.
  3. PATCH /api/v1/alerts/{alert_id}/acknowledge.
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-048: Admin Can Create Vendor
- **Module:** Vendor
- **Action:** create
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/vendors
- **Token:** Admin JWT
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. POST /api/v1/vendors with `{ "name": "Speedy Cabs", "tenant_id": "tenant_A", ... }`.
  3. Verify 201.
- **Expected Response:** `{ "id": "<uuid>", "name": "Speedy Cabs" }`

---

### RBAC-049: Employee Cannot Create Vendor
- **Module:** Vendor
- **Action:** create
- **Actor Role:** Employee
- **Endpoint:** POST /api/v1/vendors
- **Token:** Employee JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/vendors.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-050: Admin Can Assign Role to Employee
- **Module:** IAM
- **Action:** role_assign
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/iam/roles/{role_id}/assign
- **Token:** Admin JWT
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Create a role with specific permissions.
  2. Authenticate as Admin.
  3. POST /api/v1/iam/roles/{role_id}/assign with `{ "user_id": "emp_001" }`.
  4. Verify 200.
- **Expected Response:** `{ "user_id": "emp_001", "role_id": "<role_id>", "assigned": true }`

---

### RBAC-051: Driver Cannot Access Tenant Config
- **Module:** Tenant Config
- **Action:** read_tenant
- **Actor Role:** Driver
- **Endpoint:** GET /api/v1/tenants/{tenant_id}
- **Token:** Driver JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Driver.
  2. GET /api/v1/tenants/tenant_A.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-052: SubAdmin Can Create Shift Config (With Permission)
- **Module:** Tenant Config
- **Action:** shift_create
- **Actor Role:** SubAdmin
- **Endpoint:** POST /api/v1/tenants/{tenant_id}/shifts
- **Token:** SubAdmin JWT with `tenant_config.write`
- **Expected Status:** 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as SubAdmin with `tenant_config.write`.
  2. POST /api/v1/tenants/tenant_A/shifts with shift payload.
  3. Verify 201 and shift scoped to tenant_A.
- **Expected Response:** `{ "id": "<uuid>", "tenant_id": "tenant_A", "shift_name": "Morning" }`

---

### RBAC-053: Driver Reads Own Assigned Route
- **Module:** Route
- **Action:** read
- **Actor Role:** Driver
- **Endpoint:** GET /api/v1/routes/{route_id}
- **Token:** Driver JWT (`driver_id=drv_001`) where route is assigned to drv_001
- **Expected Status:** 200
- **Test Type:** Positive
- **Steps:**
  1. Create a route and assign drv_001 as driver.
  2. Authenticate as drv_001.
  3. GET /api/v1/routes/{route_id}.
  4. Verify 200 with route details.
- **Expected Response:** `{ "id": "<route_id>", "driver_id": "drv_001", ... }`

---

### RBAC-054: Driver Cannot Read Route Assigned to Another Driver
- **Module:** Route
- **Action:** read
- **Actor Role:** Driver
- **Endpoint:** GET /api/v1/routes/{route_id}
- **Token:** Driver JWT (`driver_id=drv_001`)
- **Expected Status:** 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Create a route and assign drv_002.
  2. Authenticate as drv_001.
  3. GET /api/v1/routes/{route_id} (assigned to drv_002).
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Route not assigned to this driver" }`

---

### RBAC-055: Expired Token Returns 401
- **Module:** Auth
- **Action:** Any authenticated endpoint
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/bookings
- **Token:** Employee JWT with `exp` set in the past (already expired)
- **Expected Status:** 401
- **Test Type:** Token Manipulation
- **Steps:**
  1. Generate a JWT with `exp` = (now - 1 hour).
  2. GET /api/v1/bookings with `Authorization: Bearer <expired_token>`.
  3. Verify 401.
- **Expected Response:** `{ "detail": "Token has expired" }`

---

### RBAC-056: Pre-Auth Token Cannot Access Protected Endpoints
- **Module:** Auth
- **Action:** Pre-auth token misuse
- **Actor Role:** Employee (OTP stage, before select-tenant)
- **Endpoint:** POST /api/v1/bookings
- **Token:** Pre-auth JWT (no `tenant_id`, `stage=pre_auth`)
- **Expected Status:** 401 or 403
- **Test Type:** Privilege Escalation
- **Steps:**
  1. Complete OTP verification step → receive pre-auth token.
  2. Without completing select-tenant step, use pre-auth token on POST /api/v1/bookings.
  3. Verify request is rejected.
- **Expected Response:** `{ "detail": "Token stage insufficient: select-tenant required" }`
- **Security Note:** Pre-auth tokens should have a `stage` claim that is validated at protected endpoints.

---

### RBAC-057: Vendor Token Used on Driver-Specific Endpoint
- **Module:** Driver App
- **Action:** duty_start
- **Actor Role:** Vendor (misusing token on driver endpoint)
- **Endpoint:** POST /api/v1/driver/duty/start
- **Token:** Valid Vendor JWT (no `driver_id`)
- **Expected Status:** 403
- **Test Type:** Token Manipulation
- **Steps:**
  1. Authenticate as Vendor.
  2. POST /api/v1/driver/duty/start.
  3. Verify 403 — vendor role should not be able to call driver endpoints.
- **Expected Response:** `{ "detail": "Forbidden: Driver role required" }`

---

### RBAC-058: Employee from Different Tenant Uses Valid Token for Different Tenant's Resource
- **Module:** Booking
- **Action:** read
- **Actor Role:** Employee
- **Endpoint:** GET /api/v1/bookings/{booking_id}
- **Token:** Valid Employee JWT (`tenant_id=tenant_B`) used to access tenant_A booking
- **Expected Status:** 403
- **Test Type:** Cross-Tenant Isolation
- **Steps:**
  1. Create a booking in tenant_A.
  2. Authenticate as Employee in tenant_B.
  3. GET /api/v1/bookings/{booking_id_from_tenant_A}.
  4. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Cross-tenant access denied" }`
- **Security Note:** Since `check_tenant` is commented out in PermissionChecker, handlers MUST perform this check themselves. If they don't, this test will FAIL — exposing a data breach.

---

### RBAC-059: Invalid Role in JWT Does Not Grant Access
- **Module:** Booking
- **Action:** create
- **Actor Role:** Attacker (injected role)
- **Endpoint:** POST /api/v1/bookings
- **Token:** JWT with tampered `role=admin` payload but valid signature for a regular employee token
- **Expected Status:** 401
- **Test Type:** Token Manipulation
- **Steps:**
  1. Obtain a valid Employee JWT.
  2. Decode the JWT, modify `role` claim to `admin`.
  3. Re-encode without re-signing (signature becomes invalid).
  4. POST /api/v1/bookings with tampered token.
  5. Verify 401 — signature validation should fail.
- **Expected Response:** `{ "detail": "Token signature verification failed" }`
- **Security Note:** JWT signature must be validated using the server's secret. Any tampered payload must be rejected.

---

### RBAC-060: SubAdmin from Tenant A Cannot Read IAM Packages from Tenant B
- **Module:** IAM
- **Action:** package_read
- **Actor Role:** SubAdmin
- **Endpoint:** GET /api/v1/iam/packages
- **Token:** SubAdmin JWT (`tenant_id=tenant_A`, `iam.read` permission)
- **Expected Status:** 200 (but results scoped to tenant_A only)
- **Test Type:** Cross-Tenant Isolation
- **Steps:**
  1. Create IAM packages for tenant_A and tenant_B.
  2. Authenticate as SubAdmin in tenant_A with `iam.read`.
  3. GET /api/v1/iam/packages.
  4. Verify that response contains ONLY tenant_A packages, NOT tenant_B.
- **Expected Response:** `{ "items": [/* only tenant_A packages */] }`

---

### RBAC-061: Employee Cannot Delete a Booking
- **Module:** Booking
- **Action:** delete
- **Actor Role:** Employee
- **Endpoint:** DELETE /api/v1/bookings/{booking_id}
- **Token:** Employee JWT (own booking)
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Create a booking as Employee emp_001.
  2. DELETE /api/v1/bookings/{booking_id} using emp_001's token.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Employee cannot delete bookings" }`

---

### RBAC-062: Vendor Cannot Access IAM Endpoints
- **Module:** IAM
- **Action:** role_read
- **Actor Role:** Vendor
- **Endpoint:** GET /api/v1/iam/roles
- **Token:** Vendor JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Vendor.
  2. GET /api/v1/iam/roles.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

### RBAC-063: Admin Can Bulk Import Employees
- **Module:** Employee
- **Action:** bulk_import
- **Actor Role:** Admin
- **Endpoint:** POST /api/v1/employees/bulk-import
- **Token:** Admin JWT
- **Expected Status:** 200 or 201
- **Test Type:** Positive
- **Steps:**
  1. Authenticate as Admin.
  2. POST /api/v1/employees/bulk-import with a valid CSV/JSON payload of employees.
  3. Verify 200/201 and employees created.
- **Expected Response:** `{ "imported": 10, "failed": 0, "errors": [] }`

---

### RBAC-064: Vendor Cannot Bulk Import Employees
- **Module:** Employee
- **Action:** bulk_import
- **Actor Role:** Vendor
- **Endpoint:** POST /api/v1/employees/bulk-import
- **Token:** Vendor JWT
- **Expected Status:** 403
- **Test Type:** Negative
- **Steps:**
  1. Authenticate as Vendor.
  2. POST /api/v1/employees/bulk-import.
  3. Verify 403.
- **Expected Response:** `{ "detail": "Forbidden: Insufficient permissions" }`

---

## Part 3: Privilege Escalation Scenarios

---

### PRIV-ESC-001: Employee Attempts IAM Management
- **Actor:** Employee (`emp_001`, `tenant_A`)
- **Target:** POST /api/v1/iam/roles
- **Expected:** 403
- **Attack Vector:** Employee calls IAM role creation endpoint hoping it's not permission-gated.
- **Steps:**
  1. Authenticate as Employee emp_001.
  2. POST /api/v1/iam/roles with `{ "name": "super_role", "permissions": ["iam.write", "booking.delete"] }`.
  3. Verify 403 with no role created.
- **Validation:** Confirm no new role exists in DB after the attempt.
- **Security Note:** IAM endpoints must require explicit `iam.write` permission. Employee role must never have this by default.

---

### PRIV-ESC-002: Vendor Attempts to Read Another Vendor's Vehicles
- **Actor:** Vendor (`vnd_001`, `tenant_A`)
- **Target:** GET /api/v1/vendors/vnd_002/vehicles
- **Expected:** 403
- **Attack Vector:** Vendor guesses another vendor's ID and attempts to access their vehicle roster.
- **Steps:**
  1. Authenticate as vnd_001.
  2. GET /api/v1/vendors/vnd_002/vehicles.
  3. Verify 403.
- **Validation:** Confirm no vehicle data from vnd_002 is returned.
- **Security Note:** Handler must compare token's `vendor_id` with path parameter `vendor_id`.

---

### PRIV-ESC-003: Driver Attempts to Read All Employees
- **Actor:** Driver (`drv_001`, `tenant_A`)
- **Target:** GET /api/v1/employees
- **Expected:** 403
- **Attack Vector:** Driver calls employee list endpoint; if not permission-gated, could expose PII.
- **Steps:**
  1. Authenticate as Driver.
  2. GET /api/v1/employees.
  3. Verify 403.
- **Validation:** No employee records returned.
- **Security Note:** Employee list endpoint should only be accessible to Admin and SubAdmin with `employee.read`.

---

### PRIV-ESC-004: Employee Attempts to Publish Announcement
- **Actor:** Employee (`emp_001`, `tenant_A`)
- **Target:** POST /api/v1/announcements/{id}/publish
- **Expected:** 403
- **Attack Vector:** Employee tries to publish an announcement targeting all employees.
- **Steps:**
  1. Create a DRAFT announcement as Admin.
  2. Authenticate as Employee.
  3. POST /api/v1/announcements/{id}/publish.
  4. Verify 403 and announcement remains DRAFT.
- **Validation:** GET announcement to confirm status = DRAFT.

---

### PRIV-ESC-005: Vendor Attempts to Create System-Level IAM Role
- **Actor:** Vendor (`vnd_001`, `tenant_A`)
- **Target:** POST /api/v1/iam/roles
- **Expected:** 403
- **Attack Vector:** Vendor crafts a request to create an IAM role with full permissions.
- **Steps:**
  1. Authenticate as Vendor.
  2. POST /api/v1/iam/roles with `{ "name": "hacked_admin", "permissions": ["booking.delete", "iam.write"] }`.
  3. Verify 403.
- **Validation:** Confirm no new role in DB.

---

### PRIV-ESC-006: SubAdmin Attempts to Exceed Policy Package Permissions
- **Actor:** SubAdmin (`tenant_A`), tenant package has only `[booking.read, booking.create]`
- **Target:** POST /api/v1/iam/policies
- **Expected:** 422 or 403
- **Attack Vector:** SubAdmin tries to create a policy with `route.dispatch` which is not in their package.
- **Steps:**
  1. Authenticate as SubAdmin with `iam.write` and a limited PolicyPackage.
  2. POST /api/v1/iam/policies with `{ "permissions": ["booking.read", "route.dispatch"] }`.
  3. Verify rejection.
- **Validation:** Policy not created; `route.dispatch` not accessible by any role under this tenant.

---

### PRIV-ESC-007: Pre-Auth Token Used to Access Protected Resources
- **Actor:** Employee in OTP verification flow (pre-auth token issued)
- **Target:** POST /api/v1/bookings
- **Expected:** 401 or 403
- **Attack Vector:** Attacker intercepts pre-auth token and tries to use it for booking API without completing tenant selection.
- **Steps:**
  1. Initiate OTP login flow, get pre-auth token.
  2. WITHOUT calling select-tenant endpoint, use pre-auth token on POST /api/v1/bookings.
  3. Verify rejection.
- **Validation:** Token stage check fails; no booking created.

---

### PRIV-ESC-008: Driver Token Used on Employee Booking Endpoints
- **Actor:** Driver (`drv_001`)
- **Target:** POST /api/v1/bookings
- **Expected:** 403
- **Attack Vector:** A driver (likely an employee in a dual role) tries to create a booking using their driver token.
- **Steps:**
  1. Authenticate as Driver (drv_001 who has no employee role).
  2. POST /api/v1/bookings.
  3. Verify 403.
- **Validation:** No booking created.

---

### PRIV-ESC-009: JWT Role Claim Injection Attack
- **Actor:** Attacker with a valid Employee JWT
- **Target:** POST /api/v1/iam/packages
- **Expected:** 401 (signature failure)
- **Attack Vector:** Attacker decodes JWT, changes `role` from `employee` to `admin`, attempts access.
- **Steps:**
  1. Get valid Employee JWT.
  2. Base64-decode the payload segment.
  3. Modify `"role": "employee"` → `"role": "admin"`.
  4. Re-encode (do NOT re-sign).
  5. Use tampered token on POST /api/v1/iam/packages.
  6. Verify 401 — signature mismatch.
- **Validation:** JWT library must catch signature mismatch; no access granted.
- **Security Note:** Must use asymmetric signing (RS256) or a strong HMAC secret. Never accept unsigned (`alg: none`) JWTs.

---

### PRIV-ESC-010: Escort Token Used on Announcement Publish Endpoint
- **Actor:** Escort (`tenant_A`)
- **Target:** POST /api/v1/announcements/{id}/publish
- **Expected:** 403
- **Attack Vector:** Escort (who can read announcements) tries to publish one.
- **Steps:**
  1. Create DRAFT announcement as Admin.
  2. Authenticate as Escort.
  3. POST /api/v1/announcements/{id}/publish.
  4. Verify 403 and status remains DRAFT.

---

### PRIV-ESC-011: Employee Attempts to Access Admin-Only Tenant Creation
- **Actor:** Employee
- **Target:** POST /api/v1/tenants
- **Expected:** 403
- **Attack Vector:** Employee calls tenant creation endpoint — Admin-only.
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/tenants with a new tenant payload.
  3. Verify 403.
- **Validation:** No new tenant created.

---

### PRIV-ESC-012: Vendor Attempts to Dispatch a Route
- **Actor:** Vendor (`vnd_001`)
- **Target:** POST /api/v1/routes/{route_id}/dispatch
- **Expected:** 403
- **Attack Vector:** Vendor (who owns vehicles on the route) tries to dispatch it.
- **Steps:**
  1. Create a route with vnd_001's vehicle.
  2. Authenticate as Vendor.
  3. POST /api/v1/routes/{route_id}/dispatch.
  4. Verify 403.

---

### PRIV-ESC-013: Driver Attempts to Assign Vehicle to Route
- **Actor:** Driver (`drv_001`)
- **Target:** POST /api/v1/routes/{route_id}/assign-vehicle
- **Expected:** 403
- **Attack Vector:** Driver tries to assign a different vehicle to their route (e.g., to choose a larger vehicle).
- **Steps:**
  1. Create a route.
  2. Authenticate as drv_001.
  3. POST /api/v1/routes/{route_id}/assign-vehicle with `{ "vehicle_id": "veh_002" }`.
  4. Verify 403.

---

### PRIV-ESC-014: Employee Attempts to Read All Bookings (List Endpoint)
- **Actor:** Employee (`emp_001`)
- **Target:** GET /api/v1/bookings (no filter — fetches all)
- **Expected:** 403 or 200 with only own bookings
- **Attack Vector:** Employee removes their own employee_id filter to see all bookings.
- **Steps:**
  1. Authenticate as Employee.
  2. GET /api/v1/bookings (no `employee_id` filter).
  3. Verify that ONLY emp_001's bookings are returned (not all bookings in tenant).
- **Validation:** Response items all have `employee_id = emp_001`.
- **Security Note:** Handler must always inject `employee_id` filter when the caller is an Employee role.

---

### PRIV-ESC-015: SubAdmin Attempts to Assign Role in a Different Tenant
- **Actor:** SubAdmin (`tenant_A`)
- **Target:** POST /api/v1/iam/roles/{role_id}/assign
- **Expected:** 403
- **Attack Vector:** SubAdmin with `iam.write` tries to assign a role to a user in tenant_B.
- **Steps:**
  1. Authenticate as SubAdmin in tenant_A.
  2. POST /api/v1/iam/roles/{role_id}/assign with `{ "user_id": "user_in_tenant_B" }`.
  3. Verify 403 — role assignment must be scoped to SubAdmin's tenant.
- **Validation:** No role assigned to user in tenant_B.

---

## Part 4: Token Manipulation Checks

---

### TOKEN-001: Tampered JWT Payload — Role Injection
- **Attack:** Decode valid Employee JWT → change `"role": "employee"` to `"role": "admin"` → re-encode without re-signing.
- **Endpoint:** POST /api/v1/iam/packages
- **Expected Status:** 401
- **Steps:**
  1. Obtain valid Employee JWT.
  2. Split by `.` → decode middle segment (payload) from base64url.
  3. Modify `role` claim.
  4. Re-encode modified payload, reassemble token (old signature + new payload = invalid).
  5. Call POST /api/v1/iam/packages with tampered token.
- **Expected Response:** `{ "detail": "Invalid token signature" }`
- **Validation:** JWT library must detect signature mismatch and return 401.

---

### TOKEN-002: JWT Signed with Wrong Secret
- **Attack:** Create a valid-looking JWT signed with a different HMAC secret (or wrong private key).
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Generate a JWT using a different secret key: `jwt.encode(payload, "wrong_secret", algorithm="HS256")`.
  2. GET /api/v1/bookings with `Authorization: Bearer <wrong_secret_token>`.
- **Expected Response:** `{ "detail": "Invalid token signature" }`

---

### TOKEN-003: Expired JWT — `exp` Claim in the Past
- **Attack:** Use a valid JWT where `exp` is set to Unix timestamp in the past.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Generate JWT with `exp = int(time.time()) - 3600` (1 hour ago).
  2. GET /api/v1/bookings with this token.
- **Expected Response:** `{ "detail": "Token has expired" }`
- **Validation:** Must be handled before any permission checks.

---

### TOKEN-004: Future `nbf` Claim (Not Yet Valid)
- **Attack:** Use a JWT with `nbf` (not before) set to a future timestamp.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Generate JWT with `nbf = int(time.time()) + 3600` (valid 1 hour from now).
  2. GET /api/v1/bookings with this token.
- **Expected Response:** `{ "detail": "Token is not yet valid" }`

---

### TOKEN-005: Missing Authorization Header
- **Attack:** Omit `Authorization` header entirely.
- **Endpoint:** POST /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. POST /api/v1/bookings with no `Authorization` header.
  2. Payload is valid.
- **Expected Response:** `{ "detail": "Not authenticated" }` (FastAPI default)

---

### TOKEN-006: `Authorization: Bearer null`
- **Attack:** Send the literal string `null` as the Bearer token.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. GET /api/v1/bookings with header `Authorization: Bearer null`.
- **Expected Response:** `{ "detail": "Invalid token format" }` or `{ "detail": "Not authenticated" }`
- **Validation:** Must not return 500 or treat "null" as a valid token.

---

### TOKEN-007: `Authorization: Basic <base64>` Instead of Bearer
- **Attack:** Send HTTP Basic Auth credentials instead of a Bearer JWT.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Encode `username:password` in base64.
  2. GET /api/v1/bookings with `Authorization: Basic <base64_encoded_creds>`.
- **Expected Response:** `{ "detail": "Invalid authentication scheme. Expected Bearer" }`
- **Validation:** Server must check auth scheme; Basic auth credentials must not be accepted on JWT-protected endpoints.

---

### TOKEN-008: Replaying Invalidated Session Token After Logout
- **Attack:** Obtain a valid JWT → logout → replay the same JWT on a protected endpoint.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Authenticate as Employee → receive access token.
  2. POST /api/v1/auth/logout with the token.
  3. Immediately GET /api/v1/bookings using the same token.
- **Expected Response:** `{ "detail": "SESSION_EXPIRED" }` or `{ "detail": "Token has been invalidated" }`
- **Validation:** Server must maintain a token blocklist (Redis) or use short-lived tokens with explicit invalidation.

---

### TOKEN-009: Pre-Auth Token Used as Full Access Token
- **Attack:** After OTP verification, use the pre-auth token (before select-tenant step) to access final API endpoints.
- **Endpoint:** POST /api/v1/bookings
- **Expected Status:** 401 or 403
- **Steps:**
  1. Call POST /api/v1/auth/otp/verify → receive pre-auth token.
  2. Use pre-auth token on POST /api/v1/bookings WITHOUT calling select-tenant.
- **Expected Response:** `{ "detail": "Token stage insufficient: full authentication required" }`
- **Validation:** Pre-auth tokens must have a `stage=pre_auth` claim that protected endpoints explicitly reject.

---

### TOKEN-010: Refresh Token Used as Access Token
- **Attack:** Use the refresh token (obtained during login) directly as the `Authorization: Bearer` access token on a protected API endpoint.
- **Endpoint:** GET /api/v1/bookings
- **Expected Status:** 401
- **Steps:**
  1. Authenticate → receive `access_token` and `refresh_token`.
  2. GET /api/v1/bookings with `Authorization: Bearer <refresh_token>`.
- **Expected Response:** `{ "detail": "Invalid token type: refresh token cannot be used as access token" }`
- **Validation:** Tokens must have a `type` claim (`access` vs `refresh`). Protected endpoints must validate `type == "access"`.

---

## Footnotes & Security Notes

### Critical Security Bugs Summary

| ID | Bug | Location | Severity | Impact |
|----|-----|----------|----------|--------|
| BUG-001 | All permission checks commented out | `route_grouping.py` | P0 Critical | Full unauthenticated CRUD on route groupings |
| BUG-002 | No auth dependency on push notification endpoints | Push notification handler | P0 Critical | Anyone can send push notifications to any device |
| BUG-003 | `check_tenant` flag non-functional (commented out) | `permission_checker.py` | P1 High | Cross-tenant data access if handler doesn't enforce tenant |
| BUG-004 | Password reset stub always returns 200 | Auth module | P2 Medium | No password reset actually implemented; false sense of security |

### Testing Recommendations

1. **Run TOKEN-001 through TOKEN-010 in CI** — token manipulation must never cause a 500 error.
2. **Run RBAC-016, RBAC-017, RBAC-018, RBAC-019 and mark as KNOWN FAILURES** until BUG-001 and BUG-002 are fixed.
3. **Cross-tenant tests (RBAC-020, RBAC-021, RBAC-058)** depend entirely on handler-level enforcement since `check_tenant` is non-functional.
4. **PRIV-ESC-009 (JWT Injection)** must be run against production-equivalent configuration — never against a test server with `alg: none` allowed.
5. **Maintain a negative test suite** — all `❌ DENIED` cells in the matrix must have corresponding automated test cases.
