"""
Comprehensive test suite for Tenant endpoints.

Tests cover:
1. Create Tenant
2. List Tenants (with filters)
3. Get Single Tenant
4. Update Tenant
5. Toggle Tenant Status
6. Permission-based access control
7. Edge cases and error handling
"""
import pytest
from fastapi import status


class TestCreateTenant:
    """Test suite for POST /tenants/ endpoint."""
    
    def test_create_tenant_success_as_admin(
        self, client, admin_token, seed_permissions, sample_tenant_data
    ):
        """Test successful tenant creation by admin."""
        response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        
        # Verify tenant data
        tenant = data["data"]["tenant"]
        assert tenant["tenant_id"] == sample_tenant_data["tenant_id"]
        assert tenant["name"] == sample_tenant_data["name"]
        assert tenant["is_active"] is True
        
        # Verify team created
        assert "team" in data["data"]
        assert data["data"]["team"]["tenant_id"] == sample_tenant_data["tenant_id"]
        
        # Verify admin role created
        assert "admin_role" in data["data"]
        assert data["data"]["admin_role"]["tenant_id"] == sample_tenant_data["tenant_id"]
        
        # Verify admin policy created
        assert "admin_policy" in data["data"]
        assert data["data"]["admin_policy"]["tenant_id"] == sample_tenant_data["tenant_id"]
        
        # Verify employee created
        assert "employee" in data["data"]
        employee = data["data"]["employee"]
        assert employee["email"] == sample_tenant_data["employee_email"]
        assert employee["tenant_id"] == sample_tenant_data["tenant_id"]
    
    def test_create_tenant_duplicate_id(
        self, client, admin_token, seed_permissions, sample_tenant_data, test_db
    ):
        """Test creating tenant with duplicate ID fails."""
        # Create first tenant
        client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": admin_token}
        )
        
        # Try to create with same tenant_id
        response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["detail"]["success"] is False
        assert "already exists" in data["detail"]["message"].lower()
    
    def test_create_tenant_duplicate_name(
        self, client, admin_token, seed_permissions, sample_tenant_data
    ):
        """Test creating tenant with duplicate name fails."""
        # Create first tenant
        client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": admin_token}
        )
        
        # Try to create with same name but different ID
        duplicate_name_data = sample_tenant_data.copy()
        duplicate_name_data["tenant_id"] = "TENANT002"
        
        response = client.post(
            "/api/v1/tenants/",
            json=duplicate_name_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["detail"]["success"] is False
        assert "already exists" in data["detail"]["message"].lower()
    
    def test_create_tenant_invalid_permission_ids(
        self, client, admin_token, seed_permissions, sample_tenant_data
    ):
        """Test creating tenant with invalid permission IDs fails."""
        invalid_data = sample_tenant_data.copy()
        invalid_data["permission_ids"] = [9999, 8888]  # Non-existent IDs
        
        response = client.post(
            "/api/v1/tenants/",
            json=invalid_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
        assert "permission" in data["detail"]["message"].lower()
    
    def test_create_tenant_missing_employee_email(
        self, client, admin_token, seed_permissions, sample_tenant_data
    ):
        """Test creating tenant without employee email fails."""
        invalid_data = sample_tenant_data.copy()
        del invalid_data["employee_email"]
        
        response = client.post(
            "/api/v1/tenants/",
            json=invalid_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == 422
    
    def test_create_tenant_as_employee_forbidden(
        self, client, employee_token, sample_tenant_data
    ):
        """Test that employees cannot create tenants."""
        response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # For 403 from permission checker, detail is simple string not wrapped
    
    def test_create_tenant_as_vendor_forbidden(
        self, client, vendor_token, sample_tenant_data
    ):
        """Test that vendors cannot create tenants."""
        response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_create_tenant_without_auth(self, client, sample_tenant_data):
        """Test creating tenant without authentication fails."""
        response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_tenant_minimal_data(
        self, client, admin_token, seed_permissions
    ):
        """Test creating tenant with minimal required data."""
        minimal_data = {
            "tenant_id": "MIN001",
            "name": "Minimal Tenant",
            "address": "Min Address",
            "latitude": 0.0,
            "longitude": 0.0,
            "permission_ids": [1, 2],
            "employee_email": "min@tenant.com",
            "employee_phone": "+1111111111",
            "employee_name": "Min Employee",
            "employee_code": "MIN001",
            "employee_password": "MinPass@123",
            "employee_address": "Min Emp Address",
            "employee_latitude": 0.0,
            "employee_longitude": 0.0
        }
        
        response = client.post(
            "/api/v1/tenants/",
            json=minimal_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True


class TestListTenants:
    """Test suite for GET /tenants/ endpoint."""
    
    def test_list_tenants_as_admin(
        self, client, admin_token, admin_user, second_tenant
    ):
        """Test admin can list all tenants."""
        response = client.get(
            "/api/v1/tenants/",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
        assert data["data"]["total"] >= 2  # At least TEST001 and TEST002
    
    def test_list_tenants_as_employee_restricted(
        self, client, employee_token, employee_user
    ):
        """Test employee can only see their own tenant."""
        response = client.get(
            "/api/v1/tenants/",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total"] == 1
        assert data["data"]["items"][0]["tenant_id"] == employee_user["tenant"].tenant_id
    
    def test_list_tenants_with_name_filter(
        self, client, admin_token, admin_user, employee_user
    ):
        """Test filtering tenants by name."""
        response = client.get(
            "/api/v1/tenants/?name=Test",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        # Should find TEST001 tenant
        tenant_names = [t["name"] for t in data["data"]["items"]]
        assert any("Test" in name for name in tenant_names)
    
    def test_list_tenants_with_is_active_filter(
        self, client, admin_token, admin_user
    ):
        """Test filtering tenants by active status."""
        response = client.get(
            "/api/v1/tenants/?is_active=true",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        # All returned tenants should be active
        for tenant in data["data"]["items"]:
            assert tenant["is_active"] is True
    
    def test_list_tenants_with_pagination(
        self, client, admin_token, admin_user, employee_user
    ):
        """Test pagination parameters."""
        response = client.get(
            "/api/v1/tenants/?skip=0&limit=1",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["items"]) <= 1
    
    def test_list_tenants_as_vendor_forbidden(
        self, client, vendor_token
    ):
        """Test vendors cannot list tenants."""
        response = client.get(
            "/api/v1/tenants/",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # For 403 from permission checker, detail is a string
    
    def test_list_tenants_without_auth(self, client):
        """Test listing tenants without authentication fails."""
        response = client.get("/api/v1/tenants/")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetSingleTenant:
    """Test suite for GET /tenants/{tenant_id} endpoint."""
    
    def test_get_tenant_as_admin(
        self, client, admin_token, employee_user
    ):
        """Test admin can get any tenant by ID."""
        tenant_id = employee_user["tenant"].tenant_id
        response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant"]["tenant_id"] == tenant_id
        assert "admin_policy" in data["data"]
    
    def test_get_tenant_as_employee_own_tenant(
        self, client, employee_token, employee_user
    ):
        """Test employee can get their own tenant."""
        tenant_id = employee_user["tenant"].tenant_id
        response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant"]["tenant_id"] == tenant_id
    
    def test_get_tenant_as_employee_other_tenant(
        self, client, employee_token, admin_user, employee_user
    ):
        """Test employee trying to get other tenant gets their own tenant instead."""
        # Employee tries to access admin's tenant
        other_tenant_id = admin_user["tenant"].tenant_id
        response = client.get(
            f"/api/v1/tenants/{other_tenant_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        # Should return employee's own tenant, not the requested one
        assert data["data"]["tenant"]["tenant_id"] == employee_user["tenant"].tenant_id
    
    def test_get_tenant_not_found(
        self, client, admin_token
    ):
        """Test getting non-existent tenant."""
        response = client.get(
            "/api/v1/tenants/NONEXISTENT",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
        assert "not found" in data["detail"]["message"].lower()
    
    def test_get_tenant_as_vendor_forbidden(
        self, client, vendor_token, employee_user
    ):
        """Test vendors cannot get tenant details."""
        tenant_id = employee_user["tenant"].tenant_id
        response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_tenant_without_auth(self, client, employee_user):
        """Test getting tenant without authentication fails."""
        tenant_id = employee_user["tenant"].tenant_id
        response = client.get(f"/api/v1/tenants/{tenant_id}")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateTenant:
    """Test suite for PUT /tenants/{tenant_id} endpoint."""
    
    def test_update_tenant_as_admin(
        self, client, admin_token, employee_user
    ):
        """Test admin can update tenant."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {
            "name": "Updated Test Company",
            "address": "New Address 123",
            "is_active": True
        }
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant"]["name"] == update_data["name"]
        assert data["data"]["tenant"]["address"] == update_data["address"]
    
    def test_update_tenant_with_permissions(
        self, client, admin_token, employee_user, seed_permissions
    ):
        """Test updating tenant permissions."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {
            "permission_ids": [1, 2, 3]  # Update with new permission set
        }
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "admin_policy" in data["data"]
        # Verify permissions were updated
        policy_perms = data["data"]["admin_policy"]["permissions"]
        assert len(policy_perms) == 3
    
    def test_update_tenant_invalid_permissions(
        self, client, admin_token, employee_user
    ):
        """Test updating tenant with invalid permission IDs."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {
            "permission_ids": [9999, 8888]
        }
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["detail"]["success"] is False
        assert "invalid" in data["detail"]["message"].lower()
    
    def test_update_tenant_not_found(
        self, client, admin_token
    ):
        """Test updating non-existent tenant."""
        update_data = {"name": "New Name"}
        
        response = client.put(
            "/api/v1/tenants/NONEXISTENT",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
    
    def test_update_tenant_as_employee_forbidden(
        self, client, employee_token, employee_user
    ):
        """Test employees cannot update tenants."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {"name": "New Name"}
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # For 403 from permission checker, detail is a string
    
    def test_update_tenant_as_vendor_forbidden(
        self, client, vendor_token, employee_user
    ):
        """Test vendors cannot update tenants."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {"name": "New Name"}
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_tenant_partial_update(
        self, client, admin_token, employee_user
    ):
        """Test partial update of tenant fields."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {
            "address": "Only Address Updated"
        }
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant"]["address"] == update_data["address"]
        # Other fields should remain unchanged
        assert data["data"]["tenant"]["tenant_id"] == tenant_id
    
    def test_update_tenant_without_auth(self, client, employee_user):
        """Test updating tenant without authentication fails."""
        tenant_id = employee_user["tenant"].tenant_id
        update_data = {"name": "New Name"}
        
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json=update_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestToggleTenantStatus:
    """Test suite for PATCH /tenants/{tenant_id}/toggle-status endpoint."""
    
    def test_toggle_tenant_status_as_admin(
        self, client, admin_token, employee_user, test_db
    ):
        """Test admin can toggle tenant status."""
        tenant_id = employee_user["tenant"].tenant_id
        original_status = employee_user["tenant"].is_active
        
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["is_active"] != original_status
    
    def test_toggle_tenant_status_twice(
        self, client, admin_token, employee_user
    ):
        """Test toggling status twice returns to original state."""
        tenant_id = employee_user["tenant"].tenant_id
        original_status = employee_user["tenant"].is_active
        
        # First toggle
        response1 = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_200_OK
        
        # Second toggle
        response2 = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert response2.status_code == status.HTTP_200_OK
        assert response2.json()["data"]["is_active"] == original_status
    
    def test_toggle_tenant_status_not_found(
        self, client, admin_token
    ):
        """Test toggling status of non-existent tenant."""
        response = client.patch(
            "/api/v1/tenants/NONEXISTENT/toggle-status",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
    
    def test_toggle_tenant_status_as_employee_forbidden(
        self, client, employee_token, employee_user
    ):
        """Test employees cannot toggle tenant status."""
        tenant_id = employee_user["tenant"].tenant_id
        
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # For 403 from permission checker, detail is a string
    
    def test_toggle_tenant_status_as_vendor_forbidden(
        self, client, vendor_token, employee_user
    ):
        """Test vendors cannot toggle tenant status."""
        tenant_id = employee_user["tenant"].tenant_id
        
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_toggle_tenant_status_without_auth(self, client, employee_user):
        """Test toggling status without authentication fails."""
        tenant_id = employee_user["tenant"].tenant_id
        
        response = client.patch(f"/api/v1/tenants/{tenant_id}/toggle-status")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTenantIntegration:
    """Integration tests for tenant workflows."""
    
    def test_complete_tenant_lifecycle(
        self, client, admin_token, seed_permissions, sample_tenant_data
    ):
        """Test complete CRUD lifecycle of a tenant."""
        tenant_id = "LIFECYCLE001"
        sample_tenant_data["tenant_id"] = tenant_id
        
        # 1. Create tenant
        create_response = client.post(
            "/api/v1/tenants/",
            json=sample_tenant_data,
            headers={"Authorization": admin_token}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # 2. List tenants (should include new tenant)
        list_response = client.get(
            "/api/v1/tenants/",
            headers={"Authorization": admin_token}
        )
        assert list_response.status_code == status.HTTP_200_OK
        tenant_ids = [t["tenant_id"] for t in list_response.json()["data"]["items"]]
        assert tenant_id in tenant_ids
        
        # 3. Get single tenant
        get_response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["data"]["tenant"]["tenant_id"] == tenant_id
        
        # 4. Update tenant
        update_response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json={"name": "Updated Lifecycle Tenant"},
            headers={"Authorization": admin_token}
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["data"]["tenant"]["name"] == "Updated Lifecycle Tenant"
        
        # 5. Toggle status
        toggle_response = client.patch(
            f"/api/v1/tenants/{tenant_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert toggle_response.status_code == status.HTTP_200_OK
        assert toggle_response.json()["data"]["is_active"] is False
    
    def test_tenant_isolation_between_employees(
        self, client, test_db, seed_permissions
    ):
        """Test that employees from different tenants cannot access each other's data."""
        # This test would require creating two separate employee users
        # from different tenants and verifying isolation
        pass


# Markers for organizing test execution
pytestmark = [
    pytest.mark.integration,
]
