# app/routes/app_escort_router.py
"""
Escort Mobile-App Router
========================
Provides the API surface used by the escort mobile application.

Authentication
--------------
All endpoints require a valid JWT issued by  POST /api/v1/auth/escort/login.
The token carries  user_type="escort"  and grants the  app-escort  module
permissions checked by the EscortAuth dependency.

Endpoints
---------
GET  /escort/profile               - authenticated escort's own profile
GET  /escort/routes                - routes assigned to this escort (paginated)
GET  /escort/routes/{route_id}     - full detail of one route including stop list

OTP visibility
--------------
The escort_otp field is present on route_management and is set at dispatch time.
It is returned to the escort only after the route has been dispatched
(i.e. escort_otp IS NOT NULL).  The escort tells this OTP verbally to the driver,
who enters it via  POST /driver/escort/board  to confirm boarding.

escort_status progression:
  pending_dispatch  → awaiting_boarding → boarded
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.core.logging_config import get_logger
from app.database.session import get_db
from app.models.escort import Escort
from app.models.route_management import (
    RouteManagement,
    RouteManagementBooking,
    RouteManagementStatusEnum,
)
from app.models.booking import Booking
from app.models.driver import Driver
from app.models.vehicle import Vehicle
from app.models.shift import Shift
from app.utils.response_utils import ResponseWrapper, handle_db_error
from common_utils.auth.token_validation import validate_bearer_token
from common_utils.auth.utils import hash_password, verify_password

logger = get_logger(__name__)
router = APIRouter(prefix="/escort", tags=["Escort App"])

# ──────────────────────────────────────────────────────────────────────────────
# Auth dependency
# ──────────────────────────────────────────────────────────────────────────────

async def EscortAuth(
    user_data: dict = Depends(validate_bearer_token())
):
    """
    Validates the Bearer token and ensures it belongs to an escort user.
    Uses validate_bearer_token() directly — no permission model needed.
    Returns a dict with tenant_id, escort_id, vendor_id extracted from the token.
    """
    if user_data.get("user_type") != "escort":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Escort access only",
                error_code="ESCORT_ACCESS_ONLY",
            ),
        )
    tenant_id = user_data.get("tenant_id")
    escort_id = user_data.get("user_id")
    vendor_id = user_data.get("vendor_id")

    if not tenant_id or not escort_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Escort or tenant not resolved from token",
                error_code="TOKEN_INVALID",
            ),
        )
    return {"tenant_id": tenant_id, "escort_id": escort_id, "vendor_id": vendor_id}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

# Map query-param string → enum value
_STATUS_MAP = {
    "planned": RouteManagementStatusEnum.PLANNED,
    "vendor_assigned": RouteManagementStatusEnum.VENDOR_ASSIGNED,
    "driver_assigned": RouteManagementStatusEnum.DRIVER_ASSIGNED,
    "ongoing": RouteManagementStatusEnum.ONGOING,
    "completed": RouteManagementStatusEnum.COMPLETED,
    "cancelled": RouteManagementStatusEnum.CANCELLED,
}


def _compute_escort_status(route: RouteManagement) -> str:
    """
    Human-readable status of the escort's boarding journey for this route.

    pending_dispatch  - route assigned but not yet dispatched (no OTP generated)
    awaiting_boarding - route dispatched, OTP sent to escort, driver hasn't confirmed yet
    boarded           - driver entered the OTP and confirmed boarding
    """
    if route.escort_otp is None:
        return "pending_dispatch"
    if not route.escort_boarded:
        return "awaiting_boarding"
    return "boarded"


def _serialize_route_summary(
    route: RouteManagement,
    driver: Optional[Driver],
    vehicle: Optional[Vehicle],
    shift: Optional[Shift],
    employee_count: int,
) -> dict:
    """Serialize a route into the summary format used in the list endpoint."""
    otp_available = route.escort_otp is not None

    return {
        "route_id": route.route_id,
        "route_code": route.route_code,
        "status": route.status.value if route.status else None,
        "shift_id": route.shift_id,
        "shift": (
            {
                "shift_id": shift.shift_id,
                "shift_code": shift.shift_code,
                "log_type": shift.log_type.value if shift.log_type else None,
                "shift_time": str(shift.shift_time) if shift.shift_time else None,
                "pickup_type": shift.pickup_type.value if shift.pickup_type else None,
            }
            if shift
            else None
        ),
        "driver": (
            {
                "driver_id": driver.driver_id,
                "name": driver.name,
                "phone": driver.phone,
            }
            if driver
            else None
        ),
        "vehicle": (
            {
                "vehicle_id": vehicle.vehicle_id,
                "rc_number": vehicle.rc_number,
            }
            if vehicle
            else None
        ),
        "employee_count": employee_count,
        # OTP / boarding info
        "otp_available": otp_available,
        "escort_otp": route.escort_otp if otp_available else None,
        "escort_boarded": route.escort_boarded,
        "escort_status": _compute_escort_status(route),
        "escort_status_message": _boarding_message(route),
        "created_at": route.created_at.isoformat() if route.created_at else None,
        "updated_at": route.updated_at.isoformat() if route.updated_at else None,
    }


def _boarding_message(route: RouteManagement) -> str:
    """Return a human-readable message for the escort app UI."""
    if route.escort_otp is None:
        return "Your route has not been dispatched yet. Your OTP will appear here once the route is sent."
    if not route.escort_boarded:
        return (
            f"Tell this OTP to your driver to confirm boarding: {route.escort_otp}. "
            "Once the driver enters it, your boarding will be confirmed."
        )
    return "Your boarding has been confirmed by the driver. The trip will start shortly."


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_escort_profile(
    auth: dict = Depends(EscortAuth),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated escort's own profile information.

    Useful for the app's "My Profile" screen.
    """
    escort_id = int(auth["escort_id"])
    tenant_id = auth["tenant_id"]

    escort = (
        db.query(Escort)
        .filter(
            Escort.escort_id == escort_id,
            Escort.tenant_id == tenant_id,
        )
        .first()
    )

    if not escort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Escort profile not found",
                error_code="ESCORT_NOT_FOUND",
            ),
        )

    if not escort.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Your account has been deactivated. Please contact your supervisor.",
                error_code="ACCOUNT_INACTIVE",
            ),
        )

    return ResponseWrapper.success(
        data={
            "escort_id": escort.escort_id,
            "name": escort.name,
            "phone": escort.phone,
            "email": escort.email,
            "gender": escort.gender,
            "address": escort.address,
            "is_active": escort.is_active,
            "is_available": escort.is_available,
            "vendor_id": escort.vendor_id,
            "tenant_id": escort.tenant_id,
        },
        message="Profile retrieved successfully",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Change password (self-service)
# ──────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_escort_password(
    body: ChangePasswordBody,
    auth: dict = Depends(EscortAuth),
    db: Session = Depends(get_db),
):
    """
    Allow the authenticated escort to change their own password.

    - **current_password**: the escort's existing password (plain text)
    - **new_password**: the new password they want to set (plain text)

    Returns 400 if current_password is wrong.
    """
    escort_id = int(auth["escort_id"])
    tenant_id = auth["tenant_id"]

    escort = (
        db.query(Escort)
        .filter(
            Escort.escort_id == escort_id,
            Escort.tenant_id == tenant_id,
        )
        .first()
    )

    if not escort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Escort not found",
                error_code="ESCORT_NOT_FOUND",
            ),
        )

    if not escort.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Account is deactivated",
                error_code="ACCOUNT_INACTIVE",
            ),
        )

    # Verify current password
    if not verify_password(body.current_password, escort.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Current password is incorrect",
                error_code="WRONG_PASSWORD",
            ),
        )

    if len(body.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="New password must be at least 6 characters",
                error_code="PASSWORD_TOO_SHORT",
            ),
        )

    escort.password = hash_password(body.new_password)
    db.commit()

    logger.info(f"Escort {escort_id} changed their password")
    return ResponseWrapper.success(message="Password changed successfully")


@router.get("/routes")
async def get_escort_routes(
    auth: dict = Depends(EscortAuth),
    db: Session = Depends(get_db),
    route_status: Optional[str] = Query(
        None,
        alias="status",
        description=(
            "Filter by route status. "
            "Allowed: planned, vendor_assigned, driver_assigned, ongoing, completed, cancelled"
        ),
    ),
    include_completed: bool = Query(
        False,
        description="When true, completed and cancelled routes are also returned (ignored if status filter is set)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Max routes per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List routes assigned to this escort.

    Default behaviour (no filters):
      - Returns PLANNED, VENDOR_ASSIGNED, DRIVER_ASSIGNED, and ONGOING routes.
      - Set ?include_completed=true to include COMPLETED / CANCELLED routes.
      - Use ?status=ongoing to narrow to a single status.

    Response includes:
      - Route summary, shift, driver, vehicle, employee count
      - escort_otp (only visible after dispatch — null before that)
      - escort_boarded flag and a human-readable escort_status_message
    """
    escort_id = int(auth["escort_id"])
    tenant_id = auth["tenant_id"]

    query = db.query(RouteManagement).filter(
        RouteManagement.assigned_escort_id == escort_id,
        RouteManagement.tenant_id == tenant_id,
    )

    # Apply status filter
    if route_status:
        mapped = _STATUS_MAP.get(route_status.lower())
        if not mapped:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=(
                        f"Invalid status '{route_status}'. "
                        f"Allowed values: {', '.join(_STATUS_MAP.keys())}"
                    ),
                    error_code="INVALID_STATUS",
                ),
            )
        query = query.filter(RouteManagement.status == mapped)
    elif not include_completed:
        query = query.filter(
            RouteManagement.status.notin_(
                [RouteManagementStatusEnum.COMPLETED, RouteManagementStatusEnum.CANCELLED]
            )
        )

    total = query.count()
    routes = (
        query.order_by(RouteManagement.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not routes:
        return ResponseWrapper.success(
            data={"routes": [], "total": total, "limit": limit, "offset": offset},
            message="No routes found for your account",
        )

    # Batch-load related entities to avoid N+1 queries
    driver_ids = list({r.assigned_driver_id for r in routes if r.assigned_driver_id})
    vehicle_ids = list({r.assigned_vehicle_id for r in routes if r.assigned_vehicle_id})
    shift_ids = list({r.shift_id for r in routes if r.shift_id})
    route_ids = [r.route_id for r in routes]

    drivers = (
        {d.driver_id: d for d in db.query(Driver).filter(Driver.driver_id.in_(driver_ids)).all()}
        if driver_ids
        else {}
    )
    vehicles = (
        {v.vehicle_id: v for v in db.query(Vehicle).filter(Vehicle.vehicle_id.in_(vehicle_ids)).all()}
        if vehicle_ids
        else {}
    )
    shifts = (
        {s.shift_id: s for s in db.query(Shift).filter(Shift.shift_id.in_(shift_ids)).all()}
        if shift_ids
        else {}
    )

    # Count employee bookings per route in a single query
    booking_count_rows = (
        db.query(
            RouteManagementBooking.route_id,
            func.count(RouteManagementBooking.id).label("cnt"),
        )
        .filter(RouteManagementBooking.route_id.in_(route_ids))
        .group_by(RouteManagementBooking.route_id)
        .all()
    )
    booking_counts = {row.route_id: row.cnt for row in booking_count_rows}

    result = [
        _serialize_route_summary(
            route=r,
            driver=drivers.get(r.assigned_driver_id),
            vehicle=vehicles.get(r.assigned_vehicle_id),
            shift=shifts.get(r.shift_id),
            employee_count=booking_counts.get(r.route_id, 0),
        )
        for r in routes
    ]

    return ResponseWrapper.success(
        data={"routes": result, "total": total, "limit": limit, "offset": offset},
        message=f"Found {len(result)} route(s)",
    )


@router.get("/routes/{route_id}")
async def get_escort_route_detail(
    route_id: int,
    auth: dict = Depends(EscortAuth),
    db: Session = Depends(get_db),
):
    """
    Full detail of a single route assigned to this escort.

    Includes all stops (ordered by pickup sequence) with employee pickup locations,
    booking statuses, and the escort boarding OTP (if the route has been dispatched).

    Use this endpoint for the "Route Detail" screen in the escort app.
    """
    escort_id = int(auth["escort_id"])
    tenant_id = auth["tenant_id"]

    route = (
        db.query(RouteManagement)
        .filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id,
            RouteManagement.assigned_escort_id == escort_id,
        )
        .first()
    )

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Route not found or not assigned to you",
                error_code="ROUTE_NOT_FOUND",
                details={"route_id": route_id},
            ),
        )

    # Fetch related models individually (route detail is a single record, not a list)
    driver = (
        db.query(Driver).filter(Driver.driver_id == route.assigned_driver_id).first()
        if route.assigned_driver_id
        else None
    )
    vehicle = (
        db.query(Vehicle).filter(Vehicle.vehicle_id == route.assigned_vehicle_id).first()
        if route.assigned_vehicle_id
        else None
    )
    shift = (
        db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        if route.shift_id
        else None
    )

    # Fetch ordered stop list with booking details
    stop_rows = (
        db.query(RouteManagementBooking, Booking)
        .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
        .filter(RouteManagementBooking.route_id == route_id)
        .order_by(RouteManagementBooking.order_id)
        .all()
    )

    stops = [
        {
            "stop_number": rb.order_id,
            "booking_id": booking.booking_id,
            "employee_id": booking.employee_id,
            "booking_date": str(booking.booking_date) if booking.booking_date else None,
            "pickup_location": booking.pickup_location,
            "pickup_latitude": booking.pickup_latitude,
            "pickup_longitude": booking.pickup_longitude,
            "drop_location": booking.drop_location,
            "drop_latitude": booking.drop_latitude,
            "drop_longitude": booking.drop_longitude,
            "estimated_pickup_time": rb.estimated_pick_up_time,
            "actual_pickup_time": rb.actual_pick_up_time,
            "booking_status": booking.status.value if booking.status else None,
        }
        for rb, booking in stop_rows
    ]

    # Build full route detail
    route_detail = _serialize_route_summary(
        route=route,
        driver=driver,
        vehicle=vehicle,
        shift=shift,
        employee_count=len(stops),
    )
    route_detail["stops"] = stops

    return ResponseWrapper.success(
        data=route_detail,
        message="Route details retrieved successfully",
    )
