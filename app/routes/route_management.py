import random as random
from fastapi import APIRouter, Depends, HTTPException, Path, Query ,status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import date , datetime, time
from enum import Enum

from app.database.session import get_db
from app.models.booking import Booking, BookingStatusEnum
from app.models.driver import Driver
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift  # Add shift model import
from app.models.tenant import Tenant  # Add tenant model import
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.schemas.route import RouteWithEstimations, RouteEstimations, RouteManagementBookingResponse  # Add import for response schema
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger, setup_logging
from app.utils.response_utils import ResponseWrapper, handle_db_error

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel

from app.schemas.shift import ShiftResponse
from app.services.geodesic import group_rides

# Configure logging immediately at module level
setup_logging(
    log_level="DEBUG",
    force_configure=True,
    use_colors=True
)

# Create module logger with explicit name
logger = get_logger("route_management")

# Test logger immediately
logger.info("🚀 Route Management module initialized")
logger.debug("📝 Debug logging is active")

router = APIRouter(
    prefix="/routes",
    tags=["route-management"]
)

class RequestItem(BaseModel):
    booking_ids: List[int]  # Changed from bookings to booking_ids

class CreateRoutesRequest(BaseModel):
    groups: List[RequestItem]

class MergeRoutesRequest(BaseModel):
    route_ids: List[int]  # Already int, no change needed

class SplitRouteRequest(BaseModel):
    groups: List[RequestItem]  # Changed from List[str] to List[int] for booking IDs

class RouteOperationEnum(str, Enum):
    ADD = "add"
    REMOVE = "remove"

class UpdateRouteRequest(BaseModel):
    operation: RouteOperationEnum  # Add operation field
    booking_ids: List[int]  # Changed from bookings to booking_ids for consistency

class RouteUpdate(BaseModel):
    booking_id: int
    new_order_id: int
    estimated_pickup_time: str
    estimated_drop_time: str

class UpdateBookingOrderRequest(BaseModel):
    bookings: List[RouteUpdate]  # Each dict contains booking_id, new_order, estimated_pickup_time, estimated_drop_time

def get_bookings_by_ids(booking_ids: List[int], db: Session) -> List[Dict]:
    """
    Retrieve bookings by their IDs and convert to dictionary format.
    Adds detailed logs for traceability.
    """
    logger.info(f"[get_bookings_by_ids] Raw booking_ids input: {booking_ids}")

    if not booking_ids:
        logger.warning("[get_bookings_by_ids] Empty booking_ids list received.")
        return []

    # ---- Flatten nested IDs if needed ----
    if isinstance(booking_ids[0], (tuple, list)):
        flat_booking_ids = []
        for item in booking_ids:
            if isinstance(item, (tuple, list)):
                flat_booking_ids.extend(
                    [int(x) for x in item if isinstance(x, (int, str)) and str(x).isdigit()]
                )
            else:
                flat_booking_ids.append(int(item))
        booking_ids = flat_booking_ids
        logger.debug(f"[get_bookings_by_ids] Flattened booking_ids: {booking_ids}")

    # ---- Normalize all IDs to integers ----
    booking_ids = [
        int(bid) for bid in booking_ids if isinstance(bid, (int, str)) and str(bid).isdigit()
    ]

    if not booking_ids:
        logger.warning("[get_bookings_by_ids] No valid integer booking_ids after cleanup.")
        raise HTTPException(status_code=400, detail="No valid booking IDs provided.")

    logger.info(f"[get_bookings_by_ids] Final booking_ids to query: {booking_ids}")

    # ---- Query bookings ----
    bookings = db.query(Booking).filter(Booking.booking_id.in_(booking_ids)).all()
    logger.info(f"[get_bookings_by_ids] Retrieved {len(bookings)} bookings from DB")

    # ---- Log detailed booking info ----
    for b in bookings:
        logger.debug(
            f"[get_bookings_by_ids] Booking fetched → "
            f"id={b.booking_id}, tenant={b.tenant_id}, shift={b.shift_id}, date={b.booking_date}, "
            f"employee={b.employee_code or b.employee_id}, status={b.status.name if b.status else None}"
        )

    # ---- Convert to dictionaries ----
    bookings_dicts = [
        {
            "booking_id": booking.booking_id,
            "tenant_id": booking.tenant_id,
            "employee_id": booking.employee_id,
            "employee_code": booking.employee_code,
            "shift_id": booking.shift_id,
            "team_id": booking.team_id,
            "booking_date": booking.booking_date,
            "pickup_latitude": booking.pickup_latitude,
            "pickup_longitude": booking.pickup_longitude,
            "pickup_location": booking.pickup_location,
            "drop_latitude": booking.drop_latitude,
            "drop_longitude": booking.drop_longitude,
            "drop_location": booking.drop_location,
            "status": booking.status.value if booking.status else None,
            "reason": booking.reason,
            "is_active": getattr(booking, 'is_active', True),
            "created_at": booking.created_at,
            "updated_at": booking.updated_at
        }
        for booking in bookings
    ]

    if not bookings_dicts:
        logger.warning(f"[get_bookings_by_ids] No matching bookings found for IDs {booking_ids}")

    return bookings_dicts

def get_booking_by_id(booking_id: int, db: Session) -> Optional[Dict]:
    """
    Retrieve a single booking by its ID and convert to dictionary format.
    """
    booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not booking:
        logger.warning(f"[get_booking_by_id] No booking found with ID {booking_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Booking not found.",
                error_code="BOOKING_NOT_FOUND",
            )
        )

    logger.debug(
        f"[get_booking_by_id] Booking fetched → "
        f"id={booking.booking_id}, tenant={booking.tenant_id}, shift={booking.shift_id}, date={booking.booking_date}, "
        f"employee={booking.employee_code or booking.employee_id}, status={booking.status.name if booking.status else None}"
    )

    booking_dict = {
        "booking_id": booking.booking_id,
        "tenant_id": booking.tenant_id,
        "employee_id": booking.employee_id,
        "employee_code": booking.employee_code,
        "shift_id": booking.shift_id,
        "team_id": booking.team_id,
        "booking_date": booking.booking_date,
        "pickup_latitude": booking.pickup_latitude,
        "pickup_longitude": booking.pickup_longitude,
        "pickup_location": booking.pickup_location,
        "drop_latitude": booking.drop_latitude,
        "drop_longitude": booking.drop_longitude,
        "drop_location": booking.drop_location,
        "status": booking.status.value if booking.status else None,
        "reason": booking.reason,
        "is_active": getattr(booking, 'is_active', True),
        "created_at": booking.created_at,
        "updated_at": booking.updated_at
    }

    return booking_dict


def datetime_to_minutes(dt_val):
    """
    Convert datetime/time string or object to minutes from midnight
    """
    # If already datetime or time object
    if isinstance(dt_val, datetime):
        return dt_val.hour * 60 + dt_val.minute
    
    if isinstance(dt_val, time):
        return dt_val.hour * 60 + dt_val.minute

    # Else assume it's string
    if isinstance(dt_val, str):
        dt = datetime.fromisoformat(dt_val)
        return dt.hour * 60 + dt.minute

    raise TypeError(f"Unsupported type for datetime_to_minutes: {type(dt_val)}")

@router.post("/" , status_code=status.HTTP_200_OK)
async def create_routes(
    booking_date: date = Query(..., description="Date for the bookings (YYYY-MM-DD)"),
    shift_id: int = Query(..., description="Shift ID to filter bookings"),
    radius: float = Query(1.0, description="Radius in km for clustering"),
    group_size: int = Query(2, description="Number of route clusters to generate"),
    strict_grouping: bool = Query(False, description="Whether to enforce strict grouping by group size or not"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID for multi-tenant setups"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Generate route clusters (suggestions) for a given shift and date.
    Only includes bookings NOT already assigned to any route.
    """
    try:
        logger.info(
            f"Clustering request for date={booking_date}, shift={shift_id}, user={user_data.get('user_id', 'unknown')}"
        )

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Tenant Resolution ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        # ---- Validate Shift ----
        shift = (
            db.query(Shift)
            .filter(Shift.shift_id == shift_id, Shift.tenant_id == tenant_id)
            .first()
        )

        if not shift:
            logger.warning(f"Shift not found: {shift_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found or doesn't belong to this tenant",
                    error_code="SHIFT_NOT_FOUND_OR_UNAUTHORIZED"
                ),
            )

        # ---- Determine Coordinate Columns ----
        shift_type = shift.log_type or "Unknown"
        lat_col = "pickup_latitude" if shift_type == "IN" else "drop_latitude"
        lon_col = "pickup_longitude" if shift_type == "IN" else "drop_longitude"
        
        # ---- Fetch Already Routed Booking IDs ----
        routed_booking_ids = (
            db.query(RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagement.route_id == RouteManagementBooking.route_id)
            .filter(RouteManagement.tenant_id == tenant_id)
            .distinct()
            .all()
        )
        routed_booking_ids = [b.booking_id for b in routed_booking_ids]

        # ---- Fetch Only Unrouted Bookings ----
        bookings_query = db.query(Booking).filter(
            Booking.booking_date == booking_date,
            Booking.shift_id == shift_id,
            Booking.tenant_id == tenant_id,
            Booking.status == BookingStatusEnum.REQUEST
        )
        if routed_booking_ids:
            bookings_query = bookings_query.filter(~Booking.booking_id.in_(routed_booking_ids))

        bookings = bookings_query.all()

        if not bookings:
            logger.info(f"No unrouted bookings found for tenant={tenant_id}, shift={shift_id} on {booking_date}")
            return ResponseWrapper.success(
                data={"clusters": [], "total_bookings": 0, "total_clusters": 0},
                message=f"No unrouted bookings found for shift {shift_id} on {booking_date}"
            )

        # ---- Prepare Rides for Clustering ----
        rides = []
        for booking in bookings:
            ride = {
                "lat": getattr(booking, lat_col),
                "lon": getattr(booking, lon_col),
            }
            ride.update(booking.__dict__)
            rides.append(ride)

        valid_rides = [r for r in rides if r["lat"] is not None and r["lon"] is not None]

        if not valid_rides:
            logger.warning(f"No valid coordinates found for {len(bookings)} unrouted bookings")
            return ResponseWrapper.success(
                data={"clusters": [], "total_bookings": len(bookings), "total_clusters": 0},
                message="No bookings with valid coordinates found for clustering"
            )

        # ---- Generate Clusters ----
        clusters = group_rides(valid_rides, radius, group_size, strict_grouping)

        cluster_data = []
        for idx, cluster in enumerate(clusters, start=1):
            for booking in cluster:
                booking.pop("lat", None)
                booking.pop("lon", None)
            cluster_data.append({"cluster_id": idx, "bookings": cluster})

        logger.info(f"Generated {len(cluster_data)} clusters from {len(bookings)} unrouted bookings")

        # ---- Generate optimal route for each cluster ----
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        for cluster in cluster_data:
            if shift_type == "IN":
                optimized_route = generate_optimal_route(
                    deadline_minutes=540,
                    shift_time=shift.shift_time,
                    group=cluster["bookings"],
                    drop_lat=cluster["bookings"][-1]["drop_latitude"],
                    drop_lng=cluster["bookings"][-1]["drop_longitude"],
                    drop_address=cluster["bookings"][-1]["drop_location"]
                )
            else:
                optimized_route = generate_drop_route(
                    group=cluster["bookings"],
                    start_time_minutes=datetime_to_minutes(shift.shift_time),
                    office_lat=cluster["bookings"][0]["pickup_latitude"],
                    office_lng=cluster["bookings"][0]["pickup_longitude"],
                    office_address=cluster["bookings"][0]["pickup_location"]
                )

            # Save the optimized route to the database
            if optimized_route:
                try:
                    route = RouteManagement(
                        tenant_id=tenant_id,
                        shift_id=shift_id,
                        route_code=f"Route-{cluster['cluster_id']}",
                        estimated_total_time=optimized_route[0]["estimated_time"].split()[0],
                        estimated_total_distance=optimized_route[0]["estimated_distance"].split()[0],
                        buffer_time=float(optimized_route[0]["buffer_time"].split()[0]),
                        status="PLANNED",
                    )
                    db.add(route)
                    db.flush()  # Get the route_id

                    for idx, booking in enumerate(optimized_route[0]["pickup_order"]):
                        otp_code = random.randint(1000, 9999)
                        route_booking = RouteManagementBooking(
                            route_id=route.route_id,
                            booking_id=booking["booking_id"],
                            order_id=idx + 1,
                            estimated_pick_up_time=booking["estimated_pickup_time_formatted"],
                            estimated_distance=booking["estimated_distance_km"],
                        )
                        db.add(route_booking)

                        # Update booking status to SCHEDULED (only if still in REQUEST)
                        db.query(Booking).filter(
                            Booking.booking_id == booking["booking_id"],
                            Booking.status == BookingStatusEnum.REQUEST
                        ).update(
                            {
                                Booking.status: BookingStatusEnum.SCHEDULED,
                                Booking.OTP:otp_code,
                                Booking.updated_at: func.now(),
                            },
                            synchronize_session=False
                        )

                    db.commit()

                    db.commit()
                except SQLAlchemyError as e:
                    db.rollback()
                    logger.error(f"Failed to save route to database: {e}")
                    continue

                cluster["optimized_route"] = optimized_route

        # ---- Final Response ----
        shift_response = ShiftResponse.model_validate(shift, from_attributes=True)
        return ResponseWrapper.success(
            data={
                "shift": shift_response,
                "clusters": cluster_data,
                "total_bookings": len(bookings),
                "total_clusters": len(clusters),
            },
            message="Successfully generated route suggestions for unrouted bookings"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating route suggestions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error generating route suggestions",
                error_code="ROUTE_SUGGESTION_ERROR",
                details={"error": str(e)},
            ),
        )

@router.get("/", status_code=status.HTTP_200_OK)
async def get_all_routes(
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: Optional[int] = Query(None, description="Filter by shift ID"),
    booking_date: Optional[date] = Query(None, description="Filter by booking date"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get all active routes with their details, optionally filtered by shift and booking date.
    """

    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        logger.info(
            f"[get_all_routes] user={user_data.get('user_id')} "
            f"user_type={user_type}, query_tenant={tenant_id}, token_tenant={token_tenant_id}"
        )

        # ---------- Tenant Resolution ----------
        if user_type == "employee":
            # Employees always locked to their tenant
            tenant_id = token_tenant_id

        elif user_type == "admin":
            if token_tenant_id:
                # Normal admin with tenant in token
                tenant_id = token_tenant_id
            else:
                # SuperAdmin must provide tenant_id explicitly
                if not tenant_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message="tenant_id is required for admin users",
                            error_code="TENANT_ID_REQUIRED",
                        ),
                    )
                # tenant_id from query param stays

        else:
            # fallback
            tenant_id = token_tenant_id

        # final safety check
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        # ---------- Vendor-Specific Access Control ----------
        vendor_id = user_data.get("vendor_id")
        if user_type == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_MISSING",
                    ),
                )

            # Vendor can only see their own routes
            logger.info(f"[get_all_routes] Restricting to vendor_id={vendor_id}")


        logger.info(f"[get_all_routes] resolved tenant: {tenant_id}")

        # ---------- Validate Tenant ----------
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )
        logger.info(f"Fetching all routes for tenant: {tenant_id}, shift_id: {shift_id}, booking_date: {booking_date}, user: {user_data.get('user_id', 'unknown')}")
        


        # --- Query routes ---
        routes_q = db.query(RouteManagement).filter(RouteManagement.tenant_id == tenant_id)

        if user_type == "vendor":
            logger.info(f"[get_all_routes] Applying vendor filter: {vendor_id}")
            routes_q = routes_q.filter(RouteManagement.assigned_vendor_id == vendor_id)


        if shift_id or booking_date:
            routes_q = (
                routes_q
                .join(RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id)
                .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            )
            if shift_id:
                routes_q = routes_q.filter(Booking.shift_id == shift_id)
            if booking_date:
                routes_q = routes_q.filter(Booking.booking_date == booking_date)

        routes = routes_q.distinct().all()

        if not routes:
            return ResponseWrapper.success(
                {"shifts": [], "total_shifts": 0, "total_routes": 0},
                "No routes found"
            )

        # --- Collect IDs ---
        driver_ids = {r.assigned_driver_id for r in routes if r.assigned_driver_id}
        vehicle_ids = {r.assigned_vehicle_id for r in routes if r.assigned_vehicle_id}
        vendor_ids = {r.assigned_vendor_id for r in routes if r.assigned_vendor_id}

        # --- Bulk Load related data ---
        drivers = (
            db.query(Driver.driver_id, Driver.name, Driver.phone)
            .filter(Driver.driver_id.in_(driver_ids))
            .all() if driver_ids else []
        )
        vehicles = (
            db.query(Vehicle.vehicle_id, Vehicle.rc_number)
            .filter(Vehicle.vehicle_id.in_(vehicle_ids))
            .all() if vehicle_ids else []
        )
        vendors = (
            db.query(Vendor.vendor_id, Vendor.name)
            .filter(Vendor.vendor_id.in_(vendor_ids))
            .all() if vendor_ids else []
        )

        driver_map = {d.driver_id: {"id": d.driver_id, "name": d.name, "phone": d.phone} for d in drivers}
        vehicle_map = {v.vehicle_id: {"id": v.vehicle_id, "rc_number": v.rc_number} for v in vehicles}
        vendor_map = {v.vendor_id: {"id": v.vendor_id, "name": v.name} for v in vendors}

        shifts = {}

        for route in routes:
            rbs = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route.route_id
            ).order_by(RouteManagementBooking.order_id).all()

            booking_ids = [rb.booking_id for rb in rbs]
            bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

            stops = []
            for rb in rbs:
                b = next((x for x in bookings if x["booking_id"] == rb.booking_id), None)
                if not b: continue

                stops.append({
                    **b,
                    "order_id": rb.order_id,
                    "estimated_pick_up_time": rb.estimated_pick_up_time,
                    "estimated_drop_time": rb.estimated_drop_time,
                    "estimated_distance": rb.estimated_distance,
                    "actual_pick_up_time": rb.actual_pick_up_time,
                    "actual_drop_time": rb.actual_drop_time,
                    "actual_distance": rb.actual_distance,
                })

            shift_id_key = route.shift_id
            if shift_id_key not in shifts:
                s = db.query(Shift).filter(Shift.shift_id == shift_id_key).first()
                if s:
                    shifts[shift_id_key] = {
                        "shift_id": s.shift_id,
                        "log_type": s.log_type.value,
                        "shift_time": s.shift_time.strftime("%H:%M:%S"),
                        "routes": []
                    }

            shifts[shift_id_key]["routes"].append({
                "route_id": route.route_id,
                "route_code": route.route_code,
                "status": route.status.value,
                "driver": driver_map.get(route.assigned_driver_id),
                "vehicle": vehicle_map.get(route.assigned_vehicle_id),
                "vendor": vendor_map.get(route.assigned_vendor_id),
                "stops": stops,
                "summary": {
                    "total_distance_km": route.actual_total_distance or route.estimated_total_distance or 0,
                    "total_time_minutes": route.actual_total_time or route.estimated_total_time or 0,
                },
            })

        shifts_list = list(shifts.values())

        return ResponseWrapper.success(
            {
                "shifts": shifts_list,
                "total_shifts": len(shifts_list),
                "total_routes": sum(len(s["routes"]) for s in shifts_list)
            },
            "Routes fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.get("/unrouted", status_code=status.HTTP_200_OK)
async def get_unrouted_bookings(
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: int = Query(..., description="Filter by shift ID"),
    booking_date: date = Query(..., description="Filter by booking date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get all bookings for a specific shift and date that are NOT assigned to any route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Tenant Resolution ----
        if user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        elif user_type != "admin":
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        logger.info(f"[unrouted_bookings] Effective tenant resolved: {tenant_id}")

        # ---- Validate tenant exists ----
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        logger.info(
            f"Fetching unrouted bookings for tenant {tenant_id}, shift_id: {shift_id}, booking_date: {booking_date}"
        )

        # ---- Get all booking_ids that are already mapped in any route ----
        routed_booking_ids = (
            db.query(RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagement.route_id == RouteManagementBooking.route_id)
            .filter(
                RouteManagement.tenant_id == tenant_id
            )
            .distinct()
            .all()
        )

        routed_booking_ids = [b.booking_id for b in routed_booking_ids]

        # ---- Fetch bookings NOT IN routed list ----
        unrouted_bookings = (
            db.query(Booking)
            .filter(
                Booking.tenant_id == tenant_id,
                Booking.shift_id == shift_id,
                Booking.booking_date == booking_date,
                Booking.status == BookingStatusEnum.REQUEST,
                ~Booking.booking_id.in_(routed_booking_ids) if routed_booking_ids else True,
            )
            .all()
        )

        if not unrouted_bookings:
            logger.info(f"No unrouted bookings found for tenant {tenant_id}, shift {shift_id} on {booking_date}")
            return ResponseWrapper.success(
                data={"bookings": [], "total_unrouted": 0},
                message=f"No unrouted bookings found for tenant {tenant_id}, shift {shift_id}, date {booking_date}",
            )

        bookings_data = get_bookings_by_ids([b.booking_id for b in unrouted_bookings], db)

        logger.info(f"Found {len(bookings_data)} unrouted bookings for tenant {tenant_id}")

        return ResponseWrapper.success(
            data={
                "bookings": bookings_data,
                "total_unrouted": len(bookings_data)
            },
            message=f"Successfully retrieved {len(bookings_data)} unrouted bookings for shift {shift_id} on {booking_date}"
        )

    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.put("/assign-vendor", status_code=status.HTTP_200_OK)
async def assign_vendor_to_route(
    route_id: int = Query(..., description="Route ID"),
    vendor_id: int = Query(..., description="Vendor ID to assign"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True))
):
    """
    Assign a vendor to a specific route.
    Ensures both the route and vendor belong to the same tenant.
    """
    try:

        user_id = user_data.get("user_id")
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        logger.info(f"[assign_vendor_to_route] User={user_id} | Tenant={tenant_id} | Route={route_id} | Vendor={vendor_id}")

        # ---- Validate route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found for this tenant",
                    error_code="ROUTE_NOT_FOUND",
                    details={"route_id": route_id, "tenant_id": tenant_id},
                ),
            )

        # ---- Validate vendor belongs to the same tenant ----
        vendor = (
            db.query(Vendor)
            .filter(Vendor.vendor_id == vendor_id, Vendor.tenant_id == tenant_id)
            .first()
        )
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Vendor not found under this tenant",
                    error_code="VENDOR_NOT_FOUND_OR_MISMATCH",
                    details={"vendor_id": vendor_id, "tenant_id": tenant_id},
                ),
            )

        # ---- Assign vendor ----
        route.assigned_vendor_id = vendor_id

        if route.status == RouteManagementStatusEnum.PLANNED:
            route.status = RouteManagementStatusEnum.VENDOR_ASSIGNED

        db.commit()
        db.refresh(route)

        logger.info(
            f"[assign_vendor_to_route] Vendor={vendor_id} assigned successfully to Route={route_id} (Tenant={tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "route_id": route_id,
                "assigned_vendor_id": vendor_id,
                "status": route.status,
            },
            message="Vendor assigned successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[assign_vendor_to_route] Unexpected error")
        raise handle_db_error(e)

@router.put("/assign-vehicle", status_code=status.HTTP_200_OK)
async def assign_vehicle_to_route(
    route_id: int = Query(..., description="Route ID"),
    vehicle_id: int = Query(..., description="Vehicle ID to assign"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
):
    """
    Assign a vehicle (and implicitly driver) to a route.

    Validation:
      - Vendor must be assigned to route before assigning a vehicle.
      - Route and Vehicle must belong to the same tenant.
      - Vehicle.vendor_id must match Route.assigned_vendor_id.
      - Vehicle must have a mapped driver.
      - Driver.vendor_id must match Route.assigned_vendor_id.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(
            f"[assign_vehicle_to_route] User={user_id} | Tenant={tenant_id} | Route={route_id} | Vehicle={vehicle_id}"
        )

        # ---- Validate Route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .with_for_update()
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found for this tenant",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        # ✅ Enforce vendor assignment first
        if not route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Assign a vendor to the route before assigning a vehicle/driver",
                    error_code="VENDOR_NOT_ASSIGNED",
                    details={"route_id": route_id},
                ),
            )
        # ---- Vendor-level access validation ----
        user_vendor_id = user_data.get("vendor_id")  # Comes from token if vendor persona
        if user_vendor_id:
            # Ensure vendor trying to assign belongs to the same route
            if route.assigned_vendor_id != int(user_vendor_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You can only assign vehicles to routes owned by your vendor",
                        error_code="VENDOR_ROUTE_MISMATCH",
                        details={
                            "user_vendor_id": user_vendor_id,
                            "route_vendor_id": route.assigned_vendor_id,
                        },
                    ),
                )

        # ---- Validate Vehicle ----
        vehicle = (
            db.query(Vehicle)
            .join(Vendor, Vendor.vendor_id == Vehicle.vendor_id)
            .filter(Vehicle.vehicle_id == vehicle_id, Vendor.tenant_id == tenant_id)
            .with_for_update()
            .first()
        )
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Vehicle not found under this tenant",
                    error_code="VEHICLE_NOT_FOUND",
                    details={"vehicle_id": vehicle_id, "tenant_id": tenant_id},
                ),
            )

        # ✅ Vehicle’s vendor must match route’s vendor
        if vehicle.vendor_id != route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Vehicle vendor does not match the vendor assigned to the route",
                    error_code="ROUTE_VEHICLE_VENDOR_MISMATCH",
                    details={
                        "route_vendor_id": route.assigned_vendor_id,
                        "vehicle_vendor_id": vehicle.vendor_id,
                    },
                ),
            )

        # ---- Resolve Driver from Vehicle ----
        driver = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .filter(
                Driver.driver_id == vehicle.driver_id,
                Driver.vendor_id == vehicle.vendor_id,
                Vendor.tenant_id == tenant_id,
            )
            .first()
        )
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message="No driver mapped to this vehicle",
                    error_code="DRIVER_NOT_LINKED_TO_VEHICLE",
                    details={"vehicle_id": vehicle.vehicle_id},
                ),
            )

        # ✅ Driver’s vendor must match route’s vendor too
        if driver.vendor_id != route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Driver vendor mismatch with route vendor",
                    error_code="DRIVER_VENDOR_MISMATCH",
                    details={
                        "route_vendor_id": route.assigned_vendor_id,
                        "driver_vendor_id": driver.vendor_id,
                    },
                ),
            )

        # --- Normalize gender (optional safeguard) ---
        if hasattr(driver, "gender") and driver.gender:
            valid_enums = {"MALE", "FEMALE", "OTHER"}
            if driver.gender.upper() not in valid_enums:
                driver.gender = driver.gender.upper()

        # ---- Apply assignment ----
        route.assigned_vehicle_id = vehicle.vehicle_id
        route.assigned_driver_id = driver.driver_id

        # Progress status only if vendor already assigned
        if route.status == RouteManagementStatusEnum.VENDOR_ASSIGNED:
            route.status = RouteManagementStatusEnum.DRIVER_ASSIGNED

        db.commit()
        db.refresh(route)

        logger.info(
            f"[assign_vehicle_to_route] Vehicle={vehicle_id} (Driver={driver.driver_id}) assigned to Route={route_id} (Tenant={tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "route_id": route.route_id,
                "assigned_vendor_id": route.assigned_vendor_id,
                "assigned_vehicle_id": route.assigned_vehicle_id,
                "assigned_driver_id": route.assigned_driver_id,
                "status": route.status.value,
            },
            message="Vehicle and driver assigned successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[assign_vehicle_to_route] Unexpected error")
        raise handle_db_error(e)


@router.get("/{route_id}")
async def get_route_by_id(
    route_id: int,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get details of a specific route by its ID.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if token_tenant_id:
                tenant_id = token_tenant_id  # normal admin with tenant scope
            else:
                if not tenant_id:  # superadmin case, must pass tenant
                    raise HTTPException(
                        status_code=400,
                        detail=ResponseWrapper.error(
                            message="tenant_id is required for admin users",
                            error_code="TENANT_ID_REQUIRED",
                        ),
                    )
        else:
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                )
            )

        logger.info(f"[get_route_by_id] tenant={tenant_id}, route_id={route_id}")

        # Validate tenant exists
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND"
                )
            )

        # Fetch route
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error("Route not found", "ROUTE_NOT_FOUND")
            )
        # ✅ Restrict vendor access to only their own routes
        vendor_id = user_data.get("vendor_id")
        if user_type == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_MISSING",
                    ),
                )

            if route.assigned_vendor_id != int(vendor_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You are not authorized to access this route",
                        error_code="ROUTE_ACCESS_DENIED",
                        details={
                            "requested_route_vendor": route.assigned_vendor_id,
                            "your_vendor_id": vendor_id,
                        },
                    ),
                )


        # Get bookings
        rbs = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.order_id).all()

        booking_ids = [rb.booking_id for rb in rbs]
        bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

        # ---- Fetch Driver / Vehicle / Vendor ----
        driver = None
        vehicle = None
        vendor = None

        if route.assigned_driver_id:
            driver = db.query(Driver.driver_id, Driver.name, Driver.phone).filter(
                Driver.driver_id == route.assigned_driver_id
            ).first()

        if route.assigned_vehicle_id:
            vehicle = db.query(Vehicle.vehicle_id, Vehicle.rc_number).filter(
                Vehicle.vehicle_id == route.assigned_vehicle_id
            ).first()

        if route.assigned_vendor_id:
            vendor = db.query(Vendor.vendor_id, Vendor.name).filter(
                Vendor.vendor_id == route.assigned_vendor_id
            ).first()

        # Build stops list
        stops = []
        for rb in rbs:
            b = next((x for x in bookings if x["booking_id"] == rb.booking_id), None)
            if not b: 
                continue

            stops.append({
                **b,
                "order_id": rb.order_id,
                "estimated_pick_up_time": rb.estimated_pick_up_time,
                "estimated_drop_time": rb.estimated_drop_time,
                "estimated_distance": rb.estimated_distance,
                "actual_pick_up_time": rb.actual_pick_up_time,
                "actual_drop_time": rb.actual_drop_time,
                "actual_distance": rb.actual_distance,
            })

        # Same response structure as list API ✅
        response = {
            "route_id": route.route_id,
            "shift_id": route.shift_id,
            "route_code": route.route_code,
            "status": route.status.value,
            "driver": {"id": driver.driver_id, "name": driver.name, "phone": driver.phone} if driver else None,
            "vehicle": {"id": vehicle.vehicle_id, "rc_number": vehicle.rc_number} if vehicle else None,
            "vendor": {"id": vendor.vendor_id, "name": vendor.name} if vendor else None,
            "stops": stops,
            "summary": {
                "total_distance_km": route.actual_total_distance or route.estimated_total_distance or 0,
                "total_time_minutes": route.actual_total_time or route.estimated_total_time or 0
            }
        }

        return ResponseWrapper.success(response, "Route fetched successfully")

    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.post("/merge")
async def merge_routes(
    request: MergeRoutesRequest,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Merge multiple routes into a single optimized route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[MERGE] tenant={tenant_id}, user={user_id}, route_ids={request.route_ids}")

        if not request.route_ids:
            raise HTTPException(
                400,
                ResponseWrapper.error("No route ids provided", "NO_ROUTE_IDS")
            )

        # --- Load routes & collect bookings ---
        routes = db.query(RouteManagement).filter(
            RouteManagement.route_id.in_(request.route_ids),
            RouteManagement.tenant_id == tenant_id
        ).all()

        if not routes:
            raise HTTPException(
                404,
                ResponseWrapper.error("Routes not found", "ROUTE_NOT_FOUND")
            )

        all_booking_ids = []
        shift_id = None

        for r in routes:
            if shift_id and r.shift_id != shift_id:
                raise HTTPException(
                    400,
                    ResponseWrapper.error(
                        "All routes must belong to same shift",
                        "SHIFT_MISMATCH"
                    )
                )
            shift_id = r.shift_id

            rbs = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == r.route_id
            ).all()

            all_booking_ids.extend([b.booking_id for b in rbs])

        all_booking_ids = list(dict.fromkeys(all_booking_ids))  # unique preserve order

        if not all_booking_ids:
            raise HTTPException(
                400,
                ResponseWrapper.error("No bookings in selected routes", "EMPTY_ROUTE_LIST")
            )

        # --- Pull full booking objects ---
        bookings = get_bookings_by_ids(all_booking_ids, db)

        shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
        if not shift:
            raise HTTPException(
                404, ResponseWrapper.error("Shift not found", "SHIFT_NOT_FOUND")
            )

        # --- Which route generation to call? ---
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        shift_type = shift.log_type.value if hasattr(shift.log_type, "value") else shift.log_type

        if shift_type == "IN":
            optimized = generate_optimal_route(
                shift_time=shift.shift_time,
                group=bookings,
                drop_lat=bookings[-1]["drop_latitude"],
                drop_lng=bookings[-1]["drop_longitude"],
                drop_address=bookings[-1]["drop_location"]
            )
        else:
            optimized = generate_drop_route(
                group=bookings,
                start_time_minutes=datetime_to_minutes(shift.shift_time),
                office_lat=bookings[0]["pickup_latitude"],
                office_lng=bookings[0]["pickup_longitude"],
                office_address=bookings[0]["pickup_location"]
            )

        if not optimized:
            raise HTTPException(
                500,
                ResponseWrapper.error("Route optimization failed", "OPT_FAIL")
            )

        optimized = optimized[0]  # first candidate

        # --- Create new route ---
        route = RouteManagement(
            tenant_id=tenant_id,
            shift_id=shift_id,
            # route_code=f"M-{tenant_id}-{shift_id}",
            estimated_total_time=float(optimized["estimated_time"].split()[0]),
            estimated_total_distance=float(optimized["estimated_distance"].split()[0]),
            buffer_time=float(optimized["buffer_time"].split()[0]),
            status="PLANNED"
        )

        db.add(route)
        db.flush()

        # --- Insert stops ---
        for idx, b in enumerate(optimized["pickup_order"]):
            db.add(RouteManagementBooking(
                route_id=route.route_id,
                booking_id=b["booking_id"],
                order_id=idx + 1,
                estimated_pick_up_time=b["estimated_pickup_time_formatted"],
                estimated_distance=b["estimated_distance_km"]
            ))

        # ---- Delete old routes ----
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id.in_(request.route_ids)
        ).delete(synchronize_session=False)

        db.query(RouteManagement).filter(
            RouteManagement.route_id.in_(request.route_ids)
        ).delete(synchronize_session=False)

        db.commit()

        return ResponseWrapper.success(
            {"route_id": route.route_id},
            f"Merged routes into {route.route_id}"
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[MERGE ROUTES] Error: {e}", exc_info=True)
        raise HTTPException(
            500,
            ResponseWrapper.error("Error merging routes", "ROUTE_MERGE_ERROR", {"error": str(e)})
        )


@router.put("/{route_id}")
async def update_route(
    route_id: int,
    request: UpdateRouteRequest,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
):
    """
    Update a route by adding or removing bookings, then regenerate the optimal route.
    """
    try:
        logger.debug(f"UpdateRouteRequest received: {request}")
        logger.debug(f"User data: {user_data}")
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        if user_type == "employee":
            tenant_id = token_tenant_id

        elif user_type == "vendor":
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for vendor users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        elif user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"Updating route {route_id} with operation '{request.operation}' for {len(request.booking_ids)} bookings, user: {user_data.get('user_id', 'unknown')}")

        # Validate tenant exists
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                    details={"tenant_id": tenant_id}
                )
            )
    
        if not request.booking_ids:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No booking IDs provided for update",
                    error_code="NO_BOOKINGS_PROVIDED",
                )
            )

        logger.info(f"Fetching route {route_id} for tenant {tenant_id}")
        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        logger.debug(f"Fetched route: {route}")
        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                )
            )

        # Fetch current bookings in the route
        current_rbs = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        logger.debug(f"Current route bookings: {current_rbs}")

        current_booking_ids = {rb.booking_id for rb in current_rbs}
        request_booking_ids = set(request.booking_ids)  
        logger.debug(f"Current booking IDs: {current_booking_ids}, Requested booking IDs: {request_booking_ids}")

        request_bookings = []
        for booking in request_booking_ids:
            booking_details = get_booking_by_id(booking, db)
            request_bookings.append(booking_details)

        # --- Remove booking from any other active route before adding ---
        if request.operation == "add":
            for booking_id in request_booking_ids:
                existing_links = db.query(RouteManagementBooking).join(RouteManagement).filter(
                    RouteManagementBooking.booking_id == booking_id,
                    RouteManagementBooking.route_id != route_id,
                    RouteManagement.tenant_id == tenant_id
                ).all()

                for link in existing_links:
                    logger.info(
                        f"Removing booking {booking_id} from route {link.route_id} "
                        f"because it is being moved to route {route_id}"
                    )
                    db.delete(link)

            db.flush()  # ensure removal is persisted before adding in new route

        
        logger.debug(f"Fetched request bookings: {request_bookings}")
        
        # figure out the shift type
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        shift_type = shift.log_type.value if hasattr(shift.log_type, "value") else shift.log_type
        logger.debug(f"Shift type for route {route_id} is {shift_type}")

        all_booking_ids = []
        if request.operation == "add":
            all_booking_ids = list(current_booking_ids.union(request_booking_ids))
        else:
            all_booking_ids = list(current_booking_ids.difference(request_booking_ids))
        logger.debug(f"All booking IDs after '{request.operation}': {all_booking_ids}")

        all_bookings = []
        for booking_id in all_booking_ids:
            booking_details = get_booking_by_id(booking_id, db)
            all_bookings.append(booking_details)

        # generate route based on shift type
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route
        if shift_type == "IN":
            optimized = generate_optimal_route(
                shift_time=shift.shift_time,
                group=all_bookings,
                drop_lat=all_bookings[-1]["drop_latitude"],
                drop_lng=all_bookings[-1]["drop_longitude"],
                drop_address=all_bookings[-1]["drop_location"]
            )
        else:
            optimized = generate_drop_route(
                group=all_bookings,
                start_time_minutes=datetime_to_minutes(shift.shift_time),
                office_lat=all_bookings[0]["pickup_latitude"],
                office_lng=all_bookings[0]["pickup_longitude"],
                office_address=all_bookings[0]["pickup_location"]
            )
        logger.debug(f"Optimized route data: {optimized}")
        
        # now we generated routes, lets update our route and route_bookings
        optimized = optimized[0]  # first candidate
        route.estimated_total_time = float(optimized["estimated_time"].split()[0])
        route.estimated_total_distance = float(optimized["estimated_distance"].split()[0])
        route.buffer_time = float(optimized["buffer_time"].split()[0])
        # calculate the estimations to return
        estimations = {
            "start_time": str(optimized.get("start_time", "")),
            "total_distance_km": optimized.get("estimated_distance", "0"),
            "total_time_minutes": optimized.get("total_route_duration", "0")
        }


        # --- Safely replace stops without deleting the route row (avoid StaleDataError) ---
        # Delete existing route-booking mappings for this route_id
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).delete(synchronize_session=False)

        # Add new route-booking mappings based on optimized pickup_order
        for idx, b in enumerate(optimized["pickup_order"]):
            db.add(RouteManagementBooking(
                route_id=route.route_id,
                booking_id=b["booking_id"],
                order_id=idx + 1,
                estimated_pick_up_time=b.get("estimated_pickup_time_formatted"),
                estimated_distance=b.get("estimated_distance_km"),
                estimated_drop_time=b.get("estimated_drop_time_formatted"),
            ))

        # Commit once so both route updates and new mappings are persisted together
        db.commit()

        logger.info(f"Route {route_id} updated successfully with {len(all_booking_ids)} bookings")

        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=route_id,
                bookings=all_bookings,
                estimations=estimations
            ),
            message=f"Route {route_id} updated successfully"
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating route {route_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error updating route",
                error_code="ROUTE_UPDATE_ERROR",
                details={"error": str(e)},
            ),
        )

@router.put("/{route_id}/update-booking-order", status_code=status.HTTP_200_OK)
async def update_booking_order(
    route_id: int,
    request: UpdateBookingOrderRequest,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
):
    """
    Update booking order manually.
    User may send only 1 booking with new_order_id.
    This endpoint recalculates order for ALL bookings in the route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # --- Tenant Resolution ---
        if user_type == "employee" or user_type == "vendor":
            tenant_id = token_tenant_id
            
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                400,
                ResponseWrapper.error(
                    "tenant_id is required for admin users", "TENANT_ID_REQUIRED"
                )
            )

        if not tenant_id:
            raise HTTPException(
                403,
                ResponseWrapper.error("Tenant context not available", "TENANT_ID_MISSING")
            )

        # --- Load route + shift ---
        result = (
            db.query(RouteManagement, Shift)
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .join(Shift, Shift.shift_id == Booking.shift_id)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )

        if not result:
            raise HTTPException(404, ResponseWrapper.error("Route not found", "ROUTE_NOT_FOUND"))

        route, shift = result
        shift_type = shift.log_type.value if hasattr(shift.log_type, "value") else shift.log_type
        shift_time = shift.shift_time

        # --- Step 1: Fetch ALL current bookings in this route ---
        current_links = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.order_id.asc()).all()

        if not current_links:
            raise HTTPException(
                400,
                ResponseWrapper.error("No bookings found in route", "EMPTY_ROUTE")
            )

        current_booking_ids = [c.booking_id for c in current_links]

        # --- Step 2: Convert request list into a lookup dictionary ---
        incoming_changes = {b.booking_id: b.new_order_id for b in request.bookings}

        # --- Step 3: Assign temporary order ids ---
        # If frontend didn't send a booking → keep its old order
        enriched = []
        for current in current_links:
            enriched.append({
                "booking_id": current.booking_id,
                "new_order_id": incoming_changes.get(current.booking_id, current.order_id)
            })

        # --- Step 4: Sort by new_order_id (full list reordered) ---
        enriched = sorted(enriched, key=lambda x: x["new_order_id"])

        # --- Step 5: Fetch full booking objects in the new order ---
        full_bookings = [get_booking_by_id(item["booking_id"], db) for item in enriched]

        # --- Step 6: Call optimizer ---
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        if shift_type == "IN":
            optimized = generate_optimal_route(
                shift_time=shift_time,
                group=full_bookings,
                drop_lat=full_bookings[-1]["drop_latitude"],
                drop_lng=full_bookings[-1]["drop_longitude"],
                drop_address=full_bookings[-1]["drop_location"],
                use_centroid=False
            )
        else:
            optimized = generate_drop_route(
                group=full_bookings,
                start_time_minutes=datetime_to_minutes(shift_time),
                office_lat=full_bookings[0]["pickup_latitude"],
                office_lng=full_bookings[0]["pickup_longitude"],
                office_address=full_bookings[0]["pickup_location"],
                optimize_route="false"
            )

        if not optimized:
            raise HTTPException(500, ResponseWrapper.error("Route optimization failed", "OPT_FAIL"))

        optimized = optimized[0]

        # --- Step 7: Update route metrics ---
        route.estimated_total_time = float(optimized["estimated_time"].split()[0])
        route.estimated_total_distance = float(optimized["estimated_distance"].split()[0])
        route.buffer_time = float(optimized["buffer_time"].split()[0])

        # --- Step 8: Replace mapping ---
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).delete(synchronize_session=False)

        new_links = []
        for idx, stop in enumerate(optimized["pickup_order"]):
            new_links.append(
                RouteManagementBooking(
                    route_id=route_id,
                    booking_id=stop["booking_id"],
                    order_id=idx + 1,
                    estimated_pick_up_time=stop["estimated_pickup_time_formatted"],
                    estimated_drop_time=stop.get("estimated_drop_time_formatted"),
                    estimated_distance=stop["estimated_distance_km"],
                )
            )

        db.add_all(new_links)
        db.commit()

        # --- Step 9: Prepare response ---
        response = [
            {
                "booking_id": link.booking_id,
                "order_id": link.order_id,
                "estimated_pick_up_time": link.estimated_pick_up_time,
                "estimated_drop_time": link.estimated_drop_time,
                "estimated_distance": link.estimated_distance,
            }
            for link in new_links
        ]

        return ResponseWrapper.success(response, f"Route {route_id} booking order updated")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update booking order error: {e}", exc_info=True)
        raise HTTPException(
            500,
            ResponseWrapper.error("Unexpected error", "UPDATE_BOOKING_ORDER_ERROR", {"error": str(e)})
        )

@router.delete("/bulk")
async def bulk_delete_routes(
    shift_id: int = Query(..., description="Shift ID"),
    route_date: date = Query(..., description="Booking date (YYYY-MM-DD)"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True)),
):
    """
    Permanently delete all routes and their associated route-booking records
    for a given shift and date, and revert bookings back to 'REQUEST'.
    """
    try:
        logger.info("==== BULK ROUTE HARD DELETE INITIATED ====")
        logger.info(f"Received request | shift_id={shift_id}, route_date={route_date}, tenant_query={tenant_id}")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        # --- Validate Tenant ---
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        logger.info(f"Hard deleting routes for tenant={tenant_id}, shift={shift_id}, date={route_date}")

        # --- Fetch route IDs ---
        route_query = (
            db.query(RouteManagement.route_id)
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                Booking.shift_id == shift_id,
                Booking.booking_date == route_date,
            )
            .distinct()
        )

        route_ids = [r.route_id for r in route_query.all()]
        logger.info(f"Found {len(route_ids)} routes for hard deletion")

        if not route_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"No routes found for shift {shift_id} on {route_date}",
                    error_code="ROUTES_NOT_FOUND",
                ),
            )


        # --- Fetch affected booking IDs ---
        booking_ids = [
            b.booking_id
            for b in db.query(RouteManagementBooking.booking_id)
            .filter(RouteManagementBooking.route_id.in_(route_ids))
            .distinct()
            .all()
        ]

        # --- Delete child route-booking links ---
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )

        # --- Revert booking statuses ---
        if booking_ids:
            db.query(Booking).filter(
                Booking.booking_id.in_(booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED,
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.OTP: None,
                    Booking.updated_at: func.now(),
                    Booking.reason: "Route deleted - reverted to request",
                },
                synchronize_session=False,
            )

        # --- Hard delete routes ---
        deleted_routes_count = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )

        db.commit()

        logger.info(
            f"✅ Hard deleted {deleted_routes_count} routes, {deleted_bookings_count} mappings, reverted {len(booking_ids)} bookings."
        )

        return ResponseWrapper.success(
            data={
                "deleted_route_ids": route_ids,
                "deleted_routes_count": deleted_routes_count,
                "deleted_bookings_count": deleted_bookings_count,
            },
            message=f"Successfully deleted {deleted_routes_count} routes and related records for shift {shift_id} on {route_date}",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error during bulk hard delete | tenant_id={tenant_id}, shift_id={shift_id}, date={route_date}, user_id={user_id}, error={e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Error while deleting routes",
                error_code="BULK_ROUTE_DELETE_ERROR",
                details={
                    "tenant_id": tenant_id,
                    "shift_id": shift_id,
                    "date": str(route_date),
                    "error": str(e),
                },
            ),
        )


@router.delete("/{route_id}")
async def delete_route(
    route_id: int,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True)),
):
    """
    Permanently delete a route and all its associated route-booking links,
    reverting affected bookings back to 'REQUEST'.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")

        # ---- Determine tenant context ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[delete_route] User={user_id} | Tenant={tenant_id} | Route={route_id}")

        # ---- Validate tenant ----
        tenant_exists = (
            db.query(Tenant.tenant_id)
            .filter(Tenant.tenant_id == tenant_id)
            .first()
        )
        if not tenant_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # ---- Fetch route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )

        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found for tenant {tenant_id}",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )


        # --- Get linked bookings ---
        booking_ids = [
            b.booking_id
            for b in db.query(RouteManagementBooking.booking_id)
            .filter(RouteManagementBooking.route_id == route_id)
            .distinct()
            .all()
        ]

        # --- Delete route-booking mappings ---
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .delete(synchronize_session=False)
        )

        # --- Revert bookings ---
        if booking_ids:
            db.query(Booking).filter(
                Booking.booking_id.in_(booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED,
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.OTP: None,
                    Booking.updated_at: func.now(),
                    Booking.reason: "Route deleted - reverted to request",
                },
                synchronize_session=False,
            )

        # --- Delete route itself ---
        db.delete(route)
        db.commit()

        logger.info(
            f"✅ Route {route_id} deleted. {len(booking_ids)} bookings reverted to REQUEST."
        )

        return ResponseWrapper.success(
            data={
                "deleted_route_id": route_id,
                "reverted_bookings_count": len(booking_ids),
            },
            message=f"Route {route_id} deleted successfully, reverted {len(booking_ids)} bookings to REQUEST",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[delete_route] Unexpected error deleting route {route_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Error deleting route {route_id}",
                error_code="ROUTE_DELETE_ERROR",
                details={"error": str(e)},
            ),
        )


