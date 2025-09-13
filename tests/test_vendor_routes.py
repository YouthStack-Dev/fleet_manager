from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest
from main import app
from app.models.vendor import Vendor

client = TestClient(app)

def test_create_vendor(db: Session):
    vendor_data = {
        "name": "Test Vendor API",
        "code": "TEST-API",
        "email": "vendor-api@test.com",
        "phone": "9876543299",
        "is_active": True
    }
    
    response = client.post("/vendors/", json=vendor_data)
    assert response.status_code == 201
    
    data = response.json()
    assert data["name"] == vendor_data["name"]
    assert data["code"] == vendor_data["code"]
    assert data["email"] == vendor_data["email"]
    assert data["phone"] == vendor_data["phone"]
    assert data["is_active"] == vendor_data["is_active"]
    assert "vendor_id" in data
    
    # Cleanup
    db_vendor = db.query(Vendor).filter(Vendor.vendor_id == data["vendor_id"]).first()
    db.delete(db_vendor)
    db.commit()

def test_read_vendors(create_vendor, db: Session):
    response = client.get("/vendors/")
    assert response.status_code == 200
    
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] > 0
    assert any(item["vendor_id"] == create_vendor.vendor_id for item in data["items"])

def test_read_vendor_by_id(create_vendor):
    response = client.get(f"/vendors/{create_vendor.vendor_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["vendor_id"] == create_vendor.vendor_id
    assert data["name"] == create_vendor.name
    assert data["code"] == create_vendor.code
    assert data["email"] == create_vendor.email
    assert data["phone"] == create_vendor.phone

def test_read_vendor_not_found():
    # Using a non-existent vendor ID
    response = client.get("/vendors/99999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_update_vendor(create_vendor):
    update_data = {
        "name": "Updated Vendor Name",
        "code": "UPD01",
        "is_active": False
    }
    
    response = client.put(f"/vendors/{create_vendor.vendor_id}", json=update_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["code"] == update_data["code"]
    assert data["is_active"] == update_data["is_active"]
    # The following fields should remain unchanged
    assert data["email"] == create_vendor.email
    assert data["phone"] == create_vendor.phone

def test_update_vendor_not_found():
    update_data = {"name": "Non-existent Vendor"}
    response = client.put("/vendors/99999", json=update_data)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_delete_vendor(db: Session):
    # Create a temporary vendor to delete
    vendor = Vendor(
        name="Temp Vendor",
        code="TEMP01",
        email="temp@example.com",
        phone="9876543200",
        is_active=True
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    
    vendor_id = vendor.vendor_id
    
    # Delete the vendor
    response = client.delete(f"/vendors/{vendor_id}")
    assert response.status_code == 204
    
    # Verify vendor is deleted
    db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    assert db_vendor is None

def test_delete_vendor_not_found():
    response = client.delete("/vendors/99999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_filter_vendors_by_name(create_vendor, db: Session):
    # Create an additional vendor with a distinct name
    vendor2 = Vendor(
        name="Unique Vendor Name",
        code="UNIQ01",
        email="unique@example.com",
        phone="9876543201",
        is_active=True
    )
    db.add(vendor2)
    db.commit()
    
    try:
        # Search for the unique name
        response = client.get("/vendors/?name=Unique")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] >= 1
        assert any(item["name"] == "Unique Vendor Name" for item in data["items"])
        
        # Search for a non-existent name
        response = client.get("/vendors/?name=NonExistent12345")
        assert response.status_code == 200
        assert data["total"] >= 0
    finally:
        # Cleanup
        db.delete(vendor2)
        db.commit()

def test_filter_vendors_by_code(create_vendor):
    response = client.get(f"/vendors/?code={create_vendor.code}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["total"] >= 1
    assert any(item["code"] == create_vendor.code for item in data["items"])

def test_filter_vendors_by_is_active(create_vendor, db: Session):
    # Create an inactive vendor
    inactive_vendor = Vendor(
        name="Inactive Vendor",
        code="INACT01",
        email="inactive@example.com",
        phone="9876543202",
        is_active=False
    )
    db.add(inactive_vendor)
    db.commit()
    
    try:
        # Filter for active vendors
        response = client.get("/vendors/?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert all(item["is_active"] for item in data["items"])
        
        # Filter for inactive vendors
        response = client.get("/vendors/?is_active=false")
        assert response.status_code == 200
        data = response.json()
        assert all(not item["is_active"] for item in data["items"])
    finally:
        # Cleanup
        db.delete(inactive_vendor)
        db.commit()
