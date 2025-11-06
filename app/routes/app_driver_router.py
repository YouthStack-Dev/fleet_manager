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
from app.models.booking import Booking
from app.models.tenant import Tenant
from app.models.vehicle import Vehicle
from app.models.driver import Driver
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error


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
    ctx=Depends(DriverAuth),
):
    """
    Fetch upcoming trips for the driver for today through N future days.
    Each trip includes ordered stops with employee, pickup details, and route summary.
    """
    try:
        tenant_id = ctx["tenant_id"]
        driver_id = ctx["driver_id"]
        today = date.today()
        max_date = today + timedelta(days=days_ahead)

        logger.info(f"[driver.upcoming] tenant={tenant_id}, driver={driver_id}, range={today}..{max_date}")

        # --- Get assigned routes for driver ---
        routes = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id == driver_id,
                RouteManagement.status.in_([
                    RouteManagementStatusEnum.PLANNED,
                    RouteManagementStatusEnum.ASSIGNED,
                ]),
            )
            .all()
        )

        if not routes:
            return ResponseWrapper.success(
                data={"routes": [], "count": 0},
                message="No upcoming routes assigned"
            )

        upcoming_routes = []

        for route in routes:
            # --- Fetch related route bookings ---
            rbs = (
                db.query(RouteManagementBooking)
                .filter(RouteManagementBooking.route_id == route.route_id)
                .order_by(RouteManagementBooking.order_id)
                .all()
            )

            if not rbs:
                continue

            booking_ids = [rb.booking_id for rb in rbs]

            bookings = (
                db.query(Booking)
                .filter(Booking.booking_id.in_(booking_ids))
                .all()
            )

            # join employee data
            employee_ids = [b.employee_id for b in bookings if b.employee_id]
            employees = (
                db.query(Employee.employee_id, Employee.name, Employee.phone)
                .filter(Employee.employee_id.in_(employee_ids))
                .all()
            )
            employee_map = {e.employee_id: {"name": e.name, "phone": e.phone} for e in employees}

            # --- determine earliest pickup time for sorting ---
            pickup_times = [
                rb.estimated_pick_up_time or rb.actual_pick_up_time
                for rb in rbs if rb.estimated_pick_up_time or rb.actual_pick_up_time
            ]
            if not pickup_times:
                continue
            try:
                first_pickup_time = min(
                    datetime.combine(today, datetime.strptime(t, "%H:%M").time())
                    for t in pickup_times
                )
            except Exception:
                first_pickup_time = datetime.utcnow()

            if today <= first_pickup_time.date() <= max_date:
                shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()

                # drop location is common for OUT routes
                drop_lat, drop_lng, drop_address = None, None, None
                if bookings:
                    first_booking = bookings[0]
                    drop_lat = getattr(first_booking, "drop_latitude", None)
                    drop_lng = getattr(first_booking, "drop_longitude", None)
                    drop_address = getattr(first_booking, "drop_location", None)

                # --- build ordered stops ---
                stops = []
                for rb in rbs:
                    booking = next((b for b in bookings if b.booking_id == rb.booking_id), None)
                    if not booking:
                        continue

                    emp_info = employee_map.get(booking.employee_id, {})
                    stops.append({
                        "order_id": rb.order_id,
                        "booking_id": booking.booking_id,
                        "employee_id": booking.employee_id,
                        "employee_name": emp_info.get("name"),
                        "employee_phone": emp_info.get("phone"),
                        "pickup_address": booking.pickup_location,
                        "pickup_latitude": booking.pickup_latitude,
                        "pickup_longitude": booking.pickup_longitude,
                        "estimated_pickup_time": rb.estimated_pick_up_time,
                        "actual_pickup_time": rb.actual_pick_up_time,
                    })

                upcoming_routes.append({
                    "route_id": route.route_id,
                    "route_code": route.route_code,
                    "shift_id": route.shift_id,
                    "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift else None,
                    "log_type": shift.log_type.value if shift and shift.log_type else None,
                    "status": route.status.value,
                    "start_time": first_pickup_time.strftime("%Y-%m-%d %H:%M"),
                    "drop_location": {
                        "address": drop_address,
                        "latitude": drop_lat,
                        "longitude": drop_lng,
                    },
                    "stops": stops,
                    "summary": {
                        "total_stops": len(stops),
                        "total_distance_km": route.actual_total_distance or route.estimated_total_distance or 0,
                        "total_time_minutes": route.actual_total_time or route.estimated_total_time or 0,
                    }
                })

        upcoming_routes.sort(key=lambda r: r["start_time"])

        return ResponseWrapper.success(
            data={"routes": upcoming_routes, "count": len(upcoming_routes)},
            message=f"Fetched {len(upcoming_routes)} upcoming routes"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[driver.upcoming] Unexpected error")
        return handle_db_error(e)

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
