from app.routes.employee_router import router as employee_router
from app.routes.driver_router import router as driver_router
from app.routes.booking_router import router as booking_router
from app.routes.tenant_router import router as tenant_router
from app.routes.vendor_router import router as vendor_router
from app.routes.vehicle_type_router import router as vehicle_type_router
from app.routes.vehicle_router import router as vehicle_router
from app.routes.vendor_user_router import router as vendor_user_router
from app.routes.team_router import router as team_router
from app.routes.shift_router import router as shift_router
from app.routes.escort_router import router as escort_router
# from app.routes.route_router import router as route_router
# from app.routes.route_booking_router import router as route_booking_router
from app.routes.route_grouping import router as route_grouping_router
from app.routes.weekoff_config_router import router as weekoff_config_router
from app.routes.auth_router import router as auth_router
from app.routes.cutoff import router as cutoff_router
from app.routes.app_driver_router import router as app_driver_router
from app.routes.app_employee_router import router as app_employee_router
from app.routes.reports_router import router as reports_router
from app.routes.audit_log_router import router as audit_log_router
from app.routes.monitoring_router import router as monitoring_router
from app.routes.tenant_config_router import router as tenant_config_router
from app.routes.push_notifications import router as push_notifications_router

# Development/Testing routes (admin only)
from app.routes.dev_testing_routes import router as dev_testing_router