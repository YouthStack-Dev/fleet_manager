import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta
from tests.fixtures import *

def get_auth_header(client, email, password):
    # Login to get the authentication token
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": password}
    )
    
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_booking(client, create_employee, create_shift, create_team, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Create a new booking
    booking_data = {
        "employee_id": create_employee.employee_id,
        "shift_id": create_shift.shift_id,
        "booking_date": str(date.today() + timedelta(days=1)),
        "pickup_latitude": 28.6139,
        "pickup_longitude": 77.2090,
        "pickup_location": "Test Home Address",
        "drop_latitude": 28.7041,
        "drop_longitude": 77.1025,
        "drop_location": "Office Location",
        "team_id": create_team.team_id,
        "booking_type": "Regular"
    }
    
    response = client.post(
        "/api/bookings/",
        json=booking_data,
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["employee_id"] == booking_data["employee_id"]
    assert data["shift_id"] == booking_data["shift_id"]
    assert data["booking_date"] == booking_data["booking_date"]
    assert data["pickup_location"] == booking_data["pickup_location"]
    assert data["drop_location"] == booking_data["drop_location"]
    assert data["booking_type"] == booking_data["booking_type"]
    assert data["status"] == "Pending"  # Default status
    
    # Test the booking_id was created
    assert "booking_id" in data
    assert isinstance(data["booking_id"], int)

def test_get_bookings(client, create_booking, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Get all bookings
    response = client.get(
        "/api/bookings/",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1  # At least our created booking should be there
    
    # Check if our created booking is in the list
    found = False
    for booking in data["items"]:
        if booking["booking_id"] == create_booking.booking_id:
            found = True
            break
    
    assert found == True

def test_update_booking_status(client, create_booking, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Update the booking status
    update_data = {
        "status": "Confirmed"
    }
    
    response = client.put(
        f"/api/bookings/{create_booking.booking_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["booking_id"] == create_booking.booking_id
    assert data["status"] == update_data["status"]

def test_delete_booking(client, create_booking, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Delete the booking
    response = client.delete(
        f"/api/bookings/{create_booking.booking_id}",
        headers=headers
    )
    
    assert response.status_code == 204
    
    # Verify the booking is deleted
    response = client.get(
        f"/api/bookings/{create_booking.booking_id}",
        headers=headers
    )
    
    assert response.status_code == 404

def test_employee_create_booking(client, create_employee, create_shift, employee_data):
    # Login as employee
    headers = get_auth_header(client, employee_data["email"], employee_data["password"])
    
    # Employee creates a booking for themselves
    booking_data = {
        "shift_id": create_shift.shift_id,
        "booking_date": str(date.today() + timedelta(days=2)),
        "pickup_latitude": 28.6139,
        "pickup_longitude": 77.2090,
        "pickup_location": "Employee Home Address",
        "drop_latitude": 28.7041,
        "drop_longitude": 77.1025,
        "drop_location": "Office Location",
        "booking_type": "Adhoc"
    }
    
    response = client.post(
        "/api/bookings/my-bookings",
        json=booking_data,
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["employee_id"] == create_employee.employee_id
    assert data["shift_id"] == booking_data["shift_id"]
    assert data["booking_date"] == booking_data["booking_date"]
    assert data["booking_type"] == booking_data["booking_type"]
    assert data["status"] == "Pending"
