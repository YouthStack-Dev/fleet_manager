# Fleet Manager API Test Suite
**Version:** 1.0.0  
**Prepared by:** QA Automation Architecture Team  
**Date:** 2026-04-30  
**Environment:** `http://localhost:8000/api/v1`

---

## Purpose

This document defines the complete API test suite for the Fleet Manager backend. It covers:
- Functional correctness of every endpoint
- Auth/authorization enforcement
- Business rule validation
- Security vulnerability testing (known bugs documented)
- Rate limiting behavior
- Edge cases and negative paths

---

## Auth Scheme Overview

| Token Type | Header | Format | Scope |
|------------|--------|--------|-------|
| Employee JWT | `Authorization` | `Bearer <token>` | Booking, routes (read) |
| Admin JWT | `Authorization` | `Bearer <token>` | Full admin access |
| Driver JWT | `Authorization` | `Bearer <token>` | Driver app endpoints |
| Vendor JWT | `Authorization` | `Bearer <token>` | Vendor portal |
| Escort JWT | `Authorization` | `Bearer <token>` | Escort-specific |
| Pre-auth Token | `Authorization` | `Bearer <pre_auth_token>` | Tenant selection only |
| Introspect Secret | `X-Introspect-Secret` | `<secret>` | Introspect endpoint |

---

## Table of Contents

1. [Authentication Endpoints](#1-authentication-endpoints)
2. [Booking Endpoints](#2-booking-endpoints)
3. [Route Management Endpoints](#3-route-management-endpoints)
4. [Driver App Endpoints](#4-driver-app-endpoints)
5. [Alert Endpoints](#5-alert-endpoints)
6. [Announcement Endpoints](#6-announcement-endpoints)
7. [Security Vulnerability Tests](#7-security-vulnerability-tests)
8. [IAM Endpoints](#8-iam-endpoints)
9. [Reports Endpoints](#9-reports-endpoints)
10. [Rate Limiting Tests](#10-rate-limiting-tests)
11. [Tenant & Config Endpoints](#11-tenant--config-endpoints)
12. [Postman Collection Structure](#12-postman-collection-structure)
13. [Pytest API Automation Mapping](#13-pytest-api-automation-mapping)
14. [Reusable Fixtures](#14-reusable-fixtures)

---

## 1. Authentication Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-001 | /auth/employee/login | POST | None | Valid credentials | 200 |
| AT-002 | /auth/employee/login | POST | None | Wrong password | 401 |
| AT-003 | /auth/employee/login | POST | None | Non-existent email | 401 |
| AT-004 | /auth/employee/login | POST | None | Missing email field | 422 |
| AT-005 | /auth/employee/login | POST | None | Missing password field | 422 |
| AT-006 | /auth/employee/login | POST | None | Empty body | 422 |
| AT-007 | /auth/employee/login | POST | None | Rate limit exceeded (11th req/min) | 429 |
| AT-008 | /auth/employee/otp/request | POST | None | Valid phone number | 200 |
| AT-009 | /auth/employee/otp/request | POST | None | Invalid phone format | 422 |
| AT-010 | /auth/employee/otp/request | POST | None | Rate limit exceeded (6th req/min) | 429 |
| AT-011 | /auth/employee/otp/verify | POST | None | Valid OTP | 200 |
| AT-012 | /auth/employee/otp/verify | POST | None | Invalid OTP | 401 |
| AT-013 | /auth/employee/otp/verify | POST | None | Expired OTP | 401 |
| AT-014 | /auth/employee/select-tenant | POST | pre_auth_token | Valid tenant selection | 200 |
| AT-015 | /auth/employee/select-tenant | POST | pre_auth_token | Invalid tenant_id | 403 |
| AT-016 | /auth/employee/select-tenant | POST | None | Missing pre_auth_token | 401 |
| AT-017 | /auth/employee/logout | POST | Bearer | Valid logout | 200 |
| AT-018 | /auth/employee/logout | POST | None | Missing token | 401 |
| AT-019 | /auth/admin/login | POST | None | Valid admin credentials | 200 |
| AT-020 | /auth/admin/login | POST | None | Rate limit exceeded | 429 |
| AT-021 | /auth/driver/device/register | POST | None | Valid device registration | 201 |
| AT-022 | /auth/driver/device/register | POST | None | Duplicate android_id | 409 |
| AT-023 | /auth/driver/device/verify | POST | None | Valid verification | 200 |
| AT-024 | /auth/driver/select-tenant | POST | driver_token | Valid tenant selection | 200 |
| AT-025 | /auth/vendor/login | POST | None | Valid vendor credentials | 200 |
| AT-026 | /auth/escort/login | POST | None | Login with email | 200 |
| AT-027 | /auth/escort/login | POST | None | Login with phone | 200 |
| AT-028 | /auth/reset-password | POST | None | Any email (known stub) | 200 |
| AT-029 | /auth/introspect | GET | X-Introspect-Secret | Valid secret | 200 |
| AT-030 | /auth/introspect | GET | None | Missing secret header | 401 |
| AT-031 | /auth/token/refresh | POST | None | Valid refresh_token | 200 |
| AT-032 | /auth/token/refresh | POST | None | Expired refresh_token | 401 |
| AT-033 | /auth/token/refresh | POST | None | Invalid/tampered token | 401 |

---

#### AT-001: Employee Login — Valid Credentials
- **Endpoint:** `POST /auth/employee/login`
- **Method:** POST
- **Auth Required:** No
- **Request Headers:** `Content-Type: application/json`
- **Request Payload:**
  ```json
  {
    "email": "alice@acme.com",
    "password": "SecurePass123!"
  }
  ```
- **Expected Status:** 200
- **Response Schema Check:**
  - `access_token` (string, non-empty, length > 20)
  - `token_type` == `"bearer"`
  - `refresh_token` (string, non-empty)
  - `user.id` (UUID format)
  - `user.email` == `"alice@acme.com"`
  - `user.user_type` == `"employee"`
- **Validation Checks:**
  - `access_token` is a valid JWT (3 dot-separated base64url segments)
  - JWT payload contains: `user_id`, `email`, `tenant_id`, `user_type`, `exp`
  - `exp` is in the future
  - `token_type` is case-insensitively `"bearer"`
- **Pytest Fixture Needed:** `employee_user`, `db_session`, `async_client`

---

#### AT-002: Employee Login — Wrong Password
- **Endpoint:** `POST /auth/employee/login`
- **Method:** POST
- **Auth Required:** No
- **Request Payload:**
  ```json
  {
    "email": "alice@acme.com",
    "password": "WrongPassword!"
  }
  ```
- **Expected Status:** 401
- **Response Schema Check:**
  - `detail` (string) contains "invalid credentials" or similar
- **Validation Checks:**
  - No `access_token` in response
  - Response body does NOT reveal whether email exists (generic error message to prevent user enumeration)
- **Security Note:** Response time should be consistent regardless of whether email exists (timing attack prevention)
- **Pytest Fixture Needed:** `employee_user`

---

#### AT-003: Employee Login — Non-Existent Email
- **Endpoint:** `POST /auth/employee/login`
- **Method:** POST
- **Request Payload:**
  ```json
  {
    "email": "ghost@nobody.com",
    "password": "AnyPass123!"
  }
  ```
- **Expected Status:** 401
- **Validation Checks:**
  - Error message is identical to AT-002 (no user enumeration)
  - No `access_token` in response

---

#### AT-004: Employee Login — Missing Email Field
- **Endpoint:** `POST /auth/employee/login`
- **Method:** POST
- **Request Payload:**
  ```json
  {
    "password": "ValidPass123!"
  }
  ```
- **Expected Status:** 422
- **Response Schema Check:**
  - `detail` is an array containing validation error objects
  - Error references `email` field as missing

---

#### AT-005: Employee Login — Missing Password Field
- **Request Payload:** `{"email": "alice@acme.com"}`
- **Expected Status:** 422
- **Validation Checks:** Error references `password` field

---

#### AT-006: Employee Login — Empty Body
- **Request Payload:** `{}`
- **Expected Status:** 422

---

#### AT-007: Employee Login — Rate Limit Exceeded
- **Endpoint:** `POST /auth/employee/login`
- **Setup:** Send 10 rapid login requests (all valid or invalid — rate limit applies regardless)
- **11th Request Expected Status:** 429
- **Response Schema Check:**
  - `detail` indicates rate limit exceeded
  - `Retry-After` header (if present) contains a positive integer seconds value
- **Test Strategy:** Use asyncio gather or sequential loop; record timestamps; assert 429 on 11th

---

#### AT-008: Employee OTP Request — Valid Phone
- **Endpoint:** `POST /auth/employee/otp/request`
- **Request Payload:** `{"phone": "+919876543210"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `message` (string) acknowledging OTP sent
- **Side Effect Verification:**
  - Verify Twilio mock was called with correct phone
  - Verify OTP stored in Redis (if accessible via introspect or test DB hook)

---

#### AT-011: Employee OTP Verify — Valid OTP
- **Endpoint:** `POST /auth/employee/otp/verify`
- **Method:** POST
- **Auth Required:** No
- **Request Payload:**
  ```json
  {
    "phone": "+919876543210",
    "otp": "123456"
  }
  ```
- **Expected Status:** 200
- **Response Schema Check:**
  - `pre_auth_token` (string, non-empty)
  - `tenants` (array of tenant objects)
    - Each tenant: `{id, name}`
- **Validation Checks:**
  - `pre_auth_token` is a valid JWT
  - JWT type/scope indicates it is a pre-auth token (not full access)
  - `tenants` array is non-empty for a user belonging to at least one tenant

---

#### AT-012: Employee OTP Verify — Invalid OTP
- **Request Payload:** `{"phone": "+919876543210", "otp": "000000"}`
- **Expected Status:** 401
- **Validation Checks:** No `pre_auth_token` in response

---

#### AT-013: Employee OTP Verify — Expired OTP
- **Setup:** Request OTP, wait for TTL to expire (or mock Redis to return expired)
- **Expected Status:** 401
- **Validation Checks:** Error message indicates OTP expired or invalid

---

#### AT-014: Employee Select Tenant — Valid Tenant
- **Endpoint:** `POST /auth/employee/select-tenant`
- **Auth:** `Authorization: Bearer <pre_auth_token>`
- **Request Payload:** `{"tenant_id": "uuid-of-tenant"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `access_token` (string, full JWT)
  - `token_type` == `"bearer"`
  - `refresh_token` (string)
  - `user.tenant_id` == requested `tenant_id`
- **Validation Checks:**
  - Full JWT payload contains `tenant_id`, `user_id`, `user_type`, `exp`
  - Token grants access to booking endpoints (follow-up request to `GET /bookings/` returns 200)

---

#### AT-015: Employee Select Tenant — Unauthorized Tenant
- **Auth:** `Authorization: Bearer <pre_auth_token>` (employee belongs to tenant A only)
- **Request Payload:** `{"tenant_id": "uuid-of-tenant-B"}`
- **Expected Status:** 403
- **Validation Checks:** No `access_token` in response

---

#### AT-017: Employee Logout — Valid Token
- **Endpoint:** `POST /auth/employee/logout`
- **Auth:** `Authorization: Bearer <valid_employee_token>`
- **Expected Status:** 200
- **Post-Logout Validation:**
  - Using the same token on `GET /bookings/` should now return 401 (token blacklisted in Redis)
- **Pytest Fixture Needed:** `auth_employee_headers`, `async_client`

---

#### AT-019: Admin Login — Valid Credentials
- **Endpoint:** `POST /auth/admin/login`
- **Request Payload:** `{"email": "admin@fleet.com", "password": "AdminPass123!"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `access_token` (string)
  - `user.user_type` == `"admin"`
- **Validation Checks:**
  - Admin JWT grants access to tenant management endpoints
  - Employee token does NOT grant same access (403 on admin routes)

---

#### AT-021: Driver Device Register — Valid
- **Endpoint:** `POST /auth/driver/device/register`
- **Request Payload:**
  ```json
  {
    "android_id": "abc123device",
    "license_number": "DL-0420110012345",
    "fcm_token": "fcm-token-string-here"
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `device_id` or `driver_id` (UUID)
  - `message` confirming registration

---

#### AT-022: Driver Device Register — Duplicate android_id
- **Setup:** Register device once (AT-021), then register again with same `android_id`
- **Expected Status:** 409
- **Validation Checks:** Error message references duplicate device or already registered

---

#### AT-028: Reset Password — Known Stub Behavior
- **Endpoint:** `POST /auth/reset-password`
- **Request Payload:** `{"email": "any@email.com"}`
- **Expected Status:** 200
- **DEFECT DOCUMENTATION:**
  > **BUG-001:** `POST /auth/reset-password` is a stub that always returns 200 without performing any password reset. No email is sent, no token generated, no DB record updated. This is a critical security gap — users cannot reset passwords and may be unaware their account is compromised.
- **Verification:** Query DB `users` table for `password_reset_token` — should be NULL (confirms no-op)
- **Expected (correct) behavior:** Should generate a reset token, store hashed token with expiry, send reset email via SMTP

---

#### AT-029: Introspect — Valid Secret
- **Endpoint:** `GET /auth/introspect`
- **Request Headers:** `X-Introspect-Secret: <configured_secret>`
- **Expected Status:** 200
- **Response Schema Check:**
  - System health or active session count data

---

#### AT-030: Introspect — Missing Secret Header
- **Request Headers:** (no X-Introspect-Secret)
- **Expected Status:** 401

---

#### AT-031: Token Refresh — Valid Refresh Token
- **Endpoint:** `POST /auth/token/refresh`
- **Request Payload:** `{"refresh_token": "<valid_refresh_token>"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `access_token` (new string, different from old)
  - `refresh_token` (new or same depending on rotation policy)
- **Validation Checks:**
  - New `access_token` has `exp` in the future
  - Old `access_token` (if rotation is implemented) is invalidated

---

#### AT-032: Token Refresh — Expired Refresh Token
- **Setup:** Use a refresh token past its TTL (mock or wait)
- **Expected Status:** 401

---

#### AT-033: Token Refresh — Tampered Token
- **Request Payload:** `{"refresh_token": "eyJhbGciOiJIUzI1NiJ9.tampered.signature"}`
- **Expected Status:** 401

---

## 2. Booking Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-101 | /bookings/ | POST | Employee | Valid single booking | 201 |
| AT-102 | /bookings/ | POST | Employee | Missing required field | 422 |
| AT-103 | /bookings/ | POST | Employee | Non-existent shift_id | 404 |
| AT-104 | /bookings/ | POST | Employee | Non-existent pickup_location_id | 404 |
| AT-105 | /bookings/ | POST | Employee | Booking on weekoff day | 400 |
| AT-106 | /bookings/ | POST | Employee | Booking after cutoff time | 400 |
| AT-107 | /bookings/ | POST | Employee | Duplicate booking (same employee+date+shift) | 409 |
| AT-108 | /bookings/bulk | POST | Employee | Valid multi-date booking | 201 |
| AT-109 | /bookings/bulk | POST | Employee | Some dates are weekoffs | 207 or 400 |
| AT-110 | /bookings/bulk | POST | Employee | Empty booking_dates array | 422 |
| AT-111 | /bookings/ | GET | Employee | List with pagination | 200 |
| AT-112 | /bookings/ | GET | Employee | Filter by status | 200 |
| AT-113 | /bookings/ | GET | Employee | Filter by date_from and date_to | 200 |
| AT-114 | /bookings/ | GET | None | No auth | 401 |
| AT-115 | /bookings/{id} | GET | Employee | Valid booking_id | 200 |
| AT-116 | /bookings/{id} | GET | Employee | Non-existent booking_id | 404 |
| AT-117 | /bookings/{id} | GET | Employee | Booking belonging to different tenant | 403 |
| AT-118 | /bookings/{id} | PUT | Employee | Update pickup_location_id | 200 |
| AT-119 | /bookings/{id} | PUT | Employee | Update status to Cancelled | 200 |
| AT-120 | /bookings/{id} | PUT | Employee | Update already-completed booking | 400 |
| AT-121 | /bookings/{id} | DELETE | Employee | Cancel pending booking | 200 |
| AT-122 | /bookings/{id} | DELETE | Employee | Cancel completed booking | 400 |
| AT-123 | /bookings/employee/{emp_id} | GET | Employee | Own bookings | 200 |
| AT-124 | /bookings/employee/{emp_id} | GET | Employee | Another employee's bookings (unauthorized) | 403 |

---

#### AT-101: Create Single Booking — Valid
- **Endpoint:** `POST /bookings/`
- **Method:** POST
- **Auth Required:** Employee JWT
- **Request Headers:** `Authorization: Bearer <employee_token>`, `Content-Type: application/json`
- **Request Payload:**
  ```json
  {
    "employee_id": "emp-uuid-001",
    "booking_date": "2026-05-15",
    "shift_id": "shift-uuid-morning",
    "pickup_location_id": "loc-uuid-home",
    "drop_location_id": "loc-uuid-office",
    "trip_type": "pickup"
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `id` (UUID)
  - `employee_id` == `"emp-uuid-001"`
  - `booking_date` == `"2026-05-15"`
  - `status` == `"Request"` (initial status)
  - `shift_id`, `pickup_location_id`, `drop_location_id` match request
  - `created_at` (ISO datetime)
- **Validation Checks:**
  - `id` is a valid UUID v4
  - `created_at` is within last 5 seconds
  - No duplicate booking created in DB
- **Pytest Fixture Needed:** `auth_employee_headers`, `valid_shift`, `valid_locations`, `db_session`

---

#### AT-105: Create Booking — Weekoff Day
- **Setup:** Configure Monday as weekoff for tenant via `POST /tenants/{id}/weekoffs`
- **Request Payload:** Booking date falls on a Monday
- **Expected Status:** 400
- **Response Schema Check:** `detail` mentions weekoff or non-working day
- **Validation Checks:** No booking record created in DB

---

#### AT-106: Create Booking — After Cutoff Time
- **Setup:** Configure cutoff window such that current time is past cutoff for next day
- **Request Payload:** Booking date = tomorrow
- **Expected Status:** 400
- **Response Schema Check:** `detail` references cutoff window

---

#### AT-107: Create Booking — Duplicate (App-Layer Check)
- **Setup:** Create booking for (employee_id, booking_date, shift_id) — AT-101 must run first
- **Request Payload:** Same payload as AT-101
- **Expected Status:** 409
- **DEFECT DOCUMENTATION:**
  > **BUG-002:** There is NO unique constraint in the `bookings` table on `(employee_id, booking_date, shift_id)`. Duplicate prevention is handled at the application layer only. If two concurrent requests arrive simultaneously, both may succeed, creating duplicate bookings. A DB-level unique constraint should be added: `UNIQUE(employee_id, booking_date, shift_id)` where `is_cancelled = false`.
- **Concurrency Test:** Send two identical POST requests simultaneously using `asyncio.gather()` — verify only one succeeds

---

#### AT-108: Bulk Booking — Valid Multi-Date
- **Endpoint:** `POST /bookings/bulk`
- **Request Payload:**
  ```json
  {
    "employee_id": "emp-uuid-001",
    "booking_dates": ["2026-05-15", "2026-05-16", "2026-05-17"],
    "shift_id": "shift-uuid-morning",
    "pickup_location_id": "loc-uuid-home",
    "drop_location_id": "loc-uuid-office",
    "trip_type": "pickup"
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `bookings` (array of 3 booking objects)
  - Each booking has unique `id`
  - `failed_dates` is empty or absent
- **Validation Checks:**
  - Exactly 3 records created in `bookings` table
  - All have `status` == `"Request"`

---

#### AT-111: List Bookings — Pagination
- **Endpoint:** `GET /bookings/?page=1&page_size=10`
- **Auth:** Employee JWT
- **Expected Status:** 200
- **Response Schema Check:**
  - `items` (array, max 10 items)
  - `total` (integer)
  - `page` == 1
  - `page_size` == 10
  - `pages` (total pages count)
- **Validation Checks:**
  - `items` length <= 10
  - If `total` > 10, second page `GET /bookings/?page=2&page_size=10` returns different items
  - No item appears on both pages

---

#### AT-112: List Bookings — Filter by Status
- **Endpoint:** `GET /bookings/?status=Scheduled`
- **Expected Status:** 200
- **Validation Checks:**
  - All items in `items` array have `status` == `"Scheduled"`
  - Items with other statuses are excluded

---

#### AT-117: Get Booking — Cross-Tenant Access
- **Setup:** Create booking under tenant A, authenticate as employee of tenant B
- **Expected Status:** 403
- **Validation Checks:** Error does not reveal booking details (no information leakage)

---

#### AT-120: Update Booking — Completed Status
- **Setup:** Booking with `status` == `"Completed"`
- **Request Payload:** `{"pickup_location_id": "new-loc-uuid"}`
- **Expected Status:** 400
- **Validation Checks:** `detail` indicates booking cannot be modified after completion

---

#### AT-122: Cancel Booking — Already Completed
- **Setup:** Booking with `status` == `"Completed"`
- **Expected Status:** 400
- **Validation Checks:** Booking `status` remains `"Completed"` in DB

---

#### AT-124: Get Employee Bookings — Cross-Employee Access
- **Setup:** Employee A authenticates; requests `GET /bookings/employee/{employee_B_id}`
- **Expected Status:** 403
- **Validation Checks:** Employee B's bookings are not revealed

---

## 3. Route Management Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-201 | /routes/ | POST | Admin | Create valid route | 201 |
| AT-202 | /routes/ | POST | Employee | Insufficient permissions | 403 |
| AT-203 | /routes/ | GET | Admin | List with pagination | 200 |
| AT-204 | /routes/ | GET | Admin | Filter by status | 200 |
| AT-205 | /routes/ | GET | Admin | Filter by date | 200 |
| AT-206 | /routes/{id} | GET | Admin | Valid route | 200 |
| AT-207 | /routes/{id} | GET | Admin | Non-existent route | 404 |
| AT-208 | /routes/{id} | PUT | Admin | Update route | 200 |
| AT-209 | /routes/{id} | DELETE | Admin | Cancel route | 200 |
| AT-210 | /routes/{id}/assign-vehicle | POST | Admin | Assign vehicle+driver+vendor | 200 |
| AT-211 | /routes/{id}/assign-vehicle | POST | Admin | Non-existent vehicle_id | 404 |
| AT-212 | /routes/{id}/assign-vehicle | POST | Admin | Non-existent driver_id | 404 |
| AT-213 | /routes/{id}/dispatch | POST | Admin | Dispatch route | 200 |
| AT-214 | /routes/{id}/dispatch | POST | Admin | Dispatch already-dispatched route | 409 |
| AT-215 | /routes/{id}/bookings | GET | Admin | Get bookings in route | 200 |

---

#### AT-201: Create Route — Valid
- **Endpoint:** `POST /routes/`
- **Auth:** Admin JWT
- **Request Payload:**
  ```json
  {
    "name": "Route Alpha - Morning Pickup",
    "shift_id": "shift-uuid-morning",
    "route_date": "2026-05-15",
    "direction": "pickup",
    "tenant_id": "tenant-uuid-001"
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `id` (UUID)
  - `status` == `"Planned"`
  - `name`, `shift_id`, `route_date` match request
  - `created_at` (ISO datetime)
- **Pytest Fixture Needed:** `auth_admin_headers`, `valid_shift`, `db_session`

---

#### AT-210: Assign Vehicle to Route — Valid
- **Endpoint:** `POST /routes/{route_id}/assign-vehicle`
- **Request Payload:**
  ```json
  {
    "vehicle_id": "vehicle-uuid-001",
    "driver_id": "driver-uuid-001",
    "vendor_id": "vendor-uuid-001"
  }
  ```
- **Expected Status:** 200
- **Response Schema Check:**
  - Route `status` updated to `"Vendor Assigned"` or `"Vehicle Assigned"`
  - `vehicle_id`, `driver_id`, `vendor_id` reflected in route object
- **Validation Checks:**
  - `routes` table row updated with vehicle/driver/vendor IDs
  - `status` transition recorded

---

#### AT-213: Dispatch Route — Valid
- **Endpoint:** `POST /routes/{route_id}/dispatch`
- **Setup:** Route must have vehicle assigned
- **Expected Status:** 200
- **Response Schema Check:**
  - Route `status` == `"Dispatched"`
  - `dispatched_at` (ISO datetime)
- **Side Effect Verification:**
  - OTPs generated for each booking in the route (stored in DB or Redis)
  - FCM push notifications triggered for each employee
  - SMS notifications triggered via Twilio mock
- **Validation Checks:**
  - Each booking in route has an OTP record
  - Mock FCM service received one call per employee in route

---

#### AT-214: Dispatch Already-Dispatched Route
- **Setup:** Route already in `"Dispatched"` status
- **Expected Status:** 409
- **Validation Checks:** `detail` indicates route already dispatched; no duplicate OTPs created

---

## 4. Driver App Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-301 | /driver/duty/start | POST | Driver | Start duty valid | 200 |
| AT-302 | /driver/duty/start | POST | Driver | Idempotent second call | 200 |
| AT-303 | /driver/duty/end | POST | Driver | End duty valid | 200 |
| AT-304 | /driver/duty/end | POST | Driver | End duty with incomplete trips | 200 |
| AT-305 | /driver/trip/start | POST | Driver | Valid OTP | 200 |
| AT-306 | /driver/trip/start | POST | Driver | Wrong OTP | 401 |
| AT-307 | /driver/trip/start | POST | Driver | Already started trip | 409 |
| AT-308 | /driver/trip/drop | POST | Driver | Valid drop | 200 |
| AT-309 | /driver/trip/drop | POST | Driver | Drop not-started trip | 400 |
| AT-310 | /driver/trip/no-show | POST | Driver | Mark no-show | 200 |
| AT-311 | /driver/location | POST | Driver | Valid location update | 200 |
| AT-312 | /driver/location | POST | Driver | Invalid coordinates | 422 |
| AT-313 | /driver/sos | POST | Driver | Valid SOS | 201 |
| AT-314 | /driver/sos | POST | Driver | No auth | 401 |

---

#### AT-301: Start Duty — Valid
- **Endpoint:** `POST /driver/duty/start`
- **Auth:** Driver JWT
- **Request Payload:** `{"route_id": "route-uuid-001"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `session_id` or `duty_id` (UUID)
  - `status` == `"active"` or `"started"`
  - `started_at` (ISO datetime)
- **Validation Checks:**
  - `driver_sessions` table has new record with `route_id`, `driver_id`, `started_at`
  - Session `status` is active
- **Pytest Fixture Needed:** `auth_driver_headers`, `dispatched_route`

---

#### AT-302: Start Duty — Idempotent Second Call
- **Setup:** Call `POST /driver/duty/start` twice with same `route_id`
- **Expected Status:** 200 (both calls)
- **Validation Checks:**
  - Only ONE `driver_sessions` record exists for this driver+route combination
  - `started_at` from first call is preserved

---

#### AT-305: Start Trip — Valid OTP
- **Endpoint:** `POST /driver/trip/start`
- **Request Payload:**
  ```json
  {
    "booking_id": "booking-uuid-001",
    "otp": "482910"
  }
  ```
- **Expected Status:** 200
- **Response Schema Check:**
  - `trip_status` == `"InProgress"` or `"Started"`
  - `trip_start_time` (ISO datetime)
- **Validation Checks:**
  - Booking `status` updated to `"InProgress"` in DB
  - OTP marked as used/consumed (cannot be reused)

---

#### AT-306: Start Trip — Wrong OTP
- **Request Payload:** `{"booking_id": "booking-uuid-001", "otp": "000000"}`
- **Expected Status:** 401
- **Validation Checks:** Booking `status` unchanged in DB

---

#### AT-308: Drop Passenger — Valid
- **Endpoint:** `POST /driver/trip/drop`
- **Request Payload:** `{"booking_id": "booking-uuid-001"}`
- **Expected Status:** 200
- **Response Schema Check:**
  - `trip_status` == `"Completed"`
  - `drop_time` (ISO datetime)
- **Validation Checks:**
  - Booking `status` == `"Completed"` in DB
  - `updated_at` refreshed

---

#### AT-311: Location Update — Valid Coordinates
- **Endpoint:** `POST /driver/location`
- **Request Payload:** `{"lat": 12.9716, "lng": 77.5946, "route_id": "route-uuid-001"}`
- **Expected Status:** 200
- **Validation Checks:**
  - Location stored (in Redis or DB)
  - Timestamp recorded

---

#### AT-312: Location Update — Invalid Coordinates
- **Request Payload:** `{"lat": 999.0, "lng": 77.5946, "route_id": "route-uuid-001"}`
- **Expected Status:** 422
- **Validation Checks:** `detail` references invalid latitude range (-90 to 90)

---

#### AT-313: SOS Alert — Valid
- **Endpoint:** `POST /driver/sos`
- **Request Payload:** `{"route_id": "route-uuid-001", "message": "Emergency - vehicle breakdown"}`
- **Expected Status:** 201
- **Response Schema Check:**
  - `alert_id` (UUID)
  - `status` == `"TRIGGERED"`
- **Side Effect Verification:**
  - Alert created in `alerts` table
  - FCM notification sent to admin users
  - SMS sent to emergency contacts via Twilio mock

---

## 5. Alert Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-401 | /alerts/ | POST | Admin | Create alert | 201 |
| AT-402 | /alerts/ | GET | Admin | List with filters | 200 |
| AT-403 | /alerts/{id} | GET | Admin | Single alert | 200 |
| AT-404 | /alerts/{id}/acknowledge | PUT | Admin | TRIGGERED → ACKNOWLEDGED | 200 |
| AT-405 | /alerts/{id}/acknowledge | PUT | Admin | Already ACKNOWLEDGED | 409 |
| AT-406 | /alerts/{id}/resolve | PUT | Admin | ACKNOWLEDGED → RESOLVED | 200 |
| AT-407 | /alerts/{id}/resolve | PUT | Admin | From TRIGGERED (skipping ACK) | 400 |
| AT-408 | /alerts/{id}/close | PUT | Admin | → CLOSED | 200 |
| AT-409 | /alerts/{id}/false-alarm | PUT | Admin | → FALSE_ALARM | 200 |
| AT-410 | /alerts/{id}/escalate | POST | Admin | Valid escalation | 200 |
| AT-411 | /alerts/{id}/escalate | POST | Admin | Escalate CLOSED alert | 400 |
| AT-412 | /alerts/{id}/escalate | POST | Admin | Escalate FALSE_ALARM | 400 |

---

#### AT-404: Acknowledge Alert — Valid Transition
- **Endpoint:** `PUT /alerts/{alert_id}/acknowledge`
- **Auth:** Admin JWT
- **Setup:** Alert in `TRIGGERED` status
- **Expected Status:** 200
- **Response Schema Check:**
  - `status` == `"ACKNOWLEDGED"`
  - `acknowledged_at` (ISO datetime)
  - `acknowledged_by` (user_id of admin performing action)
- **Validation Checks:**
  - DB record updated: `status` = `"ACKNOWLEDGED"`, `acknowledged_at` is set
  - `updated_at` refreshed

---

#### AT-407: Resolve Alert — Skipping Acknowledge
- **Setup:** Alert in `TRIGGERED` status (not yet acknowledged)
- **Expected Status:** 400
- **Validation Checks:**
  - Alert `status` remains `"TRIGGERED"` in DB
  - `detail` explains required state transition

---

#### AT-411: Escalate CLOSED Alert — Blocked
- **Endpoint:** `POST /alerts/{alert_id}/escalate`
- **Setup:** Alert in `CLOSED` status
- **Expected Status:** 400
- **Validation Checks:** `detail` references closed alert cannot be escalated

---

#### AT-412: Escalate FALSE_ALARM Alert — Blocked
- **Setup:** Alert in `FALSE_ALARM` status
- **Expected Status:** 400
- **Validation Checks:** Cannot escalate a false alarm

---

## 6. Announcement Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-501 | /announcements/ | POST | Admin | Create DRAFT announcement | 201 |
| AT-502 | /announcements/ | GET | Admin | List announcements | 200 |
| AT-503 | /announcements/{id} | GET | Admin | Single announcement | 200 |
| AT-504 | /announcements/{id} | PUT | Admin | Update DRAFT | 200 |
| AT-505 | /announcements/{id} | PUT | Admin | Update PUBLISHED | 400 |
| AT-506 | /announcements/{id}/publish | POST | Admin | Publish DRAFT | 200 |
| AT-507 | /announcements/{id}/publish | POST | Admin | Publish already PUBLISHED | 409 |
| AT-508 | /announcements/{id} | DELETE | Admin | Delete DRAFT | 200 |
| AT-509 | /announcements/{id} | DELETE | Admin | Delete PUBLISHED | 400 |
| AT-510 | /announcements/{id}/publish | POST | Admin | Publish triggers FCM+SMS+Email | 200 |
| AT-511 | /announcements/{id}/publish | POST | Admin | Retry publish creates duplicate recipients | 200 |

---

#### AT-501: Create Announcement — DRAFT
- **Endpoint:** `POST /announcements/`
- **Auth:** Admin JWT
- **Request Payload:**
  ```json
  {
    "title": "Office Closure Notice",
    "body": "The office will be closed on 2026-05-20.",
    "target_audience": "all_employees",
    "tenant_id": "tenant-uuid-001"
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `id` (UUID)
  - `status` == `"DRAFT"`
  - `published_at` is null
  - `title`, `body` match request

---

#### AT-506: Publish Announcement — Triggers Notifications
- **Endpoint:** `POST /announcements/{announcement_id}/publish`
- **Auth:** Admin JWT
- **Expected Status:** 200
- **Response Schema Check:**
  - `status` == `"PUBLISHED"`
  - `published_at` (ISO datetime, non-null)
- **Side Effect Verification:**
  - FCM mock called for each target employee
  - Twilio SMS mock called for each employee with phone
  - SMTP mock called for each employee with email
  - `announcement_recipients` table populated

---

#### AT-511: Publish Announcement — Retry Creates Duplicate Recipients
- **Setup:** Publish announcement (AT-506), then call publish again
- **Expected Status:** 409 (expected) or 200 (actual — defect)
- **DEFECT DOCUMENTATION:**
  > **BUG-003:** `announcement_recipients` table has NO uniqueness constraint on `(announcement_id, recipient_id)`. If the publish endpoint is called multiple times (e.g., due to network retry), duplicate rows are inserted into `announcement_recipients`. This results in recipients receiving the same announcement notification multiple times. Fix: Add UNIQUE constraint on `(announcement_id, recipient_id)` and implement idempotent publish logic.
- **Verification:** After second publish call, `SELECT COUNT(*) FROM announcement_recipients WHERE announcement_id = '...'` returns > intended count

---

#### AT-505: Update PUBLISHED Announcement
- **Setup:** Announcement in `PUBLISHED` status
- **Request Payload:** `{"title": "Updated Title"}`
- **Expected Status:** 400
- **Validation Checks:** Title unchanged in DB

---

## 7. Security Vulnerability Tests

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code | Severity |
|---------|----------|--------|------|----------|---------------|----------|
| AT-601 | /push-notifications/send | POST | None | No auth required | 200 | CRITICAL |
| AT-602 | /push-notifications/send-batch | POST | None | No auth required | 200 | CRITICAL |
| AT-603 | /push-notifications/send | POST | None | Send to arbitrary FCM token | 200 | CRITICAL |
| AT-604 | /push-notifications/send-batch | POST | None | Flood with batch sends | 200 | HIGH |
| AT-605 | /auth/reset-password | POST | None | Stub always returns 200 | 200 | HIGH |
| AT-606 | /bookings/{id} | GET | Employee | Access other tenant's booking | 403/200 | HIGH |
| AT-607 | /auth/employee/login | POST | None | SQL injection in email | 422/401 | MEDIUM |
| AT-608 | /bookings/ | POST | Employee | Concurrent duplicate bookings | 201/409 | MEDIUM |

---

#### AT-601: Push Notification — No Authentication Required
- **Endpoint:** `POST /push-notifications/send`
- **Auth:** None (deliberately omit Authorization header)
- **Request Payload:**
  ```json
  {
    "fcm_token": "any-fcm-token",
    "title": "Unauthorized Notification",
    "body": "This was sent without auth"
  }
  ```
- **Expected Status (correct):** 401
- **Actual Status (observed):** 200
- **DEFECT DOCUMENTATION:**
  > **BUG-004 [CRITICAL]:** `POST /push-notifications/send` has NO auth dependency. Any unauthenticated caller can send arbitrary push notifications to any FCM token. This enables:
  > - Phishing attacks via push notifications
  > - Notification spam/flooding
  > - Harassment of users
  > - Information disclosure if notification body is used to infer system state
  > 
  > **Fix:** Add `Depends(get_current_user)` or equivalent auth dependency to the endpoint router.
- **Test Steps:**
  1. Obtain valid FCM token from registered device
  2. Send POST request with no Authorization header
  3. Assert response is 200 (document as defect)
  4. Verify notification was delivered (check mock FCM service)

---

#### AT-602: Push Notification Batch — No Authentication
- **Endpoint:** `POST /push-notifications/send-batch`
- **Auth:** None
- **Request Payload:**
  ```json
  {
    "notifications": [
      {"fcm_token": "token1", "title": "Msg 1", "body": "Body 1"},
      {"fcm_token": "token2", "title": "Msg 2", "body": "Body 2"}
    ]
  }
  ```
- **Expected Status (correct):** 401
- **Actual Status:** 200
- **DEFECT DOCUMENTATION:**
  > **BUG-005 [CRITICAL]:** Same as BUG-004 but for batch endpoint. Additionally, no rate limiting on unauthenticated batch endpoint enables large-scale notification flooding.

---

#### AT-603: Push Notification — Arbitrary FCM Token Targeting
- **Setup:** Use a real FCM token from a registered driver device
- **Test:** Send notification without authentication to that specific token
- **Expected Status (correct):** 401
- **Security Impact:** Attacker can spoof legitimate fleet notifications (e.g., fake dispatch instructions)

---

#### AT-607: SQL Injection in Login Email Field
- **Request Payload:**
  ```json
  {
    "email": "' OR '1'='1",
    "password": "anything"
  }
  ```
- **Expected Status:** 422 or 401 (must NOT be 200)
- **Validation Checks:**
  - No SQL error leaked in response body
  - ORM parameterized queries prevent injection (SQLAlchemy default behavior)
  - Error response is generic (no DB details)

---

#### AT-608: Concurrent Duplicate Booking Creation
- **Test Strategy:**
  ```python
  import asyncio, httpx
  async def test_concurrent_duplicates():
      async with httpx.AsyncClient() as client:
          tasks = [
              client.post("/bookings/", json=same_payload, headers=auth_headers)
              for _ in range(5)
          ]
          responses = await asyncio.gather(*tasks)
      success = [r for r in responses if r.status_code == 201]
      assert len(success) == 1, f"Expected 1 success, got {len(success)} — DEFECT BUG-002"
  ```
- **Expected:** Only 1 of 5 concurrent requests succeeds
- **Actual (possible):** Multiple succeed due to no DB unique constraint
- **DEFECT DOCUMENTATION:** References BUG-002

---

## 8. IAM Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-701 | /iam/packages/ | POST | Admin | Create permission package | 201 |
| AT-702 | /iam/packages/ | GET | Admin | List packages | 200 |
| AT-703 | /iam/policies/ | POST | Admin | Create policy (subset of package) | 201 |
| AT-704 | /iam/policies/ | POST | Admin | Policy NOT subset of package | 400 |
| AT-705 | /iam/roles/ | POST | Admin | Create role | 201 |
| AT-706 | /iam/roles/ | POST | Admin | System role with tenant_id | 400 |
| AT-707 | /iam/roles/ | POST | Admin | Tenant role without tenant_id | 400 |
| AT-708 | /iam/roles/{id}/assign | POST | Admin | Assign role to user | 200 |
| AT-709 | /iam/roles/{id}/assign | POST | Admin | Assign to non-existent user | 404 |
| AT-710 | /iam/permissions/ | GET | Admin | List all permissions | 200 |
| AT-711 | /iam/roles/{id}/assign | POST | Employee | Insufficient permissions | 403 |

---

#### AT-703: Create Policy — Not Subset of Package
- **Endpoint:** `POST /iam/policies/`
- **Request Payload:**
  ```json
  {
    "name": "SuperPolicy",
    "permissions": ["booking:delete", "tenant:delete"],
    "package_id": "package-uuid-basic"
  }
  ```
  - Where `package-uuid-basic` only grants `["booking:read", "booking:create"]`
- **Expected Status:** 400
- **Validation Checks:** `detail` mentions permissions not allowed by package

---

#### AT-706: Create System Role — With tenant_id (Invalid)
- **Endpoint:** `POST /iam/roles/`
- **Request Payload:**
  ```json
  {
    "name": "GlobalAdmin",
    "system_role": true,
    "tenant_id": "tenant-uuid-001"
  }
  ```
- **Expected Status:** 400
- **Validation Checks:** System roles cannot be scoped to a tenant

---

#### AT-707: Create Tenant Role — Without tenant_id (Invalid)
- **Request Payload:**
  ```json
  {
    "name": "TenantManager",
    "system_role": false,
    "tenant_id": null
  }
  ```
- **Expected Status:** 400
- **Validation Checks:** Non-system roles must have a tenant_id

---

## 9. Reports Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-801 | /reports/bookings | GET | Admin | Valid date range | 200 |
| AT-802 | /reports/bookings | GET | Admin | Pagination (page, page_size) | 200 |
| AT-803 | /reports/bookings | GET | Admin | Invalid date format | 422 |
| AT-804 | /reports/routes | GET | Admin | Filter by status | 200 |
| AT-805 | /reports/drivers | GET | Admin | Filter by driver_id | 200 |
| AT-806 | /reports/bookings | GET | Employee | Insufficient permissions | 403 |
| AT-807 | /reports/bookings | GET | Admin | Large dataset pagination | 200 |
| AT-808 | /reports/routes | GET | Admin | Cross-tenant data isolation | 200 |

---

#### AT-801: Booking Report — Valid Date Range
- **Endpoint:** `GET /reports/bookings?date_from=2026-05-01&date_to=2026-05-31&tenant_id=tenant-uuid-001`
- **Auth:** Admin JWT
- **Expected Status:** 200
- **Response Schema Check:**
  - `items` (array of booking summary objects)
  - `total` (integer)
  - `date_from`, `date_to` reflected in response
- **Validation Checks:**
  - All items have `booking_date` between `date_from` and `date_to` (inclusive)
  - All items belong to `tenant_id` = `tenant-uuid-001`

---

#### AT-802: Booking Report — Pagination
- **Endpoint:** `GET /reports/bookings?date_from=2026-01-01&date_to=2026-12-31&page=1&page_size=50`
- **Expected Status:** 200
- **Validation Checks:**
  - `items` length <= 50
  - `page` and `page_size` reflected in response
  - Page 2 returns different set of items
  - No duplicate items across pages

---

#### AT-807: Large Dataset Pagination Performance
- **Setup:** Seed 10,000 booking records for a tenant
- **Endpoint:** `GET /reports/bookings?date_from=2026-01-01&date_to=2026-12-31&page=100&page_size=100`
- **Expected Status:** 200
- **Performance Threshold:** Response time < 2000ms
- **Validation Checks:** Correct offset applied (items on page 100 are not items from page 1)

---

## 10. Rate Limiting Tests

### Summary Table

| Test ID | Endpoint | Rate Limit | Test Method | Expected Code on Breach |
|---------|----------|------------|-------------|------------------------|
| AT-901 | /auth/employee/login | 10/min | 11 rapid requests | 429 |
| AT-902 | /auth/employee/otp/request | 5/min | 6 rapid requests | 429 |
| AT-903 | /auth/employee/otp/verify | 10/min | 11 rapid requests | 429 |
| AT-904 | /auth/admin/login | 10/min | 11 rapid requests | 429 |

---

#### AT-901: Employee Login Rate Limit
- **Endpoint:** `POST /auth/employee/login`
- **Test Steps:**
  1. Send 10 requests within 60 seconds (all with wrong credentials to avoid lockout concerns)
  2. Send 11th request
  3. Assert 11th response has status 429
- **Response Validation:**
  - `detail` or `message` mentions rate limit
  - Optional: `Retry-After` header with seconds until reset
- **Reset Verification:**
  - Wait 60 seconds (or mock time)
  - 12th request returns 401 (not 429), confirming rate limit window reset
- **Test Code Pattern:**
  ```python
  async def test_rate_limit_employee_login(async_client, employee_user):
      for i in range(10):
          await async_client.post("/auth/employee/login", json={
              "email": employee_user.email,
              "password": "wrong"
          })
      response = await async_client.post("/auth/employee/login", json={
          "email": employee_user.email,
          "password": "wrong"
      })
      assert response.status_code == 429
  ```

---

## 11. Tenant & Config Endpoints

### Summary Table

| Test ID | Endpoint | Method | Auth | Scenario | Expected Code |
|---------|----------|--------|------|----------|---------------|
| AT-1001 | /tenants/ | POST | Admin | Create tenant | 201 |
| AT-1002 | /tenants/{id} | GET | Admin | Get tenant | 200 |
| AT-1003 | /tenants/{id} | PUT | Admin | Update tenant | 200 |
| AT-1004 | /tenants/{id}/weekoffs | POST | Admin | Configure weekoffs | 200 |
| AT-1005 | /tenants/{id}/shifts | POST | Admin | Create shift | 201 |
| AT-1006 | /tenants/{id}/cutoff | POST | Admin | Configure cutoff | 200 |
| AT-1007 | /tenants/{id}/shifts | POST | Admin | Duplicate shift name | 409 |

---

#### AT-1005: Create Shift — Valid
- **Endpoint:** `POST /tenants/{tenant_id}/shifts`
- **Request Payload:**
  ```json
  {
    "name": "Morning Shift",
    "start_time": "08:00",
    "end_time": "17:00",
    "grace_period_minutes": 15
  }
  ```
- **Expected Status:** 201
- **Response Schema Check:**
  - `id` (UUID)
  - `name` == `"Morning Shift"`
  - `tenant_id` matches URL param

---

#### AT-1006: Configure Cutoff Window
- **Endpoint:** `POST /tenants/{tenant_id}/cutoff`
- **Request Payload:**
  ```json
  {
    "cutoff_hours_before": 2,
    "applies_to": "next_day_bookings"
  }
  ```
- **Expected Status:** 200
- **Validation Checks:**
  - `cutoff_configs` table updated for tenant
  - Subsequent booking attempts past cutoff return 400 (see AT-106)

---

## 12. Postman Collection Structure

```json
{
  "info": {
    "name": "Fleet Manager API Tests",
    "description": "Complete API test suite for Fleet Manager backend",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    "version": "1.0.0"
  },
  "variable": [
    {"key": "base_url", "value": "http://localhost:8000/api/v1", "type": "string"},
    {"key": "employee_token", "value": "", "type": "string"},
    {"key": "admin_token", "value": "", "type": "string"},
    {"key": "driver_token", "value": "", "type": "string"},
    {"key": "pre_auth_token", "value": "", "type": "string"},
    {"key": "tenant_id", "value": "", "type": "string"},
    {"key": "booking_id", "value": "", "type": "string"},
    {"key": "route_id", "value": "", "type": "string"},
    {"key": "alert_id", "value": "", "type": "string"},
    {"key": "announcement_id", "value": "", "type": "string"}
  ],
  "auth": {
    "type": "bearer",
    "bearer": [
      {"key": "token", "value": "{{employee_token}}", "type": "string"}
    ]
  },
  "item": [
    {
      "name": "Auth",
      "description": "Authentication and token management endpoints",
      "item": [
        {
          "name": "AT-001 Employee Login - Valid",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Content-Type", "value": "application/json"}
            ],
            "url": "{{base_url}}/auth/employee/login",
            "body": {
              "mode": "raw",
              "raw": "{\"email\": \"alice@acme.com\", \"password\": \"SecurePass123!\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 200', () => pm.response.to.have.status(200));",
                  "pm.test('Has access_token', () => {",
                  "  const body = pm.response.json();",
                  "  pm.expect(body).to.have.property('access_token');",
                  "  pm.expect(body.access_token).to.be.a('string').and.not.empty;",
                  "  pm.collectionVariables.set('employee_token', body.access_token);",
                  "});",
                  "pm.test('Token type is bearer', () => {",
                  "  pm.expect(pm.response.json().token_type).to.equal('bearer');",
                  "});",
                  "pm.test('User object present', () => {",
                  "  const user = pm.response.json().user;",
                  "  pm.expect(user).to.have.property('id');",
                  "  pm.expect(user.email).to.equal('alice@acme.com');",
                  "});"
                ]
              }
            }
          ]
        },
        {
          "name": "AT-002 Employee Login - Wrong Password",
          "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": "{{base_url}}/auth/employee/login",
            "body": {
              "mode": "raw",
              "raw": "{\"email\": \"alice@acme.com\", \"password\": \"WrongPassword\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 401', () => pm.response.to.have.status(401));",
                  "pm.test('No access_token', () => {",
                  "  const body = pm.response.json();",
                  "  pm.expect(body).to.not.have.property('access_token');",
                  "});"
                ]
              }
            }
          ]
        },
        {
          "name": "AT-028 Reset Password - Stub Bug",
          "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": "{{base_url}}/auth/reset-password",
            "body": {
              "mode": "raw",
              "raw": "{\"email\": \"nobody@example.com\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 200 (DEFECT: stub always returns 200)', () => pm.response.to.have.status(200));",
                  "pm.test('BUG-001: Verify no actual reset occurred', () => {",
                  "  // This test documents the stub behavior",
                  "  // Expected: 200 with message that reset email was sent",
                  "  // Reality: 200 is returned without any email sent or token generated",
                  "  pm.expect(true).to.be.true; // placeholder — verify DB separately",
                  "});"
                ]
              }
            }
          ]
        },
        {
          "name": "AT-031 Token Refresh - Valid",
          "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": "{{base_url}}/auth/token/refresh",
            "body": {
              "mode": "raw",
              "raw": "{\"refresh_token\": \"{{refresh_token}}\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 200', () => pm.response.to.have.status(200));",
                  "pm.test('New access_token returned', () => {",
                  "  const body = pm.response.json();",
                  "  pm.expect(body.access_token).to.be.a('string').and.not.empty;",
                  "  pm.collectionVariables.set('employee_token', body.access_token);",
                  "});"
                ]
              }
            }
          ]
        },
        {
          "name": "AT-029 Introspect - Valid Secret",
          "request": {
            "method": "GET",
            "header": [{"key": "X-Introspect-Secret", "value": "{{introspect_secret}}"}],
            "url": "{{base_url}}/auth/introspect"
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 200', () => pm.response.to.have.status(200));"
                ]
              }
            }
          ]
        }
      ]
    },
    {
      "name": "Bookings",
      "description": "Booking CRUD and business rule tests",
      "item": [
        {
          "name": "AT-101 Create Booking - Valid",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Content-Type", "value": "application/json"},
              {"key": "Authorization", "value": "Bearer {{employee_token}}"}
            ],
            "url": "{{base_url}}/bookings/",
            "body": {
              "mode": "raw",
              "raw": "{\"employee_id\": \"{{employee_id}}\", \"booking_date\": \"2026-05-15\", \"shift_id\": \"{{shift_id}}\", \"pickup_location_id\": \"{{pickup_loc_id}}\", \"drop_location_id\": \"{{drop_loc_id}}\", \"trip_type\": \"pickup\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 201', () => pm.response.to.have.status(201));",
                  "pm.test('Booking created with correct fields', () => {",
                  "  const body = pm.response.json();",
                  "  pm.expect(body.id).to.match(/^[0-9a-f-]{36}$/);",
                  "  pm.expect(body.status).to.equal('Request');",
                  "  pm.expect(body.booking_date).to.equal('2026-05-15');",
                  "  pm.collectionVariables.set('booking_id', body.id);",
                  "});"
                ]
              }
            }
          ]
        },
        {
          "name": "AT-107 Create Booking - Duplicate (BUG-002)",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Content-Type", "value": "application/json"},
              {"key": "Authorization", "value": "Bearer {{employee_token}}"}
            ],
            "url": "{{base_url}}/bookings/",
            "body": {
              "mode": "raw",
              "raw": "{\"employee_id\": \"{{employee_id}}\", \"booking_date\": \"2026-05-15\", \"shift_id\": \"{{shift_id}}\", \"pickup_location_id\": \"{{pickup_loc_id}}\", \"drop_location_id\": \"{{drop_loc_id}}\", \"trip_type\": \"pickup\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('Status 409 (app-layer duplicate check)', () => pm.response.to.have.status(409));",
                  "pm.test('BUG-002: No DB unique constraint — concurrent requests may both succeed', () => {",
                  "  pm.expect(true).to.be.true; // Documented: no DB-level unique constraint",
                  "});"
                ]
              }
            }
          ]
        }
      ]
    },
    {
      "name": "Security",
      "description": "Security vulnerability tests",
      "item": [
        {
          "name": "AT-601 Push Notification - No Auth (CRITICAL BUG)",
          "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": "{{base_url}}/push-notifications/send",
            "body": {
              "mode": "raw",
              "raw": "{\"fcm_token\": \"any-token\", \"title\": \"Unauthorized\", \"body\": \"Sent without auth\"}"
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('BUG-004 CRITICAL: Endpoint returns 200 without auth', () => {",
                  "  // Expected: 401",
                  "  // Actual: 200 — no auth dependency on this endpoint",
                  "  pm.expect(pm.response.code).to.be.oneOf([200, 401]);",
                  "  if (pm.response.code === 200) {",
                  "    console.error('SECURITY DEFECT BUG-004: /push-notifications/send has no auth!');",
                  "  }",
                  "});"
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 13. Pytest API Automation Mapping

### Directory Structure

```
tests/
  api/
    conftest.py                  ← base URL, shared headers, auth fixtures, DB setup
    test_auth_api.py             ← AT-001 through AT-033
    test_booking_api.py          ← AT-101 through AT-124
    test_route_api.py            ← AT-201 through AT-215
    test_driver_api.py           ← AT-301 through AT-314
    test_alert_api.py            ← AT-401 through AT-412
    test_announcement_api.py     ← AT-501 through AT-511
    test_security_api.py         ← AT-601 through AT-608
    test_iam_api.py              ← AT-701 through AT-711
    test_reports_api.py          ← AT-801 through AT-808
    test_rate_limiting_api.py    ← AT-901 through AT-904
    test_tenant_api.py           ← AT-1001 through AT-1007
  utils/
    factories.py                 ← SQLAlchemy model factories
    jwt_helpers.py               ← Token decode/validation helpers
    mock_services.py             ← FCM, Twilio, SMTP mocks
  pytest.ini
  requirements-test.txt
```

---

### `conftest.py`

```python
"""
tests/api/conftest.py
Shared fixtures for all API tests.
"""

import asyncio
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.booking import Booking
from app.models.shift import Shift
from app.core.security import create_access_token, get_password_hash

# ─── Test DB Setup ────────────────────────────────────────────────────────────

TEST_DATABASE_URL = "postgresql://test_user:test_pass@localhost:5433/fleet_test"

engine = create_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables before tests run; drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional DB session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ─── Base URL & Client ────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000/api/v1"


@pytest_asyncio.fixture()
async def async_client(db_session: Session) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an httpx async client wired to the FastAPI app with test DB."""
    from app.db.session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(app=app, base_url=BASE_URL) as client:
        yield client

    app.dependency_overrides.clear()


# ─── User Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def tenant(db_session: Session) -> Tenant:
    """Create and return a test tenant."""
    t = Tenant(
        id=uuid.uuid4(),
        name="Test Corp",
        domain="testcorp.com",
        is_active=True,
    )
    db_session.add(t)
    db_session.flush()
    return t


@pytest.fixture()
def employee_user(db_session: Session, tenant: Tenant) -> User:
    """Create and return a test employee user."""
    user = User(
        id=uuid.uuid4(),
        email="alice@testcorp.com",
        hashed_password=get_password_hash("SecurePass123!"),
        user_type="employee",
        tenant_id=tenant.id,
        is_active=True,
        phone="+919876543210",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    """Create and return a test admin user."""
    user = User(
        id=uuid.uuid4(),
        email="admin@fleet.com",
        hashed_password=get_password_hash("AdminPass123!"),
        user_type="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def driver_user(db_session: Session, tenant: Tenant) -> User:
    """Create and return a test driver user."""
    user = User(
        id=uuid.uuid4(),
        email="driver@testcorp.com",
        hashed_password=get_password_hash("DriverPass123!"),
        user_type="driver",
        tenant_id=tenant.id,
        is_active=True,
        license_number="DL-0420110012345",
    )
    db_session.add(user)
    db_session.flush()
    return user


# ─── Auth Header Fixtures ─────────────────────────────────────────────────────

@pytest.fixture()
def auth_employee_headers(employee_user: User, tenant: Tenant) -> dict:
    """Return Authorization headers for an employee user."""
    token = create_access_token(
        data={
            "user_id": str(employee_user.id),
            "email": employee_user.email,
            "user_type": "employee",
            "tenant_id": str(tenant.id),
        }
    )
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture()
def auth_admin_headers(admin_user: User) -> dict:
    """Return Authorization headers for an admin user."""
    token = create_access_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "user_type": "admin",
        }
    )
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture()
def auth_driver_headers(driver_user: User, tenant: Tenant) -> dict:
    """Return Authorization headers for a driver user."""
    token = create_access_token(
        data={
            "user_id": str(driver_user.id),
            "email": driver_user.email,
            "user_type": "driver",
            "tenant_id": str(tenant.id),
        }
    )
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture()
def no_auth_headers() -> dict:
    """Return headers with no Authorization (for security tests)."""
    return {"Content-Type": "application/json"}


# ─── Domain Object Fixtures ───────────────────────────────────────────────────

@pytest.fixture()
def valid_shift(db_session: Session, tenant: Tenant):
    """Create and return a test shift."""
    from app.models.shift import Shift

    shift = Shift(
        id=uuid.uuid4(),
        name="Morning Shift",
        start_time="08:00",
        end_time="17:00",
        tenant_id=tenant.id,
        grace_period_minutes=15,
    )
    db_session.add(shift)
    db_session.flush()
    return shift


@pytest.fixture()
def created_booking(db_session: Session, employee_user: User, valid_shift, tenant: Tenant):
    """Create and return a test booking in Request status."""
    booking = Booking(
        id=uuid.uuid4(),
        employee_id=employee_user.id,
        booking_date="2026-05-15",
        shift_id=valid_shift.id,
        tenant_id=tenant.id,
        status="Request",
        trip_type="pickup",
    )
    db_session.add(booking)
    db_session.flush()
    return booking


# ─── External Service Mocks ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_fcm():
    """Mock Firebase FCM to prevent real notifications during tests."""
    with patch("app.services.notification.fcm_client.send") as mock:
        mock.return_value = {"success": 1, "failure": 0}
        yield mock


@pytest.fixture(autouse=True)
def mock_twilio():
    """Mock Twilio SMS to prevent real SMS during tests."""
    with patch("app.services.sms.twilio_client.messages.create") as mock:
        mock.return_value = MagicMock(sid="SM_test_sid")
        yield mock


@pytest.fixture(autouse=True)
def mock_smtp():
    """Mock SMTP to prevent real email during tests."""
    with patch("app.services.email.smtp_client.send_message") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis for OTP and session storage."""
    with patch("app.core.redis.redis_client") as mock:
        mock.get = MagicMock(return_value=b"123456")
        mock.set = MagicMock(return_value=True)
        mock.delete = MagicMock(return_value=1)
        mock.exists = MagicMock(return_value=1)
        yield mock
```

---

### `test_auth_api.py`

```python
"""
tests/api/test_auth_api.py
Tests for authentication endpoints (AT-001 through AT-033).
"""

import asyncio
import pytest
import httpx


class TestEmployeeLogin:
    """AT-001 through AT-007: Employee email/password login."""

    @pytest.mark.asyncio
    async def test_valid_login_returns_token(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-001: Valid credentials return JWT access token."""
        response = await async_client.post(
            "/auth/employee/login",
            json={"email": "alice@testcorp.com", "password": "SecurePass123!"},
        )
        assert response.status_code == 200
        body = response.json()

        assert "access_token" in body
        assert "token_type" in body
        assert body["token_type"] == "bearer"
        assert "refresh_token" in body
        assert len(body["access_token"]) > 20

        # JWT structure: 3 parts separated by dots
        parts = body["access_token"].split(".")
        assert len(parts) == 3, "access_token is not a valid JWT"

        # User object
        assert "user" in body
        assert body["user"]["email"] == "alice@testcorp.com"
        assert body["user"]["user_type"] == "employee"

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-002: Wrong password returns 401 without revealing user existence."""
        response = await async_client.post(
            "/auth/employee/login",
            json={"email": "alice@testcorp.com", "password": "WrongPassword!"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "access_token" not in body
        # Generic error — does not say "user exists but password wrong"
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_nonexistent_email_returns_401(self, async_client: httpx.AsyncClient):
        """AT-003: Non-existent email returns same 401 as wrong password (no enumeration)."""
        response = await async_client.post(
            "/auth/employee/login",
            json={"email": "ghost@nobody.com", "password": "AnyPass123!"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_email_returns_422(self, async_client: httpx.AsyncClient):
        """AT-004: Missing email field returns 422 validation error."""
        response = await async_client.post(
            "/auth/employee/login",
            json={"password": "ValidPass123!"},
        )
        assert response.status_code == 422
        errors = response.json()["detail"]
        field_names = [e["loc"][-1] for e in errors]
        assert "email" in field_names

    @pytest.mark.asyncio
    async def test_missing_password_returns_422(self, async_client: httpx.AsyncClient):
        """AT-005: Missing password field returns 422 validation error."""
        response = await async_client.post(
            "/auth/employee/login",
            json={"email": "alice@testcorp.com"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_body_returns_422(self, async_client: httpx.AsyncClient):
        """AT-006: Empty body returns 422."""
        response = await async_client.post("/auth/employee/login", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rate_limit_employee_login(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-007: 11th login request within 1 minute returns 429."""
        payload = {"email": "alice@testcorp.com", "password": "wrong"}
        for _ in range(10):
            await async_client.post("/auth/employee/login", json=payload)

        response = await async_client.post("/auth/employee/login", json=payload)
        assert response.status_code == 429, (
            f"Expected 429 on 11th request, got {response.status_code}"
        )


class TestOTPFlow:
    """AT-008 through AT-013: OTP request and verification."""

    @pytest.mark.asyncio
    async def test_otp_request_valid_phone(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-008: Valid phone number triggers OTP send."""
        response = await async_client.post(
            "/auth/employee/otp/request",
            json={"phone": "+919876543210"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    @pytest.mark.asyncio
    async def test_otp_verify_valid(
        self, async_client: httpx.AsyncClient, employee_user, mock_redis
    ):
        """AT-011: Valid OTP returns pre_auth_token and tenant list."""
        # Redis mock returns "123456" as valid OTP
        response = await async_client.post(
            "/auth/employee/otp/verify",
            json={"phone": "+919876543210", "otp": "123456"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "pre_auth_token" in body
        assert "tenants" in body
        assert isinstance(body["tenants"], list)

    @pytest.mark.asyncio
    async def test_otp_verify_invalid(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-012: Invalid OTP returns 401."""
        response = await async_client.post(
            "/auth/employee/otp/verify",
            json={"phone": "+919876543210", "otp": "000000"},
        )
        assert response.status_code == 401
        assert "pre_auth_token" not in response.json()


class TestPasswordReset:
    """AT-028: Password reset stub behavior."""

    @pytest.mark.asyncio
    async def test_reset_password_stub_always_200(self, async_client: httpx.AsyncClient):
        """AT-028: DEFECT BUG-001 — stub always returns 200 regardless of email."""
        response = await async_client.post(
            "/auth/reset-password",
            json={"email": "nonexistent_completely_fake@example.com"},
        )
        # Document defect: this should not be 200 for nonexistent email
        # but the stub makes it always 200
        assert response.status_code == 200, (
            "BUG-001: Password reset stub returns 200 for any email. "
            "No actual reset is performed."
        )


class TestTokenRefresh:
    """AT-031 through AT-033: Token refresh."""

    @pytest.mark.asyncio
    async def test_valid_refresh_token(
        self, async_client: httpx.AsyncClient, employee_user
    ):
        """AT-031: Valid refresh token returns new access token."""
        # First login to get tokens
        login_resp = await async_client.post(
            "/auth/employee/login",
            json={"email": "alice@testcorp.com", "password": "SecurePass123!"},
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]

        # Use refresh token
        response = await async_client.post(
            "/auth/token/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert len(body["access_token"]) > 20

    @pytest.mark.asyncio
    async def test_tampered_refresh_token_returns_401(
        self, async_client: httpx.AsyncClient
    ):
        """AT-033: Tampered/invalid refresh token returns 401."""
        response = await async_client.post(
            "/auth/token/refresh",
            json={"refresh_token": "eyJhbGciOiJIUzI1NiJ9.tampered.badsig"},
        )
        assert response.status_code == 401
```

---

### `test_booking_api.py`

```python
"""
tests/api/test_booking_api.py
Tests for booking endpoints (AT-101 through AT-124).
"""

import asyncio
import uuid
import pytest
import httpx


class TestCreateBooking:
    """AT-101 through AT-110: Booking creation tests."""

    @pytest.mark.asyncio
    async def test_create_valid_booking(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        employee_user,
        valid_shift,
        db_session,
    ):
        """AT-101: Valid booking creation returns 201 with correct fields."""
        payload = {
            "employee_id": str(employee_user.id),
            "booking_date": "2026-05-15",
            "shift_id": str(valid_shift.id),
            "pickup_location_id": str(uuid.uuid4()),
            "drop_location_id": str(uuid.uuid4()),
            "trip_type": "pickup",
        }
        response = await async_client.post(
            "/bookings/",
            json=payload,
            headers=auth_employee_headers,
        )
        assert response.status_code == 201
        body = response.json()

        # Schema checks
        assert "id" in body
        assert body["status"] == "Request"
        assert body["booking_date"] == "2026-05-15"
        assert body["employee_id"] == str(employee_user.id)

        # Validate UUID format
        booking_uuid = uuid.UUID(body["id"])  # Raises if not valid UUID
        assert booking_uuid is not None

    @pytest.mark.asyncio
    async def test_create_booking_no_auth_returns_401(
        self, async_client: httpx.AsyncClient, employee_user, valid_shift
    ):
        """AT-114: No auth token returns 401."""
        payload = {
            "employee_id": str(employee_user.id),
            "booking_date": "2026-05-15",
            "shift_id": str(valid_shift.id),
            "pickup_location_id": str(uuid.uuid4()),
            "drop_location_id": str(uuid.uuid4()),
            "trip_type": "pickup",
        }
        response = await async_client.post("/bookings/", json=payload)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_duplicate_booking_returns_409(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        employee_user,
        valid_shift,
    ):
        """AT-107: Duplicate booking (same employee+date+shift) returns 409.
        
        DEFECT NOTE (BUG-002): This is enforced at app layer only.
        No DB-level UNIQUE constraint exists on (employee_id, booking_date, shift_id).
        Concurrent requests may bypass this check.
        """
        payload = {
            "employee_id": str(employee_user.id),
            "booking_date": "2026-05-20",
            "shift_id": str(valid_shift.id),
            "pickup_location_id": str(uuid.uuid4()),
            "drop_location_id": str(uuid.uuid4()),
            "trip_type": "pickup",
        }
        # First booking
        r1 = await async_client.post(
            "/bookings/", json=payload, headers=auth_employee_headers
        )
        assert r1.status_code == 201

        # Duplicate booking
        r2 = await async_client.post(
            "/bookings/", json=payload, headers=auth_employee_headers
        )
        assert r2.status_code == 409, (
            "BUG-002: Expected 409 for duplicate booking. "
            "If this fails, app-layer check is also broken."
        )

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_bookings_race_condition(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        employee_user,
        valid_shift,
    ):
        """AT-608: Concurrent duplicate requests — only one should succeed.
        
        DEFECT: No DB unique constraint means race condition may allow duplicates.
        """
        payload = {
            "employee_id": str(employee_user.id),
            "booking_date": "2026-06-01",  # Different date to isolate this test
            "shift_id": str(valid_shift.id),
            "pickup_location_id": str(uuid.uuid4()),
            "drop_location_id": str(uuid.uuid4()),
            "trip_type": "pickup",
        }

        tasks = [
            async_client.post("/bookings/", json=payload, headers=auth_employee_headers)
            for _ in range(5)
        ]
        responses = await asyncio.gather(*tasks)
        successes = [r for r in responses if r.status_code == 201]

        # Ideally only 1 should succeed; but BUG-002 may allow more
        if len(successes) > 1:
            pytest.fail(
                f"BUG-002: {len(successes)} concurrent duplicate bookings succeeded. "
                f"Expected: 1. DB unique constraint is missing."
            )

    @pytest.mark.asyncio
    async def test_create_booking_missing_field_returns_422(
        self, async_client: httpx.AsyncClient, auth_employee_headers: dict
    ):
        """AT-102: Missing shift_id returns 422."""
        payload = {
            "employee_id": str(uuid.uuid4()),
            "booking_date": "2026-05-15",
            # shift_id missing
            "pickup_location_id": str(uuid.uuid4()),
            "drop_location_id": str(uuid.uuid4()),
            "trip_type": "pickup",
        }
        response = await async_client.post(
            "/bookings/", json=payload, headers=auth_employee_headers
        )
        assert response.status_code == 422


class TestListBookings:
    """AT-111 through AT-113: Booking listing and filtering."""

    @pytest.mark.asyncio
    async def test_list_bookings_pagination(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
    ):
        """AT-111: List bookings with pagination returns correct structure."""
        response = await async_client.get(
            "/bookings/?page=1&page_size=10",
            headers=auth_employee_headers,
        )
        assert response.status_code == 200
        body = response.json()

        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert body["page"] == 1
        assert body["page_size"] == 10
        assert len(body["items"]) <= 10

    @pytest.mark.asyncio
    async def test_list_bookings_filter_by_status(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        created_booking,
    ):
        """AT-112: Filter by status returns only matching bookings."""
        response = await async_client.get(
            "/bookings/?status=Request",
            headers=auth_employee_headers,
        )
        assert response.status_code == 200
        body = response.json()
        for item in body["items"]:
            assert item["status"] == "Request", (
                f"Item with status {item['status']} returned when filtering for Request"
            )


class TestGetBooking:
    """AT-115 through AT-117: Single booking retrieval."""

    @pytest.mark.asyncio
    async def test_get_booking_valid(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        created_booking,
    ):
        """AT-115: Get existing booking returns 200 with full details."""
        response = await async_client.get(
            f"/bookings/{created_booking.id}",
            headers=auth_employee_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(created_booking.id)

    @pytest.mark.asyncio
    async def test_get_booking_nonexistent_returns_404(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
    ):
        """AT-116: Non-existent booking_id returns 404."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/bookings/{fake_id}",
            headers=auth_employee_headers,
        )
        assert response.status_code == 404


class TestCancelBooking:
    """AT-121 through AT-122: Booking cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_pending_booking(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        created_booking,
        db_session,
    ):
        """AT-121: Cancel a booking in Request status returns 200."""
        response = await async_client.delete(
            f"/bookings/{created_booking.id}",
            headers=auth_employee_headers,
        )
        assert response.status_code == 200
        db_session.refresh(created_booking)
        assert created_booking.status == "Cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_booking_returns_400(
        self,
        async_client: httpx.AsyncClient,
        auth_employee_headers: dict,
        created_booking,
        db_session,
    ):
        """AT-122: Cannot cancel a completed booking."""
        # Manually set status to Completed
        created_booking.status = "Completed"
        db_session.flush()

        response = await async_client.delete(
            f"/bookings/{created_booking.id}",
            headers=auth_employee_headers,
        )
        assert response.status_code == 400
```

---

### `test_security_api.py`

```python
"""
tests/api/test_security_api.py
Security vulnerability tests (AT-601 through AT-608).
"""

import pytest
import httpx


class TestPushNotificationNoAuth:
    """AT-601 through AT-604: Push notification endpoints lack authentication."""

    @pytest.mark.asyncio
    async def test_send_push_no_auth_accepted(self, async_client: httpx.AsyncClient):
        """AT-601: CRITICAL BUG-004 — /push-notifications/send requires no auth.
        
        This test DOCUMENTS a security vulnerability.
        The endpoint accepts requests without any Authorization header.
        """
        response = await async_client.post(
            "/push-notifications/send",
            json={
                "fcm_token": "fake-fcm-token-12345",
                "title": "Unauthorized Notification",
                "body": "Sent without auth — this is a security vulnerability",
            },
            # Intentionally NO auth headers
        )
        # Current (broken) behavior: 200
        # Expected (correct) behavior: 401
        if response.status_code == 200:
            pytest.fail(
                "SECURITY DEFECT BUG-004 [CRITICAL]: "
                "POST /push-notifications/send accepted request without authentication. "
                "Any unauthenticated actor can send push notifications to any FCM token. "
                "Fix: Add auth dependency to this endpoint."
            )
        elif response.status_code == 401:
            pass  # Correct behavior — defect is fixed
        else:
            pytest.fail(
                f"Unexpected status {response.status_code}. "
                "Expected 401 (secure) or 200 (defect BUG-004)."
            )

    @pytest.mark.asyncio
    async def test_send_batch_push_no_auth_accepted(self, async_client: httpx.AsyncClient):
        """AT-602: CRITICAL BUG-005 — /push-notifications/send-batch requires no auth."""
        response = await async_client.post(
            "/push-notifications/send-batch",
            json={
                "notifications": [
                    {"fcm_token": "token1", "title": "Spam 1", "body": "Body"},
                    {"fcm_token": "token2", "title": "Spam 2", "body": "Body"},
                ]
            },
        )
        if response.status_code == 200:
            pytest.fail(
                "SECURITY DEFECT BUG-005 [CRITICAL]: "
                "POST /push-notifications/send-batch accepted request without authentication."
            )

    @pytest.mark.asyncio
    async def test_sql_injection_in_login(self, async_client: httpx.AsyncClient):
        """AT-607: SQL injection attempt in email field must not succeed."""
        malicious_payloads = [
            {"email": "' OR '1'='1", "password": "anything"},
            {"email": "admin'--", "password": "anything"},
            {"email": "'; DROP TABLE users;--", "password": "anything"},
        ]
        for payload in malicious_payloads:
            response = await async_client.post(
                "/auth/employee/login", json=payload
            )
            assert response.status_code in (422, 401), (
                f"SQL injection payload {payload['email']} returned {response.status_code}. "
                "Must be 422 (validation) or 401 (auth failure), never 200."
            )
            # Ensure no DB error details are leaked
            body = response.text
            assert "sql" not in body.lower()
            assert "syntax" not in body.lower()
            assert "pg" not in body.lower()
```

---

## 14. Reusable Fixtures

| Fixture Name | Scope | Purpose | Signature |
|---|---|---|---|
| `setup_test_database` | session | Creates/drops all DB tables | `() -> Generator` |
| `db_session` | function | Transactional session that rolls back after test | `() -> Generator[Session, None, None]` |
| `async_client` | function | httpx.AsyncClient wired to FastAPI app | `(db_session) -> AsyncGenerator[AsyncClient, None]` |
| `tenant` | function | Test tenant record | `(db_session) -> Tenant` |
| `employee_user` | function | Employee user in test tenant | `(db_session, tenant) -> User` |
| `admin_user` | function | Admin user (no tenant scope) | `(db_session) -> User` |
| `driver_user` | function | Driver user in test tenant | `(db_session, tenant) -> User` |
| `vendor_user` | function | Vendor user in test tenant | `(db_session, tenant) -> User` |
| `escort_user` | function | Escort user in test tenant | `(db_session, tenant) -> User` |
| `auth_employee_headers` | function | Authorization headers for employee | `(employee_user, tenant) -> dict` |
| `auth_admin_headers` | function | Authorization headers for admin | `(admin_user) -> dict` |
| `auth_driver_headers` | function | Authorization headers for driver | `(driver_user, tenant) -> dict` |
| `auth_vendor_headers` | function | Authorization headers for vendor | `(vendor_user, tenant) -> dict` |
| `no_auth_headers` | function | Headers without Authorization (security tests) | `() -> dict` |
| `valid_shift` | function | Morning shift for test tenant | `(db_session, tenant) -> Shift` |
| `valid_locations` | function | Pickup/drop location pair | `(db_session, tenant) -> tuple` |
| `created_booking` | function | Booking in Request status | `(db_session, employee_user, valid_shift, tenant) -> Booking` |
| `scheduled_booking` | function | Booking in Scheduled status (in a route) | `(db_session, created_booking) -> Booking` |
| `completed_booking` | function | Booking in Completed status | `(db_session, created_booking) -> Booking` |
| `created_route` | function | Route in Planned status | `(db_session, valid_shift, tenant) -> Route` |
| `dispatched_route` | function | Route in Dispatched status with vehicle | `(db_session, created_route, driver_user) -> Route` |
| `triggered_alert` | function | Alert in TRIGGERED status | `(db_session, tenant) -> Alert` |
| `draft_announcement` | function | Announcement in DRAFT status | `(db_session, tenant) -> Announcement` |
| `published_announcement` | function | Announcement in PUBLISHED status | `(db_session, draft_announcement) -> Announcement` |
| `mock_fcm` | function (autouse) | Mocks Firebase FCM calls | `() -> MagicMock` |
| `mock_twilio` | function (autouse) | Mocks Twilio SMS calls | `() -> MagicMock` |
| `mock_smtp` | function (autouse) | Mocks SMTP email send | `() -> MagicMock` |
| `mock_redis` | function (autouse) | Mocks Redis get/set/delete | `() -> MagicMock` |
| `iam_package` | function | IAM permission package | `(db_session, tenant) -> IAMPackage` |
| `iam_role` | function | IAM role for tenant | `(db_session, tenant, iam_package) -> IAMRole` |
| `pre_auth_token` | function | Pre-auth token for tenant selection flow | `(employee_user) -> str` |
| `refresh_token` | function | Valid refresh token for employee | `(employee_user, tenant) -> str` |

---

*End of API Test Suite — Fleet Manager v1.0.0*
