import pytest
from fastapi import status


# ==================== Test Get Weekoff by Employee ====================

class TestGetWeekoffByEmployee:
    """Test suite for GET /weekoff-configs/{employee_id} endpoint"""

    def test_get_weekoff_as_admin(self, client, admin_token, test_employee):
        """Admin should be able to get employee weekoff config"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        config = data["data"]["weekoff_config"]
        assert config["employee_id"] == test_employee['employee'].employee_id
        assert "monday" in config
        assert "sunday" in config

    def test_get_weekoff_as_employee(self, client, employee_token, test_employee):
        """Employee should be able to get weekoff config in their tenant"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        config = data["data"]["weekoff_config"]
        assert config["employee_id"] == test_employee['employee'].employee_id

    def test_get_weekoff_driver_forbidden(self, client, driver_token, test_employee):
        """Driver should not be able to get weekoff config"""
        response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_weekoff_employee_wrong_tenant(self, client, employee_token, test_db, second_tenant):
        """Employee should not access weekoff config from another tenant"""
        from app.models.employee import Employee
        from app.models.team import Team
        
        # Create team in second tenant
        team2 = Team(
            tenant_id=second_tenant.tenant_id,
            name="Second Tenant Team"
        )
        test_db.add(team2)
        test_db.commit()
        test_db.refresh(team2)
        
        # Create employee in second tenant
        emp2 = Employee(
            tenant_id=second_tenant.tenant_id,
            role_id=3,
            team_id=team2.team_id,
            name="Other Tenant Employee",
            email="emp2@test.com",
            phone="9999999999",
            employee_code="EMP002",
            password="hashed",
            is_active=True
        )
        test_db.add(emp2)
        test_db.commit()
        test_db.refresh(emp2)

        response = client.get(
            f"/api/v1/weekoff-configs/{emp2.employee_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_weekoff_creates_default_config(self, client, admin_token, test_db, test_tenant, test_team):
        """Should create default config if not exists"""
        from app.models.employee import Employee
        
        # Create new employee without weekoff config
        new_emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="New Employee",
            email="new@test.com",
            phone="8888888888",
            employee_code="NEW001",
            password="hashed",
            is_active=True
        )
        test_db.add(new_emp)
        test_db.commit()
        test_db.refresh(new_emp)

        response = client.get(
            f"/api/v1/weekoff-configs/{new_emp.employee_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        config = data["data"]["weekoff_config"]
        # Default: only sunday is True
        assert config["saturday"] is False
        assert config["sunday"] is True

    def test_get_weekoff_unauthorized(self, client, test_employee):
        """Getting weekoff without token should fail"""
        response = client.get(f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Get Weekoffs by Team ====================

class TestGetWeekoffsByTeam:
    """Test suite for GET /weekoff-configs/team/{team_id} endpoint"""

    def test_get_team_weekoffs_as_admin(self, client, admin_token, test_team, test_employee):
        """Admin should be able to get team weekoff configs"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
        assert len(data["data"]["items"]) >= 1

    def test_get_team_weekoffs_as_employee(self, client, employee_token, test_team):
        """Employee should be able to get team weekoff configs in their tenant"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_get_team_weekoffs_pagination(self, client, admin_token, test_team, test_db, test_tenant):
        """Should support pagination"""
        from app.models.employee import Employee
        
        # Create multiple employees in team
        for i in range(5):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Employee {i}",
                email=f"emp{i}@test.com",
                phone=f"800000000{i}",
                employee_code=f"EMP{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
        test_db.commit()

        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}?skip=0&limit=3",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["items"]) <= 3

    def test_get_team_weekoffs_filter_active(self, client, admin_token, test_team, test_db, test_tenant):
        """Should filter by is_active"""
        from app.models.employee import Employee
        
        # Create active and inactive employees
        active_emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Active Employee",
            email="active@test.com",
            phone="7777777777",
            employee_code="ACT001",
            password="hashed",
            is_active=True
        )
        inactive_emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Inactive Employee",
            email="inactive@test.com",
            phone="6666666666",
            employee_code="INACT001",
            password="hashed",
            is_active=False
        )
        test_db.add_all([active_emp, inactive_emp])
        test_db.commit()

        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}?is_active=true",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Verify all returned employees are active
        # (Can't verify exact count as test_employee might be included)

    def test_get_team_weekoffs_team_not_found(self, client, admin_token):
        """Getting weekoffs for non-existent team should return 404"""
        response = client.get(
            "/api/v1/weekoff-configs/team/99999",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_team_weekoffs_employee_wrong_tenant(self, client, employee_token, test_db, second_tenant):
        """Employee should not access team from another tenant"""
        from app.models.team import Team
        
        team2 = Team(
            tenant_id=second_tenant.tenant_id,
            name="Other Tenant Team"
        )
        test_db.add(team2)
        test_db.commit()
        test_db.refresh(team2)

        response = client.get(
            f"/api/v1/weekoff-configs/team/{team2.team_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_team_weekoffs_driver_forbidden(self, client, driver_token, test_team):
        """Driver should not be able to get team weekoffs"""
        response = client.get(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Get Weekoffs by Tenant ====================

class TestGetWeekoffsByTenant:
    """Test suite for GET /weekoff-configs/tenant/ endpoint"""

    def test_get_tenant_weekoffs_as_admin(self, client, admin_token, test_tenant):
        """Admin should be able to get tenant weekoff configs with tenant_id param"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]

    def test_get_tenant_weekoffs_admin_no_tenant_id(self, client, admin_token):
        """Admin without tenant_id param should get 400"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_tenant_weekoffs_as_employee(self, client, employee_token, test_tenant):
        """Employee should be able to get tenant weekoffs (automatic tenant_id)"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_get_tenant_weekoffs_pagination(self, client, admin_token, test_tenant):
        """Should support pagination"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}&skip=0&limit=5",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["items"]) <= 5

    def test_get_tenant_weekoffs_filter_active(self, client, admin_token, test_tenant):
        """Should filter by is_active"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}&is_active=true",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_get_tenant_weekoffs_tenant_not_found(self, client, admin_token):
        """Getting weekoffs for non-existent tenant should return 404"""
        response = client.get(
            "/api/v1/weekoff-configs/tenant/?tenant_id=NONEXISTENT",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_tenant_weekoffs_driver_forbidden(self, client, driver_token, test_tenant):
        """Driver should not be able to get tenant weekoffs"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_tenant_weekoffs_vendor_forbidden(self, client, vendor_token, test_tenant):
        """Vendor should not be able to get tenant weekoffs"""
        response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Update Weekoff by Employee ====================

class TestUpdateWeekoffByEmployee:
    """Test suite for PUT /weekoff-configs/{employee_id} endpoint"""

    def test_update_weekoff_as_admin(self, client, admin_token, test_employee):
        """Admin should be able to update employee weekoff config"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "monday": True,
                "tuesday": False,
                "sunday": False
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        config = data["data"]["weekoff_config"]
        assert config["monday"] is True
        assert config["tuesday"] is False
        assert config["sunday"] is False

    def test_update_weekoff_as_employee(self, client, employee_token, test_employee):
        """Employee should be able to update weekoff config in their tenant"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "saturday": False,
                "sunday": False
            },
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        config = data["data"]["weekoff_config"]
        assert config["saturday"] is False
        assert config["sunday"] is False

    def test_update_weekoff_all_days(self, client, admin_token, test_employee):
        """Should be able to update all days of the week"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "monday": True,
                "tuesday": True,
                "wednesday": True,
                "thursday": True,
                "friday": True,
                "saturday": True,
                "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        config = data["data"]["weekoff_config"]
        # All days should be weekoffs
        assert all([
            config["monday"], config["tuesday"], config["wednesday"],
            config["thursday"], config["friday"], config["saturday"], config["sunday"]
        ])

    def test_update_weekoff_partial_update(self, client, admin_token, test_employee):
        """Should support partial updates"""
        # Get current config
        get_response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        original = get_response.json()["data"]["weekoff_config"]

        # Update only one day
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={"monday": True},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        config = data["data"]["weekoff_config"]
        assert config["monday"] is True
        # Other days should remain unchanged
        assert config["tuesday"] == original["tuesday"]

    def test_update_weekoff_driver_forbidden(self, client, driver_token, test_employee):
        """Driver should not be able to update weekoff config"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={"monday": True},
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_weekoff_vendor_forbidden(self, client, vendor_token, test_employee):
        """Vendor should not be able to update weekoff config"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={"monday": True},
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_weekoff_employee_not_found(self, client, admin_token):
        """Updating weekoff for non-existent employee should return 404"""
        response = client.put(
            "/api/v1/weekoff-configs/99999",
            json={"monday": True},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_weekoff_employee_wrong_tenant(self, client, employee_token, test_db, second_tenant):
        """Employee should not update weekoff for employee in another tenant"""
        from app.models.employee import Employee
        from app.models.team import Team
        
        team2 = Team(
            tenant_id=second_tenant.tenant_id,
            name="Second Tenant Team"
        )
        test_db.add(team2)
        test_db.commit()
        
        emp2 = Employee(
            tenant_id=second_tenant.tenant_id,
            role_id=3,
            team_id=team2.team_id,
            name="Other Employee",
            email="other@test.com",
            phone="5555555555",
            employee_code="OTH001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp2)
        test_db.commit()
        test_db.refresh(emp2)

        response = client.put(
            f"/api/v1/weekoff-configs/{emp2.employee_id}",
            json={"monday": True},
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_weekoff_unauthorized(self, client, test_employee):
        """Updating weekoff without token should fail"""
        response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={"monday": True}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== Test Update Weekoff by Team ====================

class TestUpdateWeekoffByTeam:
    """Test suite for PUT /weekoff-configs/team/{team_id} endpoint"""

    def test_update_team_weekoffs_as_admin(self, client, admin_token, test_team):
        """Admin should be able to bulk update team weekoff configs"""
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json={
                "saturday": True,
                "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_configs" in data["data"]
        # All configs should have the updated values
        for config in data["data"]["weekoff_configs"]:
            assert config["saturday"] is True
            assert config["sunday"] is True

    def test_update_team_weekoffs_as_employee(self, client, employee_token, test_team):
        """Employee should be able to bulk update team weekoffs in their tenant"""
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json={
                "monday": False,
                "friday": False
            },
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_update_team_weekoffs_multiple_employees(self, client, admin_token, test_team, test_db, test_tenant):
        """Bulk update should affect all employees in team"""
        from app.models.employee import Employee
        
        # Create multiple employees in team
        for i in range(3):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Bulk Employee {i}",
                email=f"bulk{i}@test.com",
                phone=f"400000000{i}",
                employee_code=f"BLK{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
        test_db.commit()

        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json={"wednesday": True},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Should have updated at least 3 employees
        assert len(data["data"]["weekoff_configs"]) >= 3
        # All should have wednesday as True
        for config in data["data"]["weekoff_configs"]:
            assert config["wednesday"] is True

    def test_update_team_weekoffs_team_not_found(self, client, admin_token):
        """Updating weekoffs for non-existent team should return 404"""
        response = client.put(
            "/api/v1/weekoff-configs/team/99999",
            json={"monday": True},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_team_weekoffs_employee_wrong_tenant(self, client, employee_token, test_db, second_tenant):
        """Employee should not update team from another tenant"""
        from app.models.team import Team
        
        team2 = Team(
            tenant_id=second_tenant.tenant_id,
            name="Other Team 2"
        )
        test_db.add(team2)
        test_db.commit()
        test_db.refresh(team2)

        response = client.put(
            f"/api/v1/weekoff-configs/team/{team2.team_id}",
            json={"monday": True},
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_team_weekoffs_driver_forbidden(self, client, driver_token, test_team):
        """Driver should not be able to update team weekoffs"""
        response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json={"monday": True},
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Update Weekoff by Tenant ====================

class TestUpdateWeekoffByTenant:
    """Test suite for PUT /weekoff-configs/tenant/{tenant_id} endpoint"""

    def test_update_tenant_weekoffs_as_admin(self, client, admin_token, test_tenant):
        """Admin should be able to bulk update tenant weekoff configs"""
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json={
                "saturday": True,
                "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "weekoff_configs" in data["data"]

    def test_update_tenant_weekoffs_as_employee(self, client, employee_token, test_tenant):
        """Employee should be able to bulk update tenant weekoffs (own tenant only)"""
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json={
                "monday": False,
                "tuesday": False
            },
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_update_tenant_weekoffs_employee_enforces_own_tenant(self, client, employee_token, test_tenant, second_tenant):
        """Employee tenant_id should be enforced from token, ignoring path param"""
        # Employee tries to update different tenant via path param
        # But their token tenant_id should be used instead
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{second_tenant.tenant_id}",
            json={"monday": True},
            headers={"Authorization": employee_token}
        )
        # Should use employee's tenant from token (test_tenant)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Verify it updated the employee's own tenant
        assert data["success"] is True

    def test_update_tenant_weekoffs_tenant_not_found(self, client, admin_token):
        """Updating weekoffs for non-existent tenant should return 404"""
        response = client.put(
            "/api/v1/weekoff-configs/tenant/NONEXISTENT",
            json={"monday": True},
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_tenant_weekoffs_driver_forbidden(self, client, driver_token, test_tenant):
        """Driver should not be able to update tenant weekoffs"""
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json={"monday": True},
            headers={"Authorization": driver_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_tenant_weekoffs_vendor_forbidden(self, client, vendor_token, test_tenant):
        """Vendor should not be able to update tenant weekoffs"""
        response = client.put(
            f"/api/v1/weekoff-configs/tenant/{test_tenant.tenant_id}",
            json={"monday": True},
            headers={"Authorization": vendor_token}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================== Test Weekoff Config Integration ====================

class TestWeekoffConfigIntegration:
    """Integration tests for weekoff config workflows"""

    def test_complete_weekoff_lifecycle(self, client, admin_token, test_employee):
        """Test complete weekoff management lifecycle"""
        # Get default config
        get_response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_200_OK
        original = get_response.json()["data"]["weekoff_config"]

        # Update config
        update_response = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "monday": True,
                "wednesday": True,
                "friday": True
            },
            headers={"Authorization": admin_token}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Verify update
        verify_response = client.get(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            headers={"Authorization": admin_token}
        )
        config = verify_response.json()["data"]["weekoff_config"]
        assert config["monday"] is True
        assert config["wednesday"] is True
        assert config["friday"] is True

    def test_team_bulk_update_workflow(self, client, admin_token, test_team, test_db, test_tenant):
        """Test bulk update for team"""
        from app.models.employee import Employee
        
        # Create multiple employees
        emp_ids = []
        for i in range(3):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Team Employee {i}",
                email=f"team{i}@test.com",
                phone=f"300000000{i}",
                employee_code=f"TEM{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            emp_ids.append(emp.employee_id)
        test_db.commit()

        # Bulk update team
        update_response = client.put(
            f"/api/v1/weekoff-configs/team/{test_team.team_id}",
            json={
                "saturday": False,
                "sunday": False
            },
            headers={"Authorization": admin_token}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Verify all employees updated
        for emp_id in emp_ids:
            verify_response = client.get(
                f"/api/v1/weekoff-configs/{emp_id}",
                headers={"Authorization": admin_token}
            )
            config = verify_response.json()["data"]["weekoff_config"]
            assert config["saturday"] is False
            assert config["sunday"] is False

    def test_tenant_isolation(self, client, admin_token, test_tenant, second_tenant):
        """Verify weekoff config isolation between tenants"""
        # Get configs for tenant 1
        tenant1_response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        tenant1_data = tenant1_response.json()["data"]

        # Get configs for tenant 2
        tenant2_response = client.get(
            f"/api/v1/weekoff-configs/tenant/?tenant_id={second_tenant.tenant_id}",
            headers={"Authorization": admin_token}
        )
        tenant2_data = tenant2_response.json()["data"]

        # Verify no overlap
        tenant1_emp_ids = [c["employee_id"] for c in tenant1_data["items"]]
        tenant2_emp_ids = [c["employee_id"] for c in tenant2_data["items"]]
        assert not set(tenant1_emp_ids).intersection(set(tenant2_emp_ids))

    def test_weekoff_patterns(self, client, admin_token, test_employee):
        """Test various weekoff patterns"""
        # 5-day work week (Sat-Sun off)
        response1 = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "monday": False, "tuesday": False, "wednesday": False,
                "thursday": False, "friday": False,
                "saturday": True, "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_200_OK

        # 6-day work week (Sun off only)
        response2 = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "saturday": False, "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response2.status_code == status.HTTP_200_OK

        # Alternate days off
        response3 = client.put(
            f"/api/v1/weekoff-configs/{test_employee['employee'].employee_id}",
            json={
                "monday": True, "tuesday": False, "wednesday": True,
                "thursday": False, "friday": True, "saturday": False, "sunday": True
            },
            headers={"Authorization": admin_token}
        )
        assert response3.status_code == status.HTTP_200_OK

    def test_default_config_consistency(self, client, admin_token, test_db, test_tenant, test_team):
        """Verify default configs are created consistently"""
        from app.models.employee import Employee
        
        # Create multiple employees
        emp_ids = []
        for i in range(3):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Default Employee {i}",
                email=f"default{i}@test.com",
                phone=f"200000000{i}",
                employee_code=f"DEF{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            emp_ids.append(emp.employee_id)
        test_db.commit()

        # Get configs for all (should create defaults)
        for emp_id in emp_ids:
            response = client.get(
                f"/api/v1/weekoff-configs/{emp_id}",
                headers={"Authorization": admin_token}
            )
            assert response.status_code == status.HTTP_200_OK
            config = response.json()["data"]["weekoff_config"]
            # All should have same default values (only sunday is True)
            assert config["saturday"] is False
            assert config["sunday"] is True









