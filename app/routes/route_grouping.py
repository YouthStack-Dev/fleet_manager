from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
import numpy as np
from sklearn.cluster import KMeans
from pydantic import BaseModel
import math

from app.database.session import get_db
from app.models import Booking, Shift
# from app.services.clustering_algorithm import group_rides
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
                'booking_id': booking.booking_id,
                'user': booking.employee_id,
                'employee_code': booking.employee_code,
                'lat': getattr(booking, lat),
                'lon': getattr(booking, long),
                'pickup_location': booking.pickup_location,
                'drop_location': booking.drop_location,
            }
            
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


        # clustering_strategy = determine_clustering_strategy(valid_rides)
        
        # # Generate route clusters based on the determined strategy
        # route_clusters = generate_route_clusters(valid_rides, num_clusters, clustering_strategy)
        
        return {
            # "bookings": bookings,
            "route_clusters": clusters,
            "total_bookings": len(bookings),
            # "clustered_bookings": sum(clusters),
            "total_clusters": len(clusters),
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving bookings and generating clusters: {str(e)}"
        )


@router.post("/split-cluster")
async def split_cluster(
    booking_date: date = Query(..., description="Date for the bookings (YYYY-MM-DD)"),
    shift_id: int = Query(..., description="Shift ID to filter bookings"),
    cluster_id: int = Query(..., description="Cluster ID to split"),
    num_splits: int = Query(2, description="Number of sub-clusters to create"),
    db: Session = Depends(get_db)
):
    """
    Split a specific cluster into smaller sub-clusters.
    
    Args:
        booking_date: The date to filter bookings
        shift_id: The shift ID to filter bookings
        cluster_id: The cluster ID to split
        num_splits: Number of sub-clusters to create
        db: Database session
    
    Returns:
        Dictionary containing the split clusters
    """
    try:
        # First get all clusters for the date and shift
        bookings = db.query(Booking).filter(
            Booking.booking_date == booking_date,
            Booking.shift_id == shift_id
        ).all()
        
        if not bookings:
            raise HTTPException(
                status_code=404, 
                detail=f"No bookings found for date {booking_date} and shift ID {shift_id}"
            )
        
        # Convert bookings to rides format
        rides = []
        for booking in bookings:
            ride = {
                'booking_id': booking.booking_id,
                'user': booking.employee_id,
                'employee_code': booking.employee_code,
                'lat': booking.drop_latitude,
                'lon': booking.drop_longitude,
                'drop_location': booking.drop_location,
                'pickup_location': booking.pickup_location,
                'pickup_lat': booking.pickup_latitude,
                'pickup_lon': booking.pickup_longitude,
                'status': booking.status,
            }
            rides.append(ride)
        
        # Generate initial clusters to find the target cluster
        valid_rides = [r for r in rides if r['lat'] is not None and r['lon'] is not None]
        clustering_strategy = determine_clustering_strategy(valid_rides)
        initial_clusters = generate_route_clusters(valid_rides, 10, clustering_strategy)  # Generate more clusters initially
        
        # Find the target cluster
        target_cluster = None
        for cluster in initial_clusters:
            if cluster['cluster_id'] == cluster_id:
                target_cluster = cluster
                break
        
        if not target_cluster:
            raise HTTPException(
                status_code=404,
                detail=f"Cluster with ID {cluster_id} not found"
            )
        
        # Split the target cluster
        cluster_bookings = target_cluster['bookings']
        if len(cluster_bookings) <= num_splits:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot split cluster with {len(cluster_bookings)} bookings into {num_splits} sub-clusters"
            )
        
        # Generate sub-clusters
        sub_clusters = generate_route_clusters(cluster_bookings, num_splits, clustering_strategy)
        
        # Update cluster IDs to be unique
        for i, sub_cluster in enumerate(sub_clusters):
            sub_cluster['cluster_id'] = f"{cluster_id}.{i + 1}"
            sub_cluster['parent_cluster_id'] = cluster_id
        
        return {
            "original_cluster": target_cluster,
            "sub_clusters": sub_clusters,
            "total_sub_clusters": len(sub_clusters),
            "clustering_strategy": clustering_strategy
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error splitting cluster: {str(e)}"
        )


@router.post("/generate-clusters")
async def generate_clusters_from_bookings(
    request: ClusterGenerationRequest
):
    """
    Generate clusters from a provided list of bookings.
    
    Args:
        request: ClusterGenerationRequest containing bookings list and cluster count
    
    Returns:
        Dictionary containing generated route clusters
    """
    try:
        if not request.bookings:
            raise HTTPException(
                status_code=400,
                detail="No bookings provided"
            )
        
        # Convert input bookings to rides format
        rides = []
        for booking_input in request.bookings:
            ride = {
                'booking_id': booking_input.booking_id,
                'user': booking_input.employee_id,
                'employee_code': booking_input.employee_code,
                'lat': booking_input.drop_latitude,
                'lon': booking_input.drop_longitude,
                'drop_location': booking_input.drop_location,
                'pickup_location': booking_input.pickup_location,
                'pickup_lat': booking_input.pickup_latitude,
                'pickup_lon': booking_input.pickup_longitude,
                'status': booking_input.status,
            }
            rides.append(ride)
        
        # Filter out rides without valid coordinates
        valid_rides = [r for r in rides if r['lat'] is not None and r['lon'] is not None]
        
        if not valid_rides:
            return {
                "route_clusters": [],
                "message": "No bookings with valid coordinates found for clustering",
                "total_bookings": len(rides),
                "clustered_bookings": 0,
                "total_clusters": 0
            }
        
        # Determine clustering strategy and generate clusters
        clustering_strategy = determine_clustering_strategy(valid_rides)
        route_clusters = generate_route_clusters(valid_rides, request.num_clusters, clustering_strategy)
        
        return {
            "route_clusters": route_clusters,
            "total_bookings": len(rides),
            "clustered_bookings": len(valid_rides),
            "total_clusters": len(route_clusters),
            "clustering_strategy": clustering_strategy
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating clusters from bookings: {str(e)}"
        )


@router.post("/optimize-route")
async def optimize_route(
    request: RouteOptimizationRequest
):
    """
    Generate optimal route for given bookings using nearest neighbor algorithm.
    
    Args:
        request: RouteOptimizationRequest containing bookings and route preferences
    
    Returns:
        Dictionary containing optimized route with stops, distances, and time estimates
    """
    try:
        if not request.bookings:
            raise HTTPException(
                status_code=400,
                detail="No bookings provided for route optimization"
            )
        
        # Convert input bookings to route points
        route_points = []
        for booking_input in request.bookings:
            # Use drop location as the destination for route optimization
            if booking_input.drop_latitude and booking_input.drop_longitude:
                route_point = {
                    'booking_id': booking_input.booking_id,
                    'employee_code': booking_input.employee_code,
                    'lat': booking_input.drop_latitude,
                    'lon': booking_input.drop_longitude,
                    'location_name': booking_input.drop_location
                }
                route_points.append(route_point)
        
        if not route_points:
            raise HTTPException(
                status_code=400,
                detail="No valid coordinates found in provided bookings"
            )
        
        # Set start location (office or first booking pickup location)
        start_location = request.start_location
        if not start_location and request.bookings[0].pickup_latitude and request.bookings[0].pickup_longitude:
            start_location = {
                "lat": request.bookings[0].pickup_latitude,
                "lon": request.bookings[0].pickup_longitude
            }
        
        # Generate optimal route
        optimal_route = generate_optimal_route(
            route_points, 
            start_location, 
            request.return_to_start
        )
        
        return {
            "optimal_route": optimal_route,
            "total_stops": len(optimal_route.route_stops),
            "optimization_method": "nearest_neighbor"
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error optimizing route: {str(e)}"
        )


def determine_clustering_strategy(rides: List[Dict]) -> str:
    """
    Determine whether to cluster by pickup or drop locations based on location patterns.
    
    Args:
        rides: List of ride dictionaries with pickup and drop coordinates
    
    Returns:
        String indicating clustering strategy: "drop" or "pickup"
    """
    if not rides:
        return "drop"
    
    # Get unique pickup locations (with some tolerance for GPS variations)
    pickup_locations = set()
    for ride in rides:
        if ride['pickup_lat'] is not None and ride['pickup_lon'] is not None:
            # Round to 4 decimal places (~11m precision) to group nearby locations
            pickup_key = (round(ride['pickup_lat'], 4), round(ride['pickup_lon'], 4))
            pickup_locations.add(pickup_key)
    
    # If most rides share the same pickup location, cluster by drop locations
    if len(pickup_locations) <= max(1, len(rides) * 0.2):  # 20% or less unique pickup locations
        return "drop"
    else:
        return "pickup"


def generate_route_clusters(rides: List[Dict], num_clusters: int, strategy: str = "drop") -> List[Dict[str, Any]]:
    """
    Generate route clusters from ride data using KMeans clustering.
    
    Args:
        rides: List of ride dictionaries with lat, lon info
        num_clusters: Number of clusters to generate
        strategy: "drop" to cluster by drop locations, "pickup" to cluster by pickup locations
    
    Returns:
        List of route clusters with grouped bookings
    """
    
    if len(rides) <= 1:
        coords = get_coordinates_for_strategy(rides[0], strategy) if rides else (0, 0)
        return [{
            "cluster_id": 1,
            "bookings": rides,
            "booking_count": len(rides),
            "center_coordinates": {
                "lat": coords[0],
                "lon": coords[1]
            },
            "clustering_strategy": strategy
        }]
    
    # Prepare data for clustering based on strategy
    valid_rides_for_clustering = []
    X_data = []
    
    for ride in rides:
        coords = get_coordinates_for_strategy(ride, strategy)
        if coords[0] is not None and coords[1] is not None:
            valid_rides_for_clustering.append(ride)
            X_data.append(coords)
    
    if not X_data:
        return [{
            "cluster_id": 1,
            "bookings": rides,
            "booking_count": len(rides),
            "center_coordinates": {"lat": 0, "lon": 0},
            "clustering_strategy": strategy
        }]
    
    X = np.array(X_data)
    
    # Adjust number of clusters if we have fewer rides than requested clusters
    effective_clusters = min(num_clusters, len(valid_rides_for_clustering))
    
    if effective_clusters == 1:
        # If only one cluster, return all rides in single cluster
        center_lat = sum(coord[0] for coord in X_data) / len(X_data)
        center_lon = sum(coord[1] for coord in X_data) / len(X_data)
        
        return [{
            "cluster_id": 1,
            "bookings": valid_rides_for_clustering,
            "booking_count": len(valid_rides_for_clustering),
            "center_coordinates": {
                "lat": center_lat,
                "lon": center_lon
            },
            "clustering_strategy": strategy
        }]
    
    # Perform KMeans clustering
    kmeans = KMeans(n_clusters=effective_clusters, random_state=0, n_init=10).fit(X)
    labels = kmeans.labels_
    
    # Group rides by cluster
    clusters = [[] for _ in range(effective_clusters)]
    for label, ride in zip(labels, valid_rides_for_clustering):
        clusters[label].append(ride)
    
    # Create cluster information
    final_clusters = []
    cluster_id = 1
    
    for cluster in clusters:
        if cluster:  # Only add non-empty clusters
            # Calculate cluster center based on strategy
            coords_list = [get_coordinates_for_strategy(r, strategy) for r in cluster]
            valid_coords = [c for c in coords_list if c[0] is not None and c[1] is not None]
            
            if valid_coords:
                center_lat = sum(c[0] for c in valid_coords) / len(valid_coords)
                center_lon = sum(c[1] for c in valid_coords) / len(valid_coords)
            else:
                center_lat, center_lon = 0, 0
            
            cluster_info = {
                "cluster_id": cluster_id,
                "bookings": cluster,
                "booking_count": len(cluster),
                "center_coordinates": {
                    "lat": center_lat,
                    "lon": center_lon
                },
                "clustering_strategy": strategy
            }
            final_clusters.append(cluster_info)
            cluster_id += 1
    
    return final_clusters


def get_coordinates_for_strategy(ride: Dict, strategy: str) -> tuple:
    """
    Get coordinates based on clustering strategy.
    
    Args:
        ride: Ride dictionary
        strategy: "drop" or "pickup"
    
    Returns:
        Tuple of (latitude, longitude)
    """
    if strategy == "pickup":
        return (ride['pickup_lat'], ride['pickup_lon'])
    else:  # default to drop
        return (ride['lat'], ride['lon'])


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth using Haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of first point in decimal degrees
        lat2, lon2: Latitude and longitude of second point in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of Earth in kilometers
    r = 6371
    
    return c * r


def generate_optimal_route(
    route_points: List[Dict], 
    start_location: Optional[Dict[str, float]] = None,
    return_to_start: bool = True
) -> OptimalRoute:
    """
    Generate optimal route using nearest neighbor algorithm.
    
    Args:
        route_points: List of route points with coordinates
        start_location: Starting location coordinates
        return_to_start: Whether to return to starting location
    
    Returns:
        OptimalRoute object with ordered stops and distance calculations
    """
    if not route_points:
        return OptimalRoute(
            route_stops=[],
            total_distance_km=0,
            estimated_time_minutes=0,
            start_location=start_location
        )
    
    # If no start location provided, use the first route point
    if not start_location:
        start_location = {
            "lat": route_points[0]['lat'],
            "lon": route_points[0]['lon']
        }
    
    # Implement nearest neighbor algorithm
    unvisited = route_points.copy()
    route_stops = []
    current_location = start_location
    total_distance = 0
    stop_order = 1
    
    while unvisited:
        # Find nearest unvisited point
        min_distance = float('inf')
        nearest_point = None
        nearest_index = -1
        
        for i, point in enumerate(unvisited):
            distance = calculate_distance(
                current_location['lat'], current_location['lon'],
                point['lat'], point['lon']
            )
            if distance < min_distance:
                min_distance = distance
                nearest_point = point
                nearest_index = i
        
        # Add nearest point to route
        total_distance += min_distance
        
        route_stop = RouteStop(
            booking_id=nearest_point['booking_id'],
            employee_code=nearest_point['employee_code'],
            location_name=nearest_point['location_name'],
            latitude=nearest_point['lat'],
            longitude=nearest_point['lon'],
            stop_order=stop_order,
            distance_from_previous=round(min_distance, 2),
            cumulative_distance=round(total_distance, 2)
        )
        
        route_stops.append(route_stop)
        
        # Update current location and remove visited point
        current_location = {'lat': nearest_point['lat'], 'lon': nearest_point['lon']}
        unvisited.pop(nearest_index)
        stop_order += 1
    
    # Add return trip if requested
    if return_to_start and route_stops:
        return_distance = calculate_distance(
            current_location['lat'], current_location['lon'],
            start_location['lat'], start_location['lon']
        )
        total_distance += return_distance
    
    # Estimate travel time (assuming average speed of 25 km/h in city traffic)
    average_speed_kmh = 25
    estimated_time_minutes = (total_distance / average_speed_kmh) * 60
    
    # Add time for stops (assuming 3 minutes per stop)
    stop_time_minutes = len(route_stops) * 3
    estimated_time_minutes += stop_time_minutes
    
    return OptimalRoute(
        route_stops=route_stops,
        total_distance_km=round(total_distance, 2),
        estimated_time_minutes=round(estimated_time_minutes, 1),
        start_location=start_location
    )



#TODO:

# 1. Estimated pick up time - for employees 
# 2. Estimated drop time - for employees 
# 3. Estimated kms - employee to employee
# 4. Estimated total time -  employee to employee
# 4. Estimated total kms - beggining to end
# 5. Estimated total time - including pick up and drop time
# 6. Geder pick from employee table
