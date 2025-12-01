"""
Comprehensive test suite for Team endpoints.

Tests cover:
- Creating teams (admin, employee, vendor, driver scenarios)
- Listing teams with filters and pagination
- Getting single team
- Updating teams
- Toggling team status
- Permission-based access control
- Tenant isolation
"""

import pytest
from fastapi import status
from app.models.team import Team
from app.models.employee import Employee


class TestCreateTeam:
    """Test cases for POST /api/v1/teams/"""

    def test_create_team_as_admin(
        self, client, admin_token, admin_user, sample_team_data
    ):
        """Test that admin can create a team with tenant_id in payload."""
        response = client.post(
            "/api/v1/teams/",
            json=sample_team_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["name"] == sample_team_data["name"]
        assert data["data"]["team"]["tenant_id"] == sample_team_data["tenant_id"]
        assert data["data"]["team"]["description"] == sample_team_data["description"]

    def test_create_team_as_employee(
        self, client, employee_token, employee_user
    ):
        """Test that employee can create a team (tenant_id from token)."""
        team_data = {
            "name": "Employee Team",
            "description": "Team created by employee",
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/teams/",
            json=team_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["name"] == team_data["name"]
        assert data["data"]["team"]["tenant_id"] == employee_user["tenant"].tenant_id

    def test_create_team_as_admin_without_tenant_id(
        self, client, admin_token
    ):
        """Test that admin must provide tenant_id."""
        team_data = {
            "name": "Test Team",
            "description": "Test description"
        }
        
        response = client.post(
            "/api/v1/teams/",
            json=team_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["detail"]["success"] is False
        assert "tenant id is required for admin" in data["detail"]["message"].lower()

    def test_create_team_as_vendor_forbidden(
        self, client, vendor_token, sample_team_data
    ):
        """Test that vendors cannot create teams."""
        response = client.post(
            "/api/v1/teams/",
            json=sample_team_data,
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "permission" in data["detail"].lower()

    def test_create_team_without_auth(
        self, client, sample_team_data
    ):
        """Test that unauthenticated requests are rejected."""
        response = client.post(
            "/api/v1/teams/",
            json=sample_team_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_team_duplicate_name(
        self, client, admin_token, admin_user, sample_team_data, test_db
    ):
        """Test creating team with duplicate name fails with 500 (router doesn't handle IntegrityError)."""
        # Create first team
        response1 = client.post(
            "/api/v1/teams/",
            json=sample_team_data,
            headers={"Authorization": admin_token}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Try to create second team with same name
        response = client.post(
            "/api/v1/teams/",
            json=sample_team_data,
            headers={"Authorization": admin_token}
        )
        
        # Currently returns 500 because router doesn't handle IntegrityError
        # TODO: Should be 409 CONFLICT with proper error handling
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestListTeams:
    """Test cases for GET /api/v1/teams/"""

    def test_list_teams_as_admin(
        self, client, admin_token, admin_user, test_db
    ):
        """Test that admin can list teams with tenant_id query param."""
        # Create teams
        tenant_id = admin_user["tenant"].tenant_id
        team1 = Team(tenant_id=tenant_id, name="Team Alpha", description="First team")
        team2 = Team(tenant_id=tenant_id, name="Team Beta", description="Second team")
        test_db.add_all([team1, team2])
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/?tenant_id={tenant_id}",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total"] >= 2
        assert len(data["data"]["items"]) >= 2

    def test_list_teams_as_employee(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that employee can list teams in their tenant only."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Employee Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            "/api/v1/teams/",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        # Verify all teams belong to employee's tenant
        for item in data["data"]["items"]:
            assert item["tenant_id"] == tenant_id

    def test_list_teams_as_admin_without_tenant_id(
        self, client, admin_token
    ):
        """Test that admin must provide tenant_id query param."""
        response = client.get(
            "/api/v1/teams/",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["detail"]["success"] is False
        assert "tenant id is required" in data["detail"]["message"].lower()

    def test_list_teams_with_name_filter(
        self, client, employee_token, employee_user, test_db
    ):
        """Test filtering teams by name."""
        tenant_id = employee_user["tenant"].tenant_id
        team1 = Team(tenant_id=tenant_id, name="Alpha Team", description="First")
        team2 = Team(tenant_id=tenant_id, name="Beta Team", description="Second")
        test_db.add_all([team1, team2])
        test_db.commit()
        
        response = client.get(
            "/api/v1/teams/?name=Alpha",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total"] >= 1
        assert any("alpha" in item["name"].lower() for item in data["data"]["items"])

    def test_list_teams_with_pagination(
        self, client, employee_token, employee_user, test_db
    ):
        """Test pagination of teams list."""
        tenant_id = employee_user["tenant"].tenant_id
        for i in range(5):
            team = Team(tenant_id=tenant_id, name=f"Team {i}", description=f"Desc {i}")
            test_db.add(team)
        test_db.commit()
        
        response = client.get(
            "/api/v1/teams/?skip=1&limit=2",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["items"]) <= 2

    def test_list_teams_as_vendor_forbidden(
        self, client, vendor_token
    ):
        """Test that vendors cannot list teams."""
        response = client.get(
            "/api/v1/teams/",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "permission" in data["detail"].lower()

    def test_list_teams_without_auth(
        self, client
    ):
        """Test that unauthenticated requests are rejected."""
        response = client.get("/api/v1/teams/")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_teams_admin_invalid_tenant(
        self, client, admin_token
    ):
        """Test admin listing teams with non-existent tenant_id."""
        response = client.get(
            "/api/v1/teams/?tenant_id=NONEXISTENT",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
        assert "not found" in data["detail"]["message"].lower()

    def test_list_teams_includes_employee_counts(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that team list includes active/inactive employee counts."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Count Team Unique", description="Test")
        test_db.add(team)
        test_db.flush()
        
        # Add employees
        emp1 = Employee(
            tenant_id=tenant_id,
            team_id=team.team_id,
            role_id=employee_user["role"].role_id,
            name="Active Employee",
            employee_code="EMPCOUNT001",
            email="activecount@test.com",
            phone="+1111111111",
            password="hashed",
            is_active=True
        )
        emp2 = Employee(
            tenant_id=tenant_id,
            team_id=team.team_id,
            role_id=employee_user["role"].role_id,
            name="Inactive Employee",
            employee_code="EMPCOUNT002",
            email="inactivecount@test.com",
            phone="+2222222222",
            password="hashed",
            is_active=False
        )
        test_db.add_all([emp1, emp2])
        test_db.commit()
        
        response = client.get(
            "/api/v1/teams/",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        team_data = next((t for t in data["data"]["items"] if t["team_id"] == team.team_id), None)
        assert team_data is not None
        assert "active_employee_count" in team_data
        assert "inactive_employee_count" in team_data


class TestGetSingleTeam:
    """Test cases for GET /api/v1/teams/{team_id}"""

    def test_get_team_as_admin(
        self, client, admin_token, employee_user, test_db
    ):
        """Test that admin can get any team."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Admin Test Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["team_id"] == team.team_id
        assert data["data"]["team"]["name"] == team.name

    def test_get_team_as_employee_own_tenant(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that employee can get team in their tenant."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Own Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["tenant_id"] == tenant_id

    def test_get_team_as_employee_other_tenant(
        self, client, employee_token, admin_user, test_db
    ):
        """Test that employee cannot get team from another tenant."""
        # Create team in different tenant
        other_tenant_id = admin_user["tenant"].tenant_id
        team = Team(tenant_id=other_tenant_id, name="Other Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False
        assert "not found" in data["detail"]["message"].lower()

    def test_get_team_not_found(
        self, client, admin_token
    ):
        """Test getting non-existent team."""
        response = client.get(
            "/api/v1/teams/99999",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False

    def test_get_team_as_vendor_forbidden(
        self, client, vendor_token, employee_user, test_db
    ):
        """Test that vendors cannot get teams."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Vendor Get Test Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "permission" in data["detail"].lower()

    def test_get_team_without_auth(
        self, client, employee_user, test_db
    ):
        """Test that unauthenticated requests are rejected."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Unauth Get Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(f"/api/v1/teams/{team.team_id}")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_team_includes_employee_counts(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that getting single team includes employee counts."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Count Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "active_employee_count" in data["data"]["team"]
        assert "inactive_employee_count" in data["data"]["team"]


class TestUpdateTeam:
    """Test cases for PUT /api/v1/teams/{team_id}"""

    def test_update_team_as_admin(
        self, client, admin_token, employee_user, test_db
    ):
        """Test that admin can update any team."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Original Name", description="Original")
        test_db.add(team)
        test_db.commit()
        
        update_data = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["name"] == update_data["name"]
        assert data["data"]["team"]["description"] == update_data["description"]

    def test_update_team_as_employee_own_tenant(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that employee can update team in their tenant."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Original", description="Test")
        test_db.add(team)
        test_db.commit()
        
        update_data = {"name": "Updated by Employee"}
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["team"]["name"] == update_data["name"]

    def test_update_team_as_employee_other_tenant(
        self, client, employee_token, admin_user, test_db
    ):
        """Test that employee cannot update team from another tenant."""
        other_tenant_id = admin_user["tenant"].tenant_id
        team = Team(tenant_id=other_tenant_id, name="Other Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        update_data = {"name": "Hacked Name"}
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False

    def test_update_team_partial_update(
        self, client, employee_token, employee_user, test_db
    ):
        """Test partial update of team (only some fields)."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Original", description="Original Desc")
        test_db.add(team)
        test_db.commit()
        
        # Only update description
        update_data = {"description": "New Description Only"}
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["team"]["description"] == update_data["description"]
        assert data["data"]["team"]["name"] == "Original"  # Unchanged

    def test_update_team_not_found(
        self, client, admin_token
    ):
        """Test updating non-existent team."""
        update_data = {"name": "New Name"}
        
        response = client.put(
            "/api/v1/teams/99999",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False

    def test_update_team_as_vendor_forbidden(
        self, client, vendor_token, employee_user, test_db
    ):
        """Test that vendors cannot update teams."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Vendor Update Test Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        update_data = {"name": "Hacked"}
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data,
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "permission" in data["detail"].lower()

    def test_update_team_without_auth(
        self, client, employee_user, test_db
    ):
        """Test that unauthenticated requests are rejected."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Unauth Update Team", description="Test")
        test_db.add(team)
        test_db.commit()
        
        update_data = {"name": "Hacked"}
        
        response = client.put(
            f"/api/v1/teams/{team.team_id}",
            json=update_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestToggleTeamStatus:
    """Test cases for PATCH /api/v1/teams/{team_id}/toggle-status"""

    def test_toggle_team_status_as_admin(
        self, client, admin_token, employee_user, test_db
    ):
        """Test that admin can toggle team status."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Active Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team"]["is_active"] is False

    def test_toggle_team_status_twice(
        self, client, employee_token, employee_user, test_db
    ):
        """Test toggling team status multiple times."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Toggle Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        # First toggle: active -> inactive
        response1 = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response1.status_code == status.HTTP_200_OK
        assert response1.json()["data"]["team"]["is_active"] is False
        
        # Second toggle: inactive -> active
        response2 = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        assert response2.status_code == status.HTTP_200_OK
        assert response2.json()["data"]["team"]["is_active"] is True

    def test_toggle_team_status_as_employee_own_tenant(
        self, client, employee_token, employee_user, test_db
    ):
        """Test that employee can toggle team status in their tenant."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Own Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["team"]["is_active"] is False

    def test_toggle_team_status_as_employee_other_tenant(
        self, client, employee_token, admin_user, test_db
    ):
        """Test that employee cannot toggle team status in other tenant."""
        other_tenant_id = admin_user["tenant"].tenant_id
        team = Team(tenant_id=other_tenant_id, name="Other Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False

    def test_toggle_team_status_not_found(
        self, client, admin_token
    ):
        """Test toggling status of non-existent team."""
        response = client.patch(
            "/api/v1/teams/99999/toggle-status",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["success"] is False

    def test_toggle_team_status_as_vendor_forbidden(
        self, client, vendor_token, employee_user, test_db
    ):
        """Test that vendors cannot toggle team status."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Vendor Toggle Test Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/teams/{team.team_id}/toggle-status",
            headers={"Authorization": vendor_token}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "permission" in data["detail"].lower()

    def test_toggle_team_status_without_auth(
        self, client, employee_user, test_db
    ):
        """Test that unauthenticated requests are rejected."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Unauth Toggle Team", description="Test", is_active=True)
        test_db.add(team)
        test_db.commit()
        
        response = client.patch(f"/api/v1/teams/{team.team_id}/toggle-status")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTeamIntegration:
    """Integration tests for team workflows"""

    def test_complete_team_lifecycle(
        self, client, admin_token, admin_user, test_db
    ):
        """Test complete CRUD lifecycle for a team."""
        tenant_id = admin_user["tenant"].tenant_id
        
        # 1. Create team
        create_data = {
            "tenant_id": tenant_id,
            "name": "Lifecycle Team",
            "description": "Full lifecycle test",
            "is_active": True
        }
        create_response = client.post(
            "/api/v1/teams/",
            json=create_data,
            headers={"Authorization": admin_token}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        team_id = create_response.json()["data"]["team"]["team_id"]
        
        # 2. Get team
        get_response = client.get(
            f"/api/v1/teams/{team_id}",
            headers={"Authorization": admin_token}
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["data"]["team"]["name"] == create_data["name"]
        
        # 3. Update team
        update_data = {"name": "Updated Lifecycle Team"}
        update_response = client.put(
            f"/api/v1/teams/{team_id}",
            json=update_data,
            headers={"Authorization": admin_token}
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["data"]["team"]["name"] == update_data["name"]
        
        # 4. Toggle status
        toggle_response = client.patch(
            f"/api/v1/teams/{team_id}/toggle-status",
            headers={"Authorization": admin_token}
        )
        assert toggle_response.status_code == status.HTTP_200_OK
        assert toggle_response.json()["data"]["team"]["is_active"] is False
        
        # 5. List and verify
        list_response = client.get(
            f"/api/v1/teams/?tenant_id={tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert list_response.status_code == status.HTTP_200_OK
        teams = list_response.json()["data"]["items"]
        lifecycle_team = next((t for t in teams if t["team_id"] == team_id), None)
        assert lifecycle_team is not None
        assert lifecycle_team["is_active"] is False

    def test_employee_tenant_isolation(
        self, client, employee_token, employee_user, admin_user, test_db
    ):
        """Test that employees can only access teams in their tenant."""
        # Create teams in different tenants
        emp_tenant_id = employee_user["tenant"].tenant_id
        admin_tenant_id = admin_user["tenant"].tenant_id
        
        emp_team = Team(tenant_id=emp_tenant_id, name="Employee Team", description="Test")
        admin_team = Team(tenant_id=admin_tenant_id, name="Admin Team", description="Test")
        test_db.add_all([emp_team, admin_team])
        test_db.commit()
        
        # List teams as employee
        list_response = client.get(
            "/api/v1/teams/",
            headers={"Authorization": employee_token}
        )
        assert list_response.status_code == status.HTTP_200_OK
        teams = list_response.json()["data"]["items"]
        
        # Should only see own tenant teams
        tenant_ids = {t["tenant_id"] for t in teams}
        assert emp_tenant_id in tenant_ids
        assert admin_tenant_id not in tenant_ids
        
        # Try to get admin's team - should fail
        get_response = client.get(
            f"/api/v1/teams/{admin_team.team_id}",
            headers={"Authorization": employee_token}
        )
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_team_with_multiple_employees(
        self, client, employee_token, employee_user, test_db
    ):
        """Test team with multiple employees shows correct counts."""
        tenant_id = employee_user["tenant"].tenant_id
        team = Team(tenant_id=tenant_id, name="Multi Employee Team Unique", description="Test")
        test_db.add(team)
        test_db.flush()
        
        # Add multiple employees
        for i in range(3):
            emp = Employee(
                tenant_id=tenant_id,
                team_id=team.team_id,
                role_id=employee_user["role"].role_id,
                name=f"Multi Employee {i}",
                employee_code=f"MULTICOD{i}",
                email=f"multiemp{i}@test.com",
                phone=f"+333333333{i}",
                password="hashed",
                is_active=i < 2  # First 2 active, last one inactive
            )
            test_db.add(emp)
        test_db.commit()
        
        # Get team and verify counts
        response = client.get(
            f"/api/v1/teams/{team.team_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]["team"]
        assert data["active_employee_count"] == 2
        assert data["inactive_employee_count"] == 1


# Fixtures
@pytest.fixture
def sample_team_data(admin_user):
    """Sample team data for testing."""
    return {
        "tenant_id": admin_user["tenant"].tenant_id,
        "name": "Test Team Alpha",
        "description": "A test team for unit testing",
        "is_active": True
    }


@pytest.fixture
def vendor_token(vendor_user):
    """Generate token for vendor user."""
    from common_utils.auth.utils import create_access_token
    
    return "Bearer " + create_access_token(
        user_id=str(vendor_user["vendor_user"].vendor_user_id),
        user_type="vendor",
        custom_claims={
            "vendor_id": vendor_user["vendor"].vendor_id,
            "permissions": ["vendor.read"]
        }
    )


@pytest.fixture
def vendor_user(test_db, employee_user):
    """Create a vendor user for testing."""
    from app.models.vendor import Vendor
    from app.models.vendor_user import VendorUser
    from common_utils.auth.utils import hash_password
    
    # Create vendor
    vendor = Vendor(
        tenant_id=employee_user["tenant"].tenant_id,
        name="Test Vendor",
        vendor_code="VCODE001",
        email="vendor@test.com",
        phone="+9876543210",
        is_active=True
    )
    test_db.add(vendor)
    test_db.flush()
    
    # Create vendor user
    vendor_user = VendorUser(
        tenant_id=vendor.tenant_id,
        vendor_id=vendor.vendor_id,
        name="Vendor User",
        email="vendoruser@test.com",
        phone="+9876543211",
        password=hash_password("Vendor@123"),
        role_id=1,
        is_active=True
    )
    test_db.add(vendor_user)
    test_db.commit()
    
    return {
        "vendor": vendor,
        "vendor_user": vendor_user
    }
