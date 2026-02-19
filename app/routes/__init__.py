# ── Core utilities ────────────────────────────────────────────
from app.routes.core_router import router as core_router

# ── Auth & tenants ────────────────────────────────────────────
from app.routes.auth_router import router as auth_router
from app.routes.tenant_router import router as tenant_router
from app.routes.tenant_config_router import router as tenant_config_router

# ── Vendors ───────────────────────────────────────────────────
from app.routes.vendor_router import router as vendor_router
from app.routes.vendor_user_router import router as vendor_user_router

# ── Employees & drivers ───────────────────────────────────────
from app.routes.employee_router import router as employee_router
from app.routes.driver_router import router as driver_router
from app.routes.app_employee_router import router as app_employee_router
from app.routes.app_driver_router import router as app_driver_router

# ── Fleet assets ──────────────────────────────────────────────
from app.routes.vehicle_type_router import router as vehicle_type_router
from app.routes.vehicle_router import router as vehicle_router
from app.routes.escort_router import router as escort_router

# ── Scheduling ────────────────────────────────────────────────
from app.routes.team_router import router as team_router
from app.routes.shift_router import router as shift_router
from app.routes.weekoff_config_router import router as weekoff_config_router
from app.routes.cutoff import router as cutoff_router

# ── Bookings & routing ────────────────────────────────────────
from app.routes.booking_router import router as booking_router
from app.routes import grouping
from app.routes import route_management

# ── Alerts (SOS) ──────────────────────────────────────────────
from app.routes.alert_router import router as alert_router
from app.routes.alert_config_router import router as alert_config_router

# ── Notifications ─────────────────────────────────────────────
from app.routes.push_notifications import router as push_notifications_router

# ── IAM ───────────────────────────────────────────────────────
from app.routes.iam import permission_router, policy_router, role_router

# ── Observability & reporting ─────────────────────────────────
from app.routes.monitoring_router import router as monitoring_router
from app.routes.audit_log_router import router as audit_log_router
from app.routes.reports_router import router as reports_router

# ── Seed & development utilities ──────────────────────────────
from app.routes.dev_testing_routes import router as dev_testing_router