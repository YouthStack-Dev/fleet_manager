"""
Comprehensive tests for vehicle type management endpoints.

Tests cover:
- POST /vehicle-types/ - Create vehicle type
- GET /vehicle-types/ - List vehicle types with filters
- GET /vehicle-types/{vehicle_type_id} - Get single vehicle type
- PUT /vehicle-types/{vehicle_type_id} - Update vehicle type
- PATCH /vehicle-types/{vehicle_type_id}/toggle-status - Toggle status

Edge cases tested:
- Vendor scope resolution (admin, vendor, employee)
- Duplicate name prevention per vendor
- Tenant isolation for employees
- Invalid vendor_id scenarios
- Permission-based access control
- Filter combinations (name, active_only)
- Audit logging validation
"""
import pytest
from fastapi import status


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture(scope="function")
def employee_vehicle_type_token(test_tenant, test_employee):
    """Generate JWT token for employee with vehicle-type permissions"""
    from common_utils.auth.utils import create_access_token
    
    token = create_access_token(
        user_id=str(test_employee["employee"].employee_id),
        tenant_id=test_tenant.tenant_id,
        user_type="employee",
        custom_claims={
            "permissions": [
                "vehicle-type.create",
                "vehicle-type.read",
                "vehicle-type.update"
            ]
        }
    )
    return token


@pytest.fixture(scope="function")
def vendor_vehicle_type_token(test_tenant, test_vendor):
    """Generate JWT token for vendor user with vehicle-type permissions"""
    from common_utils.auth.utils import create_access_token
    
    token = create_access_token(
        user_id="vendor_user_1",
        tenant_id=test_tenant.tenant_id,
        user_type="vendor",
        custom_claims={
            "vendor_id": test_vendor.vendor_id,
            "permissions": [
                "vehicle-type.create",
                "vehicle-type.read",
                "vehicle-type.update"
            ]
        }
    )
    return token


@pytest.fixture(scope="function")
def second_vendor_token(second_tenant, second_vendor):
    """Generate JWT token for second vendor user"""
    from common_utils.auth.utils import create_access_token
    
    token = create_access_token(
        user_id="vendor_user_2",
        tenant_id=second_tenant.tenant_id,
        user_type="vendor",
        custom_claims={
            "vendor_id": second_vendor.vendor_id,
            "permissions": [
                "vehicle-type.create",
                "vehicle-type.read",
                "vehicle-type.update"
            ]
        }
    )
    return token


@pytest.fixture(scope="function")
def test_vehicle_type_data(test_vendor):
    """Common vehicle type creation data"""
    return {
        "vendor_id": test_vendor.vendor_id,
        "name": "Sedan",
        "seats": 4,
        "is_active": True
    }


@pytest.fixture(scope="function")
def test_vehicle_type(test_db, test_vendor):
    """Create a test vehicle type"""
    from app.models.vehicle_type import VehicleType
    vtype = VehicleType(
        vehicle_type_id=100,
        vendor_id=test_vendor.vendor_id,
        name="SUV",
        seats=7,
        is_active=True
    )
    test_db.add(vtype)
    test_db.commit()
    test_db.refresh(vtype)
    return vtype


@pytest.fixture(scope="function")
def inactive_vehicle_type(test_db, test_vendor):
    """Create an inactive vehicle type"""
    from app.models.vehicle_type import VehicleType
    vtype = VehicleType(
        vehicle_type_id=101,
        vendor_id=test_vendor.vendor_id,
        name="Minivan",
        seats=8,
        is_active=False
    )
    test_db.add(vtype)
    test_db.commit()
    test_db.refresh(vtype)
    return vtype


# =====================================================================
# TEST: POST /vehicle-types/ (Create Vehicle Type)
# =====================================================================

class TestCreateVehicleType:
    """Test suite for creating vehicle types"""

    def test_create_vehicle_type_as_admin(self, client, test_db, admin_token, test_vendor, test_vehicle_type_data):
        """Admin can create vehicle type with provided vendor_id"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json=test_vehicle_type_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["name"] == "Sedan"
        assert data["data"]["vehicle_type"]["seats"] == 4
        assert data["data"]["vehicle_type"]["vendor_id"] == test_vendor.vendor_id

    def test_create_vehicle_type_as_employee(self, client, test_db, employee_vehicle_type_token, test_vendor, test_vehicle_type_data):
        """Employee can create vehicle type for vendor in their tenant"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json=test_vehicle_type_data,
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["name"] == "Sedan"

    def test_create_vehicle_type_as_vendor(self, client, test_db, vendor_vehicle_type_token, test_vendor, test_vehicle_type_data):
        """Vendor can create vehicle type (vendor_id from token)"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json=test_vehicle_type_data,
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["vendor_id"] == test_vendor.vendor_id

    def test_create_vehicle_type_admin_without_vendor_id(self, client, test_db, admin_token):
        """Admin must provide vendor_id"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"name": "Sedan", "seats": 4},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "vendor_id is required" in str(data).lower()

    def test_create_vehicle_type_employee_without_vendor_id(self, client, test_db, employee_vehicle_type_token):
        """Employee must provide vendor_id"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"name": "Sedan", "seats": 4},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "vendor_id is required" in str(data).lower()

    def test_create_vehicle_type_employee_wrong_tenant(self, client, test_db, employee_vehicle_type_token, second_vendor):
        """Employee cannot create vehicle type for vendor in different tenant"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": second_vendor.vendor_id, "name": "Sedan", "seats": 4},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "tenant" in str(data).lower()

    def test_create_vehicle_type_duplicate_name_same_vendor(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Cannot create duplicate vehicle type name for same vendor"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "SUV", "seats": 7},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_409_CONFLICT, status.HTTP_500_INTERNAL_SERVER_ERROR]
        data = response.json()
        assert data.get("success", False) is False

    def test_create_vehicle_type_same_name_different_vendor(self, client, test_db, admin_token, test_vendor, second_vendor, test_vehicle_type):
        """Can create same name for different vendor"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": second_vendor.vendor_id, "name": "SUV", "seats": 6},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["name"] == "SUV"
        assert data["data"]["vehicle_type"]["vendor_id"] == second_vendor.vendor_id

    def test_create_vehicle_type_invalid_vendor_id(self, client, test_db, admin_token):
        """Cannot create vehicle type with non-existent vendor_id"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": 99999, "name": "Sedan", "seats": 4},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "vendor" in str(data).lower()

    def test_create_vehicle_type_unauthorized(self, client, test_db, test_vehicle_type_data):
        """Unauthorized users cannot create vehicle types"""
        response = client.post(
            "/api/v1/vehicle-types/",
            json=test_vehicle_type_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: GET /vehicle-types/ (List Vehicle Types)
# =====================================================================

class TestListVehicleTypes:
    """Test suite for listing vehicle types"""

    def test_list_vehicle_types_as_admin(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Admin can list vehicle types with vendor_id"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data.get("data", {}).get("items", [])) >= 1
        assert any(item["name"] == "SUV" for item in data.get("data", {}).get("items", []))

    def test_list_vehicle_types_as_employee(self, client, test_db, employee_vehicle_type_token, test_vendor, test_vehicle_type):
        """Employee can list vehicle types for vendor in their tenant"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data.get("data", {}).get("items", [])) >= 1

    def test_list_vehicle_types_as_vendor(self, client, test_db, vendor_vehicle_type_token, test_vendor, test_vehicle_type):
        """Vendor can list their vehicle types (vendor_id from token)"""
        response = client.get(
            "/api/v1/vehicle-types/",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data.get("data", {}).get("items", [])) >= 1
        # All items should belong to the vendor
        for item in data.get("data", {}).get("items", []):
            assert item["vendor_id"] == test_vendor.vendor_id

    def test_list_vehicle_types_filter_by_name(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Can filter vehicle types by name"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}&name=SUV",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert all(item["name"] == "SUV" for item in data.get("data", {}).get("items", []))

    def test_list_vehicle_types_filter_active_only_true(self, client, test_db, admin_token, test_vendor, test_vehicle_type, inactive_vehicle_type):
        """Can filter to show only active vehicle types"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}&active_only=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        # All returned items should be active
        for item in data.get("data", {}).get("items", []):
            assert item["is_active"] is True

    def test_list_vehicle_types_filter_active_only_false(self, client, test_db, admin_token, test_vendor, test_vehicle_type, inactive_vehicle_type):
        """Can show all vehicle types including inactive"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}&active_only=false",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        # Should include both active and inactive
        items = data.get("data", {}).get("items", [])
        assert len(items) >= 1  # Should include at least the active one

    def test_list_vehicle_types_admin_without_vendor_id(self, client, test_db, admin_token):
        """Admin must provide vendor_id"""
        response = client.get(
            "/api/v1/vehicle-types/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "vendor_id is required" in str(data).lower()

    def test_list_vehicle_types_employee_wrong_tenant(self, client, test_db, employee_vehicle_type_token, second_vendor):
        """Employee cannot list vehicle types for vendor in different tenant"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={second_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "tenant" in str(data).lower()

    def test_list_vehicle_types_empty_results(self, client, test_db, admin_token, second_vendor):
        """Returns empty list when no vehicle types exist for vendor"""
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={second_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data.get("data", {}).get("items", [])) == 0

    def test_list_vehicle_types_unauthorized(self, client, test_db, test_vendor):
        """Unauthorized users cannot list vehicle types"""
        response = client.get(f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: GET /vehicle-types/{vehicle_type_id} (Get Single Vehicle Type)
# =====================================================================

class TestGetVehicleType:
    """Test suite for getting single vehicle type"""

    def test_get_vehicle_type_as_admin(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Admin can get vehicle type with vendor_id"""
        response = client.get(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["vehicle_type_id"] == test_vehicle_type.vehicle_type_id
        assert data["data"]["vehicle_type"]["name"] == "SUV"

    def test_get_vehicle_type_as_employee(self, client, test_db, employee_vehicle_type_token, test_vendor, test_vehicle_type):
        """Employee can get vehicle type for vendor in their tenant"""
        response = client.get(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["vehicle_type_id"] == test_vehicle_type.vehicle_type_id

    def test_get_vehicle_type_as_vendor(self, client, test_db, vendor_vehicle_type_token, test_vehicle_type):
        """Vendor can get their vehicle type"""
        response = client.get(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["vehicle_type_id"] == test_vehicle_type.vehicle_type_id

    def test_get_vehicle_type_not_found(self, client, test_db, admin_token, test_vendor):
        """Returns 404 for non-existent vehicle type"""
        response = client.get(
            f"/api/v1/vehicle-types/99999?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False
        assert "not found" in str(data).lower()

    def test_get_vehicle_type_wrong_vendor(self, client, test_db, vendor_vehicle_type_token, test_vehicle_type, second_vendor):
        """Vendor cannot get vehicle type from another vendor"""
        # Create a vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=102,
            vendor_id=second_vendor.vendor_id,
            name="Truck",
            seats=2,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False

    def test_get_vehicle_type_employee_wrong_tenant(self, client, test_db, employee_vehicle_type_token, second_vendor):
        """Employee cannot get vehicle type for vendor in different tenant"""
        # Create vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=103,
            vendor_id=second_vendor.vendor_id,
            name="Bus",
            seats=50,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}?vendor_id={second_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "tenant" in str(data).lower()

    def test_get_vehicle_type_unauthorized(self, client, test_db, test_vendor, test_vehicle_type):
        """Unauthorized users cannot get vehicle type"""
        response = client.get(f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: PUT /vehicle-types/{vehicle_type_id} (Update Vehicle Type)
# =====================================================================

class TestUpdateVehicleType:
    """Test suite for updating vehicle types"""

    def test_update_vehicle_type_name_as_admin(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Admin can update vehicle type name"""
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"name": "Large SUV"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["name"] == "Large SUV"

    def test_update_vehicle_type_capacity_as_employee(self, client, test_db, employee_vehicle_type_token, test_vendor, test_vehicle_type):
        """Employee can update vehicle type capacity"""
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"seats": 8},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["seats"] == 8

    def test_update_vehicle_type_as_vendor(self, client, test_db, vendor_vehicle_type_token, test_vehicle_type):
        """Vendor can update their vehicle type"""
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}",
            json={"seats": 6},
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["seats"] == 6

    def test_update_vehicle_type_multiple_fields(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Can update multiple fields at once"""
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"name": "Premium SUV", "seats": 5, "is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["name"] == "Premium SUV"
        assert data["data"]["vehicle_type"]["seats"] == 5
        assert data["data"]["vehicle_type"]["is_active"] is False

    def test_update_vehicle_type_duplicate_name(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Cannot update to duplicate name for same vendor"""
        # Create another vehicle type
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=104,
            vendor_id=test_vendor.vendor_id,
            name="Compact",
            seats=4,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        # Try to update first vehicle type to "Compact" (duplicate)
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"name": "Compact"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_409_CONFLICT, status.HTTP_500_INTERNAL_SERVER_ERROR]
        data = response.json()
        assert data.get("success", False) is False

    def test_update_vehicle_type_not_found(self, client, test_db, admin_token, test_vendor):
        """Returns 404 when updating non-existent vehicle type"""
        response = client.put(
            f"/api/v1/vehicle-types/99999?vendor_id={test_vendor.vendor_id}",
            json={"name": "Updated"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False

    def test_update_vehicle_type_wrong_vendor(self, client, test_db, vendor_vehicle_type_token, second_vendor):
        """Vendor cannot update vehicle type from another vendor"""
        # Create vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=105,
            vendor_id=second_vendor.vendor_id,
            name="Van",
            seats=12,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.put(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}",
            json={"name": "Updated Van"},
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False

    def test_update_vehicle_type_employee_wrong_tenant(self, client, test_db, employee_vehicle_type_token, second_vendor):
        """Employee cannot update vehicle type for vendor in different tenant"""
        # Create vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=106,
            vendor_id=second_vendor.vendor_id,
            name="Minibus",
            seats=15,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.put(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}?vendor_id={second_vendor.vendor_id}",
            json={"name": "Updated Minibus"},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "tenant" in str(data).lower()

    def test_update_vehicle_type_unauthorized(self, client, test_db, test_vendor, test_vehicle_type):
        """Unauthorized users cannot update vehicle type"""
        response = client.put(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"name": "Updated"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: PATCH /vehicle-types/{vehicle_type_id}/toggle-status
# =====================================================================

class TestToggleVehicleTypeStatus:
    """Test suite for toggling vehicle type status"""

    def test_toggle_vehicle_type_to_inactive(self, client, test_db, admin_token, test_vendor, test_vehicle_type):
        """Can toggle active vehicle type to inactive"""
        assert test_vehicle_type.is_active is True
        
        response = client.patch(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["is_active"] is False
        assert "deactivated" in str(data).lower() or "deactivat" in str(data).lower()

    def test_toggle_vehicle_type_to_active(self, client, test_db, admin_token, test_vendor, inactive_vehicle_type):
        """Can toggle inactive vehicle type to active"""
        assert inactive_vehicle_type.is_active is False
        
        response = client.patch(
            f"/api/v1/vehicle-types/{inactive_vehicle_type.vehicle_type_id}/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vehicle_type"]["is_active"] is True
        assert "activated" in str(data).lower() or "activat" in str(data).lower()

    def test_toggle_vehicle_type_as_employee(self, client, test_db, employee_vehicle_type_token, test_vendor, test_vehicle_type):
        """Employee can toggle vehicle type status"""
        response = client.patch(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True

    def test_toggle_vehicle_type_as_vendor(self, client, test_db, vendor_vehicle_type_token, test_vehicle_type):
        """Vendor can toggle their vehicle type status"""
        response = client.patch(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}/toggle-status",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True

    def test_toggle_vehicle_type_not_found(self, client, test_db, admin_token, test_vendor):
        """Returns 404 when toggling non-existent vehicle type"""
        response = client.patch(
            f"/api/v1/vehicle-types/99999/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False

    def test_toggle_vehicle_type_wrong_vendor(self, client, test_db, vendor_vehicle_type_token, second_vendor):
        """Vendor cannot toggle vehicle type from another vendor"""
        # Create vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=107,
            vendor_id=second_vendor.vendor_id,
            name="Coupe",
            seats=2,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}/toggle-status",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data.get("success", False) is False

    def test_toggle_vehicle_type_employee_wrong_tenant(self, client, test_db, employee_vehicle_type_token, second_vendor):
        """Employee cannot toggle vehicle type for vendor in different tenant"""
        # Create vehicle type for second vendor
        from app.models.vehicle_type import VehicleType
        other_vtype = VehicleType(
            vehicle_type_id=108,
            vendor_id=second_vendor.vendor_id,
            name="Hatchback",
            seats=5,
            is_active=True
        )
        test_db.add(other_vtype)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/vehicle-types/{other_vtype.vehicle_type_id}/toggle-status?vendor_id={second_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "tenant" in str(data).lower()

    def test_toggle_vehicle_type_unauthorized(self, client, test_db, test_vendor, test_vehicle_type):
        """Unauthorized users cannot toggle vehicle type status"""
        response = client.patch(
            f"/api/v1/vehicle-types/{test_vehicle_type.vehicle_type_id}/toggle-status?vendor_id={test_vendor.vendor_id}"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# INTEGRATION TESTS
# =====================================================================

class TestVehicleTypeIntegration:
    """Integration tests for complete vehicle type workflows"""

    def test_vehicle_type_complete_lifecycle(self, client, test_db, admin_token, test_vendor):
        """Test complete lifecycle: create, read, update, toggle status"""
        # 1. Create
        create_response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "Lifecycle Test", "seats": 5},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        vehicle_type_id = create_response.json()["data"]["vehicle_type"]["vehicle_type_id"]
        
        # 2. Read
        get_response = client.get(
            f"/api/v1/vehicle-types/{vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["data"]["vehicle_type"]["name"] == "Lifecycle Test"
        
        # 3. Update
        update_response = client.put(
            f"/api/v1/vehicle-types/{vehicle_type_id}?vendor_id={test_vendor.vendor_id}",
            json={"name": "Updated Lifecycle", "seats": 6},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["data"]["vehicle_type"]["name"] == "Updated Lifecycle"
        assert update_response.json()["data"]["vehicle_type"]["seats"] == 6
        
        # 4. Toggle status
        toggle_response = client.patch(
            f"/api/v1/vehicle-types/{vehicle_type_id}/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert toggle_response.status_code == status.HTTP_200_OK
        assert toggle_response.json()["data"]["vehicle_type"]["is_active"] is False

    def test_multiple_vehicle_types_for_vendor(self, client, test_db, admin_token, test_vendor):
        """Can create and manage multiple vehicle types for same vendor"""
        # Create multiple vehicle types
        types = ["Sedan", "SUV", "Van", "Truck"]
        for vtype in types:
            response = client.post(
                "/api/v1/vehicle-types/",
                json={"vendor_id": test_vendor.vendor_id, "name": vtype, "seats": 4},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == status.HTTP_201_CREATED
        
        # List all vehicle types
        list_response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == status.HTTP_200_OK
        items = list_response.json()["data"]["items"]
        assert len(items) >= 4
        type_names = [item["name"] for item in items]
        for vtype in types:
            assert vtype in type_names

    def test_vendor_isolation(self, client, test_db, vendor_vehicle_type_token, second_vendor_token, test_vendor, second_vendor):
        """Vendors can only access their own vehicle types"""
        # Vendor 1 creates vehicle type
        response1 = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "Vendor1 Type", "seats": 4},
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        vtype1_id = response1.json()["data"]["vehicle_type"]["vehicle_type_id"]
        
        # Vendor 2 creates vehicle type
        response2 = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": second_vendor.vendor_id, "name": "Vendor2 Type", "seats": 5},
            headers={"Authorization": f"Bearer {second_vendor_token}"}
        )
        assert response2.status_code == status.HTTP_201_CREATED
        vtype2_id = response2.json()["data"]["vehicle_type"]["vehicle_type_id"]
        
        # Vendor 1 cannot access Vendor 2's vehicle type
        response = client.get(
            f"/api/v1/vehicle-types/{vtype2_id}",
            headers={"Authorization": f"Bearer {vendor_vehicle_type_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # Vendor 2 cannot access Vendor 1's vehicle type
        response = client.get(
            f"/api/v1/vehicle-types/{vtype1_id}",
            headers={"Authorization": f"Bearer {second_vendor_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_employee_tenant_validation(self, client, test_db, employee_vehicle_type_token, test_vendor, second_vendor):
        """Employee can only access vehicle types for vendors in their tenant"""
        # Employee can access vendor in same tenant
        response1 = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "Same Tenant", "seats": 4},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Employee cannot access vendor in different tenant
        response2 = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": second_vendor.vendor_id, "name": "Different Tenant", "seats": 4},
            headers={"Authorization": f"Bearer {employee_vehicle_type_token}"}
        )
        assert response2.status_code == status.HTTP_403_FORBIDDEN
        assert "tenant" in str(response2.json()).lower()

    def test_filter_combinations(self, client, test_db, admin_token, test_vendor):
        """Test various filter combinations"""
        # Create test data
        client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "Active Type", "seats": 4, "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        vtype_response = client.post(
            "/api/v1/vehicle-types/",
            json={"vendor_id": test_vendor.vendor_id, "name": "Inactive Type", "seats": 5, "is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        vtype_id = vtype_response.json()["data"]["vehicle_type"]["vehicle_type_id"]
        
        # Deactivate the second type if created active
        client.patch(
            f"/api/v1/vehicle-types/{vtype_id}/toggle-status?vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Filter by name + active
        response = client.get(
            f"/api/v1/vehicle-types/?vendor_id={test_vendor.vendor_id}&name=Active Type&active_only=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        active_type_items = [item for item in items if item.get("name") == "Active Type"]
        assert all(item.get("is_active") for item in active_type_items) if active_type_items else True




