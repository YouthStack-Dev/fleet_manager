# app/routers/app_driver_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
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





@router.get("/trips/upcoming", status_code=status.HTTP_200_OK)
async def get_upcoming_trips(
    days_ahead: int = Query(14, ge=0, le=60, description="How many future days to fetch (default 14, max 60)"),
    db: Session = Depends(get_db),
    ctx = Depends(DriverAuth),
):
    """
    Fetch upcoming trips for the driver for today through N future days.
    Returns routes with `stops` shaped exactly like the example you provided.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        today = date.today()
        max_date = today + timedelta(days=days_ahead)

        logger.info(f"[driver.upcoming] tenant={tenant_id}, driver={driver_id}, range={today}..{max_date}")

        # --- Get assigned routes for this driver (only DRIVER_ASSIGNED status) ---
        routes = (
            db.query(RouteManagement)
              .filter(
                  RouteManagement.tenant_id == tenant_id,
                  RouteManagement.assigned_driver_id == driver_id,
                  RouteManagement.status.in_([ RouteManagementStatusEnum.DRIVER_ASSIGNED ]),
              )
              .all()
        )

        if not routes:
            return ResponseWrapper.success(data={"routes": [], "count": 0}, message="No upcoming routes assigned")

        upcoming_routes = []

        for route in routes:
            # fetch RBs joined with Booking and Employee in one go to avoid N+1
            rows = (
                db.query(RouteManagementBooking, Booking, Employee)
                  .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
                  .outerjoin(Employee, Booking.employee_id == Employee.employee_id)
                  .filter(RouteManagementBooking.route_id == route.route_id)
                  .order_by(RouteManagementBooking.order_id)
                  .all()
            )

            if not rows:
                continue

            # Build stops list from joined rows
            stops = []
            pickup_datetimes = []
            for rb, booking, employee in rows:
                # booking.booking_date may be date object; format as YYYY-MM-DD
                booking_date_str = booking.booking_date.isoformat() if getattr(booking, "booking_date", None) else None

                # pickup time: prefer RB estimated_pick_up_time then actual_pick_up_time then booking.pickup_time (if any)
                est_pick = getattr(rb, "estimated_pick_up_time", None)
                act_pick = getattr(rb, "actual_pick_up_time", None)
                pick_time_str = est_pick or act_pick

                # collect a datetime for earliest pickup sorting if possible (assumes pickup times are "HH:MM")
                if pick_time_str and booking_date_str:
                    try:
                        dt = datetime.combine(
                            datetime.fromisoformat(booking_date_str).date(),
                            datetime.strptime(pick_time_str, "%H:%M").time()
                        )
                        pickup_datetimes.append(dt)
                    except Exception:
                        # ignore malformed times; we'll fall back later
                        pass

                stops.append({
                    "booking_id": booking.booking_id,
                    "tenant_id": getattr(booking, "tenant_id", tenant_id),
                    "employee_id": booking.employee_id,
                    "employee_code": getattr(employee, "employee_code", None) or getattr(booking, "employee_code", None),
                    "shift_id": getattr(booking, "shift_id", None),
                    "team_id": getattr(booking, "team_id", None),
                    "booking_date": booking_date_str,
                    "pickup_latitude": getattr(booking, "pickup_latitude", None),
                    "pickup_longitude": getattr(booking, "pickup_longitude", None),
                    "pickup_location": getattr(booking, "pickup_location", None),
                    "drop_latitude": getattr(booking, "drop_latitude", None) or getattr(booking, "drop_longitude", None) and None,
                    "drop_longitude": getattr(booking, "drop_longitude", None),
                    "drop_location": getattr(booking, "drop_location", None) or getattr(booking, "drop_location", None),
                    "status": getattr(booking, "status", None),
                    "reason": getattr(booking, "reason", None),
                    "is_active": getattr(booking, "is_active", True),
                    "created_at": getattr(booking, "created_at", None).isoformat() if getattr(booking, "created_at", None) else None,
                    "updated_at": getattr(booking, "updated_at", None).isoformat() if getattr(booking, "updated_at", None) else None,
                    "order_id": getattr(rb, "order_id", None),
                    "estimated_pick_up_time": est_pick,
                    "estimated_drop_time": getattr(rb, "estimated_drop_time", None),
                    "estimated_distance": getattr(rb, "estimated_distance", None) or getattr(booking, "estimated_distance", None),
                    "actual_pick_up_time": act_pick,
                    "actual_drop_time": getattr(rb, "actual_drop_time", None),
                    "actual_distance": getattr(rb, "actual_distance", None),
                })

            # determine earliest pickup datetime for this route
            if pickup_datetimes:
                first_pickup_dt = min(pickup_datetimes)
            else:
                # fallback — try booking.booking_date + shift.shift_time if available, else use today's midnight
                first_pickup_dt = None
                # try to derive from bookings' booking_date and shift time
                sample_booking_date = next((b.booking_date for _, b, _ in rows if getattr(b, "booking_date", None)), None)
                shift_obj = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
                if sample_booking_date and shift_obj and getattr(shift_obj, "shift_time", None):
                    try:
                        first_pickup_dt = datetime.combine(sample_booking_date, shift_obj.shift_time)
                    except Exception:
                        first_pickup_dt = None
                if not first_pickup_dt:
                    first_pickup_dt = datetime.combine(today, datetime.min.time())

            # only include routes whose first pickup falls within requested window
            if not (today <= first_pickup_dt.date() <= max_date):
                continue

            # drop location common for OUT routes (use first booking's drop fields as your example)
            first_row_booking = rows[0][1]
            drop_lat = getattr(first_row_booking, "drop_latitude", None)
            drop_lng = getattr(first_row_booking, "drop_longitude", None)
            drop_addr = getattr(first_row_booking, "drop_location", None)

            shift = shift_obj if 'shift_obj' in locals() and shift_obj else db.query(Shift).filter(Shift.shift_id == route.shift_id).first()

            upcoming_routes.append({
                "route_id": route.route_id,
                "shift_id": route.shift_id,
                "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift and getattr(shift, "shift_time", None) else None,
                "log_type": shift.log_type.value if shift and getattr(shift, "log_type", None) else None,
                "status": route.status.value if getattr(route, "status", None) else None,
                "start_time": first_pickup_dt.strftime("%Y-%m-%d %H:%M"),
                # "drop_location": {
                #     "address": drop_addr,
                #     "latitude": drop_lat,
                #     "longitude": drop_lng,
                # },
                "stops": stops,
                "summary": {
                    "total_stops": len(stops),
                    "total_distance_km": float(route.actual_total_distance or route.estimated_total_distance or 0),
                    "total_time_minutes": float(route.actual_total_time or route.estimated_total_time or 0),
                }
            })

        # sort by real datetime parsed from start_time
        upcoming_routes.sort(key=lambda r: datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M"))

        return ResponseWrapper.success(
            data={"routes": upcoming_routes, "count": len(upcoming_routes)},
            message=f"Fetched {len(upcoming_routes)} upcoming routes"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[driver.upcoming] Unexpected error")
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

        if rb.order_id != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Trip can only be started with the first stop (order_id=1)",
                    error_code="INVALID_START_ORDER",
                    details={"order_id": rb.order_id},
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

        # --- Update statuses ---
        booking.status = BookingStatusEnum.ONGOING
        route.status = RouteManagementStatusEnum.ONGOING
        route.actual_start_time = datetime.utcnow()

        db.add_all([booking, route])
        db.commit()
        db.refresh(route)

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
                "started_at": route.actual_start_time.isoformat(),
                "current_booking_id": booking.booking_id,
                "current_status": booking.status.value,
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


@router.get("/trips/today", status_code=status.HTTP_200_OK)
async def get_today_trips(
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    All of today's routes for this driver, any non-cancelled status.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        require_tenant(db, tenant_id)

        today = date.today()

        logger.info(f"[driver.today] tenant={tenant_id} driver={driver_id} date={today}")

        routes = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.booking_date == today,
                RouteManagement.status != RouteManagementStatusEnum.CANCELLED
            )
            .order_by(RouteManagement.start_time.asc().nulls_last())
            .all()
        )

        data = [serialize_route(db, r) for r in routes]
        return ResponseWrapper.success(
            data={"routes": data, "count": len(data)},
            message=f"Fetched {len(data)} routes for today"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[driver.today] Unexpected error")
        return handle_db_error(e)


@router.get("/trips/history", status_code=status.HTTP_200_OK)
async def get_trip_history(
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Completed trips, optional date range, with pagination.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        require_tenant(db, tenant_id)

        q = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status == RouteManagementStatusEnum.COMPLETED
            )
        )
        if start:
            q = q.filter(RouteManagement.booking_date >= start)
        if end:
            q = q.filter(RouteManagement.booking_date <= end)

        total = q.count()
        routes = (
            q.order_by(RouteManagement.booking_date.desc(), RouteManagement.route_id.desc())
             .offset((page - 1) * page_size)
             .limit(page_size)
             .all()
        )

        data = [serialize_route(db, r) for r in routes]
        return ResponseWrapper.success(
            data={
                "routes": data,
                "count": len(data),
                "page": page,
                "page_size": page_size,
                "total": total,
            },
            message=f"Fetched {len(data)} completed routes"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[driver.history] Unexpected error")
        return handle_db_error(e)


@router.put("/trip/{route_id}/start", status_code=status.HTTP_200_OK)
async def start_trip(
    route_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Driver marks a trip as started. Transitions:
    PLANNED/ASSIGNED -> ONGOING.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]

        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status.in_([
                    RouteManagementStatusEnum.PLANNED,
                    RouteManagementStatusEnum.ASSIGNED
                ])
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Route not found or not startable", "ROUTE_NOT_FOUND_OR_INVALID_STATE"),
            )

        route.status = RouteManagementStatusEnum.ONGOING
        # Optional: audit timestamps
        if hasattr(route, "actual_start_time"):
            route.actual_start_time = datetime.utcnow()

        db.commit()
        db.refresh(route)
        logger.info(f"[driver.start] route={route_id} driver={driver_id} -> ONGOING")

        return ResponseWrapper.success(
            data={"route_id": route.route_id, "status": route.status},
            message="Trip started"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[driver.start] Unexpected error")
        return handle_db_error(e)


@router.put("/trip/{route_id}/complete", status_code=status.HTTP_200_OK)
async def complete_trip(
    route_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(DriverAuth),
):
    """
    Driver marks a trip as completed. Transitions:
    ONGOING -> COMPLETED.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]

        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status == RouteManagementStatusEnum.ONGOING
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Route not found or not completable", "ROUTE_NOT_FOUND_OR_INVALID_STATE"),
            )

        route.status = RouteManagementStatusEnum.COMPLETED
        if hasattr(route, "actual_end_time"):
            route.actual_end_time = datetime.utcnow()

        db.commit()
        db.refresh(route)
        logger.info(f"[driver.complete] route={route_id} driver={driver_id} -> COMPLETED")

        return ResponseWrapper.success(
            data={"route_id": route.route_id, "status": route.status},
            message="Trip completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[driver.complete] Unexpected error")
        return handle_db_error(e)
