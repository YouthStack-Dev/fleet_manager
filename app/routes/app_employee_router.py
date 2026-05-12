# app/routes/app_employee_router.py
from time import timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel

from app.core.logging_config import get_logger
from app.database.session import get_db
from app.models.employee import Employee
from app.models.shift import Shift, PickupTypeEnum
from app.models.vendor import Vendor
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from common_utils import get_current_ist_time
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.booking import Booking, BookingStatusEnum
from app.models.nodal_point import EmployeeNodalPoint
from app.models.tenant import Tenant
from app.models.vehicle import Vehicle
from app.models.driver import Driver
from app.models.cutoff import Cutoff


logger = get_logger(__name__)
router = APIRouter(prefix="/employee", tags=["Employee App"])

# --------------------------- Request Models ---------------------------


# ---------------------------
# Dependencies & Utilities
# ---------------------------

def EmployeeAuth(user_data=Depends(PermissionChecker(["employee_app.read"]))):
    """
    Ensures the token belongs to an employee persona and returns (tenant_id, employee_id, user_id).
    """
    if user_data.get("user_type") != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee access only")
    tenant_id = user_data.get("tenant_id")
    employee_id = user_data.get("user_id")
    if not tenant_id or not employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee or tenant not resolved from token")
    return {"tenant_id": tenant_id, "employee_id": employee_id}


def serialize_route(db: Session, route: RouteManagement):
    """
    Explicit, non-DRY serializer for response. Feel free to extend.
    """
    # Vehicle details
    vehicle_details = None
    if route.assigned_vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == route.assigned_vehicle_id).first()
        if vehicle:
            vehicle_details = {
                "vehicle_id": vehicle.vehicle_id,
                "vehicle_number": vehicle.rc_number,
                "vehicle_type": vehicle.vehicle_type.name if vehicle.vehicle_type else None,
                "capacity": vehicle.vehicle_type.seats if vehicle.vehicle_type else None,
            }

    # Driver details
    driver_details = None
    if route.assigned_driver_id:
        driver = db.query(Driver).filter(Driver.driver_id == route.assigned_driver_id).first()
        if driver:
            driver_details = {
                "driver_id": driver.driver_id,
                "driver_name": driver.name,
                "driver_phone": driver.phone,
                "license_number": driver.license_number,
            }

    # Vendor details
    vendor_details = None
    if route.assigned_vendor_id:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == route.assigned_vendor_id).first()
        if vendor:
            vendor_details = {
                "vendor_id": vendor.vendor_id,
                "vendor_name": vendor.name,
                "vendor_code": vendor.vendor_code,
            }

    # Shift details
    shift_details = None
    if route.shift_id:
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        if shift:
            shift_details = {
                "shift_id": shift.shift_id,
                "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
                "log_type": shift.log_type.value if shift.log_type else None,
            }

    return {
        "route_id": route.route_id,
        "route_code": route.route_code,
        "status": route.status.value,
        "shift_details": shift_details,
        "vehicle_details": vehicle_details,
        "driver_details": driver_details,
        "vendor_details": vendor_details,
        "escort_required": route.escort_required,
        "estimated_total_time": route.estimated_total_time,
        "estimated_total_distance": route.estimated_total_distance,
        "actual_total_time": route.actual_total_time,
        "actual_total_distance": route.actual_total_distance,
    }


@router.get("/bookings", status_code=status.HTTP_200_OK)
async def get_employee_bookings(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Fetch bookings for the employee within the date range.
    Returns a list of bookings with route details if routed.
    """
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]

        logger.info(f"[employee.bookings] tenant={tenant_id}, employee={employee_id}, start={start_date}, end={end_date}")

        # Validate date range (e.g., max 1 month)
        if (end_date - start_date).days > 31:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Date range cannot exceed 31 days",
                    error_code="INVALID_DATE_RANGE",
                ),
            )

        bookings = (
            db.query(Booking)
            .filter(
                Booking.employee_id == employee_id,
                Booking.tenant_id == tenant_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date,
            )
            .all()
        )

        bookings_list = []
        for booking in bookings:
            # Get route_details
            route_booking = db.query(RouteManagementBooking).filter(RouteManagementBooking.booking_id == booking.booking_id).first()
            route_details = None
            if route_booking:
                route = db.query(RouteManagement).filter(RouteManagement.route_id == route_booking.route_id).first()
                if route:
                    route_details = serialize_route(db, route)

            booking_dict = {
                "tenant_id": booking.tenant_id,
                "employee_id": booking.employee_id,
                "employee_code": booking.employee_code,
                "shift_id": booking.shift_id,
                "team_id": booking.team_id,
                "booking_date": booking.booking_date.isoformat(),
                "pickup_latitude": booking.pickup_latitude,
                "pickup_longitude": booking.pickup_longitude,
                "pickup_location": booking.pickup_location,
                "drop_latitude": booking.drop_latitude,
                "drop_longitude": booking.drop_longitude,
                "drop_location": booking.drop_location,
                "status": booking.status.value,
                "booking_type": booking.booking_type.value,
                "reason": booking.reason,
                "boarding_otp": booking.boarding_otp,
                "deboarding_otp": booking.deboarding_otp,
                "is_active": True,
                "booking_id": booking.booking_id,
                "shift_time": booking.shift.shift_time.strftime("%H:%M:%S") if booking.shift and booking.shift.shift_time else None,
                "route_details": route_details,
                "created_at": booking.created_at.isoformat() if booking.created_at else None,
                "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
            }
            bookings_list.append(booking_dict)

        return ResponseWrapper.paginated(
            items=bookings_list,
            total=len(bookings_list),
            page=1,
            per_page=len(bookings_list) if bookings_list else 10,
            message="Employee bookings fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching employee bookings")
        raise handle_http_error(e)


# ──────────────────────────────────────────────────────────────
# Nodal QR Onboarding
# ──────────────────────────────────────────────────────────────

class NodalQRScanRequest(BaseModel):
    """
    Payload sent by the employee app when scanning the QR code inside the vehicle.
    The QR encodes the route_id (and optionally a verification token).
    """
    route_id: int


@router.post("/nodal/scan", status_code=status.HTTP_200_OK)
async def nodal_qr_scan(
    payload: NodalQRScanRequest,
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Employee scans the QR code inside the vehicle at the nodal point.

    Flow:
    1. Validate that the employee has a SCHEDULED booking on this route for today.
    2. Validate that the booking's shift is a Nodal pickup/drop shift.
    3. Mark the employee's booking status as ONGOING (boarded).

    The route_id is encoded in the vehicle's QR code.
    """
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]
        today = date.today()

        logger.info(
            f"[nodal.qr_scan] employee={employee_id} tenant={tenant_id} "
            f"route_id={payload.route_id}"
        )

        # ── 1. Verify route exists and is Ongoing or Driver Assigned ──
        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == payload.route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.status.in_(
                    [
                        RouteManagementStatusEnum.DRIVER_ASSIGNED,
                        RouteManagementStatusEnum.ONGOING,
                    ]
                ),
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "Route not found, not yet started, or already completed",
                    "ROUTE_NOT_FOUND",
                ),
            )

        # ── 2. Find the employee's booking linked to this route for today ──
        route_booking = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == payload.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                Booking.employee_id == employee_id,
                Booking.booking_date == today,
                Booking.status == BookingStatusEnum.SCHEDULED,
            )
            .first()
        )
        if not route_booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No scheduled booking found for you on this route today",
                    "BOOKING_NOT_FOUND",
                ),
            )

        booking = (
            db.query(Booking)
            .filter(Booking.booking_id == route_booking.booking_id)
            .first()
        )

        # ── 3. Confirm this is a Nodal shift ──
        if booking.shift_id:
            shift = db.query(Shift).filter(Shift.shift_id == booking.shift_id).first()
            if shift and shift.pickup_type != PickupTypeEnum.NODAL:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        "This booking is not for a Nodal shift. "
                        "Use the standard boarding flow.",
                        "NOT_NODAL_SHIFT",
                    ),
                )

        # ── 4. Mark booking as ONGOING (boarded) ──
        booking.status = BookingStatusEnum.ONGOING

        # ── 5. Record actual pick-up time on the route–booking link ──
        now_ist = get_current_ist_time()
        route_booking.actual_pick_up_time = now_ist.strftime("%H:%M")

        db.add_all([booking, route_booking])
        db.commit()
        db.refresh(booking)

        logger.info(
            f"[nodal.qr_scan] employee={employee_id} boarding confirmed "
            f"booking_id={booking.booking_id} route_id={payload.route_id}"
        )

        # Nodal point details for response
        nodal_info = None
        if booking.nodal_point_id and booking.nodal_point:
            np = booking.nodal_point
            nodal_info = {
                "nodal_point_id": np.nodal_point_id,
                "name": np.name,
                "address": np.address,
                "latitude": float(np.latitude),
                "longitude": float(np.longitude),
            }

        return ResponseWrapper.success(
            data={
                "booking_id": booking.booking_id,
                "status": booking.status.value,
                "route_id": payload.route_id,
                "nodal_point": nodal_info,
                "message": "You have been marked as onboarded at the nodal point.",
            },
            message="Nodal onboarding successful",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error during nodal QR scan")
        raise handle_http_error(e)


@router.get("/nodal/assignment", status_code=status.HTTP_200_OK)
async def get_my_nodal_assignment(
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Return the nodal point assigned to the currently logged-in employee.
    Used by the app to display the employee's pickup / drop hub.
    """
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]

        assignment = (
            db.query(EmployeeNodalPoint)
            .filter(EmployeeNodalPoint.employee_id == employee_id)
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No nodal point assigned to you yet. Please contact your admin.",
                    "ASSIGNMENT_NOT_FOUND",
                ),
            )

        np = assignment.nodal_point
        return ResponseWrapper.success(
            data={
                "nodal_point_id": np.nodal_point_id,
                "name": np.name,
                "address": np.address,
                "latitude": float(np.latitude),
                "longitude": float(np.longitude),
                "is_overridden": assignment.is_overridden,
            },
            message="Nodal point assignment fetched",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching employee nodal assignment")
        raise handle_http_error(e)

