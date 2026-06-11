"""
API Router aggregation — all routers assembled here.

Instead of registering 30+ routers in main.py, we register them all here
and expose a single `api_router` to main.py. Keeps main.py ultra-clean.
"""

from fastapi import APIRouter

from app.routes import (
    # Core
    core_router,
    # Auth & tenants
    auth_router, tenant_router, tenant_config_router,
    # Vendors
    vendor_router, vendor_user_router,
    # Employees & drivers
    employee_router, driver_router, app_employee_router, app_driver_router,
    # Fleet assets
    vehicle_type_router, vehicle_router, escort_router, app_escort_router,
    # Scheduling
    team_router, shift_router, weekoff_config_router, cutoff_router,
    # Bookings & routing
    booking_router, grouping, route_management,
    # Nodal Points
    nodal_point_router,
    # Cost centers & route costing
    cost_center_router, costing_router,
    # Alerts
    alert_router, alert_config_router,
    # Notifications
    push_notifications_router,
    # IAM
    permission_router, policy_router, policy_package_router, role_router,
    # Observability & reporting
    monitoring_router, audit_log_router, reports_router, log_stream_router,
    # Admin & System Management
    admin_router,
    # Ride Reviews
    review_router,
    # Announcements
    announcement_router,
    # Speed Violations
    speed_violation_router,
    # Chat (Employee ↔ Driver)
    chat_router,
    # Seed & dev utilities
    dev_testing_router,
    # Dashboard
    dashboard_router,
)
from app.seed.seed_api import router as seed_router


# ──────────────────────────────────────────────────────────────
# Main API router — all sub-routers registered here
# ──────────────────────────────────────────────────────────────
api_router = APIRouter()

V1 = "/api/v1"

# Core (/, /health, /db-tables, ...)
api_router.include_router(core_router)

# Auth & tenants
api_router.include_router(auth_router,               prefix=V1)
api_router.include_router(tenant_router,             prefix=V1)
api_router.include_router(tenant_config_router,      prefix=V1)

# Vendors
api_router.include_router(vendor_router,             prefix=V1)
api_router.include_router(vendor_user_router,        prefix=V1)

# Employees & drivers
api_router.include_router(employee_router,           prefix=V1)
api_router.include_router(driver_router,             prefix=V1)
api_router.include_router(app_employee_router,       prefix=V1)
api_router.include_router(app_driver_router,         prefix=V1)
api_router.include_router(app_escort_router,         prefix=V1)

# Fleet assets
api_router.include_router(vehicle_type_router,       prefix=V1)
api_router.include_router(vehicle_router,            prefix=V1)
api_router.include_router(escort_router,             prefix=V1)

# Scheduling
api_router.include_router(team_router,               prefix=V1)
api_router.include_router(shift_router,              prefix=V1)
api_router.include_router(weekoff_config_router,     prefix=V1)
api_router.include_router(cutoff_router,             prefix=V1)

# Bookings & routing
api_router.include_router(booking_router,            prefix=V1)
api_router.include_router(grouping.router,           prefix=V1)
api_router.include_router(route_management.router,   prefix=V1)

# Nodal Points
api_router.include_router(nodal_point_router,        prefix=V1)

# Cost centers & route costing
api_router.include_router(cost_center_router,        prefix=V1)
api_router.include_router(costing_router,            prefix=V1)

# Alerts — carry /api/v1/... prefix internally
api_router.include_router(alert_router)
api_router.include_router(alert_config_router)

# Notifications
api_router.include_router(push_notifications_router, prefix=V1)

# IAM
api_router.include_router(permission_router,     prefix=f"{V1}/iam")
api_router.include_router(policy_router,         prefix=f"{V1}/iam")
api_router.include_router(policy_package_router, prefix=f"{V1}/iam")
api_router.include_router(role_router,           prefix=f"{V1}/iam")

# Observability & reporting
api_router.include_router(monitoring_router, prefix=V1)
api_router.include_router(audit_log_router,  prefix=V1)
api_router.include_router(reports_router,    prefix=V1)
api_router.include_router(log_stream_router, prefix=V1)

# Admin & System Management
api_router.include_router(admin_router,      prefix=V1)

# Ride reviews
api_router.include_router(review_router,        prefix=V1)

# Announcements / Broadcasts
api_router.include_router(announcement_router, prefix=V1)

# Speed Violations
api_router.include_router(speed_violation_router, prefix=V1)

# Chat (Employee ↔ Driver real-time messaging)
api_router.include_router(chat_router, prefix=V1)

# Seed & development utilities
api_router.include_router(seed_router,        prefix=V1)
api_router.include_router(dev_testing_router, prefix=V1)

# Dashboard
api_router.include_router(dashboard_router,   prefix=V1)
