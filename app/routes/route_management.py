from fastapi import APIRouter, Depends, HTTPException, Path, Query ,status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import date , datetime
from enum import Enum
import time

from app.database.session import get_db
from app.models.booking import Booking
from app.models.driver import Driver
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift  # Add shift model import
from app.models.tenant import Tenant  # Add tenant model import
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.schemas.route import RouteWithEstimations, RouteEstimations, RouteManagementBookingResponse  # Add import for response schema
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel

from app.schemas.shift import ShiftResponse
from app.services.geodesic import group_rides

logger = get_logger(__name__)

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
        return []

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

def calculate_route_estimations(bookings: List[Dict], shift_type: str = "OUT") -> RouteEstimations:
    """
    Calculate route estimations including distance, time, and pickup/drop times.
    """
    # Simple estimation logic - replace with actual calculation
    total_distance = len(bookings) * 5.0  # 5km per booking as example
    total_time = len(bookings) * 15.0     # 15 minutes per booking as example
    
    estimated_pickup_times = {}
    estimated_drop_times = {}
    
    base_time = 480  # 8:00 AM in minutes
    for i, booking in enumerate(bookings):
        pickup_time = base_time + (i * 15)
        drop_time = pickup_time + 10
        
        estimated_pickup_times[booking["booking_id"]] = f"{pickup_time//60:02d}:{pickup_time%60:02d}"
        estimated_drop_times[booking["booking_id"]] = f"{drop_time//60:02d}:{drop_time%60:02d}"
    
    return RouteEstimations(
        total_distance_km=total_distance,
        total_time_minutes=total_time,
        estimated_pickup_times=estimated_pickup_times,
        estimated_drop_times=estimated_drop_times
    )

def save_route_to_db(booking_ids: List[int], estimations: RouteEstimations, tenant_id: str, db: Session) -> RouteManagement:
    """
    Save route and its bookings to database.
    """
    import uuid
    # Create route - let route_id auto-increment
    route = RouteManagement(
        tenant_id=tenant_id,
        route_code=f"ROUTE-{str(uuid.uuid4())}",  # Use timestamp for unique code
        total_distance_km=estimations.total_distance_km,
        total_time_minutes=estimations.total_time_minutes
    )
    db.add(route)
    db.flush()  # This will populate the auto-generated route_id
    
    # Create route bookings
    for i, booking_id in enumerate(booking_ids):
        route_booking = RouteManagementBooking(
            route_id=route.route_id,  # Use the auto-generated route_id
            booking_id=booking_id,
            stop_order=i + 1,
            estimated_pickup_time=estimations.estimated_pickup_times.get(booking_id),
            estimated_drop_time=estimations.estimated_drop_times.get(booking_id),
            distance_from_previous=5.0 if i > 0 else 0.0,
            cumulative_distance=(i + 1) * 5.0
        )
        db.add(route_booking)
    
    db.commit()
    return route

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
                        buffer_time=optimized_route[0]["buffer_time"].split()[0],
                        status="PLANNED",
                    )
                    db.add(route)
                    db.flush()  # Get the route_id

                    for idx, booking in enumerate(optimized_route[0]["pickup_order"]):
                        route_booking = RouteManagementBooking(
                            route_id=route.route_id,
                            booking_id=booking["booking_id"],
                            order_id=idx + 1,
                            estimated_pick_up_time=booking["estimated_pickup_time_formatted"],
                            estimated_distance=booking["estimated_distance_km"],
                        )
                        db.add(route_booking)

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
        

        
        # Base query for routes
        if shift_id or booking_date:
            routes_query = (
                db.query(RouteManagement)
                .join(RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id)
                .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
                .filter(RouteManagement.tenant_id == tenant_id)
                .distinct()
            )

            if shift_id:
                routes_query = routes_query.filter(Booking.shift_id == shift_id)
            if booking_date:
                routes_query = routes_query.filter(Booking.booking_date == booking_date)
        else:
            routes_query = db.query(RouteManagement).filter(RouteManagement.tenant_id == tenant_id)

        routes = routes_query.all()

        if not routes:
            return ResponseWrapper.success(
                data={"shifts": [], "total_shifts": 0, "total_routes": 0},
                message=f"No active routes found for tenant {tenant_id}"
                       f"{f' shift {shift_id}' if shift_id else ''}"
                       f"{f' date {booking_date}' if booking_date else ''}",
            )

        # ---------- Group Routes by Shift ----------
        shifts_data = {}

        for route in routes:
            route_bookings = (
                db.query(RouteManagementBooking)
                .filter(RouteManagementBooking.route_id == route.route_id)
                .order_by(RouteManagementBooking.order_id)
                .all()
            )

            booking_ids = [rb.booking_id for rb in route_bookings]
            bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

            for booking in bookings:
                sid = booking["shift_id"]
                if sid and sid not in shifts_data:
                    shift = db.query(Shift).filter(Shift.shift_id == sid).first()
                    if shift:
                        shifts_data[sid] = {
                            "shift_id": shift.shift_id,
                            "log_type": shift.log_type.value if shift.log_type else None,
                            "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
                            "routes": [],
                        }

            estimations = RouteEstimations(
                total_distance_km=(
                    route.actual_total_distance 
                    or route.estimated_total_distance 
                    or 0.0
                ),
                total_time_minutes=(
                    route.actual_total_time 
                    or route.estimated_total_time 
                    or 0.0
                ),
                estimated_pickup_times={
                    rb.booking_id: rb.estimated_pick_up_time
                    for rb in route_bookings if rb.estimated_pick_up_time
                },
                estimated_drop_times={
                    rb.booking_id: rb.estimated_drop_time
                    for rb in route_bookings if rb.estimated_drop_time
                },
            )


            stops = []
            for rb in route_bookings:
                booking = next((b for b in bookings if b["booking_id"] == rb.booking_id), None)
                if not booking:
                    continue
                
                stops.append({
                    "order_id": rb.order_id,
                    "booking_id": rb.booking_id,
                    "employee_name": booking.get("employee_name"),
                    "pickup_location": booking.get("pickup_location"),
                    "pickup_latitude": booking.get("pickup_latitude"),
                    "pickup_longitude": booking.get("pickup_longitude"),
                    "drop_location": booking.get("drop_location"),
                    "drop_latitude": booking.get("drop_latitude"),
                    "drop_longitude": booking.get("drop_longitude"),

                    "estimated_pick_up_time": rb.estimated_pick_up_time,
                    "estimated_drop_time": rb.estimated_drop_time,
                    "estimated_distance": rb.estimated_distance,

                    "actual_pick_up_time": rb.actual_pick_up_time,
                    "actual_drop_time": rb.actual_drop_time,
                    "actual_distance": rb.actual_distance,
                })
                
            route_response = {
                "route_id": route.route_id,
                "shift_id": route.shift_id,
                "route_code": route.route_code,
                "status": route.status.value if hasattr(route.status, "value") else route.status,

                "stops": stops,
                "summary": {
                    "total_distance_km": (
                        route.actual_total_distance or route.estimated_total_distance or 0.0
                    ),
                    "total_time_minutes": (
                        route.actual_total_time or route.estimated_total_time or 0.0
                    ),
                }
            }

            for booking in bookings:
                sid = booking["shift_id"]
                if sid in shifts_data and not any(r["route_id"] == route.route_id for r in shifts_data[sid]["routes"]):
                    shifts_data[sid]["routes"].append(route_response)
                    break

        shifts_list = list(shifts_data.values())
        total_routes = sum(len(s["routes"]) for s in shifts_list)

        logger.info(f"[get_all_routes] {len(shifts_list)} shifts, {total_routes} routes")

        return ResponseWrapper.success(
            data={
                "shifts": shifts_list,
                "total_shifts": len(shifts_list),
                "total_routes": total_routes,
            },
            message=f"Successfully retrieved {len(shifts_list)} shifts with {total_routes} routes",
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
            route.status = RouteManagementStatusEnum.ASSIGNED

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
    Assign a vehicle to a specific route.

    Validation:
      - Route and Vehicle must belong to the same tenant.
      - Vehicle.vendor_id must match Route.assigned_vendor_id.
      - If route has no vendor, assign from the vehicle.vendor_id.
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
            .with_for_update()  # avoid race conditions
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
        
        # ---- Resolve Driver from Vehicle (1:1 mapping) ----
        driver = db.query(Driver).filter(
            Driver.driver_id == vehicle.driver_id,
            Driver.vendor_id == vehicle.vendor_id,
            Vendor.tenant_id == tenant_id
        ).first()
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message="No driver mapped to this vehicle",
                    error_code="DRIVER_NOT_LINKED_TO_VEHICLE",
                    details={"vehicle_id": vehicle.vehicle_id},
                ),
            )
        if vehicle.driver_id != driver.driver_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message="Vehicle and driver mismatch",
                    error_code="VEHICLE_DRIVER_MISMATCH",
                    details={
                        "vehicle_id": vehicle.vehicle_id,
                        "driver_id": driver.driver_id,
                    },
                ),
            )   
        # ---- Vendor logic ----
        if not route.assigned_vendor_id:
            # Auto-assign vendor from vehicle if route vendor missing
            route.assigned_vendor_id = vehicle.vendor_id
            logger.info(
                f"[assign_vehicle_to_route] Route {route_id} had no vendor assigned. Auto-set vendor_id={vehicle.vendor_id}"
            )
        elif route.assigned_vendor_id != vehicle.vendor_id:
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
        # assigned_conflict = (
        #     db.query(RouteManagement)
        #     .filter(
        #         RouteManagement.assigned_vehicle_id == vehicle.vehicle_id,
        #         RouteManagement.route_id != route_id,
        #         RouteManagement.tenant_id == tenant_id,
        #         RouteManagement.shift_id == route.shift_id,  # example constraint
        #         RouteManagement.date == route.date          # depends on your schema
        #     ).first()
        # )
        # if assigned_conflict:
        #     raise HTTPException(
        #         status_code=status.HTTP_409_CONFLICT,
        #         detail=ResponseWrapper.error(
        #             message="Vehicle is already assigned to another route for the same shift and date",
        #             error_code="VEHICLE_ALREADY_ASSIGNED",
        #             details={
        #                 "conflicting_route_id": assigned_conflict.route_id,
        #                 "vehicle_id": vehicle.vehicle_id,
        #             },
        #         ),
        #     )
        # ---- Apply assignment ----
        route.assigned_vehicle_id = vehicle.vehicle_id
        route.assigned_driver_id = driver.driver_id

        if route.status == RouteManagementStatusEnum.ASSIGNED:
            route.status = RouteManagementStatusEnum.PLANNED  # better status progression

        db.commit()
        db.refresh(route)

        logger.info(
            f"[assign_vehicle_to_route] Vehicle={vehicle_id} assigned to Route={route_id} (Tenant={tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "route_id": route.route_id,
                "assigned_vendor_id": route.assigned_vendor_id,
                "assigned_vehicle_id": route.assigned_vehicle_id,
                "status": route.status,
            },
            message="Vehicle assigned successfully",
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
            RouteManagement.tenant_id == tenant_id,
        ).first()

        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        # Fetch bookings in this route
        route_bookings = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .order_by(RouteManagementBooking.order_id)
            .all()
        )

        booking_ids = [rb.booking_id for rb in route_bookings]
        bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

        # ---- Build stops list same format as listing API ----
        stops = []
        for rb in route_bookings:
            booking = next((b for b in bookings if b["booking_id"] == rb.booking_id), None)
            if not booking:
                continue
            
            stops.append({
                "order_id": rb.order_id,
                "booking_id": rb.booking_id,
                "employee_name": booking.get("employee_name"),
                "pickup_location": booking.get("pickup_location"),
                "pickup_latitude": booking.get("pickup_latitude"),
                "pickup_longitude": booking.get("pickup_longitude"),
                "drop_location": booking.get("drop_location"),
                "drop_latitude": booking.get("drop_latitude"),
                "drop_longitude": booking.get("drop_longitude"),

                "estimated_pick_up_time": rb.estimated_pick_up_time,
                "estimated_drop_time": rb.estimated_drop_time,
                "estimated_distance": rb.estimated_distance,

                "actual_pick_up_time": rb.actual_pick_up_time,
                "actual_drop_time": rb.actual_drop_time,
                "actual_distance": rb.actual_distance,
            })

        # ---- Response same as list API ----
        response = {
            "route_id": route.route_id,
            "shift_id": route.shift_id,
            "route_code": route.route_code,
            "status": route.status.value if hasattr(route.status, "value") else route.status,
            "stops": stops,
            "summary": {
                "total_distance_km": (
                    route.actual_total_distance or route.estimated_total_distance or 0.0
                ),
                "total_time_minutes": (
                    route.actual_total_time or route.estimated_total_time or 0.0
                ),
            }
        }

        logger.info(f"[get_route_by_id] success route={route_id}, stops={len(stops)}")

        return ResponseWrapper.success(
            data=response,
            message=f"Route {route_id} retrieved successfully"
        )

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

        logger.info(f"Merging {len(request.route_ids)} routes for tenant={tenant_id}, user={user_id}")

        # --- Tenant Validation ---
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                    details={"tenant_id": tenant_id},
                ),
            )

        if not request.route_ids:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No route IDs provided for merging",
                    error_code="NO_ROUTE_IDS_PROVIDED",
                ),
            )

        # --- Collect all bookings from the routes to be merged ---
        all_booking_ids = []
        route_ids_to_delete = []

        for route_id in request.route_ids:
            route = (
                db.query(RouteManagement)
                .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
                .first()
            )

            if not route:
                raise HTTPException(
                    status_code=404,
                    detail=ResponseWrapper.error(
                        message=f"Route {route_id} not found",
                        error_code="ROUTE_NOT_FOUND",
                        details={"route_id": route_id},
                    ),
                )

            route_bookings = (
                db.query(RouteManagementBooking)
                .filter(RouteManagementBooking.route_id == route_id)
                .all()
            )

            all_booking_ids.extend([rb.booking_id for rb in route_bookings])
            route_ids_to_delete.append(route_id)

        # Deduplicate booking IDs (preserve order)
        all_booking_ids = list(dict.fromkeys(all_booking_ids))

        # --- Validate bookings exist ---
        bookings = get_bookings_by_ids(all_booking_ids, db)
        if not bookings:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="No valid bookings found for provided route IDs",
                    error_code="BOOKINGS_NOT_FOUND",
                ),
            )

        # --- Compute new estimations ---
        estimations = calculate_route_estimations(bookings)

        # --- Create merged route ---
        merged_route = save_route_to_db(all_booking_ids, estimations, tenant_id, db)
        logger.info(f"Created merged route {merged_route.route_id}")

        # --- Hard delete old routes and related records ---
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id.in_(route_ids_to_delete))
            .delete(synchronize_session=False)
        )

        deleted_routes_count = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id.in_(route_ids_to_delete))
            .delete(synchronize_session=False)
        )

        db.commit()
        logger.info(
            f"Merged route {merged_route.route_id} created. "
            f"Deleted {deleted_routes_count} old routes and {deleted_bookings_count} linked route-booking records."
        )

        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=merged_route.route_id,
                bookings=bookings,
                estimations=estimations,
            ),
            message=f"Successfully merged {len(request.route_ids)} routes into {merged_route.route_id}",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error merging routes: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error merging routes",
                error_code="ROUTE_MERGE_ERROR",
                details={"error": str(e)},
            ),
        )

@router.post("/{route_id}/split")
async def split_route(
    route_id: int,  # Changed from str to int
    request: SplitRouteRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Split a route into multiple routes based on provided booking ID groups.
    """
    try:
        logger.info(f"Splitting route {route_id} into {len(request.groups)} groups for tenant: {tenant_id}, user: {user_data.get('user_id', 'unknown')}")
        
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
        
        if not request.groups:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No booking groups provided for splitting",
                    error_code="NO_GROUPS_PROVIDED"
                )
            )
        
        # Check if original route exists
        original_route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id
        ).first()
        
        if not original_route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                    details = "No rount found"
                )
            )
        
        routes = []
        
        for i, group in enumerate(request.groups):  # Changed to use group instead of booking_ids_group
            # Get bookings for this split group
            bookings = get_bookings_by_ids(group.booking_ids, db)  # Use group.booking_ids
            
            if not bookings:
                raise HTTPException(status_code=404, detail=ResponseWrapper.error(
                    message=f"No valid bookings found for provided route ids",
                    error_code="BOOKINGS_NOT_FOUND",
                    details="No bookings found"
                ))
            # Calculate estimations
            estimations = calculate_route_estimations(bookings)
            
            # Create split route - route_id will be auto-generated
            split_route = save_route_to_db(group.booking_ids, estimations, tenant_id, db)  # Use group.booking_ids
            
            route = RouteWithEstimations(
                route_id=split_route.route_id,
                bookings=bookings,
                estimations=estimations
            )
            routes.append(route)
        
        # Deactivate original route
        original_route.is_active = False
        db.commit()
        
        logger.info(f"Successfully split route {route_id} into {len(routes)} new routes")
        
        return ResponseWrapper.success(
            data=routes,
            message=f"Successfully split route {route_id} into {len(routes)} new routes"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
    except Exception as e:
        logger.error(f"Error splitting route {route_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Error splitting route {route_id}",
                error_code="ROUTE_SPLIT_ERROR",
                details={"error": str(e)}
            )
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

        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                )
            )

        # Get existing booking IDs from the route
        existing_route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        existing_booking_ids = [rb.booking_id for rb in existing_route_bookings]

        # Perform operation based on request
        if request.operation == RouteOperationEnum.ADD:
            # Add new bookings to existing ones, removing duplicates while preserving order
            all_booking_ids = list(set(existing_booking_ids + request.booking_ids))
        elif request.operation == RouteOperationEnum.REMOVE:
            # Remove specified bookings from existing ones
            all_booking_ids = [bid for bid in existing_booking_ids if bid not in request.booking_ids]
            if not all_booking_ids:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Cannot remove all bookings from route. Route must have at least one booking.",
                        error_code="CANNOT_REMOVE_ALL_BOOKINGS"
                    )
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message=f"Invalid operation: {request.operation}. Must be 'add' or 'remove'",
                    error_code="INVALID_OPERATION"
                )
            )

        # Fetch updated bookings
        bookings = get_bookings_by_ids(all_booking_ids, db)
        if not bookings:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="No valid bookings found for the updated route",
                    error_code="BOOKINGS_NOT_FOUND",
                )
            )

        # Generate optimal route
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        if not shift:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Shift {route.shift_id} not found",
                    error_code="SHIFT_NOT_FOUND",
                )
            )

        shift_type = shift.log_type or "OUT"
        estimations = calculate_route_estimations(bookings, shift_type=shift_type)

        # Update route details
        route.total_distance_km = estimations.total_distance_km
        route.total_time_minutes = estimations.total_time_minutes

        # Delete existing route bookings
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).delete()

        # Create new route bookings with updated order
        for i, booking_id in enumerate(all_booking_ids):
            route_booking = RouteManagementBooking(
                route_id=route_id,
                booking_id=booking_id,
                stop_order=i + 1,
                estimated_pickup_time=estimations.estimated_pickup_times.get(booking_id),
                estimated_drop_time=estimations.estimated_drop_times.get(booking_id),
                distance_from_previous=5.0 if i > 0 else 0.0,
                cumulative_distance=(i + 1) * 5.0
            )
            db.add(route_booking)

        db.commit()

        operation_msg = f"added {len(request.booking_ids)} bookings to" if request.operation == RouteOperationEnum.ADD else f"removed {len(request.booking_ids)} bookings from"
        logger.info(f"Successfully {operation_msg} route {route_id}")

        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=route_id,
                bookings=bookings,
                estimations=estimations
            ),
            message=f"Route {route_id} updated successfully: {operation_msg} route"
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
    Update the order of bookings and their estimated times in a route.
    """
    try:
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

        logger.info(f"Updating booking order for route {route_id} by user: {user_data.get('user_id', 'unknown')}")

        # Validate route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id,
        ).first()

        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        # Validate request data
        if not request.bookings:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No booking data provided for update",
                    error_code="NO_BOOKINGS_PROVIDED",
                ),
            )

        # Update booking order and estimated times
        for booking_data in request.bookings:
            route_booking = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route_id,
                RouteManagementBooking.booking_id == booking_data.booking_id,
            ).first()

            if not route_booking:
                raise HTTPException(
                    status_code=404,
                    detail=ResponseWrapper.error(
                        message=f"Booking {booking_data.booking_id} not found in route {route_id}",
                        error_code="BOOKING_NOT_FOUND_IN_ROUTE",
                    ),
                )

            # Update fields
            route_booking.order_id = booking_data.new_order_id
            route_booking.estimated_pick_up_time = booking_data.estimated_pickup_time
            route_booking.estimated_drop_time = booking_data.estimated_drop_time

        # Commit changes
        db.commit()

        # Fetch updated bookings
        updated_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.order_id).all()

        response_data = [
            RouteManagementBookingResponse.model_validate(booking, from_attributes=True)
            for booking in updated_bookings
        ]

        logger.info(f"Successfully updated booking order for route {route_id}")

        return ResponseWrapper.success(
            data=response_data,
            message=f"Booking order and estimated times updated successfully for route {route_id}",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating booking order for route {route_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error updating booking order",
                error_code="UPDATE_BOOKING_ORDER_ERROR",
                details={"error": str(e)},
            ),
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
    for a given shift and date.
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

        # --- Delete child records first (FK safety) ---
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )

        # --- Hard delete routes ---
        deleted_routes_count = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )

        db.commit()

        logger.info(
            f"Hard deleted {deleted_routes_count} routes and {deleted_bookings_count} route-booking links successfully"
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
    Permanently delete a route and all its associated bookings.
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
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
            )
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

        # ---- Delete associated bookings ----
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .delete(synchronize_session=False)
        )

        # ---- Delete the route ----
        db.delete(route)
        db.commit()

        logger.info(
            f"[delete_route] ✅ Route {route_id} permanently deleted with {deleted_bookings_count} associated bookings."
        )

        return ResponseWrapper.success(
            data={
                "deleted_route_id": route_id,
                "deleted_bookings_count": deleted_bookings_count,
            },
            message=f"Route {route_id} deleted successfully",
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


