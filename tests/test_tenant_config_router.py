import pytest
from fastapi import status
from datetime import time


# ==================== Test Get Tenant Config ====================

class TestGetTenantConfig:
    """Test suite for GET /tenant-config/ endpoint"""

    def test_get_config_as_admin_with_tenant_id(self, client, admin_token, test_tenant):
        """Admin should be able to get config with tenant_id parameter"""
        response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tenant_id"] == test_tenant.tenant_id
        assert "escort_required_for_women" in data
        assert "login_boarding_otp" in data

    def test_get_config_as_admin_without_tenant_id(self, client, admin_token):
        """Admin without tenant_id parameter should get 400"""
        response = client.get(
            "/api/v1/tenant-config/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "tenant id" in str(response.json()).lower()

    def test_get_config_as_employee(self, client, employee_token, test_tenant):
        """Employee should be able to get config (tenant_id from token)"""
        response = client.get(
            "/api/v1/tenant-config/",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tenant_id"] == test_tenant.tenant_id

    def test_get_config_as_vendor(self, client, vendor_token, test_tenant):
        """Vendor should be able to get config (tenant_id from token)"""
        # Create vendor token with tenant_config.read permission
        from common_utils.auth.utils import create_access_token
        vendor_token_with_permission = create_access_token(
            user_id="999",
            tenant_id=test_tenant.tenant_id,
            user_type="vendor",
            custom_claims={
                "email": "vendor@test.com",
                "permissions": ["tenant_config.read"]
            }
        )
        
        response = client.get(
            "/api/v1/tenant-config/",
            headers={"Authorization": f"Bearer {vendor_token_with_permission}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tenant_id"] == test_tenant.tenant_id

    def test_get_config_driver_forbidden(self, client, driver_token, test_tenant):
        """Driver should not be able to access tenant config"""
        response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_config_unauthorized(self, client, test_tenant):
        """Getting config without token should fail"""
        response = client.get(f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_config_creates_default_if_not_exists(self, client, admin_token, second_tenant):
        """Should create default config if none exists for tenant"""
        response = client.get(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tenant_id"] == second_tenant.tenant_id
        # Default values
        assert data["escort_required_for_women"] is True
        assert data["login_boarding_otp"] is True
        assert data["login_deboarding_otp"] is True

    def test_get_config_employee_no_permission(self, client, test_tenant):
        """Employee without tenant_config.read permission should fail"""
        from common_utils.auth.utils import create_access_token
        token = create_access_token(
            user_id="123",
            tenant_id=test_tenant.tenant_id,
            user_type="employee",
            custom_claims={
                "email": "emp@test.com",
                "permissions": []
            }
        )
        
        response = client.get(
            "/api/v1/tenant-config/",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Update Tenant Config ====================

class TestUpdateTenantConfig:
    """Test suite for PUT /tenant-config/ endpoint"""

    def test_update_config_as_admin(self, client, admin_token, test_tenant):
        """Admin should be able to update config with tenant_id parameter"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_for_women": False,
                "login_boarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_required_for_women"] is False
        assert data["login_boarding_otp"] is False

    def test_update_config_as_admin_without_tenant_id(self, client, admin_token):
        """Admin without tenant_id parameter should get 400"""
        response = client.put(
            "/api/v1/tenant-config/",
            json={"escort_required_for_women": False},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_config_as_employee(self, client, employee_token, test_tenant):
        """Employee should be able to update config (tenant_id from token)"""
        response = client.put(
            "/api/v1/tenant-config/",
            json={
                "escort_required_for_women": False,
                "logout_boarding_otp": False
            },
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_required_for_women"] is False
        assert data["logout_boarding_otp"] is False

    def test_update_config_escort_time_windows(self, client, admin_token, test_tenant):
        """Should be able to update escort time windows"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": "22:00:00",
                "escort_required_end_time": "06:00:00"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_required_start_time"] == "22:00:00"
        assert data["escort_required_end_time"] == "06:00:00"

    def test_update_config_all_otp_flags(self, client, admin_token, test_tenant):
        """Should be able to update all OTP flags"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "login_boarding_otp": True,
                "login_deboarding_otp": False,
                "logout_boarding_otp": True,
                "logout_deboarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["login_boarding_otp"] is True
        assert data["login_deboarding_otp"] is False
        assert data["logout_boarding_otp"] is True
        assert data["logout_deboarding_otp"] is False

    def test_update_config_partial_update(self, client, admin_token, test_tenant):
        """Should support partial updates"""
        # First get current config
        get_response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        original = get_response.json()

        # Update only one field
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={"escort_required_for_women": False},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["escort_required_for_women"] is False
        # Other fields should remain unchanged
        assert data["login_boarding_otp"] == original["login_boarding_otp"]

    def test_update_config_driver_forbidden(self, client, driver_token, test_tenant):
        """Driver should not be able to update config"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={"escort_required_for_women": False},
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_config_unauthorized(self, client, test_tenant):
        """Updating config without token should fail"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={"escort_required_for_women": False}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_config_invalid_time_format(self, client, admin_token, test_tenant):
        """Invalid time format should fail"""
        response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": "invalid_time"
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_config_employee_no_permission(self, client, test_tenant):
        """Employee without tenant_config.update permission should fail"""
        from common_utils.auth.utils import create_access_token
        token = create_access_token(
            user_id="123",
            tenant_id=test_tenant.tenant_id,
            user_type="employee",
            custom_claims={
                "email": "emp@test.com",
                "permissions": ["tenant_config.read"]
            }
        )
        
        response = client.put(
            "/api/v1/tenant-config/",
            json={"escort_required_for_women": False},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Tenant Config Integration ====================

class TestTenantConfigIntegration:
    """Integration tests for tenant config workflows"""

    def test_complete_config_lifecycle(self, client, admin_token, test_tenant):
        """Test complete configuration management lifecycle"""
        # Get default config
        get_response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_200_OK
        original = get_response.json()

        # Update multiple times with different values
        update1_response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_for_women": False,
                "login_boarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert update1_response.status_code == status.HTTP_200_OK
        assert update1_response.json()["escort_required_for_women"] is False

        # Update again with escort times
        update2_response = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": "20:00:00",
                "escort_required_end_time": "07:00:00"
            },
            headers={"Authorization": admin_token}
        )
        assert update2_response.status_code == status.HTTP_200_OK
        data = update2_response.json()
        assert data["escort_required_start_time"] == "20:00:00"
        assert data["escort_required_end_time"] == "07:00:00"

        # Verify final state
        final_response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        final_data = final_response.json()
        assert final_data["escort_required_start_time"] == "20:00:00"
        assert final_data["escort_required_end_time"] == "07:00:00"
        assert final_data["escort_required_for_women"] is False

    def test_tenant_isolation(self, client, admin_token, test_tenant, second_tenant):
        """Verify config isolation between tenants"""
        # Update tenant 1 config
        client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={"escort_required_for_women": False},
            headers={"Authorization": admin_token}
        )

        # Update tenant 2 config differently
        client.put(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            json={"escort_required_for_women": True},
            headers={"Authorization": admin_token}
        )

        # Verify tenant 1 config
        tenant1_response = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert tenant1_response.json()["escort_required_for_women"] is False

        # Verify tenant 2 config
        tenant2_response = client.get(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert tenant2_response.json()["escort_required_for_women"] is True

    def test_employee_access_own_tenant_only(self, client, employee_token, test_tenant, second_tenant):
        """Employee should only access their own tenant config"""
        # Employee can access their own tenant (automatic from token)
        own_response = client.get(
            "/api/v1/tenant-config/",
            headers={"Authorization": employee_token}
        )
        assert own_response.status_code == status.HTTP_200_OK
        assert own_response.json()["tenant_id"] == test_tenant.tenant_id

        # Employee cannot override with query param (it's ignored for employee)
        # The tenant_id from token is always used
        response = client.get(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        # Should still get their own tenant config
        assert response.json()["tenant_id"] == test_tenant.tenant_id

    def test_otp_configuration_combinations(self, client, admin_token, test_tenant):
        """Test various OTP configuration combinations"""
        # All OTPs disabled
        response1 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "login_boarding_otp": False,
                "login_deboarding_otp": False,
                "logout_boarding_otp": False,
                "logout_deboarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_200_OK
        data1 = response1.json()
        assert data1["login_boarding_otp"] is False
        assert data1["logout_deboarding_otp"] is False

        # Only login OTPs enabled
        response2 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "login_boarding_otp": True,
                "login_deboarding_otp": True,
                "logout_boarding_otp": False,
                "logout_deboarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()
        assert data2["login_boarding_otp"] is True
        assert data2["logout_boarding_otp"] is False

    def test_escort_time_window_configurations(self, client, admin_token, test_tenant):
        """Test various escort time window configurations"""
        # Night shift (10 PM to 6 AM)
        response1 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": "22:00:00",
                "escort_required_end_time": "06:00:00",
                "escort_required_for_women": True
            },
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_200_OK

        # Early morning (4 AM to 8 AM)
        response2 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": "04:00:00",
                "escort_required_end_time": "08:00:00"
            },
            headers={"Authorization": admin_token}
        )
        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()
        assert data2["escort_required_start_time"] == "04:00:00"

        # Clear escort times (set to null)
        response3 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_start_time": None,
                "escort_required_end_time": None
            },
            headers={"Authorization": admin_token}
        )
        assert response3.status_code == status.HTTP_200_OK
        data3 = response3.json()
        assert data3["escort_required_start_time"] is None
        assert data3["escort_required_end_time"] is None

    def test_admin_manages_multiple_tenants(self, client, admin_token, test_tenant, second_tenant):
        """Admin should be able to manage configs for multiple tenants"""
        # Configure tenant 1
        response1 = client.put(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            json={
                "escort_required_for_women": True,
                "login_boarding_otp": True
            },
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_200_OK

        # Configure tenant 2 differently
        response2 = client.put(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            json={
                "escort_required_for_women": False,
                "login_boarding_otp": False
            },
            headers={"Authorization": admin_token}
        )
        assert response2.status_code == status.HTTP_200_OK

        # Verify both tenants have correct configs
        verify1 = client.get(
            f"/api/v1/tenant-config/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        verify2 = client.get(
            f"/api/v1/tenant-config/?tenant_id={second_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )

        assert verify1.json()["escort_required_for_women"] is True
        assert verify2.json()["escort_required_for_women"] is False

