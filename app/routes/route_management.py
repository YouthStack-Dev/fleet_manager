from fastapi import APIRouter, Depends, HTTPException, Query ,status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import date
from enum import Enum
import time

from app.database.session import get_db
from app.models.booking import Booking
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.models.shift import Shift  # Add shift model import
from app.models.tenant import Tenant  # Add tenant model import
from app.schemas.route import RouteWithEstimations, RouteEstimations
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error

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
        total_time_minutes=estimations.total_time_minutes,
        is_active=True
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

@router.post("/")
async def create_routes(
    request: CreateRoutesRequest,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Create routes from grouped bookings with estimations.
    Validations:
      - All booking IDs in a group belong to the same tenant.
      - All bookings share the same date.
      - All bookings share the same shift.
    """
    try:
        logger.info(f"[create_routes] Received request with {len(request.groups)} group(s) | Raw tenant={tenant_id} | User={user_data.get('user_id')}")

        # ---- Determine effective tenant_id ----
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

        logger.info(f"[create_routes] Effective tenant resolved: {tenant_id}")

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

        if not request.groups:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No route groups provided",
                    error_code="NO_GROUPS_PROVIDED",
                ),
            )

        # ---- Collect validations across all groups ----
        all_booking_dates = set()
        all_shift_ids = set()
        all_tenant_ids = set()

        routes = []
        for idx, group in enumerate(request.groups, start=1):
            logger.info(f"[create_routes] ─── Processing group #{idx} ({len(group.booking_ids)} bookings) ───")

            bookings = get_bookings_by_ids(group.booking_ids, db)
            logger.info(f"[create_routes] Retrieved {len(bookings)} booking(s) for group #{idx}: {[b['booking_id'] for b in bookings]}")

            if not bookings:
                raise HTTPException(
                    status_code=404,
                    detail=ResponseWrapper.error(
                        message=f"No bookings found for IDs {group.booking_ids}",
                        error_code="NO_BOOKINGS_FOUND",
                    ),
                )

            # ---- Check if any booking is already assigned to another active route ----
            existing_routes = (
                db.query(RouteManagement.route_id, RouteManagementBooking.booking_id)
                .join(RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id)
                .filter(
                    RouteManagementBooking.booking_id.in_(group.booking_ids),
                    RouteManagement.tenant_id == tenant_id,
                    RouteManagement.is_active == True,
                )
                .all()
            )

            if existing_routes:
                existing_route_ids = list({r.route_id for r in existing_routes})
                already_assigned_bookings = list({r.booking_id for r in existing_routes})
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="Some bookings are already assigned to existing routes",
                        error_code="BOOKINGS_ALREADY_ASSIGNED",
                        details={
                            "already_assigned_bookings": already_assigned_bookings,
                            "existing_route_ids": existing_route_ids,
                        },
                    ),
                )
            # ---- Strict per-group validations ----
            tenant_ids = {b["tenant_id"] for b in bookings if b.get("tenant_id")}
            booking_dates = {b["booking_date"] for b in bookings if b.get("booking_date")}
            shift_ids = {b["shift_id"] for b in bookings if b.get("shift_id")}

            if len(tenant_ids) != 1 or tenant_id not in tenant_ids:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="All bookings in a group must belong to the same tenant",
                        error_code="CROSS_TENANT_BOOKINGS",
                        details={"expected_tenant": tenant_id, "found_tenants": list(tenant_ids)},
                    ),
                )

            if len(booking_dates) != 1:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="All bookings in a route must have the same booking date",
                        error_code="MIXED_BOOKING_DATES",
                        details={"booking_dates": list(booking_dates)},
                    ),
                )

            if len(shift_ids) != 1:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="All bookings in a route must belong to the same shift",
                        error_code="MIXED_SHIFTS",
                        details={"shift_ids": list(shift_ids)},
                    ),
                )

            # ---- Collect global-level validations ----
            all_booking_dates.update(booking_dates)
            all_shift_ids.update(shift_ids)
            all_tenant_ids.update(tenant_ids)

            booking_date = list(booking_dates)[0]
            shift_id = list(shift_ids)[0]
            logger.info(f"[create_routes] ✅ Valid group | Tenant={tenant_id} | Date={booking_date} | Shift={shift_id}")

            estimations = calculate_route_estimations(bookings)
            saved_route = save_route_to_db(group.booking_ids, estimations, tenant_id, db)

            routes.append(
                RouteWithEstimations(
                    route_id=saved_route.route_id,
                    bookings=bookings,
                    estimations=estimations,
                )
            )

        # ---- Cross-group (global) validations ----
        if len(all_booking_dates) > 1:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="All groups in this request must have bookings from the same date",
                    error_code="MULTIPLE_BOOKING_DATES_IN_REQUEST",
                    details={"booking_dates": list(all_booking_dates)},
                ),
            )

        if len(all_shift_ids) > 1:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="All groups in this request must belong to the same shift",
                    error_code="MULTIPLE_SHIFTS_IN_REQUEST",
                    details={"shift_ids": list(all_shift_ids)},
                ),
            )

        logger.info(f"[create_routes] ✅ Successfully created {len(routes)} route(s)")
        return ResponseWrapper.success(
            data={"routes": routes},
            message=f"Successfully created {len(routes)} route(s)",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[create_routes] Unexpected error")
        return handle_db_error(e)


@router.get("/")
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

        logger.info(f"[create_routes] Effective tenant resolved: {tenant_id}")

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
        logger.info(f"Fetching all routes for tenant: {tenant_id}, shift_id: {shift_id}, booking_date: {booking_date}, user: {user_data.get('user_id', 'unknown')}")
        

        
        # Base query for routes
        if shift_id or booking_date:
            # If shift_id or booking_date is provided, filter routes by bookings
            routes_query = db.query(RouteManagement).join(
                RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id
            ).join(
                Booking, RouteManagementBooking.booking_id == Booking.booking_id
            ).filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.is_active == True
            )
            
            # Add filters based on provided parameters
            if shift_id:
                routes_query = routes_query.filter(Booking.shift_id == shift_id)
            if booking_date:
                routes_query = routes_query.filter(Booking.booking_date == booking_date)
                
            routes_query = routes_query.distinct()
        else:
            routes_query = db.query(RouteManagement).filter(
                RouteManagement.tenant_id == tenant_id, 
                RouteManagement.is_active == True
            )
        
        routes = routes_query.all()
        
        if not routes:
            filter_msg = f" and shift {shift_id}" if shift_id else ""
            filter_msg += f" and date {booking_date}" if booking_date else ""
            logger.info(f"No active routes found for tenant {tenant_id}{filter_msg}")
            return ResponseWrapper.success(
                data={
                    "shifts": [],
                    "total_shifts": 0,
                    "total_routes": 0,
                },
                message=f"No active routes found for tenant {tenant_id}{filter_msg}"
            )
        
        # Group routes by shift
        shifts_data = {}
        
        for route in routes:
            route_bookings = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route.route_id
            ).order_by(RouteManagementBooking.stop_order).all()
            
            booking_ids = [rb.booking_id for rb in route_bookings]
            bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []
            
            # Get shift information from bookings
            for booking in bookings:
                shift_id_key = booking["shift_id"]
                if shift_id_key and shift_id_key not in shifts_data:
                    # Get shift details
                    shift = db.query(Shift).filter(Shift.shift_id == shift_id_key).first()
                    if shift:
                        shifts_data[shift_id_key] = {
                            "shift_id": shift.shift_id,
                            "log_type": shift.log_type.value if shift.log_type else None,
                            "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
                            "routes": []
                        }
            
            estimations = RouteEstimations(
                total_distance_km=route.total_distance_km or 0.0,
                total_time_minutes=route.total_time_minutes or 0.0,
                estimated_pickup_times={
                    rb.booking_id: rb.estimated_pickup_time 
                    for rb in route_bookings if rb.estimated_pickup_time
                },
                estimated_drop_times={
                    rb.booking_id: rb.estimated_drop_time 
                    for rb in route_bookings if rb.estimated_drop_time
                }
            )
            
            route_response = {
                "route_id": route.route_id,
                "bookings": bookings,
                "estimations": estimations
            }
            
            # Add route to appropriate shift
            for booking in bookings:
                shift_id_key = booking["shift_id"]
                if shift_id_key and shift_id_key in shifts_data:
                    # Check if route already added to this shift
                    route_exists = any(r["route_id"] == route.route_id for r in shifts_data[shift_id_key]["routes"])
                    if not route_exists:
                        shifts_data[shift_id_key]["routes"].append(route_response)
                    break
        
        # Convert to list format
        shifts_list = list(shifts_data.values())
        total_routes = sum(len(shift["routes"]) for shift in shifts_list)
        
        logger.info(f"Successfully fetched {len(shifts_list)} shifts with {total_routes} total routes")
        
        return ResponseWrapper.success(
            data={
                "shifts": shifts_list,
                "total_shifts": len(shifts_list),
                "total_routes": total_routes
            },
            message=f"Successfully retrieved {len(shifts_list)} shifts with {total_routes} routes"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.get("/{route_id}")
async def get_route_by_id(
    route_id: int,  # Changed from str to int
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
        logger.info(f"Fetching route {route_id} for tenant: {tenant_id}, user: {user_data.get('user_id', 'unknown')}")
        
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
        
        # Query the route
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id,
            RouteManagement.is_active == True
        ).first()
        
        if not route:
            logger.warning(f"Route {route_id} not found for tenant {tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                    details = "No rount found"
                )
            )
        
        # Get route bookings
        route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.stop_order).all()
        
        booking_ids = [rb.booking_id for rb in route_bookings]
        bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []
        
        # Create estimations
        estimations = RouteEstimations(
            total_distance_km=route.total_distance_km or 0.0,
            total_time_minutes=route.total_time_minutes or 0.0,
            estimated_pickup_times={
                rb.booking_id: rb.estimated_pickup_time 
                for rb in route_bookings if rb.estimated_pickup_time
            },
            estimated_drop_times={
                rb.booking_id: rb.estimated_drop_time 
                for rb in route_bookings if rb.estimated_drop_time
            }
        )
        
        logger.info(f"Successfully retrieved route {route_id}")
        
        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=route.route_id,
                bookings=bookings,
                estimations=estimations
            ),
            message=f"Route {route_id} retrieved successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)
    except Exception as e:
        logger.error(f"Error retrieving route {route_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Error retrieving route {route_id}",
                error_code="ROUTE_RETRIEVAL_ERROR",
                details={"error": str(e)}
            )
        )

@router.post("/merge")
async def merge_routes(
    request: MergeRoutesRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Merge multiple routes into a single optimized route.
    """
    try:
        logger.info(f"Merging {len(request.route_ids)} routes for tenant: {tenant_id}, user: {user_data.get('user_id', 'unknown')}")
        
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
        
        if not request.route_ids:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No route IDs provided for merging",
                    error_code="NO_ROUTE_IDS_PROVIDED"
                )
            )
        
        # Get all booking IDs from the routes to be merged
        all_booking_ids = []
        routes_to_delete = []
        
        for route_id in request.route_ids:
            route = db.query(RouteManagement).filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.is_active == True
            ).first()
            
            if not route:
                
                raise HTTPException(status_code=404, detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                    details = "No rount found",
                ))
            
            route_bookings = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route_id
            ).all()
            
            all_booking_ids.extend([rb.booking_id for rb in route_bookings])
            routes_to_delete.append(route)
        
        # Remove duplicates while preserving order
        all_booking_ids = list(dict.fromkeys(all_booking_ids))
        
        # Get all bookings
        bookings = get_bookings_by_ids(all_booking_ids, db)
        
        if not bookings:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error(
                    message=f"No valid bookings found for provided route ids",
                    error_code="BOOKINGS_NOT_FOUND",
                    details="No bookings found"
                ))
        
        # Calculate new estimations
        estimations = calculate_route_estimations(bookings)
        
        # Save merged route - route_id will be auto-generated
        merged_route = save_route_to_db(all_booking_ids, estimations, tenant_id, db)
        
        # Deactivate original routes
        for route in routes_to_delete:
            route.is_active = False
        
        db.commit()
        
        logger.info(f"Successfully merged routes into {merged_route.route_id}")
        
        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=merged_route.route_id,  # Use the auto-generated route_id
                bookings=bookings,
                estimations=estimations
            ),
            message=f"Successfully merged {len(request.route_ids)} routes into {merged_route.route_id}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
    except Exception as e:
        logger.error(f"Error merging routes: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error merging routes",
                error_code="ROUTE_MERGE_ERROR",
                details={"error": str(e)}
            )
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
            RouteManagement.route_id == route_id, 
            RouteManagement.is_active == True
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
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
):
    """
    Update a route by adding or removing booking assignments based on operation.
    """
    try:
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
            RouteManagement.is_active == True
        ).first()
        
        if not route:
            raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
        
        # Get existing booking IDs from the route
        existing_route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        
        existing_booking_ids = [rb.booking_id for rb in existing_route_bookings]
        
        # Perform operation based on request
        if request.operation == RouteOperationEnum.ADD:
            # Add new bookings to existing ones, removing duplicates while preserving order
            all_booking_ids = existing_booking_ids.copy()
            for booking_id in request.booking_ids:
                if booking_id not in all_booking_ids:
                    all_booking_ids.append(booking_id)
        elif request.operation == RouteOperationEnum.REMOVE:
            # Remove specified bookings from existing ones
            all_booking_ids = [booking_id for booking_id in existing_booking_ids if booking_id not in request.booking_ids]
            
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
        
        # Get all bookings (final list after operation)
        bookings = get_bookings_by_ids(all_booking_ids, db)
        
        if not bookings:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error(
                    message=f"No valid bookings found for provided route ids",
                    error_code="BOOKINGS_NOT_FOUND",
                    details="No bookings found"
                ))
        
        # Calculate new estimations for the updated route
        estimations = calculate_route_estimations(bookings)
        
        # Update route with new estimations
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
        raise
    except Exception as e:
        db.rollback()
        return handle_db_error(e)

@router.delete("/{route_id}")
async def delete_route(
    route_id: int,  # Changed from str to int
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True)),
):
    """
    Delete a route by its ID.
    """
    try:
        logger.info(f"Deleting route {route_id}, user: {user_data.get('user_id', 'unknown')}")
        
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
        
        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id, 
            RouteManagement.is_active == True
        ).first()
        
        if not route:
            raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
        
        # Delete route bookings
        route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        
        for rb in route_bookings:
            db.delete(rb)
        
        # Soft delete the route
        route.is_active = False
        db.commit()
        
        logger.info(f"Successfully deleted route {route_id}")
        
        return ResponseWrapper.success(
            data={
                "deleted_route_id": route_id
            },
            message=f"Route {route_id} deleted successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
    except Exception as e:
        logger.error(f"Error deleting route {route_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message=f"Error deleting route {route_id}",
                error_code="ROUTE_DELETE_ERROR",
                details={"error": str(e)}
            )
        )
