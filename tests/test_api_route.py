import pytest
from fastapi.testclient import TestClient
from datetime import datetime, date
from tests.fixtures import *

def get_auth_header(client, email, password):
    # Login to get the authentication token
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": password}
    )
    
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_route(client, create_shift, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Create a new route
    route_data = {
        "shift_id": create_shift.shift_id,
        "route_code": f"RT-{datetime.now().strftime('%Y%m%d%H%M')}",
        "planned_distance_km": 25.5,
        "planned_duration_minutes": 45,
        "route_date": str(date.today())
    }
    
    response = client.post(
        "/api/routes/",
        json=route_data,
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["shift_id"] == route_data["shift_id"]
    assert data["route_code"] == route_data["route_code"]
    assert data["planned_distance_km"] == route_data["planned_distance_km"]
    assert data["planned_duration_minutes"] == route_data["planned_duration_minutes"]
    assert data["status"] == "Planned"  # Default status
    assert data["route_date"] == route_data["route_date"]
    
    # Test the route_id was created
    assert "route_id" in data
    assert isinstance(data["route_id"], int)

def test_assign_route(client, create_route, create_vendor, create_vehicle, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Assign vendor, vehicle and driver to the route
    update_data = {
        "status": "Assigned",
        "assigned_vendor_id": create_vendor.vendor_id,
        "assigned_vehicle_id": create_vehicle.vehicle_id,
        "assigned_driver_id": create_driver.driver_id
    }
    
    response = client.put(
        f"/api/routes/{create_route.route_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["route_id"] == create_route.route_id
    assert data["status"] == update_data["status"]
    assert data["assigned_vendor_id"] == update_data["assigned_vendor_id"]
    assert data["assigned_vehicle_id"] == update_data["assigned_vehicle_id"]
    assert data["assigned_driver_id"] == update_data["assigned_driver_id"]

def test_update_route_status(client, create_route, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Update route status
    update_data = {
        "status": "In Progress"
    }
    
    response = client.put(
        f"/api/routes/{create_route.route_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["route_id"] == create_route.route_id
    assert data["status"] == update_data["status"]

def test_complete_route(client, create_route, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Complete the route with actual metrics
    update_data = {
        "status": "Completed",
        "actual_distance_km": 27.3,
        "actual_duration_minutes": 52
    }
    
    response = client.put(
        f"/api/routes/{create_route.route_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["route_id"] == create_route.route_id
    assert data["status"] == update_data["status"]
    assert data["actual_distance_km"] == update_data["actual_distance_km"]
    assert data["actual_duration_minutes"] == update_data["actual_duration_minutes"]
    assert "completed_at" in data and data["completed_at"] is not None

def test_get_route_bookings(client, create_route_booking, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Get all bookings for a specific route
    response = client.get(
        f"/api/routes/{create_route_booking.route_id}/bookings",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Check if our created route_booking is in the response
    booking_found = False
    for booking in data:
        if booking["booking_id"] == create_route_booking.booking_id:
            booking_found = True
            assert booking["planned_eta_minutes"] == create_route_booking.planned_eta_minutes
    
    assert booking_found is True
