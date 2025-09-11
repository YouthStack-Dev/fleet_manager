import pytest
from fastapi.testclient import TestClient
from tests.fixtures import *

def test_login_admin(client, create_admin, admin_data):
    # Test admin login
    response = client.post(
        "/api/auth/token",
        data={
            "username": admin_data["email"],
            "password": admin_data["password"],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_type"] == "admin"
    assert data["email"] == admin_data["email"]
    assert data["name"] == admin_data["name"]

def test_login_vendor_user(client, create_vendor_user, vendor_user_data):
    # Test vendor user login
    response = client.post(
        "/api/auth/token",
        data={
            "username": vendor_user_data["email"],
            "password": vendor_user_data["password"],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_type"] == "vendor_user"
    assert data["email"] == vendor_user_data["email"]
    assert data["name"] == vendor_user_data["name"]

def test_login_employee(client, create_employee, employee_data):
    # Test employee login
    response = client.post(
        "/api/auth/token",
        data={
            "username": employee_data["email"],
            "password": employee_data["password"],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_type"] == "employee"
    assert data["email"] == employee_data["email"]
    assert data["name"] == employee_data["name"]

def test_login_driver(client, create_driver, driver_data):
    # Test driver login
    response = client.post(
        "/api/auth/token",
        data={
            "username": driver_data["email"],
            "password": driver_data["password"],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_type"] == "driver"
    assert data["email"] == driver_data["email"]
    assert data["name"] == driver_data["name"]

def test_login_invalid_credentials(client):
    # Test login with invalid credentials
    response = client.post(
        "/api/auth/token",
        data={
            "username": "nonexistent@example.com",
            "password": "wrongpassword",
        },
    )
    
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]
