from fastapi import APIRouter
from app.routes import (
    auth_router,
    driver_router,
    vendor_router,
    vehicle_type_router,
    vehicle_router,
    vendor_user_router,
    team_router,
    tenant_router,
    employee_router,
    shift_router,
    booking_router,
    route_router,
    route_booking_router,
    weekoff_config_router,
    # Include any additional routers here
)

api_router = APIRouter()

# Include all routers
api_router.include_router(auth_router.router, prefix="/api")
api_router.include_router(driver_router.router, prefix="/api")
api_router.include_router(vendor_router.router, prefix="/api")
api_router.include_router(vehicle_type_router.router, prefix="/api")
api_router.include_router(vehicle_router.router, prefix="/api")
api_router.include_router(vendor_user_router.router, prefix="/api")
api_router.include_router(team_router.router, prefix="/api")
api_router.include_router(tenant_router.router, prefix="/api")
api_router.include_router(employee_router.router, prefix="/api")
api_router.include_router(shift_router.router, prefix="/api")
api_router.include_router(booking_router.router, prefix="/api")
api_router.include_router(route_router.router, prefix="/api")
api_router.include_router(route_booking_router.router, prefix="/api")
api_router.include_router(weekoff_config_router.router, prefix="/api")
