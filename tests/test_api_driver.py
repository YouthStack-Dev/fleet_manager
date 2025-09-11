import pytest
from fastapi.testclient import TestClient
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

def test_create_driver(client, create_vendor, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Create a new driver
    driver_data = {
        "name": "New Test Driver",
        "code": "DRVTEST",
        "email": "newdriver@test.com",
        "phone": "9876543299",
        "vendor_id": create_vendor.vendor_id,
        "password": "newpassword",
        "license_number": "DL99999"
    }
    
    response = client.post(
        "/api/drivers/",
        json=driver_data,
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == driver_data["name"]
    assert data["code"] == driver_data["code"]
    assert data["email"] == driver_data["email"]
    assert data["vendor_id"] == driver_data["vendor_id"]
    assert "password" not in data  # Password should not be returned
    
    # Test the driver_id was created
    assert "driver_id" in data
    assert isinstance(data["driver_id"], int)
    
    # Verify the driver can be retrieved
    driver_id = data["driver_id"]
    response = client.get(
        f"/api/drivers/{driver_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == driver_id
    assert data["name"] == driver_data["name"]
    assert data["email"] == driver_data["email"]

def test_get_drivers(client, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Get all drivers
    response = client.get(
        "/api/drivers/",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1  # At least our created driver should be there
    
    # Check if our created driver is in the list
    found = False
    for driver in data["items"]:
        if driver["email"] == create_driver.email:
            found = True
            break
    
    assert found == True

def test_update_driver(client, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Update the driver
    update_data = {
        "name": "Updated Driver Name",
        "license_number": "DL98765"
    }
    
    response = client.put(
        f"/api/drivers/{create_driver.driver_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == create_driver.driver_id
    assert data["name"] == update_data["name"]  # Name should be updated
    assert data["license_number"] == update_data["license_number"]  # License should be updated
    assert data["email"] == create_driver.email  # Email should remain unchanged

def test_delete_driver(client, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Delete the driver
    response = client.delete(
        f"/api/drivers/{create_driver.driver_id}",
        headers=headers
    )
    
    assert response.status_code == 204
    
    # Verify the driver is deleted
    response = client.get(
        f"/api/drivers/{create_driver.driver_id}",
        headers=headers
    )
    
    assert response.status_code == 404
