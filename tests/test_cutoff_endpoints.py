"""
Test suite for cutoff endpoints (/api/v1/cutoffs/)
Tests: GET (fetch cutoff), PUT (update cutoff)
"""

import pytest
from fastapi import status


class TestGetCutoffs:
    """Test GET /api/v1/cutoffs/"""
    
    def test_get_cutoffs_as_admin_all_tenants(self, client, admin_token):
        """Admin without tenant_id can fetch all cutoffs"""
        response = client.get(
            "/api/v1/cutoffs/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "data" in data
        assert "cutoffs" in data["data"]
        assert isinstance(data["data"]["cutoffs"], list)
    
    def test_get_cutoffs_as_admin_specific_tenant(self, client, admin_token, test_tenant):
        """Admin with tenant_id can fetch specific tenant's cutoff"""
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert isinstance(cutoffs, list)
        assert len(cutoffs) == 1
        assert cutoffs[0]["tenant_id"] == test_tenant.tenant_id
    
    def test_get_cutoffs_as_employee_success(self, client, employee_token, test_tenant):
        """Employee fetches cutoff for their own tenant"""
        response = client.get(
            "/api/v1/cutoffs/",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert isinstance(cutoffs, list)
        assert len(cutoffs) == 1
        assert cutoffs[0]["tenant_id"] == test_tenant.tenant_id
    
    def test_get_cutoffs_employee_enforces_own_tenant(self, client, employee_token, test_tenant):
        """Employee cannot specify different tenant_id"""
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": "OTHER_TENANT"},
            headers={"Authorization": employee_token}
        )
        # Should still return employee's own tenant, ignoring the parameter
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert len(cutoffs) == 1
        assert cutoffs[0]["tenant_id"] == test_tenant.tenant_id
    
    def test_get_cutoffs_vendor_forbidden(self, client, vendor_token):
        """Vendor users cannot access cutoffs"""
        response = client.get(
            "/api/v1/cutoffs/",
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_cutoffs_unauthorized(self, client):
        """Unauthorized request returns 401"""
        response = client.get("/api/v1/cutoffs/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_cutoffs_tenant_not_found(self, client, admin_token):
        """Return 404 for non-existent tenant"""
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": "NONEXISTENT"},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_cutoffs_creates_default_if_not_exists(self, client, admin_token, test_tenant):
        """GET creates default cutoff if none exists"""
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert len(cutoffs) == 1
        cutoff = cutoffs[0]
        assert cutoff["tenant_id"] == test_tenant.tenant_id
        # Default values should be "0:00"
        assert "booking_login_cutoff" in cutoff
        assert "cancel_login_cutoff" in cutoff


class TestUpdateCutoff:
    """Test PUT /api/v1/cutoffs/"""
    
    def test_update_cutoff_as_employee_success(self, client, employee_token, test_tenant):
        """Employee can update cutoff for their tenant"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "02:00",
            "cancel_login_cutoff": "01:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        cutoff = data["data"]["cutoff"]
        assert cutoff["tenant_id"] == test_tenant.tenant_id
        assert "booking_login_cutoff" in cutoff
        assert "cancel_login_cutoff" in cutoff
    
    def test_update_cutoff_as_admin_success(self, client, admin_token, test_tenant):
        """Admin can update cutoff for any tenant"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "03:00",
            "cancel_login_cutoff": "01:30"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
    
    def test_update_cutoff_partial_update(self, client, employee_token, test_tenant):
        """Can update only booking_cutoff"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "04:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_cutoff_admin_without_tenant_id(self, client, admin_token):
        """Admin must provide tenant_id"""
        cutoff_update = {
            "booking_login_cutoff": "02:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_update_cutoff_employee_enforces_own_tenant(self, client, employee_token, test_tenant, second_tenant):
        """Employee's tenant_id is enforced from token, ignoring request body"""
        cutoff_update = {
            "tenant_id": second_tenant.tenant_id,  # Trying to specify TEST002
            "booking_login_cutoff": "02:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": employee_token}
        )
        # API enforces employee's tenant from token, request succeeds but updates TEST001
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Verify it updated TEST001 (employee's tenant), not TEST002
        assert data["data"]["cutoff"]["tenant_id"] == test_tenant.tenant_id
    
    def test_update_cutoff_tenant_not_found(self, client, admin_token):
        """Return 404 for non-existent tenant"""
        cutoff_update = {
            "tenant_id": "NONEXISTENT",
            "booking_login_cutoff": "02:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_cutoff_invalid_time_format(self, client, admin_token, test_tenant):
        """Reject invalid time format"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "invalid_time"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_update_cutoff_negative_time(self, client, admin_token, test_tenant):
        """Reject negative time values"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "-01:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_update_cutoff_zero_values(self, client, admin_token, test_tenant):
        """Zero values are valid"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "00:00",
            "cancel_login_cutoff": "00:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_cutoff_large_values(self, client, admin_token, test_tenant):
        """Large time values (48 hours) are valid"""
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "48:00",
            "cancel_login_cutoff": "24:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK


class TestCutoffIntegration:
    """Integration tests for cutoff complete lifecycle"""
    
    def test_cutoff_complete_lifecycle(self, client, admin_token, test_tenant):
        """Test create → read → update → read cycle"""
        # Initial GET (creates default)
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Update cutoff
        cutoff_update = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "03:00",
            "cancel_login_cutoff": "01:30"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Verify update
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert len(cutoffs) == 1
        cutoff = cutoffs[0]
        assert cutoff["booking_login_cutoff"] == "3:00"  # Schema returns "H:MM" not "HH:MM"
        assert cutoff["cancel_login_cutoff"] == "1:30"
    
    def test_cutoff_tenant_isolation(self, client, admin_token, test_tenant, second_tenant):
        """Cutoffs are isolated per tenant"""
        # Update TEST001 cutoff
        cutoff_update1 = {
            "tenant_id": test_tenant.tenant_id,
            "booking_login_cutoff": "02:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update1,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Update TEST002 cutoff with different value
        cutoff_update2 = {
            "tenant_id": second_tenant.tenant_id,
            "booking_login_cutoff": "05:00"
        }
        response = client.put(
            "/api/v1/cutoffs/",
            json=cutoff_update2,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Verify TEST001 cutoff unchanged
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        cutoffs1 = response.json()["data"]["cutoffs"]
        assert cutoffs1[0]["booking_login_cutoff"] == "2:00"
        
        # Verify TEST002 cutoff
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": second_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        cutoffs2 = response.json()["data"]["cutoffs"]
        assert cutoffs2[0]["booking_login_cutoff"] == "5:00"
    
    def test_cutoff_auto_creation_on_first_get(self, client, admin_token, test_tenant):
        """First GET creates default cutoff with 0:00 values"""
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        cutoffs = data["data"]["cutoffs"]
        assert len(cutoffs) == 1
        cutoff = cutoffs[0]
        assert cutoff["tenant_id"] == test_tenant.tenant_id
        # Defaults should be "0:00"
        assert cutoff["booking_login_cutoff"] == "0:00"
        assert cutoff["cancel_login_cutoff"] == "0:00"
    
    def test_cutoff_multiple_updates(self, client, admin_token, test_tenant):
        """Multiple updates should overwrite previous values"""
        updates = [
            {"tenant_id": test_tenant.tenant_id, "booking_login_cutoff": "01:00"},
            {"tenant_id": test_tenant.tenant_id, "booking_login_cutoff": "02:00"},
            {"tenant_id": test_tenant.tenant_id, "booking_login_cutoff": "03:00"}
        ]
        
        for update in updates:
            response = client.put(
                "/api/v1/cutoffs/",
                json=update,
                headers={"Authorization": admin_token}
            )
            assert response.status_code == status.HTTP_200_OK
        
        # Final value should be last update
        response = client.get(
            "/api/v1/cutoffs/",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        cutoffs = response.json()["data"]["cutoffs"]
        assert cutoffs[0]["booking_login_cutoff"] == "3:00"
