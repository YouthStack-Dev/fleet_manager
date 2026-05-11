# Backend Functional Test Scope Analysis

## Scope Basis
- Code analyzed from `app/routes`, `app/models`, `app/schemas`, `app/crud`, `app/services`, middleware, and existing tests under `tests/`.
- API surface is primarily mounted under `/api/v1` via `app/api.py`.
- Risk ranking is based on business impact, security impact, data integrity impact, and production blast radius.

## Test Depth Legend
- **L4**: Exhaustive (positive, negative, boundary, concurrency, misuse, integration, DB verification)
- **L3**: Deep functional (positive/negative/boundary + key integration paths)
- **L2**: Standard functional (core positive + common negative)
- **L1**: Smoke-only critical availability checks

## Module-Wise Scope Matrix

| Module Name | Features Covered | Risk Level | Test Priority | Dependencies | Recommended Test Depth |
|---|---|---|---|---|---|
| Authentication and Session Management | Employee/vendor/admin login, token creation, refresh, introspection, `/auth/me`, `/auth/profile`, session invalidation | Critical | P0 | JWT, Redis opaque-token cache, DB user tables | L4 |
| Employee OTP Authentication | OTP request, verify, pre-auth token, tenant selection and switching | Critical | P0 | Redis OTP/session keys, SMTP/SMS services, tenant-role mapping | L4 |
| Driver Device Authentication | Device verify, active Android device binding, tenant/vendor selection, driver refresh | Critical | P0 | Driver table, Redis sessions, device history JSON, JWT | L4 |
| Escort Authentication | Escort login, password-required checks, escort session model | High | P1 | Escort table, Redis session pointer, JWT | L3 |
| IAM Permissions | Permission CRUD and uniqueness (`module`,`action`) | High | P1 | IAM tables, policy/role references | L3 |
| IAM Policies | Policy CRUD, system vs tenant policy rules, package-boundary permission validation | Critical | P0 | Permission table, policy package table, role-policy links | L4 |
| IAM Roles | Role CRUD, system vs tenant role rules, role-policy compatibility checks | Critical | P0 | Policies, users (employee/vendor/driver/admin), cache invalidation | L4 |
| IAM Policy Packages | Tenant permission boundary read/update, super-admin updates | Critical | P0 | Tenant table, permissions table, policy/role compatibility | L4 |
| Tenant Management | Tenant create/list/get/update/toggle, seed baseline IAM package objects | Critical | P0 | Tenant, role/policy/package, employee bootstrap | L4 |
| Tenant Configuration | Escort OTP toggles and escort window configs | High | P1 | Tenant config table, route dispatch behavior | L3 |
| Vendor Management | Vendor CRUD, tenant scoping, active state toggles | High | P1 | Tenant FK, drivers/vehicles/vendor-users | L3 |
| Vendor User Management | Vendor user CRUD/toggle/delete, tenant and vendor ownership checks | High | P1 | Vendor, role, auth password policy, uniqueness constraints | L3 |
| Employee Management | Employee CRUD, bulk template, bulk upload validation, duplicate handling | Critical | P0 | Tenant/team/role, unique constraints, email generation | L4 |
| Driver Management (Admin APIs) | Driver create/read/update/toggle, vendor scoping, identity docs | Critical | P0 | Vendor, role, driver unique constraints, auth flows | L4 |
| Escort Management (Admin APIs) | Escort CRUD, set-password, available escort listing | High | P1 | Tenant/vendor links, escort app auth flow | L3 |
| Team Management | Team CRUD and toggle, tenant-level isolation | Medium | P2 | Tenant FK, employee references | L3 |
| Shift Management | Shift CRUD/toggle, shift-time format and tenant isolation | High | P1 | Tenant FK, bookings/routes linkage | L3 |
| Weekoff Configuration | Employee/team/tenant weekoff rules and inheritance behavior | High | P1 | Employee/team/tenant models, booking create validation | L3 |
| Cutoff Configuration | Booking/cancel/login/logout/adhoc/emergency cutoff rules | Critical | P0 | Tenant FK, booking routes and shift timing | L4 |
| Vehicle Type Management | Vehicle type CRUD, name uniqueness per vendor, toggle status | Medium | P2 | Vendor FK, vehicle creation dependency | L3 |
| Vehicle Management and File Access | Vehicle CRUD/status, driver assignment rules, file URL/path access control | High | P1 | Vendor/driver/vehicle type, storage service, auth role scoping | L4 |
| Booking Management | Create/list/get/update/cancel, cutoff/weekoff/duplicate logic, tenant scope | Critical | P0 | Employee/team/shift/cutoff/weekoff, route linkage | L4 |
| Route Grouping and Suggestions | Route suggestion, clustering by bookings | High | P1 | Booking geo data, shift/tenant context, clustering algorithm | L3 |
| Route Management Core | Create/list/get/update/merge/delete routes, vendor/vehicle/escort assignment, dispatch notifications | Critical | P0 | Booking state transitions, vendor/vehicle/driver, OTP, notifications, transaction locking | L4 |
| Driver App Operations | Duty start/end, trip start/drop/no-show, location/OTP/order checks | Critical | P0 | Route/booking statuses, tenant config OTP settings, escort boarded state | L4 |
| Employee App Endpoints | Employee booking feed and access controls | Medium | P2 | Booking/route joins, token claims | L2 |
| Escort App Endpoints | Escort profile/routes/detail/password change, OTP visibility rules | High | P1 | Escort auth, route assignment/dispatch state | L3 |
| SOS Alert Lifecycle | Trigger/acknowledge/close/escalate/timeline and active alerts | Critical | P0 | Alert/config tables, employee/booking context, notification services | L4 |
| Alert Configuration | Team/tenant routing rules, escalation thresholds, dry-run/real notification tests | Critical | P0 | Alert configuration JSON fields, teams, notification services | L4 |
| Announcements/Broadcast | Draft/create/update/publish/delete, recipient expansion, channel delivery tracking, read-state | High | P1 | Announcement tables, employee/driver recipients, FCM/SMS/Email services | L4 |
| Reviews | Tags CRUD, booking/route review submit/read/list, one-review-per-booking enforcement | High | P1 | Booking completion state, driver/vehicle joins, rating constraints | L3 |
| Push Notification Session and Dispatch | Register token/logout/session-info/send/send-batch, cache-first token lookup | Critical | P0 | User sessions table, Redis cache, FCM service, JWT verification | L4 |
| Reports | Booking export and analytics with role-scoped filtering | High | P1 | Booking/route joins, openpyxl generation, date-range constraints | L3 |
| Audit Logs | Module-scoped audit retrieval and role restrictions | Medium | P2 | Audit table, auth claims | L2 |
| Monitoring APIs | Health/DB/cache/system/task/error/request metrics endpoints | High | P1 | middleware trackers, Redis cache, DB monitor utils | L3 |
| Metrics Endpoint Security | `/metrics` basic-auth protection behavior | High | P1 | Settings `METRICS_USER/PASSWORD`, middleware ordering | L3 |
| Core Operational Endpoints | `/health`, `/db-tables`, seed/create/drop tables operational APIs | Critical | P0 | DB schema, safety controls, deployment profile | L4 |
| Dev Utilities | Cache clear/stats endpoints | Medium | P2 | Cache manager, admin permission assumptions | L2 |
| Middleware Behavior | URL validation, request tracking, error tracking side effects | High | P1 | Middleware stack order, Redis cache, exception handling | L3 |
| Integrations and Async Services | Email, SMS, FCM, unified notification orchestration, session cleanup | Critical | P0 | SMTP, Twilio, Firebase, Redis, background tasks | L4 |
| Migration and Schema Integrity | Alembic heads, upgrade/downgrade, constraints/indexes correctness | Critical | P0 | Postgres, migration scripts, CI migration workflow | L4 |

## Critical Business Workflows (Must Pass Before Release)
1. Employee OTP login -> tenant select -> booking create -> route plan -> dispatch -> driver duty/trip completion.
2. Driver device verification -> tenant/vendor select -> token refresh -> duty lifecycle completion.
3. SOS trigger -> responder acknowledgment -> escalation path -> close/false-alarm closure with timeline/audit.
4. Tenant onboarding -> policy package boundaries -> role/policy creation -> scoped user access enforcement.
5. Announcement draft -> publish (push/sms/email/in-app) -> recipient read state -> reporting analytics consistency.

## High-Risk Dependency Areas
- **Redis dependency**: auth opaque token/session pointers, OTP, push session cache, middleware trackers.
- **Cross-module state coupling**: booking status and route status are tightly coupled; route operations mutate booking states.
- **JSON configuration correctness**: alert recipient/channel schemas and policy-package permission boundaries.
- **External integrations**: FCM token validity cleanup, SMTP retry behavior, SMS provider failures.
- **Operational endpoint exposure**: monitoring/core/dev routes include sensitive controls; must be role-gated in production profiles.

## Recommended Execution Order
1. P0 modules (Auth, IAM, Booking, Route, Driver app, Alerts, Push sessions, Migrations)
2. P1 modules (Vendor/User, Employee, Vehicle, Announcements, Reports, Monitoring)
3. P2 modules and observability refinements
