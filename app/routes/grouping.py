from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel

import app
from app.database.session import get_db
from app.models.booking import Booking
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
    Get all bookings for a specific date and shift ID and generate clusters for route planning.
    """
    try:
        logger.info(f"Clustering request for date: {booking_date}, shift: {shift_id}, user: {user_data.get('user_id', 'unknown')}")
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Determine effective tenant_id ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
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

        # ---- Validate shift belongs to this tenant ----
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

        shift_type = shift.log_type if shift else "Unknown"
        if shift_type == "IN":
            lat = "pickup_latitude"
            long = "pickup_longitude"
        else:
            lat = "drop_latitude"
            long = "drop_longitude"

        bookings = db.query(Booking).filter(
            Booking.booking_date == booking_date,
            Booking.shift_id == shift_id,
            Booking.tenant_id == tenant_id
        ).all()

        
        if not bookings:
            logger.info(f"No bookings found for date {booking_date} and shift {shift_id}")
            return ResponseWrapper.success(
                data={
                    "clusters": [],
                    "total_bookings": 0,
                    "total_clusters": 0,
                },
                message=f"No bookings found for date {booking_date} and shift ID {shift_id}"
            )
        
        # Convert bookings to the format expected by clustering algorithm
        rides = []
        for booking in bookings:
            ride = {
                'lat': getattr(booking, lat),
                'lon': getattr(booking, long),
            }
            ride.update(booking.__dict__)
            rides.append(ride)
        
        # Filter out rides without valid coordinates
        valid_rides = [r for r in rides if r['lat'] is not None and r['lon'] is not None]
        
        if not valid_rides:
            logger.warning(f"No valid coordinates found for {len(bookings)} bookings")
            return ResponseWrapper.success(
                data={
                    "clusters": [],
                    "total_bookings": len(bookings),
                    "total_clusters": 0,
                },
                message="No bookings with valid coordinates found for clustering"
            )
        
        # Generate clusters using geodesic grouping
        clusters = group_rides(valid_rides, radius, group_size, strict_grouping)

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

        logger.info(f"Successfully generated {len(cluster_updated)} clusters from {len(bookings)} bookings")
        
        shift_response = ShiftResponse.model_validate(shift, from_attributes=True)
        return ResponseWrapper.success(
            data={
                "shift": shift_response,
                "clusters": cluster_updated,
                "total_bookings": len(bookings),
                "total_clusters": len(clusters),
            },
            message="Bookings clustered successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clustering bookings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error clustering bookings",
                error_code="CLUSTERING_ERROR",
                details={"error": str(e)}
            )
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
