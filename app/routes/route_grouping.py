from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
import numpy as np
from sklearn.cluster import KMeans
from pydantic import BaseModel
import math

from app.database.session import get_db
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.schemas.route import RouteWithEstimations, RouteEstimations
from app.schemas.booking import BookingResponse
from app.services.geodesic import group_rides

router = APIRouter(
    prefix="/route-grouping",
    tags=["route-grouping"]
)

class BookingInput(BaseModel):
    booking_id: int
    employee_id: Optional[str] = None
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
    num_clusters: int = 2

class RouteOptimizationRequest(BaseModel):
    bookings: List[BookingInput]
    start_location: Optional[Dict[str, float]] = None  # {"lat": lat, "lon": lon}
    return_to_start: bool = True

class RouteStop(BaseModel):
    booking_id: int
    employee_code: Optional[str] = None
    location_name: Optional[str] = None
    latitude: float
    longitude: float
    stop_order: int
    distance_from_previous: float
    cumulative_distance: float

class OptimalRoute(BaseModel):
    route_stops: List[RouteStop]
    total_distance_km: float
    estimated_time_minutes: float
    start_location: Optional[Dict[str, float]] = None

class RouteResponse(BaseModel):
    route_id: str
    bookings: List[BookingInput]
    estimations: RouteEstimations

class RequestItem(BaseModel):
    group_id: int
    bookings: List[int]  # List of booking IDs

class SaveConfirmRequest(BaseModel):
    groups: List[RequestItem]

class MergeRequest(BaseModel):
    route_ids: List[str]

class SplitRequest(BaseModel):
    route_id: str
    groups: List[List[int]]  # List of booking ID groups - [[b1,b2], [b3,b4]]

class UpdateRequest(BaseModel):
    route_id: str
    bookings: List[int]  # List of booking IDs

class DeleteRequest(BaseModel):
    route_id: str

@router.get("/bookings")
async def get_bookings_by_date_and_shift(
    booking_date: date = Query(..., description="Date for the bookings (YYYY-MM-DD)"),
    shift_id: int = Query(..., description="Shift ID to filter bookings"),
    radius: float = Query(1.0, description="Radius in km for clustering"),
    group_size: int = Query(2, description="Number of route clusters to generate"),
    strict_grouping: bool = Query(False, description="Whether to enforce strict grouping by group size or not"),
    db: Session = Depends(get_db)
):
    """
    Get all bookings for a specific date and shift ID and generate route clusters.
    
    Args:
        booking_date: The date to filter bookings
        shift_id: The shift ID to filter bookings
        num_clusters: Number of route clusters to generate
        db: Database session
    
    Returns:
        Dictionary containing original bookings and generated route clusters
    """
    try:
        shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()

        shift_type = shift.log_type if shift else "Unknown"
        if shift_type == "IN":
            lat = "pickup_latitude"
            long = "pickup_longitude"
        else:
            lat = "drop_latitude"
            long = "drop_longitude"

        bookings = db.query(Booking).filter(
            Booking.booking_date == booking_date,
            Booking.shift_id == shift_id
        ).all()
        
        if not bookings:
            raise HTTPException(
                status_code=404, 
                detail=f"No bookings found for date {booking_date} and shift ID {shift_id}"
            )
        
        # Convert bookings to the format expected by clustering algorithm
        rides = []
        for booking in bookings:
            # Use correct attribute names based on sample data
            ride = {
                'lat': getattr(booking, lat),
                'lon': getattr(booking, long),
            }

            ride.update(booking.__dict__)
            
            rides.append(ride)
        
        # Filter out rides without valid coordinates
        valid_rides = [r for r in rides if r['lat'] is not None and r['lon'] is not None]
        
        if not valid_rides:
            return {
                "bookings": bookings,
                "route_clusters": [],
                "message": "No bookings with valid coordinates found for clustering"
            }
        
        # Determine clustering strategy based on pickup locations
        clusters = group_rides(rides, radius, group_size, strict_grouping)

        cluster_id = 1
        cluster_updated = []
        for cluster in clusters:
            for booking in cluster:
                _ = booking.pop("lat")
                _ = booking.pop("lon")
            cluster_ = {
                "cluster_id": cluster_id,
                "bookings": cluster
            }
            cluster_updated.append(cluster_)

            cluster_id += 1

        return {
            "route_clusters": cluster_updated,
            "total_bookings": len(bookings),
            "total_clusters": len(clusters),
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving bookings and generating clusters: {str(e)}"
        )

def get_bookings_by_ids(booking_ids: List[int], db: Session) -> List[Dict]:
    """
    Retrieve bookings by their IDs and convert to dictionary format.
    """
    bookings = db.query(Booking).filter(Booking.booking_id.in_(booking_ids)).all()
    return [
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

def save_route_to_db(route_id: str, booking_ids: List[int], estimations: RouteEstimations, tenant_id: str, db: Session) -> RouteManagement:
    """
    Save route and its bookings to database.
    """
    # Create route
    route = RouteManagement(
        route_id=route_id,
        tenant_id=tenant_id,
        route_code=f"ROUTE-{route_id}",
        total_distance_km=estimations.total_distance_km,
        total_time_minutes=estimations.total_time_minutes,
        is_active=True  # Explicitly set is_active to True
    )
    db.add(route)
    db.flush()
    
    # Create route bookings
    for i, booking_id in enumerate(booking_ids):
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
    return route

@router.post("/save-confirm", response_model=List[RouteWithEstimations])
async def save_confirm_routes(
    request: SaveConfirmRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """
    Save/Confirm route groups and generate optimal routes with estimations.
    """
    try:
        routes = []
        
        for group in request.groups:
            # Get bookings for this group
            bookings = get_bookings_by_ids(group.bookings, db)
            
            if not bookings:
                continue
            
            # Calculate estimations
            estimations = calculate_route_estimations(bookings)
            
            # Save to database
            route_id = str(group.group_id)
            saved_route = save_route_to_db(route_id, group.bookings, estimations, tenant_id, db)
            
            # Create route response
            route = RouteWithEstimations(
                route_id=route_id,
                bookings=bookings,
                estimations=estimations
            )
            routes.append(route)
        
        return routes
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error saving/confirming routes: {str(e)}"
        )

@router.post("/merge", response_model=RouteWithEstimations)
async def merge_routes(
    request: MergeRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """
    Merge multiple routes into a single optimized route.
    """
    try:
        # Get all booking IDs from the routes to be merged
        all_booking_ids = []
        routes_to_delete = []
        
        for route_id in request.route_ids:
            # Query each route individually
            route = db.query(RouteManagement).filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.is_active == True
            ).first()
            
            if not route:
                raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
            
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
            raise HTTPException(status_code=404, detail="No valid bookings found for the provided route IDs")
        
        # Calculate new estimations
        estimations = calculate_route_estimations(bookings)
        
        # Generate new merged route ID using timestamp to ensure uniqueness
        import time
        merged_route_id = f"merged-{int(time.time())}"
        
        # Save merged route
        save_route_to_db(merged_route_id, all_booking_ids, estimations, tenant_id, db)
        
        # Deactivate original routes
        for route in routes_to_delete:
            route.is_active = False
        
        db.commit()
        
        return RouteWithEstimations(
            route_id=merged_route_id,
            bookings=bookings,
            estimations=estimations
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error merging routes: {str(e)}")

@router.post("/split", response_model=List[RouteWithEstimations])
async def split_route(
    request: SplitRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """
    Split a route into multiple routes based on provided booking ID groups.
    Input format: {"route_id": "1", "groups": [[b1,b2], [b3,b4]]}
    where b1, b2, etc. are booking IDs
    """
    try:
        # Check if original route exists
        original_route = db.query(RouteManagement).filter(
            RouteManagement.route_id == request.route_id, 
            RouteManagement.is_active == True
        ).first()
        
        if not original_route:
            raise HTTPException(status_code=404, detail=f"Route {request.route_id} not found")
        
        routes = []
        
        for i, booking_ids_group in enumerate(request.groups):
            # Get bookings for this split group
            bookings = get_bookings_by_ids(booking_ids_group, db)
            
            if not bookings:
                continue
            
            # Calculate estimations
            estimations = calculate_route_estimations(bookings)
            
            # Create split route
            split_route_id = f"{request.route_id}-split-{i+1}"
            save_route_to_db(split_route_id, booking_ids_group, estimations, tenant_id, db)
            
            route = RouteWithEstimations(
                route_id=split_route_id,
                bookings=bookings,
                estimations=estimations
            )
            routes.append(route)
        
        # Deactivate original route
        original_route.is_active = False
        db.commit()
        
        return routes
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error splitting route: {str(e)}")

@router.put("/update", response_model=RouteWithEstimations)
async def update_route(
    request: UpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update a route by extending it with new booking assignments.
    """
    try:
        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == request.route_id, 
            RouteManagement.is_active == True
        ).first()
        
        if not route:
            raise HTTPException(status_code=404, detail=f"Route {request.route_id} not found")
        
        # Get existing booking IDs from the route
        existing_route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == request.route_id
        ).all()
        
        existing_booking_ids = [rb.booking_id for rb in existing_route_bookings]
        
        # Combine existing and new booking IDs, removing duplicates while preserving order
        all_booking_ids = existing_booking_ids.copy()
        for booking_id in request.bookings:
            if booking_id not in all_booking_ids:
                all_booking_ids.append(booking_id)
        
        # Get all bookings (existing + new)
        bookings = get_bookings_by_ids(all_booking_ids, db)
        
        if not bookings:
            raise HTTPException(status_code=404, detail="No valid bookings found")
        
        # Calculate new estimations for the extended route
        estimations = calculate_route_estimations(bookings)
        
        # Update route with new estimations
        route.total_distance_km = estimations.total_distance_km
        route.total_time_minutes = estimations.total_time_minutes
        
        # Delete existing route bookings
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == request.route_id
        ).delete()
        
        # Create new route bookings with updated order
        for i, booking_id in enumerate(all_booking_ids):
            route_booking = RouteManagementBooking(
                route_id=request.route_id,
                booking_id=booking_id,
                stop_order=i + 1,
                estimated_pickup_time=estimations.estimated_pickup_times.get(booking_id),
                estimated_drop_time=estimations.estimated_drop_times.get(booking_id),
                distance_from_previous=5.0 if i > 0 else 0.0,
                cumulative_distance=(i + 1) * 5.0
            )
            db.add(route_booking)
        
        db.commit()
        
        return RouteWithEstimations(
            route_id=request.route_id,
            bookings=bookings,
            estimations=estimations
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating route: {str(e)}")

@router.delete("/delete/{route_id}")
async def delete_route(
    route_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a route by its ID.
    """
    try:
        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id, 
            RouteManagement.is_active == True
        ).first()
        
        if not route:
            raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
        
        # Soft delete route bookings first
        route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        
        for rb in route_bookings:
            db.delete(rb)
        
        # Soft delete the route by setting is_active to False
        route.is_active = False
        db.commit()
        
        return {
            "message": f"Route {route_id} deleted successfully",
            "deleted_route_id": route_id
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting route: {str(e)}")

@router.get("/routes")
async def get_all_routes(
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """
    Get all active routes with their details.
    """
    try:
        routes = db.query(RouteManagement).filter(
            RouteManagement.tenant_id == tenant_id, 
            RouteManagement.is_active == True
        ).all()
        
        if not routes:
            return {
                "routes": [],
                "total_routes": 0,
                "message": f"No active routes found for tenant {tenant_id}"
            }
        
        route_responses = []
        for route in routes:
            route_bookings = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route.route_id
            ).order_by(RouteManagementBooking.stop_order).all()
            
            booking_ids = [rb.booking_id for rb in route_bookings]
            bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []
            
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
            
            route_response = RouteWithEstimations(
                route_id=route.route_id,
                bookings=bookings,
                estimations=estimations
            )
            route_responses.append(route_response)
        
        return {
            "routes": route_responses,
            "total_routes": len(route_responses)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving routes: {str(e)}")
