import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from tests.fixtures import *

def get_auth_header(client, email, password):
    response = client.post(
        "/api/auth/token",
        data={
            "username": email,
            "password": password,
        },
    )
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}

def test_create_route(client, create_shift, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Create a new route
    route_data = {
        "shift_id": create_shift.shift_id,
        "route_code": f"RT-TEST-{datetime.now().strftime('%Y%m%d')}-01",
        "planned_distance_km": 22.5,
        "planned_duration_minutes": 55,
        "is_active": True
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
    
    # Update the route status to InProgress
    update_data = {
        "status": "InProgress",
        "actual_start_time": datetime.now().isoformat()
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
    assert data["actual_start_time"] is not None

def test_complete_route(client, create_route, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Complete the route
    now = datetime.now()
    start_time = now - timedelta(minutes=45)
    
    update_data = {
        "status": "Completed",
        "actual_start_time": start_time.isoformat(),
        "actual_end_time": now.isoformat(),
        "actual_distance_km": 21.2,
        "actual_duration_minutes": 43
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
