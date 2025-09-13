import pytest
from fastapi.testclient import TestClient
from tests.fixtures import *

def get_auth_header(client, email, password):
    # Login to get the authentication token
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": password}
    )
    
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

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
        "license_number": "DL99999",
        "license_expiry": str(date.today() + timedelta(days=365))
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
    assert data["license_number"] == driver_data["license_number"]
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
    assert len(data["items"]) >= 1
    
    # Check if our created driver is in the list
    found = False
    for driver in data["items"]:
        if driver["driver_id"] == create_driver.driver_id:
            found = True
            assert driver["name"] == create_driver.name
            assert driver["email"] == create_driver.email
            break
    
    assert found == True

def test_update_driver(client, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Update the driver
    update_data = {
        "name": "Updated Driver Name",
        "phone": "9876543298",
        "license_expiry": str(date.today() + timedelta(days=730))
    }
    
    response = client.put(
        f"/api/drivers/{create_driver.driver_id}",
        json=update_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == create_driver.driver_id
    assert data["name"] == update_data["name"]
    assert data["phone"] == update_data["phone"]
    assert "license_expiry" in data

def test_delete_driver(client, create_driver, create_admin, admin_data):
    # Login as admin
    headers = get_auth_header(client, admin_data["email"], admin_data["password"])
    
    # Delete the driver
    response = client.delete(
        f"/api/drivers/{create_driver.driver_id}",
        headers=headers
    )
    
    assert response.status_code == 204
    
    # Verify the driver is marked as inactive (soft delete)
    response = client.get(
        f"/api/drivers/{create_driver.driver_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] == False

def test_driver_login(client, create_driver, driver_data):
    # Test that a driver can login
    response = client.post(
        "/api/auth/login",
        data={"username": driver_data["email"], "password": driver_data["password"]}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "token_type" in data
    assert data["token_type"] == "bearer"
    assert "user_type" in data
    assert data["user_type"] == "driver"
