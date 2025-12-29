"""
Test cases for weekoff config endpoints.
Tests GET and PUT operations for employee, team, and tenant level weekoff configs.
"""
import pytest
from fastapi import status


class TestGetWeekoffByEmployee:
    """Test GET /api/v1/weekoff-configs/{employee_id}"""
    
    def test_get_weekoff_by_employee_as_employee_success(self, client, employee_token, test_employee):
        """Employee can fetch their own weekoff config"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_config" in data["data"]
        weekoff = data["data"]["weekoff_config"]
        assert weekoff["employee_id"] == test_employee["employee"].employee_id
        assert "monday" in weekoff
        assert "tuesday" in weekoff
    
    def test_get_weekoff_by_employee_as_admin_success(self, client, admin_token, test_employee):
        """Admin can fetch any employee's weekoff config"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_config" in data["data"]
    
    def test_get_weekoff_by_employee_cross_tenant_forbidden(self, client, employee_token, second_employee):
        """Employee cannot fetch weekoff config from another tenant"""
        response = client.get(
            f"/api/v1/weekoff-configs/{second_employee['employee'].employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()
    
    def test_get_weekoff_by_employee_not_found(self, client, admin_token):
        """Return error for non-existent employee"""
        response = client.get(
            "/api/v1/weekoff-configs/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
    def test_get_weekoff_by_employee_without_auth(self, client, test_employee):
        """Unauthenticated request should fail"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetWeekoffsByTeam:
    """Test GET /api/v1/weekoff-configs/team/{team_id}"""
    
    def test_get_weekoffs_by_team_as_employee_success(self, client, employee_token, test_team, test_employee):
        """Employee can fetch weekoff configs for their team"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
        assert isinstance(data["data"]["items"], list)
    
    def test_get_weekoffs_by_team_as_admin_success(self, client, admin_token, test_team):
        """Admin can fetch weekoff configs for any team"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
    
    def test_get_weekoffs_by_team_cross_tenant_forbidden(self, client, employee_token, second_team):
        """Employee cannot fetch weekoff configs from another tenant's team"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{second_team.team_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_weekoffs_by_team_with_pagination(self, client, employee_token, test_team):
        """Test pagination parameters"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}?skip=0&limit=10",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total" in data["data"]
        assert "items" in data["data"]
    
    def test_get_weekoffs_by_team_filter_active(self, client, employee_token, test_team):
        """Test filtering by is_active"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}?is_active=true",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_weekoffs_by_team_not_found(self, client, admin_token):
        """Return error for non-existent team"""
        response = client.get(
            "/api/v1/weekoff-configs/team/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetWeekoffsByTenant:
    """Test GET /api/v1/weekoff-configs/tenant/"""
    
    def test_get_weekoffs_by_tenant_as_employee_success(self, client, employee_token, test_tenant):
        """Employee can fetch weekoff configs for their tenant"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
    
    def test_get_weekoffs_by_tenant_as_admin_success(self, client, admin_token, test_tenant):
        """Admin can fetch weekoff configs for any tenant"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_weekoffs_by_tenant_employee_enforces_own_tenant(self, client, employee_token):
        """Employee gets their own tenant's weekoffs regardless of query param"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/?tenant_id=OTHER_TENANT",
            headers={"Authorization": employee_token}
        )
        # Should succeed but return employee's tenant data
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_weekoffs_by_tenant_admin_requires_tenant_id(self, client, admin_token):
        """Admin must provide tenant_id"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_get_weekoffs_by_tenant_with_pagination(self, client, employee_token):
        """Test pagination parameters"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/?skip=0&limit=5",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_weekoffs_by_tenant_filter_active(self, client, employee_token):
        """Test filtering by is_active"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/?is_active=true",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_weekoffs_by_tenant_not_found(self, client, admin_token):
        """Return error for non-existent tenant"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/?tenant_id=NONEXISTENT",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateWeekoffByEmployee:
    """Test PUT /api/v1/weekoff-configs/{employee_id}"""
    
    def test_update_weekoff_by_employee_as_employee_success(self, client, employee_token, test_employee):
        """Employee can update weekoff config for employees in their tenant"""
        weekoff_update = {
            "monday": False,
            "tuesday": False,
            "wednesday": True,
            "thursday": False,
            "friday": False,
            "saturday": True,
            "sunday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        weekoff = data["data"]["weekoff_config"]
        assert weekoff["wednesday"] is True
        assert weekoff["saturday"] is True
    
    def test_update_weekoff_by_employee_as_admin_success(self, client, admin_token, test_employee):
        """Admin can update any employee's weekoff config"""
        weekoff_update = {
            "saturday": True,
            "sunday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_weekoff_by_employee_partial_update(self, client, employee_token, test_employee):
        """Partial update should work"""
        weekoff_update = {
            "monday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        weekoff = response.json()["data"]["weekoff_config"]
        assert weekoff["monday"] is True
    
    def test_update_weekoff_by_employee_cross_tenant_forbidden(self, client, employee_token, second_employee):
        """Employee cannot update weekoff config for another tenant"""
        weekoff_update = {"monday": True}
        response = client.put(
            f"/api/v1/weekoff-configs/{second_employee['employee'].employee_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_weekoff_by_employee_not_found(self, client, admin_token):
        """Return error for non-existent employee"""
        weekoff_update = {"monday": True}
        response = client.put(
            "/api/v1/weekoff-configs/99999",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_weekoff_by_employee_invalid_data(self, client, employee_token, test_employee):
        """Invalid boolean values should fail"""
        weekoff_update = {"monday": "invalid"}
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUpdateWeekoffByTeam:
    """Test PUT /api/v1/weekoff-configs/team/{team_id}"""
    
    def test_update_weekoff_by_team_as_employee_success(self, client, employee_token, test_team):
        """Employee can bulk update weekoff configs for their team"""
        weekoff_update = {
            "saturday": True,
            "sunday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_configs" in data["data"]
        assert isinstance(data["data"]["weekoff_configs"], list)
    
    def test_update_weekoff_by_team_as_admin_success(self, client, admin_token, test_team):
        """Admin can bulk update weekoff configs for any team"""
        weekoff_update = {
            "friday": True,
            "saturday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_weekoff_by_team_cross_tenant_forbidden(self, client, employee_token, second_team):
        """Employee cannot update weekoff configs for another tenant's team"""
        weekoff_update = {"monday": True}
        response = client.put(
            f"/api/v1/weekoff-configs/team/{second_team.team_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_weekoff_by_team_not_found(self, client, admin_token):
        """Return error for non-existent team"""
        weekoff_update = {"monday": True}
        response = client.put(
            "/api/v1/weekoff-configs/team/99999",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_weekoff_by_team_affects_multiple_employees(self, client, admin_token, test_team):
        """Bulk update should affect all employees in team"""
        weekoff_update = {"sunday": True}
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        configs = response.json()["data"]["weekoff_configs"]
        for config in configs:
            assert config["sunday"] is True


class TestUpdateWeekoffByTenant:
    """Test PUT /api/v1/weekoff-configs/tenant/{tenant_id}"""
    
    def test_update_weekoff_by_tenant_as_employee_success(self, client, employee_token, test_tenant):
        """Employee can bulk update weekoff configs for their tenant"""
        weekoff_update = {
            "saturday": True,
            "sunday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_configs" in data["data"]
    
    def test_update_weekoff_by_tenant_as_admin_success(self, client, admin_token, test_tenant):
        """Admin can bulk update weekoff configs for any tenant"""
        weekoff_update = {
            "friday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_weekoff_by_tenant_employee_enforces_own_tenant(self, client, employee_token, second_tenant):
        """Employee update is enforced to their own tenant"""
        weekoff_update = {"monday": True}
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{second_tenant.tenant_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        # Should succeed but apply to employee's own tenant
        assert response.status_code == status.HTTP_200_OK
    
    def test_update_weekoff_by_tenant_not_found(self, client, admin_token):
        """Return error for non-existent tenant"""
        weekoff_update = {"monday": True}
        response = client.put(
            "/api/v1/weekoff-configs/tenant/NONEXISTENT",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_weekoff_by_tenant_affects_all_employees(self, client, admin_token, test_tenant):
        """Bulk update should affect all employees in tenant"""
        weekoff_update = {"saturday": True, "sunday": True}
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        configs = response.json()["data"]["weekoff_configs"]
        for config in configs:
            assert config["saturday"] is True
            assert config["sunday"] is True


class TestWeekoffIntegration:
    """Integration tests for weekoff configs"""
    
    def test_weekoff_complete_lifecycle(self, client, employee_token, test_employee):
        """Test complete weekoff config lifecycle"""
        employee_id = test_employee["employee"].employee_id
        
        # 1. Get initial weekoff
        response = client.get(
            f"/api/v1/weekoff-configs/{employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        initial = response.json()["data"]["weekoff_config"]
        
        # 2. Update weekoff
        weekoff_update = {
            "monday": True,
            "wednesday": True,
            "friday": True
        }
        response = client.put(
            f"/api/v1/weekoff-configs/{employee_id}",
            json=weekoff_update,
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        updated = response.json()["data"]["weekoff_config"]
        assert updated["monday"] is True
        assert updated["wednesday"] is True
        
        # 3. Verify changes persisted
        response = client.get(
            f"/api/v1/weekoff-configs/{employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        verified = response.json()["data"]["weekoff_config"]
        assert verified["monday"] is True
        assert verified["wednesday"] is True
    
    def test_weekoff_tenant_isolation(self, client, employee_token, admin_token, test_employee, second_employee):
        """Ensure weekoff configs are tenant-isolated"""
        # Employee can access their tenant
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Employee cannot access other tenant
        response = client.get(
            f"/api/v1/weekoff-configs/{second_employee['employee'].employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Admin can access both
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        response = client.get(
            f"/api/v1/weekoff-configs/{second_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_weekoff_bulk_operations_consistency(self, client, admin_token, test_team):
        """Bulk operations should be consistent across employees"""
        weekoff_update = {
            "saturday": True,
            "sunday": True,
            "friday": True
        }
        
        # Bulk update team
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json=weekoff_update,
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Verify all team members have same weekoff
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        configs = response.json()["data"]["items"]
        for config in configs:
            assert config["saturday"] is True
            assert config["sunday"] is True
            assert config["friday"] is True
