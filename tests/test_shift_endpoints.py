"""
Test cases for shift endpoints.
Tests CRUD operations for shift management.
"""
import pytest
from fastapi import status
from datetime import time


class TestCreateShift:
    """Test POST /api/v1/shifts/"""
    
    def test_create_shift_as_employee_success(self, client, employee_token, test_tenant):
        """Employee can create shift in their tenant"""
        shift_data = {
            "shift_code": "EMP_SHIFT_001",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup",
            "gender": "Male",
            "waiting_time_minutes": 15
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Response: {response.json()}")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        shift = data["data"]
        assert shift["shift_code"] == "EMP_SHIFT_001"
        assert shift["log_type"] == "IN"
        assert shift["tenant_id"] == test_tenant.tenant_id
    
    def test_create_shift_as_admin_success(self, client, admin_token, test_tenant):
        """Admin can create shift for any tenant"""
        shift_data = {
            "tenant_id": test_tenant.tenant_id,
            "shift_code": "ADMIN_SHIFT_001",
            "log_type": "OUT",
            "shift_time": "18:00",
            "pickup_type": "Nodal",
            "gender": "Female",
            "waiting_time_minutes": 20
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        shift = response.json()["data"]
        assert shift["shift_code"] == "ADMIN_SHIFT_001"
        assert shift["log_type"] == "OUT"
    
    def test_create_shift_admin_without_tenant_id(self, client, admin_token):
        """Admin must provide tenant_id when creating shift"""
        shift_data = {
            "shift_code": "ADMIN_SHIFT",
            "log_type": "IN",
            "shift_time": "10:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.json()
    
    def test_create_shift_duplicate_code(self, client, employee_token, test_shift):
        """Cannot create shift with duplicate code in same tenant"""
        shift_data = {
            "shift_code": test_shift.shift_code,
            "log_type": "IN",
            "shift_time": "10:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_409_CONFLICT
    
    def test_create_shift_invalid_log_type(self, client, employee_token):
        """Invalid log_type should fail"""
        shift_data = {
            "shift_code": "INVALID_LOG",
            "log_type": "INVALID",
            "shift_time": "09:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_create_shift_invalid_time_format(self, client, employee_token):
        """Invalid time format should fail"""
        shift_data = {
            "shift_code": "INVALID_TIME",
            "log_type": "IN",
            "shift_time": "25:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_create_shift_missing_required_fields(self, client, employee_token):
        """Missing required fields should fail"""
        shift_data = {
            "shift_code": "INCOMPLETE"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_create_shift_vendor_forbidden(self, client, vendor_token):
        """Vendor users cannot create shifts"""
        shift_data = {
            "shift_code": "VENDOR_SHIFT",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_create_shift_without_auth(self, client):
        """Unauthenticated request should fail"""
        shift_data = {
            "shift_code": "UNAUTH_SHIFT",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_shift_with_optional_fields(self, client, employee_token):
        """Create shift with all optional fields"""
        shift_data = {
            "shift_code": "FULL_SHIFT",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup",
            "gender": "Other",
            "waiting_time_minutes": 30,
            "is_active": True
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        shift = response.json()["data"]
        assert shift["pickup_type"] == "Pickup"
        assert shift["gender"] == "Other"
        assert shift["waiting_time_minutes"] == 30


class TestListShifts:
    """Test GET /api/v1/shifts/"""
    
    def test_list_shifts_as_employee_success(self, client, employee_token, test_tenant):
        """Employee can list shifts in their tenant"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
        assert isinstance(data["data"]["items"], list)
    
    def test_list_shifts_as_admin_success(self, client, admin_token, test_tenant):
        """Admin can list shifts for any tenant"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert "items" in response.json()["data"]
    
    def test_list_shifts_admin_without_tenant_id(self, client, admin_token):
        """Admin without tenant_id gets their own tenant (SYSTEM)"""
        response = client.get(
            "/api/v1/shifts/",
            headers={"Authorization": admin_token}
        )
        # Admin defaults to SYSTEM tenant
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data["data"]
    
    def test_list_shifts_filter_by_log_type(self, client, employee_token, test_tenant):
        """Filter shifts by log_type"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}&log_type=IN",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        for shift in items:
            assert shift["log_type"] == "IN"
    
    def test_list_shifts_filter_by_is_active(self, client, employee_token, test_tenant):
        """Filter shifts by is_active"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}&is_active=true",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        for shift in items:
            assert shift["is_active"] is True
    
    def test_list_shifts_with_pagination(self, client, employee_token, test_tenant):
        """Test pagination parameters"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}&skip=0&limit=5",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "total" in data
        assert len(data["items"]) <= 5
    
    def test_list_shifts_tenant_not_found(self, client, admin_token):
        """Return error for non-existent tenant"""
        response = client.get(
            "/api/v1/shifts/?tenant_id=NONEXISTENT",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_list_shifts_vendor_forbidden(self, client, vendor_token):
        """Vendor cannot list shifts"""
        response = client.get(
            "/api/v1/shifts/?tenant_id=TEST001",
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGetSingleShift:
    """Test GET /api/v1/shifts/{shift_id}"""
    
    def test_get_shift_as_employee_success(self, client, employee_token, test_shift):
        """Employee can get shift in their tenant"""
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        shift = data["data"]
        assert shift["shift_id"] == test_shift.shift_id
        assert shift["shift_code"] == test_shift.shift_code
    
    def test_get_shift_as_admin_success(self, client, admin_token, test_shift):
        """Admin can get any shift"""
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        shift = response.json()["data"]
        assert shift["shift_id"] == test_shift.shift_id
    
    def test_get_shift_employee_cross_tenant_forbidden(self, client, employee_token, second_shift):
        """Employee cannot get shift from another tenant"""
        response = client.get(
            f"/api/v1/shifts/{second_shift.shift_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_shift_not_found(self, client, admin_token):
        """Return error for non-existent shift"""
        response = client.get(
            "/api/v1/shifts/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_shift_vendor_forbidden(self, client, vendor_token, test_shift):
        """Vendor cannot get shifts"""
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUpdateShift:
    """Test PUT /api/v1/shifts/{shift_id}"""
    
    def test_update_shift_as_employee_success(self, client, employee_token, test_shift):
        """Employee can update shift in their tenant"""
        shift_update = {
            "shift_time": "10:00",
            "waiting_time_minutes": 25
        }
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        shift = data["data"]
        assert shift["waiting_time_minutes"] == 25
    
    def test_update_shift_as_admin_success(self, client, admin_token, test_shift):
        """Admin can update any shift"""
        shift_update = {
            "shift_time": "11:00",
            "pickup_type": "Nodal"
        }
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        shift = response.json()["data"]
        assert shift["pickup_type"] == "Nodal"
    
    def test_update_shift_partial_update(self, client, employee_token, test_shift):
        """Partial update should work"""
        shift_update = {
            "waiting_time_minutes": 30
        }
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        shift = response.json()["data"]
        assert shift["waiting_time_minutes"] == 30
    
    def test_update_shift_employee_cross_tenant_forbidden(self, client, employee_token, second_shift):
        """Employee cannot update shift from another tenant"""
        shift_update = {"waiting_time_minutes": 20}
        response = client.put(
            f"/api/v1/shifts/{second_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_shift_not_found(self, client, admin_token):
        """Return error for non-existent shift"""
        shift_update = {"waiting_time_minutes": 20}
        response = client.put(
            "/api/v1/shifts/99999",
            json=shift_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_shift_invalid_log_type(self, client, employee_token, test_shift):
        """Invalid log_type should fail"""
        shift_update = {"log_type": "INVALID"}
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_update_shift_invalid_time(self, client, employee_token, test_shift):
        """Invalid time format should fail"""
        shift_update = {"shift_time": "25:00"}
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_update_shift_change_multiple_fields(self, client, admin_token, test_shift):
        """Update multiple fields at once"""
        shift_update = {
            "shift_time": "12:00",
            "waiting_time_minutes": 40,
            "pickup_type": "Nodal",
            "gender": "Female"
        }
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        shift = response.json()["data"]
        assert shift["waiting_time_minutes"] == 40
        assert shift["pickup_type"] == "Nodal"
        assert shift["gender"] == "Female"
    
    def test_update_shift_vendor_forbidden(self, client, vendor_token, test_shift):
        """Vendor cannot update shifts"""
        shift_update = {"waiting_time_minutes": 20}
        response = client.put(
            f"/api/v1/shifts/{test_shift.shift_id}",
            json=shift_update,
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestToggleShiftStatus:
    """Test PATCH /api/v1/shifts/{shift_id}/toggle-status"""
    
    def test_toggle_shift_status_as_employee_success(self, client, employee_token, test_shift):
        """Employee can toggle shift status in their tenant"""
        initial_status = test_shift.is_active
        response = client.patch(
            f"/api/v1/shifts/{test_shift.shift_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        shift = data["data"]
        assert shift["is_active"] == (not initial_status)
    
    def test_toggle_shift_status_as_admin_success(self, client, admin_token, test_shift):
        """Admin can toggle shift status for any shift"""
        response = client.patch(
            f"/api/v1/shifts/{test_shift.shift_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_toggle_shift_status_twice(self, client, employee_token, test_shift):
        """Toggle twice should return to original state"""
        # Get initial status
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": employee_token}
        )
        initial_status = response.json()["data"]["is_active"]
        
        # Toggle once
        response = client.patch(
            f"/api/v1/shifts/{test_shift.shift_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_active"] == (not initial_status)
        
        # Toggle again
        response = client.patch(
            f"/api/v1/shifts/{test_shift.shift_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_active"] == initial_status
    
    def test_toggle_shift_status_employee_cross_tenant_forbidden(self, client, employee_token, second_shift):
        """Employee cannot toggle shift from another tenant"""
        response = client.patch(
            f"/api/v1/shifts/{second_shift.shift_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_toggle_shift_status_not_found(self, client, admin_token):
        """Return error for non-existent shift"""
        response = client.patch(
            "/api/v1/shifts/99999/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_toggle_shift_status_vendor_forbidden(self, client, vendor_token, test_shift):
        """Vendor cannot toggle shift status"""
        response = client.patch(
            f"/api/v1/shifts/{test_shift.shift_id}/toggle-status",
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestShiftIntegration:
    """Integration tests for shift operations"""
    
    def test_shift_complete_lifecycle(self, client, employee_token, test_tenant):
        """Test complete shift lifecycle"""
        # 1. Create shift
        shift_data = {
            "shift_code": "LIFECYCLE_SHIFT",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup",
            "waiting_time_minutes": 15
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data,
            headers={"Authorization": employee_token}
        )
        print(f"\n>>> Response status: {response.status_code}")
        print(f">>> Response body: {response.json()}")
        assert response.status_code == status.HTTP_201_CREATED
        shift_id = response.json()["data"]["shift_id"]
        
        # 2. Read shift
        response = client.get(
            f"/api/v1/shifts/{shift_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["shift_code"] == "LIFECYCLE_SHIFT"
        
        # 3. Update shift
        shift_update = {"waiting_time_minutes": 25}
        response = client.put(
            f"/api/v1/shifts/{shift_id}",
            json=shift_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["waiting_time_minutes"] == 25
        
        # 4. Toggle status
        response = client.patch(
            f"/api/v1/shifts/{shift_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_active"] is False
    
    def test_shift_tenant_isolation(self, client, employee_token, admin_token, test_shift, second_shift):
        """Ensure shifts are tenant-isolated"""
        # Employee can access their tenant's shift
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Employee cannot access other tenant's shift
        response = client.get(
            f"/api/v1/shifts/{second_shift.shift_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Admin can access both
        response = client.get(
            f"/api/v1/shifts/{test_shift.shift_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        response = client.get(
            f"/api/v1/shifts/{second_shift.shift_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_shift_with_multiple_filters(self, client, employee_token, test_tenant):
        """Test listing shifts with multiple filters"""
        response = client.get(
            f"/api/v1/shifts/?tenant_id={test_tenant.tenant_id}&log_type=IN&is_active=true&skip=0&limit=10",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        for shift in items:
            assert shift["log_type"] == "IN"
            assert shift["is_active"] is True
            assert shift["tenant_id"] == test_tenant.tenant_id
    
    def test_shift_unique_code_per_tenant(self, client, admin_token, test_tenant, second_tenant):
        """Same shift code can exist in different tenants"""
        shift_data_tenant1 = {
            "tenant_id": test_tenant.tenant_id,
            "shift_code": "SHARED_CODE",
            "log_type": "IN",
            "shift_time": "09:00",
            "pickup_type": "Pickup"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data_tenant1,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_201_CREATED
        
        # Same code in different tenant should succeed
        shift_data_tenant2 = {
            "tenant_id": second_tenant.tenant_id,
            "shift_code": "SHARED_CODE",
            "log_type": "OUT",
            "shift_time": "18:00",
            "pickup_type": "Nodal"
        }
        response = client.post(
            "/api/v1/shifts/",
            json=shift_data_tenant2,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_201_CREATED

