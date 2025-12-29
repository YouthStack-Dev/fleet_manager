import pytest
from fastapi import status
from app.models.escort import Escort
from app.models.vendor import Vendor


# ==================== Test Create Escort ====================

class TestCreateEscort:
    """Test suite for POST /escorts/ endpoint"""

    def test_create_escort_as_admin(self, client, admin_token, test_db, test_tenant, test_vendor):
        """Admin should be able to create escort"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "9876543210",
                "email": "escort@test.com",
                "gender": "FEMALE",
                "is_active": True,
                "is_available": True
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Test Escort"
        assert data["phone"] == "9876543210"
        assert data["vendor_id"] == test_vendor.vendor_id
        assert data["tenant_id"] == test_tenant.tenant_id

    def test_create_escort_as_employee(self, client, employee_token, test_db, test_vendor):
        """Employee should be able to create escort"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Employee Created Escort",
                "phone": "8765432109",
                "email": "escort2@test.com",
                "gender": "MALE"
            },
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Employee Created Escort"
        assert data["phone"] == "8765432109"

    def test_create_escort_driver_forbidden(self, client, driver_token, test_vendor):
        """Driver should not be able to create escort"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "9876543210"
            },
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_escort_invalid_vendor(self, client, admin_token, test_db, test_tenant):
        """Creating escort with invalid vendor should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": 99999,
                "name": "Test Escort",
                "phone": "9876543210"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "vendor not found" in str(response.json()).lower()

    def test_create_escort_vendor_wrong_tenant(self, client, admin_token, test_db, second_tenant_vendor):
        """Creating escort with vendor from different tenant should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": second_tenant_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "9876543210"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "vendor not found" in str(response.json()).lower()

    def test_create_escort_duplicate_phone(self, client, admin_token, test_db, test_vendor, test_escort):
        """Creating escort with duplicate phone should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Another Escort",
                "phone": test_escort.phone
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone" in str(response.json()).lower()

    def test_create_escort_invalid_phone(self, client, admin_token, test_vendor):
        """Creating escort with invalid phone should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "123"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_escort_invalid_gender(self, client, admin_token, test_vendor):
        """Creating escort with invalid gender should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "9876543210",
                "gender": "INVALID"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_escort_optional_fields(self, client, admin_token, test_vendor):
        """Creating escort with only required fields should succeed"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Minimal Escort",
                "phone": "7654321098"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Minimal Escort"
        assert data.get("email") is None
        assert data.get("address") is None

    def test_create_escort_unauthorized(self, client, test_vendor):
        """Creating escort without token should fail"""
        response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Test Escort",
                "phone": "9876543210"
            }
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test List Escorts ====================

class TestListEscorts:
    """Test suite for GET /escorts/ endpoint"""

    def test_list_escorts_as_admin(self, client, admin_token, test_db, test_escort):
        """Admin should be able to list escorts"""
        response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(e["escort_id"] == test_escort.escort_id for e in data)

    def test_list_escorts_as_employee(self, client, employee_token, test_escort):
        """Employee should be able to list escorts"""
        response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_escorts_driver_forbidden(self, client, driver_token):
        """Driver should not be able to list escorts"""
        response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_escorts_filter_by_vendor(self, client, admin_token, test_db, test_vendor, test_escort):
        """Should filter escorts by vendor_id"""
        # Create another vendor and escort
        vendor2 = Vendor(
            vendor_id=2,
            tenant_id=test_escort.tenant_id,
            vendor_code="VEND002",
            name="Second Vendor",
            email="vendor2@test.com",
            phone="1234567891",
            is_active=True
        )
        test_db.add(vendor2)
        test_db.commit()

        escort2 = Escort(
            tenant_id=test_escort.tenant_id,
            vendor_id=vendor2.vendor_id,
            name="Escort 2",
            phone="8888888888",
            is_active=True,
            is_available=True
        )
        test_db.add(escort2)
        test_db.commit()

        response = client.get(
            f"/api/v1/escorts/?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(e["vendor_id"] == test_vendor.vendor_id for e in data)

    def test_list_escorts_available_only(self, client, admin_token, test_db, test_escort):
        """Should list only available escorts"""
        # Create unavailable escort
        unavailable_escort = Escort(
            tenant_id=test_escort.tenant_id,
            vendor_id=test_escort.vendor_id,
            name="Unavailable Escort",
            phone="7777777777",
            is_active=True,
            is_available=False
        )
        test_db.add(unavailable_escort)
        test_db.commit()

        response = client.get(
            "/api/v1/escorts/?available_only=true",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(e["is_available"] for e in data)

    def test_list_escorts_pagination(self, client, admin_token, test_db, test_escort):
        """Should support pagination"""
        # Create multiple escorts
        for i in range(5):
            escort = Escort(
                tenant_id=test_escort.tenant_id,
                vendor_id=test_escort.vendor_id,
                name=f"Escort {i}",
                phone=f"900000000{i}",
                is_active=True,
                is_available=True
            )
            test_db.add(escort)
        test_db.commit()

        response = client.get(
            "/api/v1/escorts/?skip=0&limit=3",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) <= 3

    def test_list_escorts_tenant_isolation(self, client, admin_token, test_db, second_tenant_escort):
        """Should not return escorts from other tenants"""
        response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(e["escort_id"] == second_tenant_escort.escort_id for e in data)

    def test_list_escorts_unauthorized(self, client):
        """Listing escorts without token should fail"""
        response = client.get("/api/v1/escorts/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Get Escort ====================

class TestGetEscort:
    """Test suite for GET /escorts/{escort_id} endpoint"""

    def test_get_escort_as_admin(self, client, admin_token, test_escort):
        """Admin should be able to get escort by ID"""
        response = client.get(
            f"/api/v1/escorts/{test_escort.escort_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_id"] == test_escort.escort_id
        assert data["name"] == test_escort.name
        assert data["phone"] == test_escort.phone

    def test_get_escort_as_employee(self, client, employee_token, test_escort):
        """Employee should be able to get escort by ID"""
        response = client.get(
            f"/api/v1/escorts/{test_escort.escort_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_id"] == test_escort.escort_id

    def test_get_escort_driver_forbidden(self, client, driver_token, test_escort):
        """Driver should not be able to get escort"""
        response = client.get(
            f"/api/v1/escorts/{test_escort.escort_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_escort_not_found(self, client, admin_token):
        """Getting non-existent escort should return 404"""
        response = client.get(
            "/api/v1/escorts/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_escort_wrong_tenant(self, client, admin_token, second_tenant_escort):
        """Getting escort from different tenant should return 404"""
        response = client.get(
            f"/api/v1/escorts/{second_tenant_escort.escort_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_escort_unauthorized(self, client, test_escort):
        """Getting escort without token should fail"""
        response = client.get(f"/api/v1/escorts/{test_escort.escort_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Update Escort ====================

class TestUpdateEscort:
    """Test suite for PUT /escorts/{escort_id} endpoint"""

    def test_update_escort_name_as_admin(self, client, admin_token, test_escort):
        """Admin should be able to update escort name"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"name": "Updated Escort Name"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Escort Name"
        assert data["escort_id"] == test_escort.escort_id

    def test_update_escort_phone_as_employee(self, client, employee_token, test_escort):
        """Employee should be able to update escort phone"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"phone": "5555555555"},
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["phone"] == "5555555555"

    def test_update_escort_multiple_fields(self, client, admin_token, test_escort):
        """Should be able to update multiple fields"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={
                "name": "Multi Update",
                "phone": "4444444444",
                "email": "updated@test.com",
                "is_available": False
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Multi Update"
        assert data["phone"] == "4444444444"
        assert data["email"] == "updated@test.com"
        assert data["is_available"] is False

    def test_update_escort_driver_forbidden(self, client, driver_token, test_escort):
        """Driver should not be able to update escort"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"name": "Updated Name"},
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_escort_duplicate_phone(self, client, admin_token, test_db, test_vendor, test_escort):
        """Updating to duplicate phone should fail"""
        # Create another escort
        escort2 = Escort(
            tenant_id=test_escort.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Escort 2",
            phone="6666666666",
            is_active=True,
            is_available=True
        )
        test_db.add(escort2)
        test_db.commit()

        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"phone": "6666666666"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone" in str(response.json()).lower()

    def test_update_escort_invalid_vendor(self, client, admin_token, test_escort):
        """Updating to invalid vendor should fail"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"vendor_id": 99999},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "vendor not found" in str(response.json()).lower()

    def test_update_escort_vendor_wrong_tenant(self, client, admin_token, test_escort, second_tenant_vendor):
        """Updating to vendor from different tenant should fail"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"vendor_id": second_tenant_vendor.vendor_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "vendor not found" in str(response.json()).lower()

    def test_update_escort_not_found(self, client, admin_token):
        """Updating non-existent escort should return 404"""
        response = client.put(
            "/api/v1/escorts/99999",
            json={"name": "Test"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_escort_wrong_tenant(self, client, admin_token, second_tenant_escort):
        """Updating escort from different tenant should return 404"""
        response = client.put(
            f"/api/v1/escorts/{second_tenant_escort.escort_id}",
            json={"name": "Test"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_escort_invalid_phone(self, client, admin_token, test_escort):
        """Updating to invalid phone should fail"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"phone": "123"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_escort_unauthorized(self, client, test_escort):
        """Updating escort without token should fail"""
        response = client.put(
            f"/api/v1/escorts/{test_escort.escort_id}",
            json={"name": "Test"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Delete Escort ====================

class TestDeleteEscort:
    """Test suite for DELETE /escorts/{escort_id} endpoint"""

    def test_delete_escort_as_admin(self, client, admin_token, test_db, test_vendor, test_tenant):
        """Admin should be able to delete escort"""
        # Create escort to delete
        escort = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Delete Me",
            phone="3333333333",
            is_active=True,
            is_available=True
        )
        test_db.add(escort)
        test_db.commit()
        test_db.refresh(escort)

        response = client.delete(
            f"/api/v1/escorts/{escort.escort_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deletion
        deleted = test_db.query(Escort).filter(Escort.escort_id == escort.escort_id).first()
        assert deleted is None

    def test_delete_escort_as_employee(self, client, employee_token, test_db, test_vendor, test_tenant):
        """Employee should be able to delete escort"""
        escort = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Delete Me 2",
            phone="2222222222",
            is_active=True,
            is_available=True
        )
        test_db.add(escort)
        test_db.commit()
        test_db.refresh(escort)

        response = client.delete(
            f"/api/v1/escorts/{escort.escort_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_escort_driver_forbidden(self, client, driver_token, test_escort):
        """Driver should not be able to delete escort"""
        response = client.delete(
            f"/api/v1/escorts/{test_escort.escort_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_escort_not_found(self, client, admin_token):
        """Deleting non-existent escort should return 404"""
        response = client.delete(
            "/api/v1/escorts/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_escort_wrong_tenant(self, client, admin_token, second_tenant_escort):
        """Deleting escort from different tenant should return 404"""
        response = client.delete(
            f"/api/v1/escorts/{second_tenant_escort.escort_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_escort_unauthorized(self, client, test_escort):
        """Deleting escort without token should fail"""
        response = client.delete(f"/api/v1/escorts/{test_escort.escort_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Get Available Escorts ====================

class TestGetAvailableEscorts:
    """Test suite for GET /escorts/available/ endpoint"""

    def test_get_available_escorts(self, client, admin_token, test_db, test_vendor, test_tenant):
        """Should return only available escorts"""
        # Create available and unavailable escorts
        available = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Available Escort",
            phone="1111111111",
            is_active=True,
            is_available=True
        )
        unavailable = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Unavailable Escort",
            phone="1111111112",
            is_active=True,
            is_available=False
        )
        test_db.add(available)
        test_db.add(unavailable)
        test_db.commit()

        response = client.get(
            "/api/v1/escorts/available/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert all(e["is_available"] for e in data)
        escort_ids = [e["escort_id"] for e in data]
        assert available.escort_id in escort_ids
        assert unavailable.escort_id not in escort_ids

    def test_get_available_escorts_as_employee(self, client, employee_token, test_db, test_vendor, test_tenant):
        """Employee should be able to get available escorts"""
        escort = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Available Escort 2",
            phone="1111111113",
            is_active=True,
            is_available=True
        )
        test_db.add(escort)
        test_db.commit()

        response = client.get(
            "/api/v1/escorts/available/",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(e["is_available"] for e in data)

    def test_get_available_escorts_driver_forbidden(self, client, driver_token):
        """Driver should not be able to get available escorts"""
        response = client.get(
            "/api/v1/escorts/available/",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_available_escorts_tenant_isolation(self, client, admin_token, test_db, second_tenant_vendor):
        """Should not return escorts from other tenants"""
        # Create escort in another tenant
        escort = Escort(
            tenant_id="tenant_2",
            vendor_id=second_tenant_vendor.vendor_id,
            name="Other Tenant Escort",
            phone="1111111114",
            is_active=True,
            is_available=True
        )
        test_db.add(escort)
        test_db.commit()

        response = client.get(
            "/api/v1/escorts/available/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        escort_ids = [e["escort_id"] for e in data]
        assert escort.escort_id not in escort_ids

    def test_get_available_escorts_unauthorized(self, client):
        """Getting available escorts without token should fail"""
        response = client.get("/api/v1/escorts/available/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Escort Integration ====================

class TestEscortIntegration:
    """Integration tests for complete escort workflows"""

    def test_complete_escort_lifecycle(self, client, admin_token, test_db, test_vendor):
        """Test complete CRUD lifecycle of an escort"""
        # Create
        create_response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Lifecycle Test",
                "phone": "9999999999",
                "email": "lifecycle@test.com",
                "gender": "FEMALE",
                "is_available": True
            },
            headers={"Authorization": admin_token}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        escort_id = create_response.json()["escort_id"]

        # Read
        get_response = client.get(
            f"/api/v1/escorts/{escort_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["name"] == "Lifecycle Test"

        # Update
        update_response = client.put(
            f"/api/v1/escorts/{escort_id}",
            json={"name": "Updated Lifecycle", "is_available": False},
            headers={"Authorization": admin_token}
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["name"] == "Updated Lifecycle"
        assert update_response.json()["is_available"] is False

        # Delete
        delete_response = client.delete(
            f"/api/v1/escorts/{escort_id}",
            headers={"Authorization": admin_token}
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deletion
        verify_response = client.get(
            f"/api/v1/escorts/{escort_id}",
            headers={"Authorization": admin_token}
        )
        assert verify_response.status_code == status.HTTP_404_NOT_FOUND

    def test_tenant_isolation_complete(self, client, admin_token, employee_token, test_db, test_vendor, second_tenant_vendor):
        """Verify tenant isolation across all operations"""
        # Create escort in tenant 1
        create_response = client.post(
            "/api/v1/escorts/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Tenant 1 Escort",
                "phone": "8888888881"
            },
            headers={"Authorization": admin_token}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        escort1_id = create_response.json()["escort_id"]

        # Create escort in tenant 2
        escort2 = Escort(
            tenant_id="tenant_2",
            vendor_id=second_tenant_vendor.vendor_id,
            name="Tenant 2 Escort",
            phone="8888888882",
            is_active=True,
            is_available=True
        )
        test_db.add(escort2)
        test_db.commit()
        test_db.refresh(escort2)

        # Tenant 1 should not see tenant 2 escort
        list_response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": admin_token}
        )
        assert list_response.status_code == status.HTTP_200_OK
        escort_ids = [e["escort_id"] for e in list_response.json()]
        assert escort1_id in escort_ids
        assert escort2.escort_id not in escort_ids

        # Tenant 1 should not be able to access tenant 2 escort
        get_response = client.get(
            f"/api/v1/escorts/{escort2.escort_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_available_escorts_filtering(self, client, admin_token, test_db, test_vendor, test_tenant):
        """Test filtering of available escorts"""
        # Create mixed escorts
        available1 = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Available 1",
            phone="7777777771",
            is_active=True,
            is_available=True
        )
        available2 = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Available 2",
            phone="7777777772",
            is_active=True,
            is_available=True
        )
        unavailable1 = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Unavailable 1",
            phone="7777777773",
            is_active=True,
            is_available=False
        )
        test_db.add_all([available1, available2, unavailable1])
        test_db.commit()

        # Get all escorts
        all_response = client.get(
            "/api/v1/escorts/",
            headers={"Authorization": admin_token}
        )
        all_escorts = all_response.json()

        # Get only available escorts using query parameter
        available_response = client.get(
            "/api/v1/escorts/?available_only=true",
            headers={"Authorization": admin_token}
        )
        available_escorts = available_response.json()

        # Get available escorts using dedicated endpoint
        available_endpoint_response = client.get(
            "/api/v1/escorts/available/",
            headers={"Authorization": admin_token}
        )
        available_endpoint_escorts = available_endpoint_response.json()

        # Verify filtering
        assert len(all_escorts) > len(available_escorts)
        assert all(e["is_available"] for e in available_escorts)
        assert all(e["is_available"] for e in available_endpoint_escorts)

    def test_vendor_filtering_with_multiple_vendors(self, client, admin_token, test_db, test_vendor, test_tenant):
        """Test filtering escorts by vendor with multiple vendors"""
        # Create second vendor
        vendor2 = Vendor(
            vendor_id=3,
            tenant_id=test_tenant.tenant_id,
            vendor_code="VEND003",
            name="Test Vendor 3",
            email="vendor3@test.com",
            phone="1234567893",
            is_active=True
        )
        test_db.add(vendor2)
        test_db.commit()

        # Create escorts for both vendors
        escort1 = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor.vendor_id,
            name="Vendor 1 Escort",
            phone="6666666661",
            is_active=True,
            is_available=True
        )
        escort2 = Escort(
            tenant_id=test_tenant.tenant_id,
            vendor_id=vendor2.vendor_id,
            name="Vendor 2 Escort",
            phone="6666666662",
            is_active=True,
            is_available=True
        )
        test_db.add_all([escort1, escort2])
        test_db.commit()

        # Filter by vendor 1
        vendor1_response = client.get(
            f"/api/v1/escorts/?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": admin_token}
        )
        vendor1_escorts = vendor1_response.json()
        assert all(e["vendor_id"] == test_vendor.vendor_id for e in vendor1_escorts)

        # Filter by vendor 2
        vendor2_response = client.get(
            f"/api/v1/escorts/?vendor_id={vendor2.vendor_id}",
            headers={"Authorization": admin_token}
        )
        vendor2_escorts = vendor2_response.json()
        assert all(e["vendor_id"] == vendor2.vendor_id for e in vendor2_escorts)


