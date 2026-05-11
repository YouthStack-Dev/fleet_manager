# Fleet Manager — Regression Test Suite

**Document Version:** 1.0  
**Last Updated:** 2026-04-30  
**Author:** QA Automation Architect  
**Stack:** FastAPI + SQLAlchemy + PostgreSQL + Redis  
**Repository:** fleet_manager  

---

## Purpose

This document defines the complete regression test suite for the Fleet Manager backend API. It is structured into three phases of increasing depth and coverage:

- **Phase A — Smoke Tests:** Fast pass/fail signal. If any smoke test fails, halt all further testing and escalate immediately.
- **Phase B — Critical Business Flow (CBF) Tests:** End-to-end functional flows that represent the core value of the product. Must pass before any production release.
- **Phase C — Full Regression Tests:** Comprehensive module-by-module coverage including edge cases, error paths, security regressions, and documented known defects.

---

## How to Run

### Prerequisites

```bash
# 1. Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt  # pytest, httpx, faker, pytest-asyncio, pytest-xdist

# 2. Environment variables
cp .env.test.example .env.test
# Fill in: DATABASE_URL, REDIS_URL, JWT_SECRET, FCM_MOCK_MODE=true, SMS_MOCK_MODE=true

# 3. Start services
docker-compose -f docker-compose.test.yml up -d  # PostgreSQL + Redis

# 4. Run migrations
alembic upgrade head

# 5. Seed test data
python scripts/seed_test_data.py
```

### Running Each Phase

```bash
# Phase A — Smoke Tests (fast, ~5 min)
pytest tests/smoke/ -v --tb=short -x

# Phase B — Critical Business Flows (~25 min)
pytest tests/cbf/ -v --tb=long

# Phase C — Full Regression (~60 min)
pytest tests/regression/ -v --tb=long --html=reports/regression_report.html

# Run all phases sequentially (CI/CD)
pytest tests/ -v --tb=long -m "smoke or cbf or regression" \
  --html=reports/full_report.html \
  --junitxml=reports/junit.xml

# Parallel execution (Phase C only, split by module)
pytest tests/regression/ -v -n 4 --dist=loadfile
```

### Environment Requirements

| Requirement | Value |
|-------------|-------|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| Redis | 7+ |
| FCM | Mock mode (`FCM_MOCK_MODE=true`) |
| SMS Gateway | Mock mode |
| Email Service | Mock mode |
| External services | All mocked via environment flags |

### Estimated Execution Times

| Phase | Tests | Estimated Time |
|-------|-------|----------------|
| Phase A — Smoke | 17 | ~5 minutes |
| Phase B — CBF | 27 | ~25 minutes |
| Phase C — Full Regression | 55+ | ~60 minutes |
| **Total** | **99+** | **~90 minutes** |

---

## Phase A: Smoke Tests

> These tests must ALL pass before any further testing begins. They verify that the API server, database, and core authentication are operational. If even one fails, halt and escalate.

---

### SMOKE-001: API Server Health Check
- **Priority:** Critical
- **Module:** Infrastructure
- **Endpoint:** GET /health
- **What it verifies:** The API server is running, DB connection is alive, Redis is reachable.
- **Pass Criteria:** HTTP 200; response body contains `{ "status": "healthy", "db": "connected", "redis": "connected" }`
- **Estimated Time:** 5s

---

### SMOKE-002: Employee Login Returns Valid JWT
- **Priority:** Critical
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/otp/send → POST /api/v1/auth/otp/verify → POST /api/v1/auth/select-tenant
- **What it verifies:** Full OTP login flow completes and returns a usable JWT.
- **Pass Criteria:**
  - `/otp/send` returns 200
  - `/otp/verify` returns 200 with `pre_auth_token`
  - `/select-tenant` returns 200 with `access_token` and `refresh_token`
  - JWT is decodable and contains `employee_id`, `tenant_id`, `role=employee`
- **Estimated Time:** 15s

---

### SMOKE-003: Admin Login Returns Valid JWT
- **Priority:** Critical
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/admin/login
- **What it verifies:** Admin login (non-OTP flow) returns valid JWT with admin claims.
- **Pass Criteria:**
  - HTTP 200
  - Response contains `access_token` and `refresh_token`
  - JWT contains `admin_id`, no `tenant_id`, `role=admin`
- **Estimated Time:** 10s

---

### SMOKE-004: Driver Device Registration + Verification
- **Priority:** Critical
- **Module:** Auth / Driver App
- **Endpoint:** POST /api/v1/driver/device/register → POST /api/v1/driver/device/verify
- **What it verifies:** Driver can register a device and complete verification.
- **Pass Criteria:**
  - `/device/register` returns 200 with OTP sent to driver mobile
  - `/device/verify` with correct OTP returns 200 and a Driver JWT
  - JWT contains `driver_id`, `tenant_id`, `role=driver`
- **Estimated Time:** 15s

---

### SMOKE-005: Create a Booking
- **Priority:** Critical
- **Module:** Booking
- **Endpoint:** POST /api/v1/bookings
- **What it verifies:** An authenticated Employee can create a booking.
- **Pass Criteria:**
  - HTTP 201
  - Response contains `id`, `status=Pending`, `employee_id`, `booking_date`
  - Booking persisted in DB (verify via GET)
- **Estimated Time:** 15s

---

### SMOKE-006: List Bookings with Pagination
- **Priority:** Critical
- **Module:** Booking
- **Endpoint:** GET /api/v1/bookings?page=1&page_size=10
- **What it verifies:** Booking list endpoint is functional and returns paginated results.
- **Pass Criteria:**
  - HTTP 200
  - Response contains `items`, `total`, `page`, `page_size`
  - Results scoped to caller's tenant
- **Estimated Time:** 10s

---

### SMOKE-007: Create a Route
- **Priority:** Critical
- **Module:** Route
- **Endpoint:** POST /api/v1/routes
- **What it verifies:** Admin/SubAdmin can create a route.
- **Pass Criteria:**
  - HTTP 201
  - Response contains `id`, `status=Created`, `tenant_id`
- **Estimated Time:** 15s

---

### SMOKE-008: Get Route by ID
- **Priority:** Critical
- **Module:** Route
- **Endpoint:** GET /api/v1/routes/{route_id}
- **What it verifies:** A created route can be retrieved by its ID.
- **Pass Criteria:**
  - HTTP 200
  - Route data matches what was created in SMOKE-007
- **Estimated Time:** 10s

---

### SMOKE-009: Dispatch a Route
- **Priority:** Critical
- **Module:** Route
- **Endpoint:** POST /api/v1/routes/{route_id}/dispatch
- **What it verifies:** A route with assigned driver and vehicle can be dispatched.
- **Pre-conditions:** Route has driver assigned and vehicle assigned (status = DriverAssigned).
- **Pass Criteria:**
  - HTTP 200
  - Route `status = Dispatched`
  - OTPs generated for each booking on route
- **Estimated Time:** 20s

---

### SMOKE-010: Driver Duty Start
- **Priority:** Critical
- **Module:** Driver App
- **Endpoint:** POST /api/v1/driver/duty/start
- **What it verifies:** Driver can start duty for their dispatched route.
- **Pre-conditions:** Route is Dispatched; Driver token available.
- **Pass Criteria:**
  - HTTP 200
  - Duty record created with `status=OnDuty`
- **Estimated Time:** 15s

---

### SMOKE-011: Create an Alert
- **Priority:** Critical
- **Module:** Alert
- **Endpoint:** POST /api/v1/alerts
- **What it verifies:** An alert can be created (e.g., system-generated SOS).
- **Pass Criteria:**
  - HTTP 201
  - Alert has `status=TRIGGERED`
- **Estimated Time:** 10s

---

### SMOKE-012: Create Announcement as DRAFT
- **Priority:** Critical
- **Module:** Announcement
- **Endpoint:** POST /api/v1/announcements
- **What it verifies:** Admin can create a DRAFT announcement.
- **Pass Criteria:**
  - HTTP 201
  - Announcement `status=DRAFT`
  - `id` returned
- **Estimated Time:** 10s

---

### SMOKE-013: Publish Announcement
- **Priority:** Critical
- **Module:** Announcement
- **Endpoint:** POST /api/v1/announcements/{id}/publish
- **What it verifies:** A DRAFT announcement can be published.
- **Pre-conditions:** DRAFT announcement exists (from SMOKE-012).
- **Pass Criteria:**
  - HTTP 200
  - Announcement `status=Published`
  - Notification dispatch triggered (verify in mock logs)
- **Estimated Time:** 15s

---

### SMOKE-014: List IAM Permissions
- **Priority:** Critical
- **Module:** IAM
- **Endpoint:** GET /api/v1/iam/permissions
- **What it verifies:** The system can enumerate available permissions.
- **Pass Criteria:**
  - HTTP 200
  - Response contains all expected permission strings (e.g., `booking.create`, `route.dispatch`, etc.)
- **Estimated Time:** 10s

---

### SMOKE-015: Booking Report Endpoint Returns Data
- **Priority:** Critical
- **Module:** Report
- **Endpoint:** GET /api/v1/reports/bookings?start_date=2026-04-01&end_date=2026-04-30
- **What it verifies:** Reports module is functional; returns booking report data.
- **Pass Criteria:**
  - HTTP 200
  - Response contains `items` array and `total` count
  - Data is scoped to caller's tenant
- **Estimated Time:** 15s

---

### SMOKE-016: Refresh Token Flow
- **Priority:** Critical
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/refresh
- **What it verifies:** Refresh token can be exchanged for a new access token.
- **Pre-conditions:** Valid refresh token available.
- **Pass Criteria:**
  - HTTP 200
  - New `access_token` returned (different from original)
  - New `refresh_token` returned
- **Estimated Time:** 10s

---

### SMOKE-017: Logout Invalidates Session
- **Priority:** Critical
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/logout
- **What it verifies:** Logging out invalidates the session token.
- **Pass Criteria:**
  - HTTP 200
  - Subsequent call to GET /api/v1/bookings with the same token returns 401
- **Estimated Time:** 15s

---

## Phase B: Critical Business Flow Tests

> These end-to-end flows represent the core business logic of the Fleet Manager. Every flow must pass before a production release. Each test is self-contained with full setup and teardown.

---

### CBF-001: Complete Booking Lifecycle — End to End
- **Flow:** Employee books → Admin schedules → Route dispatched → Driver completes → Booking Completed
- **Priority:** Critical
- **Personas Involved:** Employee, Admin, Driver
- **Steps:**
  1. **[Setup]** Create tenant, employee, driver, vehicle, shift, and weekday config.
  2. Authenticate as Employee → create booking for tomorrow's morning shift → verify `status=Pending`.
  3. Authenticate as Admin → create route for that shift date → add the booking to route.
  4. Assign driver and vehicle to route → verify `status=DriverAssigned`.
  5. Dispatch route → verify `status=Dispatched` → verify OTPs generated per booking.
  6. Authenticate as Driver → POST /driver/duty/start for that route → verify `status=OnDuty`.
  7. Driver calls POST /driver/trip/start with valid OTP for first booking → verify trip started.
  8. Driver calls POST /driver/trip/drop for that booking → verify booking `status=Completed`.
  9. Driver calls POST /driver/duty/end → verify all trips finalized.
  10. GET booking by ID → verify final `status=Completed`.
- **Pass Criteria:**
  - All status transitions are correct at each step.
  - No 4xx/5xx errors at any step.
  - Booking final status = `Completed`.
- **Estimated Time:** 3 minutes

---

### CBF-002: OTP Login Flow — Employee Full Authentication
- **Flow:** OTP request → OTP verify → Tenant select → JWT issued → JWT used for API call
- **Priority:** Critical
- **Personas Involved:** Employee
- **Steps:**
  1. POST /api/v1/auth/otp/send with `{ "mobile": "+91-9876543210" }` → verify 200.
  2. Retrieve OTP from mock SMS service.
  3. POST /api/v1/auth/otp/verify with `{ "mobile": "...", "otp": "..." }` → verify pre-auth token returned.
  4. Confirm pre-auth token has `stage=pre_auth` claim.
  5. POST /api/v1/auth/select-tenant with pre-auth token and `{ "tenant_id": "tenant_A" }` → verify full JWT.
  6. Use the full JWT to GET /api/v1/bookings → verify 200.
  7. **Negative:** Attempt to use pre-auth token directly on GET /api/v1/bookings → verify 401/403.
- **Pass Criteria:**
  - Pre-auth token rejected on final API endpoints.
  - Full JWT accepted and functional.
- **Estimated Time:** 1 minute

---

### CBF-003: Driver Device Registration and Trip Completion Flow
- **Flow:** Register device → Verify device → Select tenant → Start duty → Complete trip
- **Priority:** Critical
- **Personas Involved:** Driver, Admin
- **Steps:**
  1. Admin creates a driver record with mobile number.
  2. POST /api/v1/driver/device/register with `{ "mobile": "...", "device_id": "device_xyz" }`.
  3. Retrieve OTP from mock SMS.
  4. POST /api/v1/driver/device/verify with OTP → receive Driver JWT.
  5. POST /api/v1/auth/select-tenant with Driver JWT → receive scoped Driver JWT.
  6. Admin creates and dispatches a route assigned to this driver.
  7. Driver → POST /driver/duty/start → 200.
  8. Driver → POST /driver/trip/start with valid OTP → 200.
  9. Driver → POST /driver/trip/drop → 200.
  10. Driver → POST /driver/duty/end → 200.
- **Pass Criteria:** All steps succeed; booking status = Completed; route status = Completed.
- **Estimated Time:** 3 minutes

---

### CBF-004: Route Complete Lifecycle
- **Flow:** Create → Assign Vehicle → Dispatch → Driver Starts → All Trips Complete → Route Completed
- **Priority:** Critical
- **Personas Involved:** Admin, Driver
- **Steps:**
  1. Admin creates a route with 3 bookings.
  2. Admin assigns a vehicle → route `status=VehicleAssigned`.
  3. Admin assigns a driver → route `status=DriverAssigned`.
  4. Admin dispatches route → `status=Dispatched`, 3 OTPs generated.
  5. Driver starts duty → `status=InProgress`.
  6. Driver completes all 3 trips (trip_start + trip_drop for each).
  7. Driver ends duty.
  8. Verify route `status=Completed`.
  9. **Negative:** Attempt to dispatch again → verify appropriate error (already dispatched).
  10. **Negative:** Attempt to add booking to completed route → verify error.
- **Pass Criteria:** Route lifecycle transitions are valid and irreversible at each stage.
- **Estimated Time:** 4 minutes

---

### CBF-005: Announcement Publish Flow
- **Flow:** Create DRAFT → Update → Publish → Verify Notifications → Attempt Update After Publish
- **Priority:** Critical
- **Personas Involved:** Admin, Employee, Driver
- **Steps:**
  1. Admin → POST /api/v1/announcements with `{ "title": "...", "body": "...", "status": "DRAFT" }` → 201.
  2. Admin → PATCH /api/v1/announcements/{id} to update title → 200.
  3. Admin → POST /api/v1/announcements/{id}/publish → 200.
  4. Verify mock FCM/SMS/email logs show notifications dispatched.
  5. Employee → GET /api/v1/announcements → verify announcement appears with `status=Published`.
  6. **Negative:** Admin → PATCH /api/v1/announcements/{id} to update body after publish → verify error (update blocked).
  7. **Negative:** Admin → DELETE /api/v1/announcements/{id} after publish → verify error (delete blocked).
- **Pass Criteria:** Publish is a one-way transition; post-publish modifications fail.
- **Estimated Time:** 2 minutes

---

### CBF-006: Alert Escalation Lifecycle
- **Flow:** TRIGGERED → ACKNOWLEDGED → IN_PROGRESS → CLOSED (test escalation blocked post-close)
- **Priority:** Critical
- **Personas Involved:** Driver (creates SOS), Admin/SubAdmin (manages alert)
- **Steps:**
  1. Driver → POST /driver/sos → alert `status=TRIGGERED`.
  2. Admin → PATCH /api/v1/alerts/{id}/acknowledge → `status=ACKNOWLEDGED`.
  3. Admin → PATCH /api/v1/alerts/{id}/start → `status=IN_PROGRESS`.
  4. Admin → PATCH /api/v1/alerts/{id}/close → `status=CLOSED`.
  5. **Negative:** Admin → PATCH /api/v1/alerts/{id}/escalate after CLOSED → verify 422 or error (escalation blocked after close).
  6. **Negative:** Repeat test but mark as FALSE_ALARM in step 4 → attempt escalate → verify blocked.
- **Pass Criteria:** All transitions work; escalation after CLOSED/FALSE_ALARM is rejected.
- **Estimated Time:** 2 minutes

---

### CBF-007: Vendor and Vehicle Assignment Flow
- **Flow:** Create Vendor → Create Vendor User → Add Vehicle → Assign Vehicle to Route
- **Priority:** Critical
- **Personas Involved:** Admin, Vendor
- **Steps:**
  1. Admin → POST /api/v1/vendors → create vendor (201).
  2. Admin → POST /api/v1/vendors/{id}/users → create vendor user (201).
  3. Vendor user logs in, obtains Vendor JWT.
  4. Vendor → POST /api/v1/vendors/{id}/vehicles → add vehicle (201).
  5. Admin → POST /api/v1/routes with a new route.
  6. Admin → POST /api/v1/routes/{route_id}/assign-vehicle with new vehicle → 200.
  7. Verify route now shows `vehicle_id` and `vendor_id`.
- **Pass Criteria:** Vehicle-route association is correct; vendor can manage their own vehicles.
- **Estimated Time:** 2 minutes

---

### CBF-008: IAM Policy-to-Permission Inheritance Flow
- **Flow:** Create Package → Create Policy → Create Role → Assign Role → Verify Permissions
- **Priority:** Critical
- **Personas Involved:** Admin, SubAdmin
- **Steps:**
  1. Admin → POST /api/v1/iam/packages with permissions `["booking.read", "booking.create"]` → 201.
  2. Admin → assign this package to tenant_A.
  3. Admin → POST /api/v1/iam/policies under tenant_A with `["booking.read"]` → 201.
  4. Admin → POST /api/v1/iam/roles with this policy → 201.
  5. Admin → POST /api/v1/iam/roles/{id}/assign to SubAdmin user → 200.
  6. SubAdmin authenticates → GET /api/v1/bookings → 200 (booking.read allowed).
  7. SubAdmin → POST /api/v1/bookings → 403 (booking.create not in policy, even though package has it).
  8. **Negative:** Admin attempts to add `route.dispatch` to policy (not in package) → verify rejection.
- **Pass Criteria:** Permission hierarchy enforced: policy cannot exceed package, user gets exactly what the policy allows.
- **Estimated Time:** 3 minutes

---

### CBF-009: Session Invalidation / Single Session Enforcement
- **Flow:** Employee logs in on Device A → logs in on Device B → Device A returns SESSION_EXPIRED
- **Priority:** Critical
- **Personas Involved:** Employee
- **Steps:**
  1. Employee authenticates on Device A → receives `token_A`.
  2. Employee authenticates again on Device B (new OTP flow) → receives `token_B`.
  3. GET /api/v1/bookings with `token_A` → verify 401 with `{ "detail": "SESSION_EXPIRED" }`.
  4. GET /api/v1/bookings with `token_B` → verify 200 (second session is valid).
  5. Logout using `token_B`.
  6. GET /api/v1/bookings with `token_B` → verify 401.
- **Pass Criteria:** Only the latest session is active; prior sessions are invalidated.
- **Estimated Time:** 1.5 minutes

---

### CBF-010: Booking Business Rules Validation
- **Flow:** Attempt various invalid booking scenarios and verify correct rejection
- **Priority:** Critical
- **Personas Involved:** Employee
- **Steps:**
  1. Configure tenant_A: weekoff on Sundays, cutoff at 10pm, shifts at 8am and 5pm.
  2. Authenticate as Employee.
  3. **Weekoff:** Attempt to book on a Sunday → verify 422 with `"error_code": "BOOKING_ON_WEEKOFF"`.
  4. **Cutoff:** Simulate system time after 10pm → attempt to book for tomorrow → verify 422 with `"error_code": "BOOKING_CUTOFF_EXCEEDED"`.
  5. **Past Shift:** Attempt to book for a shift that has already passed today → verify 422 with `"error_code": "SHIFT_ALREADY_PASSED"`.
  6. **Valid:** Book for a future date within cutoff → verify 201.
- **Pass Criteria:** All invalid scenarios fail with correct error codes; valid booking succeeds.
- **Estimated Time:** 2 minutes

---

### CBF-011: Bulk Booking Creation and Partial Cancellation
- **Flow:** Create bookings for 5 dates → cancel 1 → verify atomicity
- **Priority:** Critical
- **Personas Involved:** Employee, Admin
- **Steps:**
  1. Authenticate as Employee.
  2. POST /api/v1/bookings/bulk with 5 different future dates → verify 201 and 5 bookings created.
  3. GET /api/v1/bookings → verify all 5 exist with `status=Pending`.
  4. Cancel booking #3 (PATCH with `status=Cancelled` or DELETE).
  5. GET /api/v1/bookings → verify booking #3 = Cancelled, bookings #1,2,4,5 = Pending.
  6. **Atomicity test:** POST /api/v1/bookings/bulk where one date is a weekoff → verify ALL fail or ALL succeed (atomicity behavior should be documented).
- **Pass Criteria:** Individual cancellation works; atomicity behavior is consistent and documented.
- **Estimated Time:** 2 minutes

---

### CBF-012: Driver No-Show Flow
- **Flow:** Dispatch route → Driver starts → Marks booking as No-Show → Booking status verified
- **Priority:** Critical
- **Personas Involved:** Admin, Driver
- **Steps:**
  1. Admin creates, assigns, and dispatches a route with 2 bookings.
  2. Driver starts duty.
  3. Driver → POST /driver/trip/no-show for booking_1 (employee didn't board) → verify 200.
  4. GET booking_1 → verify `status=NoShow`.
  5. Driver continues → POST /driver/trip/start with valid OTP for booking_2 → verify 200.
  6. Driver → POST /driver/trip/drop for booking_2 → verify `status=Completed`.
  7. Driver ends duty.
- **Pass Criteria:** No-show and completed bookings coexist correctly in a route.
- **Estimated Time:** 2 minutes

---

### CBF-013: SOS Alert Full Flow
- **Flow:** Driver triggers SOS → Alert created → Acknowledged → Resolved
- **Priority:** Critical
- **Personas Involved:** Driver, Admin
- **Steps:**
  1. Admin dispatches a route; Driver starts duty.
  2. Driver → POST /driver/sos with `{ "route_id": "...", "location": { "lat": 12.9, "lng": 77.6 } }` → 201.
  3. Verify alert: `type=SOS`, `status=TRIGGERED`, `driver_id`, `location`.
  4. Admin → PATCH /api/v1/alerts/{id}/acknowledge → `status=ACKNOWLEDGED`.
  5. Admin → PATCH /api/v1/alerts/{id}/resolve → `status=RESOLVED` (or CLOSED).
  6. Verify notification was sent on SOS trigger (check mock FCM log).
- **Pass Criteria:** SOS creates correct alert; lifecycle transitions work; notification dispatched.
- **Estimated Time:** 2 minutes

---

### CBF-014: Cross-Tenant Data Isolation
- **Flow:** Employee from Tenant A attempts to read Tenant B bookings — must be denied
- **Priority:** Critical
- **Personas Involved:** Employee (Tenant A), Admin
- **Steps:**
  1. Admin creates bookings in tenant_B.
  2. Authenticate as Employee in tenant_A.
  3. GET /api/v1/bookings — verify results contain ONLY tenant_A bookings.
  4. GET /api/v1/bookings/{booking_id_from_tenant_B} → verify 403 or 404.
  5. Authenticate as SubAdmin in tenant_A.
  6. GET /api/v1/routes → verify only tenant_A routes returned.
  7. GET /api/v1/routes/{route_id_from_tenant_B} → verify 403 or 404.
- **Pass Criteria:** Zero cross-tenant data leakage; all tenant B resources return 403/404 to Tenant A users.
- **Estimated Time:** 2 minutes

---

### CBF-015: Route Grouping Unauthenticated Access — Known Security Bug Verification
- **Flow:** Document that route grouping endpoints are fully unauthenticated
- **Priority:** Critical (Security Bug Tracking)
- **Personas Involved:** None (no token)
- **Steps:**
  1. POST /api/v1/route-groupings with no Authorization header and valid payload → observe response.
  2. GET /api/v1/route-groupings with no Authorization header → observe response.
  3. PATCH /api/v1/route-groupings/{id} with no Authorization header → observe response.
  4. DELETE /api/v1/route-groupings/{id} with no Authorization header → observe response.
  5. Document observed status codes as **KNOWN FAILURES**.
- **Pass Criteria:** This test is expected to FAIL until BUG-001 is fixed. Mark test with `@pytest.mark.xfail(reason="BUG-001: route_grouping auth bypass")`.
- **Estimated Time:** 1 minute

---

### CBF-016: Push Notification Unauthenticated Access — Known Security Bug Verification
- **Flow:** Document that push notification endpoints are fully unauthenticated
- **Priority:** Critical (Security Bug Tracking)
- **Personas Involved:** None (no token)
- **Steps:**
  1. POST /api/v1/push-notifications/send with no token and `{ "device_token": "test", "title": "T", "body": "B" }` → observe response.
  2. POST /api/v1/push-notifications/send-batch with no token → observe response.
  3. Document as **KNOWN FAILURES**.
- **Pass Criteria:** Expected to FAIL until BUG-002 is fixed. Mark with `@pytest.mark.xfail(reason="BUG-002: push notification auth bypass")`.
- **Estimated Time:** 1 minute

---

### CBF-017: Employee Bulk Import Flow
- **Flow:** Admin bulk imports employees from CSV → verify all created with correct roles
- **Priority:** High
- **Personas Involved:** Admin
- **Steps:**
  1. Authenticate as Admin.
  2. POST /api/v1/employees/bulk-import with CSV payload of 10 employees for tenant_A.
  3. Verify response: `{ "imported": 10, "failed": 0, "errors": [] }`.
  4. GET /api/v1/employees → verify 10 new employees exist in tenant_A.
  5. **Error case:** Include a duplicate mobile number in the CSV → verify `failed` count and `errors` array populated.
- **Pass Criteria:** Bulk import succeeds for valid records; errors reported per invalid record; partial success documented.
- **Estimated Time:** 2 minutes

---

### CBF-018: SubAdmin Manages Bookings Within Their Tenant
- **Flow:** SubAdmin with booking permissions creates, reads, updates bookings in their tenant
- **Priority:** High
- **Personas Involved:** Admin, SubAdmin
- **Steps:**
  1. Admin sets up SubAdmin with IAM policy: `["booking.create", "booking.read", "booking.update"]`.
  2. SubAdmin authenticates.
  3. SubAdmin → POST /api/v1/bookings for an employee in their tenant → 201.
  4. SubAdmin → GET /api/v1/bookings → 200 (returns tenant-scoped bookings).
  5. SubAdmin → PATCH /api/v1/bookings/{id} to update booking → 200.
  6. **Negative:** SubAdmin → DELETE /api/v1/bookings/{id} (no delete permission) → 403.
  7. **Negative:** SubAdmin → GET /api/v1/bookings/{booking_id_from_tenant_B} → 403.
- **Pass Criteria:** SubAdmin can do exactly what their policy allows; no more, no less.
- **Estimated Time:** 2 minutes

---

### CBF-019: Driver Location Tracking
- **Flow:** Driver starts duty → sends periodic location updates → location visible in tracking
- **Priority:** High
- **Personas Involved:** Driver, Admin
- **Steps:**
  1. Driver starts duty on dispatched route.
  2. Driver → POST /driver/location with `{ "lat": 12.9716, "lng": 77.5946, "timestamp": "..." }` → 200.
  3. Repeat 3 more times with different coordinates.
  4. Admin → GET /api/v1/routes/{route_id}/tracking → verify last known location is the latest update.
  5. Driver ends duty.
  6. Admin → GET /api/v1/routes/{route_id}/tracking → verify tracking data available in history.
- **Pass Criteria:** Location updates accepted; last known location queryable; tracking history retained.
- **Estimated Time:** 2 minutes

---

### CBF-020: Password Reset Stub Behavior
- **Flow:** Verify password reset endpoint behavior (stub — no actual reset implemented)
- **Priority:** Medium (Defect Documentation)
- **Personas Involved:** Employee, Guest
- **Steps:**
  1. POST /api/v1/auth/reset-password with `{ "mobile": "..." }` without any token → observe response.
  2. Verify that it returns 200 regardless of whether the mobile exists.
  3. Verify that no actual password change occurs (login still works with old credentials).
  4. Document as **KNOWN DEFECT — STUB BEHAVIOR**.
- **Pass Criteria:** Test documents stub behavior. Flag for implementation.
- **Estimated Time:** 1 minute

---

### CBF-021: Announcement Targeting by Audience
- **Flow:** Announcement created for specific audience (Drivers) — only Drivers see it, not Employees
- **Priority:** High
- **Personas Involved:** Admin, Driver, Employee
- **Steps:**
  1. Admin → create announcement with `audience=["driver"]` → publish.
  2. Driver → GET /api/v1/announcements → verify announcement appears.
  3. Employee → GET /api/v1/announcements → verify announcement does NOT appear.
  4. Admin → create another announcement with `audience=["employee", "driver"]`.
  5. Both Employee and Driver should see it.
- **Pass Criteria:** Audience-based filtering is enforced in the response.
- **Estimated Time:** 2 minutes

---

### CBF-022: Shift, Weekoff, and Cutoff Configuration
- **Flow:** Admin configures tenant settings → Employee bookings respect constraints
- **Priority:** High
- **Personas Involved:** Admin, Employee
- **Steps:**
  1. Admin → POST /api/v1/tenants/{id}/shifts with Morning shift (8:00 AM).
  2. Admin → POST /api/v1/tenants/{id}/weekoff with Saturday and Sunday.
  3. Admin → POST /api/v1/tenants/{id}/cutoff with 10 PM cutoff for next-day booking.
  4. Employee attempts booking on Saturday → 422 (weekoff).
  5. Employee attempts booking past cutoff → 422 (cutoff exceeded).
  6. Employee books for Monday morning → 201 (valid).
- **Pass Criteria:** All tenant config constraints are enforced during booking creation.
- **Estimated Time:** 2.5 minutes

---

### CBF-023: Alert Config CRUD
- **Flow:** Admin creates alert configurations; verify they trigger alerts appropriately
- **Priority:** High
- **Personas Involved:** Admin
- **Steps:**
  1. Admin → POST /api/v1/alert-configs with alert type=GEOFENCE_BREACH and threshold config.
  2. Admin → GET /api/v1/alert-configs → verify config exists.
  3. Admin → PATCH /api/v1/alert-configs/{id} to update threshold → verify 200.
  4. Admin → DELETE /api/v1/alert-configs/{id} → verify 200 or 204.
  5. GET /api/v1/alert-configs/{id} → verify 404 after deletion.
- **Pass Criteria:** Full CRUD works for alert configs.
- **Estimated Time:** 1.5 minutes

---

### CBF-024: Role Assignment and Permission Inheritance
- **Flow:** Admin assigns role to Employee → Employee now has role-based permissions
- **Priority:** Critical
- **Personas Involved:** Admin, Employee
- **Steps:**
  1. Admin creates a role with `["booking.read", "booking.create"]`.
  2. Admin assigns this role to Employee emp_001.
  3. emp_001 authenticates (receives updated JWT or token reflects new role).
  4. emp_001 → POST /api/v1/bookings → 201 (now allowed).
  5. Admin revokes the role from emp_001.
  6. emp_001 logs out and back in.
  7. emp_001 → POST /api/v1/bookings → 403 (permission revoked).
- **Pass Criteria:** Role assignment and revocation are reflected in subsequent tokens.
- **Estimated Time:** 2 minutes

---

### CBF-025: Report Data Tenant Scoping
- **Flow:** SubAdmin requests report → verifies only their tenant's data is in results
- **Priority:** High
- **Personas Involved:** Admin, SubAdmin
- **Steps:**
  1. Create bookings in tenant_A and tenant_B.
  2. Authenticate as SubAdmin in tenant_A with `report.read`.
  3. GET /api/v1/reports/bookings → verify ONLY tenant_A booking data in response.
  4. Verify no tenant_B IDs, names, or data in response.
  5. Authenticate as Admin → GET /api/v1/reports/bookings → verify data from BOTH tenants present.
- **Pass Criteria:** SubAdmin reports are tenant-scoped; Admin reports are global.
- **Estimated Time:** 2 minutes

---

### CBF-026: Concurrent Booking — Duplicate Prevention
- **Flow:** Two employees try to book the same seat on the same route simultaneously
- **Priority:** High
- **Personas Involved:** Employee (2 separate users)
- **Steps:**
  1. Configure a route with limited capacity (e.g., 1 seat remaining).
  2. Send 2 concurrent POST /api/v1/bookings requests from 2 different employee tokens.
  3. Observe that one booking succeeds (201) and the other fails (422 or 409).
  4. **Known Issue:** If DB lacks unique constraint, both may succeed — document as defect.
- **Pass Criteria:** At most one booking succeeds when capacity is exceeded. Document actual behavior.
- **Estimated Time:** 1.5 minutes

---

### CBF-027: Token Refresh Mid-Session
- **Flow:** Access token expires → refresh token used → new access token issued → session continues
- **Priority:** Critical
- **Personas Involved:** Employee
- **Steps:**
  1. Employee authenticates → receive `access_token` (short expiry in test config, e.g., 1 min).
  2. Wait for access_token to expire (or manipulate token exp in test).
  3. GET /api/v1/bookings with expired access_token → 401.
  4. POST /api/v1/auth/refresh with refresh_token → 200, new `access_token`.
  5. GET /api/v1/bookings with new access_token → 200.
  6. **Negative:** Attempt to use old expired access_token → still 401.
- **Pass Criteria:** Refresh flow works; old expired token remains invalid after refresh.
- **Estimated Time:** 2 minutes

---

## Phase C: Full Regression Tests

> This phase covers all modules in depth. It must be completed before every production release. Tests marked with ⚠️ are known flaky tests or tests that document known defects.

---

## C1. Authentication Module

---

### REG-AUTH-001: Admin Login Works with Correct Credentials
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/admin/login
- **Scenario:** Admin provides valid username + password.
- **Pass Criteria:** 200, JWT with `admin_id`, no `tenant_id`.

---

### REG-AUTH-002: Employee Login Works via OTP Flow
- **Module:** Auth
- **Scenario:** Full OTP→verify→select-tenant→JWT flow.
- **Pass Criteria:** JWT with `employee_id`, `tenant_id`, `role=employee`.

---

### REG-AUTH-003: OTP Expiry Respected (5-Minute Limit)
- **Module:** Auth
- **Endpoint:** POST /api/v1/auth/otp/verify
- **Scenario:** Send OTP → wait > 5 minutes → attempt verify with expired OTP.
- **Pass Criteria:** 422 with `"error_code": "OTP_EXPIRED"`.
- **Note:** In test environment, configure OTP TTL to 10 seconds for speed.

---

### REG-AUTH-004: Wrong OTP Returns Error
- **Module:** Auth
- **Scenario:** Use incorrect OTP during verification.
- **Pass Criteria:** 422 with `"error_code": "INVALID_OTP"`.

---

### REG-AUTH-005: Pre-Auth Token Rejected on Final Endpoints
- **Module:** Auth
- **Scenario:** Use pre-auth token (before select-tenant) on GET /api/v1/bookings.
- **Pass Criteria:** 401 or 403 with `"error_code": "INSUFFICIENT_TOKEN_STAGE"`.

---

### REG-AUTH-006: Logout Invalidates Session
- **Module:** Auth
- **Scenario:** Login → logout → use old token.
- **Pass Criteria:** 401 with `"error_code": "SESSION_EXPIRED"`.

---

### REG-AUTH-007: Password Reset Stub Always Returns 200 (Defect Documentation)
- **Module:** Auth
- **Scenario:** POST /auth/reset-password with random mobile number.
- **Pass Criteria:** 200 regardless of input. **Marked as KNOWN DEFECT.**

---

### REG-AUTH-008: Rate Limiting on OTP Send ⚠️
- **Module:** Auth
- **Scenario:** Send OTP 10+ times in rapid succession from same IP/mobile.
- **Pass Criteria:** After threshold, returns 429 with `Retry-After` header.
- **Note:** ⚠️ Flaky — depends on timing. Run with `--timeout=5` and `@pytest.mark.flaky(reruns=2)`.

---

### REG-AUTH-009: Single Session Enforcement
- **Module:** Auth
- **Scenario:** Employee logs in twice from different devices.
- **Pass Criteria:** First session returns 401 after second login.

---

### REG-AUTH-010: Refresh Token Cannot Be Reused After Rotation
- **Module:** Auth
- **Scenario:** Refresh access token → use old refresh token again.
- **Pass Criteria:** Second refresh with old refresh token returns 401 (token rotated).

---

## C2. Booking Module

---

### REG-BOOK-001: Employee Creates Valid Booking
- **Endpoint:** POST /api/v1/bookings
- **Pass Criteria:** 201, `status=Pending`.

---

### REG-BOOK-002: Admin Creates Booking for Any Employee
- **Endpoint:** POST /api/v1/bookings
- **Scenario:** Admin creates booking specifying another employee's ID.
- **Pass Criteria:** 201.

---

### REG-BOOK-003: Booking on Weekoff Day Rejected
- **Scenario:** Configure weekoff, attempt booking on that day.
- **Pass Criteria:** 422, `"error_code": "BOOKING_ON_WEEKOFF"`.

---

### REG-BOOK-004: Booking After Cutoff Time Rejected
- **Scenario:** Simulate post-cutoff time, attempt booking for next day.
- **Pass Criteria:** 422, `"error_code": "BOOKING_CUTOFF_EXCEEDED"`.

---

### REG-BOOK-005: Booking for Past Shift Rejected
- **Scenario:** Attempt to book a shift that has already passed today.
- **Pass Criteria:** 422, `"error_code": "SHIFT_ALREADY_PASSED"`.

---

### REG-BOOK-006: Pagination — Page 0 Behavior
- **Endpoint:** GET /api/v1/bookings?page=0&page_size=10
- **Pass Criteria:** Either 200 with first page results, or 422 if page=0 is invalid. Behavior must be consistent and not 500.

---

### REG-BOOK-007: Pagination — page_size=0 Behavior
- **Endpoint:** GET /api/v1/bookings?page=1&page_size=0
- **Pass Criteria:** Either 200 with empty items array (or default page_size applied), or 422. Must not be 500.

---

### REG-BOOK-008: Pagination — page_size=1000 (Large Page)
- **Endpoint:** GET /api/v1/bookings?page=1&page_size=1000
- **Pass Criteria:** Either 200 with results (capped at max allowed page_size), or 422 with max page_size error. Server must not time out or OOM.

---

### REG-BOOK-009: Booking Status Transition — Valid (Pending → Cancelled)
- **Scenario:** Employee cancels a Pending booking before cutoff.
- **Pass Criteria:** 200, `status=Cancelled`.

---

### REG-BOOK-010: Booking Status Transition — Invalid (Completed → Cancelled)
- **Scenario:** Attempt to cancel an already Completed booking.
- **Pass Criteria:** 422, `"error_code": "INVALID_STATUS_TRANSITION"`.

---

### REG-BOOK-011: Bulk Booking Atomicity — All Valid Dates
- **Scenario:** POST /bookings/bulk with 5 valid future dates.
- **Pass Criteria:** 201, all 5 bookings created.

---

### REG-BOOK-012: Bulk Booking Atomicity — One Invalid Date (Weekoff) ⚠️
- **Scenario:** POST /bookings/bulk where one date is a weekoff.
- **Pass Criteria:** Either ALL fail (atomicity) or partial success is explicitly documented. **Known behavior gap — document if DB constraint is missing.**

---

### REG-BOOK-013: Concurrent Duplicate Booking Detection ⚠️
- **Scenario:** Two identical booking requests sent concurrently for same employee, same date, same shift.
- **Pass Criteria:** Only one booking created. Second returns 409 or 422.
- **Note:** ⚠️ Flaky — race condition. If duplicate constraint missing in DB, both will succeed — **document as defect.**

---

## C3. Route Management Module

---

### REG-ROUTE-001: Admin Creates Route
- **Endpoint:** POST /api/v1/routes
- **Pass Criteria:** 201, `status=Created`.

---

### REG-ROUTE-002: Assign Vehicle to Route
- **Endpoint:** POST /api/v1/routes/{id}/assign-vehicle
- **Pass Criteria:** 200, `status=VehicleAssigned`.

---

### REG-ROUTE-003: Assign Vehicle Idempotency
- **Scenario:** Call assign-vehicle twice with same vehicle.
- **Pass Criteria:** Second call returns 200 or 409 (idempotent or error). Must not 500.

---

### REG-ROUTE-004: Assign Driver to Route
- **Endpoint:** POST /api/v1/routes/{id}/assign-driver
- **Pass Criteria:** 200, `status=DriverAssigned`.

---

### REG-ROUTE-005: Dispatch Route Generates Correct OTPs
- **Scenario:** Route has 3 bookings → dispatch → verify 3 OTPs generated (one per booking).
- **Pass Criteria:** 200, `status=Dispatched`, 3 OTP records in DB.

---

### REG-ROUTE-006: Cannot Dispatch Route Without DriverAssigned Status
- **Scenario:** Attempt to dispatch a route that has no driver assigned (status=Created or VehicleAssigned).
- **Pass Criteria:** 422, `"error_code": "INVALID_STATUS_FOR_DISPATCH"`.

---

### REG-ROUTE-007: Cancel a Dispatched Route
- **Scenario:** Admin cancels an already-dispatched route.
- **Pass Criteria:** 200, `status=Cancelled`. Associated bookings status updated.

---

### REG-ROUTE-008: Cannot Re-Dispatch a Completed Route
- **Scenario:** Attempt to dispatch a Completed route.
- **Pass Criteria:** 422, `"error_code": "INVALID_STATUS_TRANSITION"`.

---

### REG-ROUTE-009: Route CRUD — Update and Delete
- **Scenario:** Create route → update name/details → delete.
- **Pass Criteria:** Update returns 200 with new values; DELETE returns 200 or 204; GET returns 404 after delete.

---

### REG-ROUTE-010: Route List is Tenant-Scoped
- **Scenario:** Create routes in tenant_A and tenant_B. Query as SubAdmin of tenant_A.
- **Pass Criteria:** Only tenant_A routes returned.

---

## C4. Driver App Module

---

### REG-DRIVER-001: Duty Start is Idempotent
- **Scenario:** Driver calls POST /driver/duty/start twice for same route.
- **Pass Criteria:** First call = 200; second call = 200 (idempotent) or 409 (already on duty). Must not 500.

---

### REG-DRIVER-002: Duty End Finalizes All Active Trips
- **Scenario:** Driver ends duty with one open trip.
- **Pass Criteria:** 200; open trip is auto-finalized; route status = Completed.

---

### REG-DRIVER-003: Trip Start with Invalid OTP Fails
- **Scenario:** Driver calls POST /driver/trip/start with incorrect OTP.
- **Pass Criteria:** 422, `"error_code": "INVALID_OTP"`.

---

### REG-DRIVER-004: Trip Start with Valid OTP Succeeds
- **Scenario:** Driver calls POST /driver/trip/start with correct OTP.
- **Pass Criteria:** 200, trip `status=InProgress`.

---

### REG-DRIVER-005: No-Show Booking
- **Scenario:** Driver marks employee as no-show.
- **Pass Criteria:** 200, booking `status=NoShow`.

---

### REG-DRIVER-006: Location Update Accepted
- **Scenario:** Driver sends location update with valid coordinates.
- **Pass Criteria:** 200, location stored.

---

### REG-DRIVER-007: SOS Alert Creation
- **Scenario:** Driver triggers SOS during active trip.
- **Pass Criteria:** 201, alert `type=SOS`, `status=TRIGGERED`, notification dispatched.

---

### REG-DRIVER-008: Driver Cannot Start Duty for Unassigned Route
- **Scenario:** Driver calls duty/start for a route assigned to a different driver.
- **Pass Criteria:** 403, `"error_code": "ROUTE_NOT_ASSIGNED"`.

---

## C5. Alert Module

---

### REG-ALERT-001: Full Alert Lifecycle (TRIGGERED → ACKNOWLEDGED → IN_PROGRESS → CLOSED)
- **Pass Criteria:** Each transition returns 200; final status = CLOSED.

---

### REG-ALERT-002: Mark Alert as FALSE_ALARM
- **Scenario:** Alert acknowledged → marked as FALSE_ALARM.
- **Pass Criteria:** 200, `status=FALSE_ALARM`.

---

### REG-ALERT-003: Escalation Blocked After CLOSED
- **Scenario:** Close alert → attempt escalate.
- **Pass Criteria:** 422, `"error_code": "ALERT_ALREADY_CLOSED"`.

---

### REG-ALERT-004: Escalation Blocked After FALSE_ALARM
- **Scenario:** Mark FALSE_ALARM → attempt escalate.
- **Pass Criteria:** 422, `"error_code": "ALERT_CANNOT_BE_ESCALATED"`.

---

### REG-ALERT-005: Alert List is Tenant-Scoped
- **Scenario:** Create alerts in two tenants; query as SubAdmin of one.
- **Pass Criteria:** Only own tenant's alerts returned.

---

### REG-ALERT-006: Alert Config CRUD
- **Scenario:** Create, read, update, delete an alert config.
- **Pass Criteria:** Full CRUD cycle succeeds.

---

### REG-ALERT-007: SOS Notification Dispatched on Trigger
- **Scenario:** Trigger SOS alert → verify mock notification log.
- **Pass Criteria:** At least one notification entry in mock logs for alert creation.

---

### REG-ALERT-008: Duplicate SOS Prevention
- **Scenario:** Driver triggers SOS twice within 60 seconds on same route.
- **Pass Criteria:** Second SOS returns 200 or 409 — no duplicate alerts created. Document behavior.

---

## C6. Announcement Module

---

### REG-ANNC-001: DRAFT Status on Create
- **Endpoint:** POST /api/v1/announcements
- **Pass Criteria:** 201, `status=DRAFT`.

---

### REG-ANNC-002: Update Allowed on DRAFT
- **Endpoint:** PATCH /api/v1/announcements/{id}
- **Pass Criteria:** 200, changes persisted.

---

### REG-ANNC-003: Publish Transitions to PUBLISHED
- **Endpoint:** POST /api/v1/announcements/{id}/publish
- **Pass Criteria:** 200, `status=Published`.

---

### REG-ANNC-004: Update Rejected After Published
- **Scenario:** Attempt PATCH after publish.
- **Pass Criteria:** 422, `"error_code": "ANNOUNCEMENT_ALREADY_PUBLISHED"`.

---

### REG-ANNC-005: Delete Rejected After Published
- **Scenario:** Attempt DELETE after publish.
- **Pass Criteria:** 422 or 403, `"error_code": "CANNOT_DELETE_PUBLISHED_ANNOUNCEMENT"`.

---

### REG-ANNC-006: Publish Triggers Notification Dispatch
- **Scenario:** Publish announcement → check mock FCM/SMS/email logs.
- **Pass Criteria:** Notification dispatched to all targeted recipients.

---

### REG-ANNC-007: Duplicate Recipient on Retry ⚠️
- **Scenario:** Publish notification fails mid-way → admin retries publish.
- **Pass Criteria:** System prevents duplicate notifications to recipients who already received them.
- **Note:** ⚠️ **Known Defect** — idempotency on notification retry may not be implemented. Document actual behavior.

---

### REG-ANNC-008: Audience Filtering Works Correctly
- **Scenario:** Create announcement for `audience=["driver"]`; publish; verify employee cannot see it.
- **Pass Criteria:** Drivers see it; employees do not.

---

## C7. IAM Module

---

### REG-IAM-001: PolicyPackage Hierarchy Enforced
- **Scenario:** Create policy under tenant with permissions NOT in the PolicyPackage.
- **Pass Criteria:** 422, `"error_code": "PERMISSIONS_EXCEED_PACKAGE"`.

---

### REG-IAM-002: Policy Cannot Exceed Package Permissions
- **Scenario:** Package has `["booking.read"]`; attempt to add `"route.dispatch"` to policy.
- **Pass Criteria:** Request rejected.

---

### REG-IAM-003: Role Assignment and Permission Inheritance
- **Scenario:** Assign role to user → user's next token reflects role permissions.
- **Pass Criteria:** User gains new permissions after role assignment and re-login.

---

### REG-IAM-004: Role Revocation Removes Permissions
- **Scenario:** Revoke role → user re-authenticates → no longer has those permissions.
- **Pass Criteria:** 403 on previously allowed endpoints.

---

### REG-IAM-005: System Role Cannot Be Created by SubAdmin
- **Scenario:** SubAdmin (even with `iam.write`) attempts to create a system-level role.
- **Pass Criteria:** 403.

---

### REG-IAM-006: Tenant-Scoped Role Cannot Be Used in Another Tenant
- **Scenario:** Create role in tenant_A; attempt to assign it to a user in tenant_B.
- **Pass Criteria:** 422 or 403.

---

### REG-IAM-007: Package CRUD by Admin
- **Scenario:** Admin creates, reads, updates a package.
- **Pass Criteria:** Full lifecycle works.

---

### REG-IAM-008: Policy CRUD by SubAdmin (With Permission)
- **Scenario:** SubAdmin with `iam.write` creates, reads, updates a policy.
- **Pass Criteria:** Full lifecycle works within package constraints.

---

## C8. Security Regression

---

### REG-SEC-001: Route Grouping Endpoints Unauthenticated (Known Bug) ⚠️
- **Scenario:** All 4 CRUD operations without token.
- **Expected (Desired):** 401 on all.
- **Actual (Current):** 200/201 — unauthenticated access succeeds.
- **Note:** Mark `@pytest.mark.xfail(reason="BUG-001: route_grouping auth bypass")`. This test should FAIL until the bug is fixed.

---

### REG-SEC-002: Push Notification Endpoints Unauthenticated (Known Bug) ⚠️
- **Scenario:** POST /push-notifications/send and /send-batch without token.
- **Expected (Desired):** 401.
- **Actual (Current):** 200 — unauthenticated access.
- **Note:** Mark `@pytest.mark.xfail(reason="BUG-002: push notification auth bypass")`.

---

### REG-SEC-003: Cross-Tenant Data Isolation
- **Scenario:** Employee from tenant_A accesses tenant_B booking by ID.
- **Pass Criteria:** 403 or 404. No tenant_B data returned.

---

### REG-SEC-004: Expired Token Universally Rejected
- **Scenario:** Use expired JWT on 5 different endpoints across modules.
- **Pass Criteria:** All return 401, never 500.

---

### REG-SEC-005: SQL Injection in Search Parameters
- **Scenario:** GET /api/v1/bookings?search='; DROP TABLE bookings; --
- **Pass Criteria:** 400 or empty results; never 500; no DB error exposed.

---

### REG-SEC-006: SQL Injection in Path Parameter
- **Scenario:** GET /api/v1/bookings/1' OR '1'='1
- **Pass Criteria:** 422 (FastAPI validation rejects non-UUID) or 404. Never 500.

---

### REG-SEC-007: XSS Payload in Announcement Body
- **Scenario:** POST /api/v1/announcements with `"body": "<script>alert(1)</script>"`.
- **Pass Criteria:** Either 422 (rejected), or stored as escaped string (harmless). Never stored as raw HTML and served back unescaped.

---

## C9. Reports Module

---

### REG-REPORT-001: Booking Report with Valid Date Range
- **Endpoint:** GET /api/v1/reports/bookings?start_date=2026-04-01&end_date=2026-04-30
- **Pass Criteria:** 200, results within date range only.

---

### REG-REPORT-002: Route Report with Pagination
- **Endpoint:** GET /api/v1/reports/routes?page=1&page_size=20
- **Pass Criteria:** 200, paginated results.

---

### REG-REPORT-003: Driver Report Returns Correct Metrics
- **Endpoint:** GET /api/v1/reports/drivers
- **Pass Criteria:** 200, response contains trip counts, no-show rates per driver.

---

### REG-REPORT-004: Report Data is Tenant-Scoped for SubAdmin
- **Scenario:** SubAdmin requests report → only own tenant data returned.
- **Pass Criteria:** Zero cross-tenant data in response.

---

### REG-REPORT-005: Report with Invalid Date Range
- **Scenario:** start_date > end_date.
- **Pass Criteria:** 422, `"error_code": "INVALID_DATE_RANGE"`.

---

## Regression Execution Checklist

### Environment Setup

```bash
# 1. Start infrastructure
docker-compose -f docker-compose.test.yml up -d postgres redis

# 2. Wait for services to be healthy
docker-compose -f docker-compose.test.yml ps  # all should show "healthy"

# 3. Apply migrations
alembic upgrade head

# 4. Seed required base data
python scripts/seed_test_data.py
# Creates: test tenants (tenant_A, tenant_B), admin user, test employees, 
#          test drivers, test vendors, test shifts, weekoff configs, 
#          IAM packages, and sample routes

# 5. Verify environment
pytest tests/smoke/test_health.py -v  # must pass before continuing
```

### Test Data Seeding Requirements

| Data Item | Required For | Notes |
|-----------|-------------|-------|
| tenant_A, tenant_B | All cross-tenant tests | Different IAM packages |
| admin user | Auth, IAM, all admin-required tests | Global admin, no tenant |
| SubAdmin (tenant_A) with full IAM policy | CBF, IAM, booking tests | Must have all permissions |
| SubAdmin (tenant_A) with limited policy | RBAC negative tests | Only `booking.read` |
| Employee emp_001 (tenant_A) | Booking, session tests | |
| Employee emp_002 (tenant_A) | Cross-employee isolation tests | |
| Employee emp_003 (tenant_B) | Cross-tenant tests | |
| Driver drv_001 (tenant_A) | Driver app tests | Device registered |
| Driver drv_002 (tenant_A) | Cross-driver isolation | |
| Vendor vnd_001 (tenant_A) | Vendor tests | With 2 vehicles |
| Vendor vnd_002 (tenant_A) | Cross-vendor isolation | |
| Escort user (tenant_A) | Escort role tests | |
| Morning Shift + Evening Shift | Booking rule tests | |
| Weekoff: Saturday, Sunday | Booking rule tests | |
| Cutoff: 10 PM | Booking cutoff tests | |
| IAM Package (full) for tenant_A | IAM hierarchy tests | All permissions |
| IAM Package (limited) for tenant_B | Cross-package tests | Subset only |

### Execution Order Dependencies

```
Phase A (Smoke) → must all pass
    ↓
Phase B — CBF flows can run in parallel EXCEPT:
    CBF-001 depends on: CBF-002 (employee auth), CBF-003 (driver auth)
    CBF-008 (IAM flow) must run before CBF-018 (SubAdmin bookings)
    CBF-007 (vendor setup) must run before route tests using vendor vehicles
    ↓
Phase C — Run by module:
    C1 (Auth) → prerequisite for all other modules
    C2 (Booking) → requires C1 complete
    C3 (Route) → requires C2 (bookings must exist for route creation)
    C4 (Driver) → requires C3 (route must be dispatched)
    C5 (Alert) → requires C4 (driver on active route for SOS)
    C6, C7, C8, C9 → independent of C4/C5, can run in parallel with them
```

### Known Flaky Tests

| Test ID | Reason | Mitigation |
|---------|--------|------------|
| REG-AUTH-008 | Rate limiting depends on Redis TTL timing | Use `@pytest.mark.flaky(reruns=3)`, run last in Auth suite |
| REG-BOOK-013 | Race condition in concurrent booking | Use thread synchronization in test; rerun on failure |
| REG-ANNC-007 | Notification retry idempotency not guaranteed | Run 2x manually; document if both produce duplicates |
| CBF-026 | Concurrent booking capacity check | Use `ThreadPoolExecutor` with barriers; mark xfail if DB constraint missing |
| Any test using OTP TTL | OTP expiry tests need timing control | Set `OTP_TTL_SECONDS=10` in test env |

### Pass/Fail Thresholds

| Phase | Required Pass Rate | Action if Below Threshold |
|-------|-------------------|--------------------------|
| Phase A — Smoke | **100%** — Zero tolerance | **STOP all testing. Escalate immediately. Do not proceed to Phase B.** |
| Phase B — CBF | **≥ 95%** (max 1 failure in non-security flows) | Investigate and fix; re-run before release |
| Phase C — Full Regression | **≥ 90%** (excluding known xfail tests) | P1 failures block release; P2 failures tracked in backlog |
| Security Regression (C8) | **100%** (excluding documented known bugs) | Any new security failure = **RELEASE BLOCKED** |

### Known Failures to Exclude from Pass Rate

The following tests are documented known defects and are marked `xfail`. They **should not** count against pass/fail thresholds until the bugs are fixed:

| Test | Bug Reference | Priority |
|------|--------------|----------|
| REG-SEC-001, CBF-015 | BUG-001: route_grouping auth bypass | P0 — fix before production |
| REG-SEC-002, CBF-016 | BUG-002: push notification auth bypass | P0 — fix before production |
| REG-AUTH-007, CBF-020 | BUG-004: password reset stub | P2 — fix in next sprint |
| REG-BOOK-013 | Missing DB unique constraint on concurrent bookings | P2 — needs schema change |
| REG-ANNC-007 | Notification retry idempotency | P2 — track in backlog |

### Post-Run Reporting

```bash
# Generate HTML report
pytest tests/ --html=reports/regression_$(date +%Y%m%d).html --self-contained-html

# Generate JUnit XML (for CI integration)
pytest tests/ --junitxml=reports/junit_$(date +%Y%m%d).xml

# Coverage report (if configured)
pytest tests/ --cov=app --cov-report=html:reports/coverage/

# View known failures summary
pytest tests/ -v -r x  # shows xfailed tests with reasons
```

### CI/CD Integration

```yaml
# Sample GitHub Actions step
- name: Run Smoke Tests
  run: pytest tests/smoke/ -v --tb=short -x --junitxml=smoke_results.xml

- name: Run Full Regression (on main branch only)
  if: github.ref == 'refs/heads/main'
  run: pytest tests/ -v --tb=long -n 4 --junitxml=regression_results.xml

- name: Upload Test Reports
  uses: actions/upload-artifact@v3
  with:
    name: test-reports
    path: reports/
```
