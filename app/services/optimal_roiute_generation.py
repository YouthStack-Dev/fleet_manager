try:
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

import requests
from fastapi import HTTPException

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = f"https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_MAPS_API_KEY = "AIzaSyCI7CwlYJ6Qt5pQGW--inSsJmdEManW-K0" 

def generate_optimal_route(group, drop_lat, drop_lng, drop_address, deadline_minutes=600, buffer_minutes=15):

    # Find the pickup location with maximum distance from destination
    def calculate_distance(lat1, lng1, lat2, lng2):
        import math
        # Haversine formula for distance calculation
        R = 6371  # Earth's radius in km
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lat2 - lat1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    # Calculate distances from each pickup to destination
    distances = []
    for booking in group:
        dist = calculate_distance(booking["pickup_latitude"], booking["pickup_longitude"], drop_lat, drop_lng)
        distances.append((dist, booking))
    
    # Sort by distance (descending) and use the farthest as origin
    distances.sort(key=lambda x: x[0], reverse=True)
    origin_booking = distances[0][1]
    remaining_bookings = [booking for booking in group if booking != origin_booking]
    
    origin = f"{origin_booking['pickup_latitude']},{origin_booking['pickup_longitude']}"
    waypoints = "|".join([f"{b['pickup_latitude']},{b['pickup_longitude']}" for b in remaining_bookings])
    
    print(f"Origin (farthest pickup): {origin}, Destination: {drop_lat},{drop_lng}, Waypoints: {waypoints}")

    params = {
        "origin": origin,
        "destination": f"{drop_lat},{drop_lng}",
        "waypoints": f"optimize:true|{waypoints}" if waypoints else "",
        "key": GOOGLE_MAPS_API_KEY
    }

    logger.info(f"Requesting Google Maps directions API with params: {params}")
    response = requests.get(URL, params=params)

    if response.status_code != 200:
        logger.error(f"Google Maps API request failed: {response.text}")
        return []  # Return an empty list instead of raising an exception

    data = response.json()
    if not data.get("routes"):
        logger.warning("Google Maps API returned no routes")
        return []  # Return an empty list instead of raising an exception

    route = data["routes"][0]
    order = route.get("waypoint_order", [])
    leg_data = route.get("legs", [])

    print(route,order,leg_data)
    distance = sum(leg["distance"]["value"] for leg in leg_data) / 1000  # km
    duration = sum(leg["duration"]["value"] for leg in leg_data) / 60    # minutes

    # Reorder bookings: origin booking + optimized order of remaining bookings
    ordered = [origin_booking] + [remaining_bookings[i] for i in order] if waypoints else [origin_booking]

    # Calculate pickup times working backwards from deadline
    pickup_order = []
    
    # Calculate total time for each pickup point to reach destination
    for i, booking in enumerate(ordered):
        # Calculate remaining travel time from this pickup to destination
        remaining_legs = leg_data[i:]
        remaining_travel_time = sum(leg["duration"]["value"] for leg in remaining_legs) / 60  # minutes
        
        # Add pickup time for subsequent passengers (2 minutes each)
        subsequent_pickup_time = (len(ordered) - i - 1) * 2  # 2 minutes per subsequent pickup
        
        # Calculate pickup time: deadline - remaining_travel_time - buffer - subsequent_pickup_time
        pickup_time = deadline_minutes - remaining_travel_time - buffer_minutes - subsequent_pickup_time
        
        # Calculate distance traveled to reach this pickup point
        distance_to_pickup = sum(leg["distance"]["value"] for leg in leg_data[:i]) / 1000 if i > 0 else 0
        
        pickup_order.append({
            "order_id": i + 1,  # Add order_id
            "booking_id": booking["booking_id"],
            "pickup_lat": booking["pickup_latitude"],
            "pickup_lng": booking["pickup_longitude"],
            "estimated_pickup_time_minutes": pickup_time,
            "estimated_pickup_time_formatted": f"{int(pickup_time // 60):02d}:{int(pickup_time % 60):02d}",
            "estimated_distance_km": round(distance_to_pickup, 2),
            "estimated_distance_formatted": f"{round(distance_to_pickup, 2)} km",
            "travel_time_to_destination": f"{int(remaining_travel_time + subsequent_pickup_time)} mins"
        })

    # Calculate earliest pickup time for route duration
    earliest_pickup = min(p["estimated_pickup_time_minutes"] for p in pickup_order)
    latest_arrival = deadline_minutes
    total_route_duration = latest_arrival - earliest_pickup

    final_routes = []
    final_routes.append(
        {
            "temp_route_id": 1,
            "booking_ids": [b["booking_id"] for b in ordered],
            "pickup_order": pickup_order,
            "estimated_time": f"{int(duration)} mins",
            "estimated_distance": f"{round(distance, 1)} km",
            "total_route_duration": f"{int(total_route_duration)} mins",
            "deadline_time": f"{int(deadline_minutes // 60):02d}:{int(deadline_minutes % 60):02d}",
            "buffer_time": f"{buffer_minutes} mins",
            "drop_lat": drop_lat,
            "drop_lng": drop_lng,
            "drop_address": drop_address
        }
    )

    return final_routes

def generate_drop_route(group, office_lat, office_lng, office_address, start_time_minutes=1020):
    """
    Generate optimal route from office to varying drop locations
    Args:
        group: List of booking dictionaries with drop locations
        office_lat, office_lng: Office coordinates
        office_address: Office address
        start_time_minutes: Start time from office (default 5:00 PM = 1020 minutes)
    """
    
    # Use office as origin and all drop locations as waypoints
    origin = f"{office_lat},{office_lng}"
    waypoints = "|".join([f"{b['drop_latitude']},{b['drop_longitude']}" for b in group])
    
    print(f"Origin (Office): {origin}, Waypoints (Drop locations): {waypoints}")

    params = {
        "origin": origin,
        "destination": origin,  # Return to office (circular route)
        "waypoints": f"optimize:true|{waypoints}",
        "key": GOOGLE_MAPS_API_KEY
    }

    logger.info(f"Requesting Google Maps directions API with params: {params}")
    response = requests.get(URL, params=params)

    if response.status_code != 200:
        logger.error(f"Google Maps API request failed: {response.text}")
        return []  # Return an empty list instead of raising an exception

    data = response.json()
    if not data.get("routes"):
        logger.warning("Google Maps API returned no routes")
        return []  # Return an empty list instead of raising an exception

    route = data["routes"][0]
    order = route.get("waypoint_order", [])
    leg_data = route.get("legs", [])

    distance = sum(leg["distance"]["value"] for leg in leg_data[:-1]) / 1000  # km (exclude return to office)
    duration = sum(leg["duration"]["value"] for leg in leg_data[:-1]) / 60    # minutes (exclude return to office)

    # Reorder bookings based on optimized waypoint order
    ordered = [group[i] for i in order]

    # Calculate drop times starting from office
    current_time = start_time_minutes
    current_distance = 0
    drop_order = []
    
    for i, booking in enumerate(ordered):
        # Add travel time from previous location
        if i == 0:
            # First drop: office to first location
            travel_time = leg_data[0]["duration"]["value"] / 60  # minutes
            travel_distance = leg_data[0]["distance"]["value"] / 1000  # km
        else:
            # Subsequent drops: previous location to current location
            travel_time = leg_data[i]["duration"]["value"] / 60  # minutes
            travel_distance = leg_data[i]["distance"]["value"] / 1000  # km
        
        current_time += travel_time + 2  # Add 2 minutes for drop-off time
        current_distance += travel_distance
        
        drop_order.append({
            "order_id": i + 1,  # Add order_id
            "booking_id": booking["booking_id"],
            "drop_lat": booking["drop_latitude"],
            "drop_lng": booking["drop_longitude"],
            "estimated_drop_time_minutes": current_time,
            "estimated_drop_time_formatted": f"{int(current_time // 60):02d}:{int(current_time % 60):02d}",
            "estimated_distance_km": round(current_distance, 2),
            "estimated_distance_formatted": f"{round(current_distance, 2)} km",
            "travel_time_from_office": f"{int(current_time - start_time_minutes)} mins"
        })

    total_route_duration = current_time - start_time_minutes

    final_routes = []
    final_routes.append(
        {
            "temp_route_id": 1,
            "booking_ids": [b["booking_id"] for b in ordered],
            "drop_order": drop_order,
            "estimated_time": f"{int(duration)} mins",
            "estimated_distance": f"{round(distance, 1)} km",
            "total_route_duration": f"{int(total_route_duration)} mins",
            "start_time": f"{int(start_time_minutes // 60):02d}:{int(start_time_minutes % 60):02d}",
            "office_lat": office_lat,
            "office_lng": office_lng,
            "office_address": office_address
        }
    )

    return final_routes

if __name__ == "__main__":
    # Example usage - Updated to use Bangalore coordinates
    DROP_LAT = 12.9316  # Bangalore, India
    DROP_LNG = 77.5946
    DROP_ADDRESS = "Bangalore, India"

    # Sample booking group as dictionaries
    group = [
        {"booking_id": "user20", "pickup_latitude": 12.9254, "pickup_longitude": 77.5828},
        {"booking_id": "user23", "pickup_latitude": 12.9258, "pickup_longitude": 77.5825},
        {"booking_id": "user26", "pickup_latitude": 12.9252, "pickup_longitude": 77.5830},
        {"booking_id": "user37", "pickup_latitude": 12.9256, "pickup_longitude": 77.5827},
    ]

    # Deadline at 10:00 AM (600 minutes from midnight) with 15 minute buffer
    deadline_time = 600  # 10:00 AM in minutes
    buffer_time = 15     # 15 minutes buffer
    final_routes = generate_optimal_route(group, DROP_LAT, DROP_LNG, DROP_ADDRESS, deadline_time, buffer_time)
    for route in final_routes:
        print(f"Route ID: {route['temp_route_id']}")
        print(f"Total Distance: {route['estimated_distance']}")
        print(f"Total Duration: {route['total_route_duration']}")
        print(f"Deadline: {route['deadline_time']} with {route['buffer_time']} buffer")
        print("Pickup Schedule:")
        for pickup in route['pickup_order']:
            print(f"  Booking {pickup['booking_id']}: {pickup['estimated_pickup_time_formatted']} - {pickup['estimated_distance_formatted']} (Travel: {pickup['travel_time_to_destination']})")
        print()

    # Test drop route function
    print("\n" + "="*50)
    print("TESTING DROP ROUTE (Office to Home)")
    print("="*50)
    
    # Office coordinates (Bangalore)
    OFFICE_LAT = 12.9316
    OFFICE_LNG = 77.5946
    OFFICE_ADDRESS = "Office, Bangalore"
    
    # Sample booking group with drop locations as dictionaries
    drop_group = [
        {"booking_id": "user20", "drop_latitude": 12.9254, "drop_longitude": 77.5828},
        {"booking_id": "user23", "drop_latitude": 12.9258, "drop_longitude": 77.5825},
        {"booking_id": "user26", "drop_latitude": 12.9252, "drop_longitude": 77.5830},
        {"booking_id": "user37", "drop_latitude": 12.9256, "drop_longitude": 77.5827},
    ]

    # Start at 5:00 PM (1020 minutes from midnight)
    start_time = 1020  # 5:00 PM in minutes
    drop_routes = generate_drop_route(drop_group, OFFICE_LAT, OFFICE_LNG, OFFICE_ADDRESS, start_time)
    for route in drop_routes:
        print(f"Route ID: {route['temp_route_id']}")
        print(f"Total Distance: {route['estimated_distance']}")
        print(f"Total Duration: {route['total_route_duration']}")
        print(f"Start Time: {route['start_time']} from {route['office_address']}")
        print("Drop Schedule:")
        for drop in route['drop_order']:
            print(f"  Booking {drop['booking_id']}: {drop['estimated_drop_time_formatted']} - {drop['estimated_distance_formatted']} (Travel: {drop['travel_time_from_office']})")
        print()