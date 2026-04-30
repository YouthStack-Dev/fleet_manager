try:
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from datetime import datetime, time
import requests
from fastapi import HTTPException

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = f"https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_MAPS_API_KEY = "AIzaSyCI7CwlYJ6Qt5pQGW--inSsJmdEManW-K0" 

def calculate_distance(lat1, lng1, lat2, lng2):
    import math
    # Haversine formula for distance calculation
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lat2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def find_centroid_origin(group, drop_lat, drop_lng):
    # Calculate distances from each pickup to destination
    distances = []
    for booking in group:
        dist = calculate_distance(booking["pickup_latitude"], booking["pickup_longitude"], drop_lat, drop_lng)
        distances.append((dist, booking))
    
    # Sort by distance (descending) and use the farthest as origin
    distances.sort(key=lambda x: x[0], reverse=True)
    return distances[0][1]

def generate_optimal_route(group, drop_lat, drop_lng, drop_address, shift_time, deadline_minutes=600, buffer_minutes=15, use_centroid=True):
    # Parse shift time to minutes
    if isinstance(shift_time, str):
        shift_hours, shift_minutes = map(int, shift_time.split(":"))
    elif isinstance(shift_time, time):
        shift_hours, shift_minutes = shift_time.hour, shift_time.minute
    else:
        raise TypeError(f"Unsupported type for shift_time: {type(shift_time)}")

    shift_time_minutes = shift_hours * 60 + shift_minutes

    # Choose origin based on use_centroid flag
    if use_centroid:
        origin_booking = find_centroid_origin(group, drop_lat, drop_lng)
    else:
        origin_booking = group[0]

    remaining_bookings = [booking for booking in group if booking != origin_booking]
    
    origin = f"{origin_booking['pickup_latitude']},{origin_booking['pickup_longitude']}"
    waypoints = "|".join([f"{b['pickup_latitude']},{b['pickup_longitude']}" for b in remaining_bookings])
    
    logger.info("🗺️  Step 3: Preparing Google Maps API request...")
    logger.info(f"  Origin (booking #{origin_booking['booking_id']}): {origin}")
    logger.info(f"  Destination (drop point): {drop_lat},{drop_lng}")
    logger.info(f"  Waypoints: {len(remaining_bookings)} stops")
    if remaining_bookings:
        for idx, b in enumerate(remaining_bookings, 1):
            logger.info(f"    Waypoint {idx}: Booking #{b['booking_id']} at ({b['pickup_latitude']}, {b['pickup_longitude']})")

    params = {
        "origin": origin,
        "destination": f"{drop_lat},{drop_lng}",
        "waypoints": f"optimize:true|{waypoints}" if waypoints else "",
        "key": GOOGLE_MAPS_API_KEY
    }

    logger.info(f"🌐 Step 4: Calling Google Maps Directions API...")
    logger.info(f"  URL: {URL}")
    logger.info(f"  Origin: {params['origin']}")
    logger.info(f"  Destination: {params['destination']}")
    logger.info(f"  Waypoints: {params['waypoints'][:100]}..." if len(params.get('waypoints', '')) > 100 else f"  Waypoints: {params['waypoints']}")
    
    response = requests.get(URL, params=params)
    logger.info(f"📡 API Response Status: {response.status_code}")

    if response.status_code != 200:
        logger.error(f"❌ Google Maps API request FAILED - Status: {response.status_code}")
        logger.error(f"Response: {response.text}")
        return []  # Return an empty list instead of raising an exception

    data = response.json()
    logger.info(f"📊 API returned {len(data.get('routes', []))} route(s)")
    
    if not data.get("routes"):
        logger.error("❌ Google Maps API returned NO routes")
        logger.error(f"Full API response: {data}")
        return []  # Return an empty list instead of raising an exception
    
    logger.info("✅ Google Maps API call successful")

    route = data["routes"][0]
    order = route.get("waypoint_order", [])
    leg_data = route.get("legs", [])

    logger.info("🔄 Step 5: Processing route optimization results...")
    logger.info(f"  Waypoint order: {order}")
    logger.info(f"  Total legs in route: {len(leg_data)}")
    
    distance = sum(leg["distance"]["value"] for leg in leg_data) / 1000  # km
    duration = sum(leg["duration"]["value"] for leg in leg_data) / 60    # minutes
    
    logger.info(f"  Total distance: {distance:.2f} km")
    logger.info(f"  Total travel time: {duration:.2f} minutes")

    # Reorder bookings: origin booking + optimized order of remaining bookings
    ordered = [origin_booking] + [remaining_bookings[i] for i in order] if waypoints else [origin_booking]
    logger.info(f"  Optimized booking sequence: {[b['booking_id'] for b in ordered]}")

    # Calculate total time for each pickup point to reach destination
    total_route_time = sum(leg["duration"]["value"] for leg in leg_data) / 60  # minutes
    pickup_time_per_stop = 2  # minutes per pickup
    total_pickup_time = len(ordered) * pickup_time_per_stop
    
    # Total route duration = travel time + pickup times + buffer
    total_route_duration = total_route_time + total_pickup_time + buffer_minutes
    
    logger.info("⏱️  Step 6: Calculating timings...")
    logger.info(f"  Travel time: {total_route_time:.1f} mins")
    logger.info(f"  Pickup stops: {len(ordered)} × 2 mins = {total_pickup_time} mins")
    logger.info(f"  Buffer: {buffer_minutes} mins")
    logger.info(f"  Total route duration: {total_route_duration:.1f} mins")

    # Calculate base pickup time by working backwards from shift time
    base_pickup_time = shift_time_minutes - total_route_duration
    logger.info(f"  Base pickup time (shift - total duration): {base_pickup_time:.0f} mins = {int(base_pickup_time//60):02d}:{int(base_pickup_time%60):02d}")

    # Calculate pickup times for each stop
    logger.info("📋 Step 7: Calculating pickup schedule for each stop...")
    pickup_order = []
    for i, booking in enumerate(ordered):
        remaining_legs = leg_data[i:]
        remaining_travel_time = sum(leg["duration"]["value"] for leg in remaining_legs) / 60
        distance_to_destination = sum(leg["distance"]["value"] for leg in remaining_legs) / 1000
        
        # Calculate actual pickup time (base time + 2 mins per previous pickup)
        actual_pickup_time = base_pickup_time + (i * 2)
        
        # Format time as HH:MM
        hours = int(actual_pickup_time // 60)
        minutes = int(actual_pickup_time % 60)
        formatted_pickup_time = f"{hours:02d}:{minutes:02d}"
        
        logger.info(
            f"  Stop {i+1}/{len(ordered)}: Booking #{booking['booking_id']} - "
            f"Pickup @ {formatted_pickup_time}, Distance to drop: {distance_to_destination:.2f}km, "
            f"Travel time: {remaining_travel_time:.1f} mins"
        )
        
        pickup_order.append({
            "order_id": i + 1,
            "booking_id": booking["booking_id"],
            "pickup_lat": booking["pickup_latitude"],
            "pickup_lng": booking["pickup_longitude"],
            "estimated_pickup_time_minutes": actual_pickup_time,
            "estimated_drop_time_formatted": shift_time,
            "estimated_pickup_time_formatted": formatted_pickup_time,
            "estimated_distance_km": round(distance_to_destination, 2),
            "estimated_distance_formatted": f"{round(distance_to_destination, 2)} km",
            "travel_time_to_destination": f"{int(remaining_travel_time)} mins"
        })

    final_routes = []
    route_result = {
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
    final_routes.append(route_result)
    
    logger.info("🎉 PICKUP ROUTE OPTIMIZATION COMPLETED SUCCESSFULLY")
    logger.info(f"✅ Final Route: {len(ordered)} bookings, {route_result['estimated_distance']}, {route_result['estimated_time']}")
    logger.info(f"📦 Booking sequence: {route_result['booking_ids']}")
    logger.info("="*80)

    return final_routes

def generate_drop_route(group, office_lat, office_lng, office_address,buffer_minutes=15, start_time_minutes=1020, optimize_route: str ="true"):
    """
    Generate optimal route from office to varying drop locations
    Args:
        group: List of booking dictionaries with drop locations
        office_lat, office_lng: Office coordinates
        office_address: Office address
        start_time_minutes: Start time from office (default 5:00 PM = 1020 minutes)
    """
    logger.info("="*80)
    logger.info("🚀 STARTING DROP ROUTE OPTIMIZATION")
    logger.info(f"🏢 Office Location: ({office_lat}, {office_lng}) - {office_address}")
    logger.info(f"⏰ Start Time: {start_time_minutes} mins ({start_time_minutes//60:02d}:{start_time_minutes%60:02d}), Buffer: {buffer_minutes} mins")
    logger.info(f"📦 Total Bookings: {len(group)}")
    logger.info(f"🎯 Optimize: {optimize_route}")
    
    # Log all booking details
    for idx, booking in enumerate(group, 1):
        logger.info(
            f"  Booking {idx}/{len(group)}: ID={booking.get('booking_id')}, "
            f"Employee={booking.get('employee_code')}, "
            f"Drop=({booking.get('drop_latitude')}, {booking.get('drop_longitude')})"
        )
    
    # Validate all coordinates are within reasonable distance (500km radius)
    logger.info("🔍 Step 1: Validating coordinate proximity (max 500km radius)...")
    
    def _validate_coordinates(lat1, lon1, lat2, lon2, max_distance_km=500):
        """Check if two coordinates are within max_distance_km using Haversine formula."""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in km
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        return distance <= max_distance_km, distance
    
    # Validate all drop locations are near the office
    for idx, booking in enumerate(group, 1):
        drop_lat = booking.get('drop_latitude')
        drop_lon = booking.get('drop_longitude')
        
        if not drop_lat or not drop_lon:
            logger.error(
                f"❌ Validation FAILED - Booking {booking.get('booking_id')} "
                f"missing drop coordinates (lat={drop_lat}, lon={drop_lon})"
            )
            return []
        
        is_valid, distance = _validate_coordinates(office_lat, office_lng, drop_lat, drop_lon)
        logger.info(f"  ✓ Booking {idx}: Distance from office = {distance:.2f}km {'✓ VALID' if is_valid else '✗ INVALID'}")
        
        if not is_valid:
            logger.error(
                f"❌ Validation FAILED - Booking {booking.get('booking_id')} ({booking.get('employee_code')}) "
                f"has invalid drop location: {distance:.1f}km from office. "
                f"Drop coordinates: ({drop_lat}, {drop_lon}) vs Office: ({office_lat}, {office_lng}). "
                f"Max allowed distance: 500km. This location appears to be in a different region/country."
            )
            return []
    
    logger.info("✅ All coordinates validated successfully")
    
    # Use office as origin and all drop locations as waypoints
    origin = f"{office_lat},{office_lng}"
    waypoints = "|".join([f"{b['drop_latitude']},{b['drop_longitude']}" for b in group])
    
    print(f"Origin (Office): {origin}, Waypoints (Drop locations): {waypoints}")

    params = {
        "origin": origin,
        "destination": origin,  # Return to office (circular route)
        "waypoints": f"optimize:{optimize_route}|{waypoints}",
        "key": GOOGLE_MAPS_API_KEY
    }

    logger.info(f"Requesting Google Maps directions API with params: {params}")
    response = requests.get(URL, params=params)

    if response.status_code != 200:
        logger.error(f"Google Maps API request failed: {response.text}")
        return []  # Return an empty list instead of raising an exception

    data = response.json()
    logger.info(f"📊 API returned {len(data.get('routes', []))} route(s)")
    
    if not data.get("routes"):
        logger.error("❌ Google Maps API returned NO routes")
        logger.error(f"Full API response: {data}")
        return []  # Return an empty list instead of raising an exception
    
    logger.info("✅ Google Maps API call successful")

    route = data["routes"][0]
    order = route.get("waypoint_order", [])
    leg_data = route.get("legs", [])

    logger.info("🔄 Step 4: Processing route optimization results...")
    logger.info(f"  Waypoint order: {order}")
    logger.info(f"  Total legs in route: {len(leg_data)}")
    
    distance = sum(leg["distance"]["value"] for leg in leg_data[:-1]) / 1000  # km (exclude return to office)
    duration = sum(leg["duration"]["value"] for leg in leg_data[:-1]) / 60    # minutes (exclude return to office)
    
    logger.info(f"  Total distance (excluding return): {distance:.2f} km")
    logger.info(f"  Total travel time (excluding return): {duration:.2f} minutes")

    # Reorder bookings based on optimized waypoint order
    ordered = [group[i] for i in order]
    logger.info(f"  Optimized booking sequence: {[b['booking_id'] for b in ordered]}")

    # Calculate drop times starting from office
    logger.info("📋 Step 5: Calculating drop-off schedule for each stop...")
    logger.info(f"  Starting from office at {start_time_minutes//60:02d}:{start_time_minutes%60:02d}")
    
    current_time = start_time_minutes
    current_distance = 0
    drop_order = []
    
    for i, booking in enumerate(ordered):
        # Add travel time from previous location
        if i == 0:
            # First drop: office to first location
            travel_time = leg_data[0]["duration"]["value"] / 60  # minutes
            travel_distance = leg_data[0]["distance"]["value"] / 1000  # km
            logger.info(f"  First leg: Office → Booking #{booking['booking_id']}, {travel_distance:.2f}km, {travel_time:.1f} mins")
        else:
            # Subsequent drops: previous location to current location
            travel_time = leg_data[i]["duration"]["value"] / 60  # minutes
            travel_distance = leg_data[i]["distance"]["value"] / 1000  # km
            logger.info(f"  Leg {i+1}: Booking #{ordered[i-1]['booking_id']} → Booking #{booking['booking_id']}, {travel_distance:.2f}km, {travel_time:.1f} mins")
        
        current_time += travel_time + 2  # Add 2 minutes for drop-off time
        current_distance += travel_distance
        
        drop_time_formatted = f"{int(current_time // 60):02d}:{int(current_time % 60):02d}"
        logger.info(
            f"  Stop {i+1}/{len(ordered)}: Booking #{booking['booking_id']} - "
            f"Drop @ {drop_time_formatted}, Cumulative distance: {current_distance:.2f}km"
        )
        
        drop_time_formatted = f"{int(current_time // 60):02d}:{int(current_time % 60):02d}"
        logger.info(
            f"  Stop {i+1}/{len(ordered)}: Booking #{booking['booking_id']} - "
            f"Drop @ {drop_time_formatted}, Cumulative distance: {current_distance:.2f}km"
        )
        
        drop_order.append({
            "order_id": i + 1,  # Add order_id
            "booking_id": booking["booking_id"],
            "drop_lat": booking["drop_latitude"],
            "drop_lng": booking["drop_longitude"],
            "estimated_pickup_time_formatted": f"{start_time_minutes // 60:02d}:{start_time_minutes % 60:02d}",
            "estimated_drop_time_minutes": current_time,
            "estimated_drop_time_formatted": drop_time_formatted,
            "estimated_distance_km": round(current_distance, 2),
            "estimated_distance_formatted": f"{round(current_distance, 2)} km",
            "travel_time_from_office": f"{int(current_time - start_time_minutes)} mins"
        })

    total_route_duration = current_time - start_time_minutes
    logger.info(f"⏱️  Total route duration from office: {total_route_duration:.1f} mins")

    final_routes = []
    route_result = {
        "temp_route_id": 1,
        "booking_ids": [b["booking_id"] for b in ordered],
        "pickup_order": drop_order,
        "estimated_time": f"{int(duration)} mins",
        "estimated_distance": f"{round(distance, 1)} km",
        "total_route_duration": f"{int(total_route_duration)} mins",
        "buffer_time": f"{buffer_minutes} mins",
        "start_time": f"{int(start_time_minutes // 60):02d}:{int(start_time_minutes % 60):02d}",
        "office_lat": office_lat,
        "office_lng": office_lng,
        "office_address": office_address
    }
    final_routes.append(route_result)
    
    logger.info("🎉 DROP ROUTE OPTIMIZATION COMPLETED SUCCESSFULLY")
    logger.info(f"✅ Final Route: {len(ordered)} bookings, {route_result['estimated_distance']}, {route_result['estimated_time']}")
    logger.info(f"📦 Booking sequence: {route_result['booking_ids']}")
    logger.info(f"🕐 Start time: {route_result['start_time']}")
    logger.info("="*80)

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
    shift_time = "09:00"  # 9:00 AM shift time
    final_routes = generate_optimal_route(group, DROP_LAT, DROP_LNG, DROP_ADDRESS, shift_time, deadline_time, buffer_time)
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