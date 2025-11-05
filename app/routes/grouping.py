from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel

import app
from app.database.session import get_db
from app.models.booking import Booking
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.models.shift import Shift
from app.schemas.shift import ShiftResponse
from app.services.geodesic import group_rides
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error

logger = get_logger(__name__)

router = APIRouter(
    prefix="/grouping",
    tags=["route-suggestion"],
)

class BookingInput(BaseModel):
    booking_id: int
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None
    drop_latitude: float
    drop_longitude: float
    drop_location: Optional[str] = None
    pickup_location: Optional[str] = None
    pickup_latitude: Optional[float] = None
    pickup_longitude: Optional[float] = None
    status: Optional[str] = None

class ClusterGenerationRequest(BaseModel):
    bookings: List[BookingInput]
    group_size: int = 2
    radius: int = 1
    strict_grouping: bool = False

from datetime import datetime

def datetime_to_minutes(datetime_str):
    """
    Convert datetime string to integer minutes from midnight
    Args:
        datetime_str: String in format "2025-10-30T13:50:00.733946"
    Returns:
        int: Minutes from midnight (0-1439)
    """
    # Parse the datetime string
    dt = datetime.fromisoformat(datetime_str)
    return dt.hour * 60 + dt.minute

@router.get("/bookings/routesuggestion")
async def route_suggestion(
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

        # ---- Generate optimal route for each cluster (optional) ----
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        if shift_type == "IN":
            for cluster in cluster_data:
                optimized_route = generate_optimal_route(
                    group=cluster["bookings"],
                    start_time_minutes=datetime_to_minutes(shift.shift_time),
                    drop_lat=cluster["bookings"][-1]["drop_latitude"],
                    drop_lon=cluster["bookings"][-1]["drop_longitude"],
                    drop_address=cluster["bookings"][-1]["drop_location"]
                )
                cluster["optimized_route"] = optimized_route
        else:
            for cluster in cluster_data:
                optimized_route = generate_drop_route(
                    group=cluster["bookings"],
                    start_time_minutes=datetime_to_minutes(shift.shift_time),
                    office_lat=cluster["bookings"][0]["pickup_latitude"],
                    office_lng=cluster["bookings"][0]["pickup_longitude"],
                    office_address=cluster["bookings"][0]["pickup_location"]
                )
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

@router.post("/bookings/cluster-by-bookings")
async def cluster_custom_bookings(
    request: ClusterGenerationRequest,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Generate clusters from a custom list of bookings.
    """
    try:
        logger.info(f"Custom clustering request for {len(request.bookings)} bookings from user: {user_data.get('user_id', 'unknown')}")
        
        if not request.bookings:
            raise HTTPException(
                status_code=400, 
                detail=ResponseWrapper.error(
                    message="No bookings provided",
                    error_code="NO_BOOKINGS_PROVIDED"
                )
            )
        
        # Convert to rides format for clustering
        rides = []
        for booking in request.bookings:
            ride = {
                'lat': booking.drop_latitude,
                'lon': booking.drop_longitude,
                'booking_id': booking.booking_id,
                'employee_code': booking.employee_code,
                'drop_location': booking.drop_location,
                'pickup_location': booking.pickup_location,
                'status': booking.status
            }
            rides.append(ride)
        
        # Generate clusters
        clusters = group_rides(rides, radius_km=request.radius, group_size=request.group_size, strict_grouping=request.strict_grouping)
        
        cluster_id = 1
        cluster_updated = []
        for cluster in clusters:
            for booking in cluster:
                _ = booking.pop("lat", None)
                _ = booking.pop("lon", None)
            cluster_ = {
                "cluster_id": cluster_id,
                "bookings": cluster
            }
            cluster_updated.append(cluster_)
            cluster_id += 1
        
        logger.info(f"Successfully generated {len(cluster_updated)} clusters from custom bookings")
        
        return ResponseWrapper.success(
            data={
                "clusters": cluster_updated,
                "total_bookings": len(request.bookings),
                "total_clusters": len(clusters)
            },
            message="Custom bookings clustered successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)
    except Exception as e:
        logger.error(f"Error clustering custom bookings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error clustering custom bookings",
                error_code="CUSTOM_CLUSTERING_ERROR",
                details={"error": str(e)}
            )
        )
