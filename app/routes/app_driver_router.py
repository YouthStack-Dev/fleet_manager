# app/routers/app_driver_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, timedelta

from app.database.session import get_db
from app.models.employee import Employee
from app.models.shift import Shift
from common_utils.auth.permission_checker import PermissionChecker
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.booking import Booking, BookingStatusEnum
from app.models.tenant import Tenant
from app.models.vehicle import Vehicle
from app.models.driver import Driver
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error


logger = get_logger(__name__)
router = APIRouter(prefix="/driver", tags=["Driver App"])

# ---------------------------
# Dependencies & Utilities
# ---------------------------

async def DriverAuth(user_data=Depends(PermissionChecker(["app-driver.read", "app-driver.write"]))):
    """
    Ensures the token belongs to a driver persona and returns (tenant_id, driver_id, user_id).
    """
    if user_data.get("user_type") != "driver":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver access only")
    tenant_id = user_data.get("tenant_id")
    driver_id = user_data.get("user_id")
    vendor_id = user_data.get("vendor_id")
    if not tenant_id or not driver_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver or tenant not resolved from token")
    return {"tenant_id": tenant_id, "driver_id": driver_id, "vendor_id": vendor_id}


def serialize_route(db: Session, route: RouteManagement):
    """
    Explicit, non-DRY serializer for response. Feel free to extend.
    """
    # Fetch bookings for the route (explicit join)
    booking_rows: List[Booking] = (
        db.query(Booking)
        .join(RouteManagementBooking, RouteManagementBooking.booking_id == Booking.booking_id)
        .filter(RouteManagementBooking.route_id == route.route_id)
        .all()
    )

    bookings_data = []
    for b in booking_rows:
        bookings_data.append({
            "booking_id": b.booking_id,
            "employee_id": getattr(b, "employee_id", None),
            "employee_name": getattr(b, "employee_name", None),
            "pickup_lat": getattr(b, "pickup_lat", None),
            "pickup_lng": getattr(b, "pickup_lng", None),
            "drop_lat": getattr(b, "drop_lat", None),
            "drop_lng": getattr(b, "drop_lng", None),
            "shift_id": b.shift_id,
            "booking_date": str(b.booking_date),
            "status": getattr(b, "status", None),
            "phone": getattr(b, "phone", None),
            "stop_seq": getattr(b, "stop_seq", None),
        })

    return {
        "route_id": route.route_id,
        "tenant_id": route.tenant_id,
        "booking_date": str(getattr(route, "booking_date", None)),
        "shift_id": getattr(route, "shift_id", None),
        "status": route.status,
        "assigned_vendor_id": getattr(route, "assigned_vendor_id", None),
        "assigned_vehicle_id": getattr(route, "assigned_vehicle_id", None),
        "assigned_driver_id": getattr(route, "assigned_driver_id", None),
        "start_time": str(getattr(route, "start_time", None)),
        "end_time": str(getattr(route, "end_time", None)),
        "stops_count": len(bookings_data),
        "bookings": bookings_data,
    }


def require_tenant(db: Session, tenant_id: str):
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message=f"Tenant {tenant_id} not found",
                error_code="TENANT_NOT_FOUND",
            ),
        )
    return tenant





from sqlalchemy import func, and_

@router.get("/trips", status_code=status.HTTP_200_OK)
async def get_driver_trips(
    status_filter: str = Query(..., regex="^(upcoming|ongoing|completed)$", description="Trip status filter"),
    booking_date: date = Query(default=date.today(), description="Filter trips by booking date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Fetch driver trips by status: upcoming | ongoing | completed.
    Filters by booking_date from the Booking table.
    Unified structure for mobile driver app.
    Derives start time from the earliest actual/estimated pickup in RouteManagementBooking.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]

        logger.info(f"[driver.trips] tenant={tenant_id}, driver={driver_id}, status={status_filter}, date={booking_date}")

        # --- Map status_filter to RouteManagementStatusEnum ---
        if status_filter == "upcoming":
            status_enum = RouteManagementStatusEnum.DRIVER_ASSIGNED
        elif status_filter == "ongoing":
            status_enum = RouteManagementStatusEnum.ONGOING
        elif status_filter == "completed":
            status_enum = RouteManagementStatusEnum.COMPLETED

        # --- Fetch all routes for the driver for the given date ---
        routes = (
            db.query(RouteManagement)
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, Booking.booking_id == RouteManagementBooking.booking_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status == status_enum,
                func.date(Booking.booking_date) == booking_date,
            )
            .group_by(RouteManagement.route_id)
            .order_by(RouteManagement.created_at.desc())
            .all()
        )

        if not routes:
            return ResponseWrapper.success(
                data={"routes": [], "count": 0},
                message=f"No {status_filter} trips found for {booking_date}",
            )

        response_routes = []

        for route in routes:
            # --- Get all bookings for the route ---
            rows = (
                db.query(RouteManagementBooking, Booking, Employee)
                .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
                .outerjoin(Employee, Booking.employee_id == Employee.employee_id)
                .filter(
                    RouteManagementBooking.route_id == route.route_id,
                    func.date(Booking.booking_date) == booking_date,
                )
                .order_by(RouteManagementBooking.order_id)
                .all()
            )

            if not rows:
                continue

            stops, pickup_datetimes = [], []

            for rb, booking, employee in rows:
                booking_date_str = booking.booking_date.isoformat()
                est_pick = getattr(rb, "estimated_pick_up_time", None)
                act_pick = getattr(rb, "actual_pick_up_time", None)
                pick_time_str = act_pick or est_pick  # prioritize actual over estimated

                if pick_time_str:
                    try:
                        dt = datetime.combine(
                            booking.booking_date,
                            datetime.strptime(pick_time_str, "%H:%M").time(),
                        )
                        pickup_datetimes.append(dt)
                    except Exception:
                        pass

                stops.append({
                    "booking_id": booking.booking_id,
                    "tenant_id": booking.tenant_id,
                    "employee_id": booking.employee_id,
                    "employee_code": getattr(employee, "employee_code", None),
                    "shift_id": booking.shift_id,
                    "team_id": booking.team_id,
                    "booking_date": booking_date_str,
                    "pickup_latitude": booking.pickup_latitude,
                    "pickup_longitude": booking.pickup_longitude,
                    "pickup_location": booking.pickup_location,
                    "drop_latitude": booking.drop_latitude,
                    "drop_longitude": booking.drop_longitude,
                    "drop_location": booking.drop_location,
                    "status": booking.status.value if booking.status else None,
                    "reason": booking.reason,
                    "is_active": getattr(booking, "is_active", True),
                    "created_at": booking.created_at.isoformat() if booking.created_at else None,
                    "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
                    "order_id": rb.order_id,
                    "estimated_pick_up_time": est_pick,
                    "estimated_drop_time": rb.estimated_drop_time,
                    "estimated_distance": rb.estimated_distance,
                    "actual_pick_up_time": act_pick,
                    "actual_drop_time": rb.actual_drop_time,
                    "actual_distance": rb.actual_distance,
                })

            # --- Derive first pickup (actual preferred, fallback to estimated) ---
            if pickup_datetimes:
                first_pickup_dt = min(pickup_datetimes)
            else:
                first_pickup_dt = datetime.combine(booking_date, datetime.min.time())

            shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()

            response_routes.append({
                "route_id": route.route_id,
                "shift_id": route.shift_id,
                "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift and shift.shift_time else None,
                "log_type": shift.log_type.value if shift and shift.log_type else None,
                "status": route.status.value,
                "start_time": first_pickup_dt.strftime("%Y-%m-%d %H:%M"),
                "stops": stops,
                "summary": {
                    "total_stops": len(stops),
                    "total_distance_km": float(route.actual_total_distance or route.estimated_total_distance or 0),
                    "total_time_minutes": float(route.actual_total_time or route.estimated_total_time or 0),
                },
            })

        # --- Sorting logic ---
        if status_filter == "upcoming":
            response_routes.sort(key=lambda r: datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M"))
        else:
            response_routes.sort(key=lambda r: r["start_time"], reverse=True)

        return ResponseWrapper.success(
            data={"routes": response_routes, "count": len(response_routes)},
            message=f"Fetched {len(response_routes)} {status_filter} routes for {booking_date}",
        )

    except HTTPException as e:
        logger.warning(f"[driver.trips] HTTP error: {e.detail}")
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("[driver.trips] Unexpected error")
        return handle_db_error(e)

@router.post("/start", status_code=status.HTTP_200_OK)
async def start_trip(
    route_id: int,
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Start the trip for the given route.
    - Verify OTP for the first booking (order_id=1)
    - Update both booking and route statuses to 'Ongoing'
    - Update actual_pick_up_time
    - Return next stop details
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]

        logger.info(f"[driver.start_trip] tenant={tenant_id}, driver={driver_id}, route={route_id}, booking={booking_id}")

        # --- Validate route ---
        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.tenant_id == tenant_id,
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found or not assigned to driver",
                    error_code="ROUTE_NOT_FOUND",
                    details={"route_id": route_id, "driver_id": driver_id},
                ),
            )

        # --- Validate booking in route ---
        rb = (
            db.query(RouteManagementBooking)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.booking_id == booking_id,
            )
            .first()
        )
        if not rb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found in this route",
                    error_code="BOOKING_NOT_FOUND_IN_ROUTE",
                    details={"route_id": route_id, "booking_id": booking_id},
                ),
            )

        # allow start from first available booking if previous ones are no-show
        previous_pending = (
            db.query(RouteManagementBooking)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.order_id < rb.order_id,
                Booking.status.notin_([BookingStatusEnum.NO_SHOW, BookingStatusEnum.ONGOING, BookingStatusEnum.COMPLETED]),
            )
            .count()
        )

        if previous_pending > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot start from this stop. Previous pickups still pending.",
                    error_code="PREVIOUS_PENDING_STOPS",
                    details={"pending_count": previous_pending},
                ),
            )


        # --- Validate booking object ---
        booking = (
            db.query(Booking)
            .filter(
                Booking.booking_id == booking_id,
                Booking.tenant_id == tenant_id,
            )
            .first()
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found for this tenant",
                    error_code="BOOKING_NOT_FOUND",
                    details={"booking_id": booking_id, "tenant_id": tenant_id},
                ),
            )

        # --- Verify OTP ---
        if str(booking.OTP).strip() != str(otp).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Invalid OTP",
                    error_code="INVALID_OTP",
                    details={"booking_id": booking_id},
                ),
            )

        # --- Update statuses + timestamps ---
        now = datetime.utcnow()
        booking.status = BookingStatusEnum.ONGOING
        route.status = RouteManagementStatusEnum.ONGOING
        rb.actual_pick_up_time = now.strftime("%H:%M")

        db.add_all([booking, route, rb])
        db.commit()
        db.refresh(route)

        logger.info(
            f"[driver.start_trip] Trip started: route={route_id}, booking={booking_id}, "
            f"actual_pick_up_time={rb.actual_pick_up_time}"
        )

        # --- Fetch next stop (order_id = 2) ---
        next_rb = (
            db.query(RouteManagementBooking)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.order_id == rb.order_id + 1,
            )
            .first()
        )

        next_stop = None
        if next_rb:
            booking_next = db.query(Booking).filter(Booking.booking_id == next_rb.booking_id).first()
            if booking_next:
                next_stop = {
                    "booking_id": booking_next.booking_id,
                    "employee_id": booking_next.employee_id,
                    "pickup_latitude": booking_next.pickup_latitude,
                    "pickup_longitude": booking_next.pickup_longitude,
                    "pickup_location": booking_next.pickup_location,
                    "estimated_pickup_time": next_rb.estimated_pick_up_time,
                }

        return ResponseWrapper.success(
            message="Trip started successfully",
            data={
                "route_id": route.route_id,
                "route_status": route.status.value,
                "started_at": rb.actual_pick_up_time,
                "current_booking_id": booking.booking_id,
                "current_status": booking.status.value,
                "actual_pick_up_time": rb.actual_pick_up_time,
                "next_stop": next_stop,
            },
        )

    except HTTPException as e:
        logger.warning(f"[driver.start_trip] HTTP error: {e.detail}")
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("[driver.start_trip] Unexpected error")
        db.rollback()
        return ResponseWrapper.error(message=str(e))

@router.put("/trip/no-show", status_code=status.HTTP_200_OK)
async def mark_no_show(
    route_id: int,
    booking_id: int,
    reason: Optional[str] = Query(None, description="Reason for marking as no-show"),
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Mark a booking as NO_SHOW when employee did not board.
    - Allowed only if route is assigned to the driver.
    - Updates booking.status = NO_SHOW.
    - Updates route.status = ONGOING if it wasn’t already.
    - If route has only one booking → auto-complete route.
    - Otherwise, only mark route COMPLETED if all DROPS are completed.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        now = datetime.utcnow()

        logger.info(f"[driver.no_show] tenant={tenant_id}, driver={driver_id}, route={route_id}, booking={booking_id}")

        # --- Validate route ---
        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.tenant_id == tenant_id,
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found or not assigned to driver",
                    error_code="ROUTE_NOT_FOUND",
                    details={"route_id": route_id, "driver_id": driver_id},
                ),
            )

        # --- Validate route-booking association ---
        rb = (
            db.query(RouteManagementBooking)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.booking_id == booking_id,
            )
            .first()
        )
        if not rb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not associated with this route",
                    error_code="BOOKING_NOT_FOUND_IN_ROUTE",
                    details={"route_id": route_id, "booking_id": booking_id},
                ),
            )

        # --- Validate booking object ---
        booking = (
            db.query(Booking)
            .filter(
                Booking.booking_id == booking_id,
                Booking.tenant_id == tenant_id,
            )
            .first()
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found for this tenant",
                    error_code="BOOKING_NOT_FOUND",
                    details={"booking_id": booking_id, "tenant_id": tenant_id},
                ),
            )

        # --- Prevent marking ongoing or completed bookings as no-show ---
        if booking.status in [BookingStatusEnum.ONGOING, BookingStatusEnum.COMPLETED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot mark no-show for an active or completed booking",
                    error_code="INVALID_BOOKING_STATE",
                    details={"booking_status": booking.status.value},
                ),
            )

        # --- Allow marking current booking as no-show only if all previous stops are done ---
        previous_pending = (
            db.query(RouteManagementBooking)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.order_id < rb.order_id,
                Booking.status.notin_([BookingStatusEnum.NO_SHOW, BookingStatusEnum.ONGOING, BookingStatusEnum.COMPLETED]),
            )
            .count()
        )
        if previous_pending > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot mark no-show. Previous stops are still pending.",
                    error_code="PREVIOUS_PENDING_STOPS",
                    details={"pending_count": previous_pending},
                ),
            )

        # --- Update booking as NO_SHOW ---
        booking.status = BookingStatusEnum.NO_SHOW
        booking.reason = reason or "Employee did not board"
        booking.updated_at = now
        rb.actual_pick_up_time = now.strftime("%H:%M")

        # --- If route not ongoing yet, set it ---
        if route.status != RouteManagementStatusEnum.ONGOING:
            route.status = RouteManagementStatusEnum.ONGOING
            route.updated_at = now

        db.add_all([booking, rb, route])
        db.commit()

        logger.info(
            f"[driver.no_show] Booking {booking_id} marked NO_SHOW; route={route_id}, driver={driver_id}"
        )

        # --- Count total bookings & completed drops ---
        total_bookings = (
            db.query(Booking)
            .join(RouteManagementBooking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(RouteManagementBooking.route_id == route_id)
            .count()
        )
        completed_drops = (
            db.query(Booking)
            .join(RouteManagementBooking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                Booking.status == BookingStatusEnum.COMPLETED,
            )
            .count()
        )

        route_completed = False

        # ✅ Case 1: If route has only one booking → auto-complete immediately
        if total_bookings == 1:
            route.status = RouteManagementStatusEnum.COMPLETED
            route.updated_at = now
            if hasattr(route, "actual_end_time"):
                setattr(route, "actual_end_time", now)
            db.commit()
            route_completed = True
            logger.info(f"[driver.no_show] Single-booking route {route_id} marked COMPLETED after no-show")

        # ✅ Case 2: If all drops are completed → mark route completed
        elif total_bookings > 1 and completed_drops == total_bookings:
            route.status = RouteManagementStatusEnum.COMPLETED
            route.updated_at = now
            if hasattr(route, "actual_end_time"):
                setattr(route, "actual_end_time", now)
            db.commit()
            route_completed = True
            logger.info(f"[driver.no_show] Route {route_id} marked COMPLETED — all drops done.")

        # --- Get next stop ---
        next_rb = (
            db.query(RouteManagementBooking)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.order_id > rb.order_id,
                Booking.status.notin_([BookingStatusEnum.NO_SHOW, BookingStatusEnum.COMPLETED]),
            )
            .order_by(RouteManagementBooking.order_id)
            .first()
        )

        next_stop = None
        if next_rb:
            booking_next = db.query(Booking).filter(Booking.booking_id == next_rb.booking_id).first()
            if booking_next:
                next_stop = {
                    "booking_id": booking_next.booking_id,
                    "employee_id": booking_next.employee_id,
                    "pickup_latitude": booking_next.pickup_latitude,
                    "pickup_longitude": booking_next.pickup_longitude,
                    "pickup_location": booking_next.pickup_location,
                    "estimated_pickup_time": next_rb.estimated_pick_up_time,
                }

        return ResponseWrapper.success(
            message="Booking marked as no-show successfully"
            if not route_completed
            else "Booking marked as no-show; route closed as completed",
            data={
                "route_id": route.route_id,
                "route_status": route.status.value,
                "booking_id": booking.booking_id,
                "booking_status": booking.status.value,
                "actual_pick_up_time": rb.actual_pick_up_time,
                "next_stop": next_stop,
                "route_completed": route_completed,
            },
        )

    except HTTPException as e:
        logger.warning(f"[driver.no_show] HTTP error: {e.detail}")
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("[driver.no_show] Unexpected error")
        db.rollback()
        return ResponseWrapper.error(message=str(e))

@router.put("/trip/drop", status_code=status.HTTP_200_OK)
async def verify_drop_and_complete_route(
    route_id: int,
    booking_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Driver confirms drop for a booking.
    - Marks booking as COMPLETED and sets actual_drop_time.
    - If all other bookings are NO_SHOW or COMPLETED, auto-completes the route.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        now = datetime.utcnow()

        logger.info(f"[driver.drop] tenant={tenant_id}, driver={driver_id}, route={route_id}, booking={booking_id}")

        # --- Validate route ---
        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status == RouteManagementStatusEnum.ONGOING,
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found or not in ongoing state",
                    error_code="ROUTE_NOT_FOUND_OR_INVALID_STATE",
                    details={"route_id": route_id, "driver_id": driver_id},
                ),
            )

        # --- Validate route-booking association ---
        rb = (
            db.query(RouteManagementBooking)
            .filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.booking_id == booking_id,
            )
            .first()
        )
        if not rb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not associated with this route",
                    error_code="BOOKING_NOT_FOUND_IN_ROUTE",
                ),
            )

        # --- Fetch booking ---
        booking = (
            db.query(Booking)
            .filter(
                Booking.booking_id == booking_id,
                Booking.tenant_id == tenant_id,
            )
            .first()
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found", "BOOKING_NOT_FOUND"),
            )

        # --- Prevent re-marking if already dropped ---
        if booking.status == BookingStatusEnum.COMPLETED:
            return ResponseWrapper.success(
                message="Booking already marked as completed",
                data={
                    "route_id": route_id,
                    "booking_id": booking_id,
                    "status": booking.status.value,
                    "actual_drop_time": rb.actual_drop_time,
                },
            )

        # --- Mark booking as completed ---
        booking.status = BookingStatusEnum.COMPLETED
        booking.updated_at = now
        rb.actual_drop_time = now.strftime("%H:%M")

        db.add_all([booking, rb])
        db.commit()

        logger.info(f"[driver.drop] Booking {booking_id} marked as completed by driver {driver_id}")

        # --- Check if route should be completed ---
        total_bookings = (
            db.query(Booking)
            .join(RouteManagementBooking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(RouteManagementBooking.route_id == route_id)
            .count()
        )

        # Bookings still pending (neither completed nor no-show)
        pending = (
            db.query(Booking)
            .join(RouteManagementBooking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagementBooking.route_id == route_id,
                Booking.status.notin_([BookingStatusEnum.COMPLETED, BookingStatusEnum.NO_SHOW]),
            )
            .count()
        )

        # --- Auto-complete route if all bookings are done or no-shows ---
        route_completed = False
        if total_bookings > 0 and pending == 0:
            route.status = RouteManagementStatusEnum.COMPLETED
            route.updated_at = now
            if hasattr(route, "actual_end_time"):
                setattr(route, "actual_end_time", now)
            db.commit()
            route_completed = True
            logger.info(f"[driver.drop] Auto-completed route_id={route_id} (all drops done or no-shows)")

        return ResponseWrapper.success(
            message="Drop verified successfully" if not route_completed else "Drop verified and trip auto-completed",
            data={
                "route_id": route.route_id,
                "booking_id": booking.booking_id,
                "booking_status": booking.status.value,
                "actual_drop_time": rb.actual_drop_time,
                "route_status": route.status.value,
                "route_completed": route_completed,
            },
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(f"[driver.drop] HTTP error: {e.detail}")
        raise handle_http_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("[driver.drop] Unexpected error")
        return handle_db_error(e)
