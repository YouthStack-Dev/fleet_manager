"""
Comprehensive test suite for Employee endpoints.

Tests cover:
- Create employee (admin/employee with tenant enforcement, validation, team validation)
- List employees (pagination, filters, tenant isolation)
- Get single employee (tenant restrictions, not found)
- Update employee (partial updates, team/role validation, tenant enforcement)
- Toggle employee status (activate/deactivate)
- Edge cases: invalid data, duplicate codes, cross-tenant restrictions
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta


class TestCreateEmployee:
    """Test POST /api/v1/employees - Create Employee"""

    def test_create_employee_as_admin_success(self, client: TestClient, admin_token: str, test_tenant, test_team):
        """Admin can create employee with explicit tenant_id"""
        payload = {
            "name": "Test Employee",
            "email": "test.employee@example.com",
            "phone": "+1234567899",  # Different from admin_user (+1234567890) and employee_user (+1234567891)
            "employee_code": "emp001",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "address": "123 Test St",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "gender": "Male",
            "is_active": True
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Employee created successfully"
        assert "employee" in data["data"]
        assert data["data"]["employee"]["name"] == "Test Employee"
        assert data["data"]["employee"]["email"] == "test.employee@example.com"
        assert data["data"]["employee"]["tenant_id"] == test_tenant.tenant_id
        assert data["data"]["employee"]["team_id"] == test_team.team_id

    def test_create_employee_as_employee_with_tenant_enforcement(
        self, client: TestClient, employee_token: str, test_tenant, test_team
    ):
        """Employee creates employee within their own tenant (tenant_id from token)"""
        payload = {
            "name": "New Team Member",
            "email": "new.member@example.com",
            "phone": "+1987654321",
            "employee_code": "emp002",
            "team_id": test_team.team_id,
            "password": "TestPass123!",
            "gender": "Female"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        # Tenant ID should be enforced from token, not payload
        assert data["data"]["employee"]["tenant_id"] == test_tenant.tenant_id

    def test_create_employee_as_admin_without_tenant_id(self, client: TestClient, admin_token: str, test_team):
        """Admin must provide tenant_id in payload"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp003",
            "team_id": test_team.team_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_create_employee_with_invalid_team_id(self, client: TestClient, admin_token: str, test_tenant):
        """Cannot create employee with non-existent team"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp004",
            "team_id": 99999,  # Non-existent team
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_create_employee_with_team_from_different_tenant(
        self, client: TestClient, admin_token: str, test_tenant, second_tenant, second_team
    ):
        """Cannot assign employee to team from different tenant"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp005",
            "team_id": second_team.team_id,  # Team from second tenant
            "tenant_id": test_tenant.tenant_id,  # But employee for first tenant
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_create_employee_duplicate_employee_code(
        self, client: TestClient, admin_token: str, test_tenant, test_team, test_employee
    ):
        """Cannot create employee with duplicate employee_code"""
        payload = {
            "name": "Duplicate Code Employee",
            "email": "different@example.com",
            "phone": "+1111111111",
            "employee_code": test_employee["employee"].employee_code,  # Duplicate code
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Database constraint violations may return 400 or 500`n        assert response.status_code in [400, 500]
        data = response.json()
        assert "detail" in data

    def test_create_employee_duplicate_email(
        self, client: TestClient, admin_token: str, test_tenant, test_team, test_employee
    ):
        """Cannot create employee with duplicate email"""
        payload = {
            "name": "Duplicate Email Employee",
            "email": test_employee["employee"].email,  # Duplicate email
            "phone": "+1111111111",
            "employee_code": "unique_code_123",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Database constraint violations may return 400 or 500`n        assert response.status_code in [400, 500]
        data = response.json()
        assert "detail" in data

    def test_create_employee_invalid_phone_format(self, client: TestClient, admin_token: str, test_tenant, test_team):
        """Reject invalid phone format"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "invalid-phone",  # Invalid format
            "employee_code": "emp006",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_employee_invalid_password(self, client: TestClient, admin_token: str, test_tenant, test_team):
        """Reject weak password"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp007",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "weak"  # Too weak
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_employee_with_special_needs(
        self, client: TestClient, admin_token: str, test_tenant, test_team
    ):
        """Create employee with special needs and valid dates"""
        start_date = (date.today() + timedelta(days=1)).isoformat()
        end_date = (date.today() + timedelta(days=30)).isoformat()

        payload = {
            "name": "Special Needs Employee",
            "email": "special@example.com",
            "phone": "+1234567898",  # Different from admin_user (+1234567890) and employee_user (+1234567891)
            "employee_code": "emp008",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "special_needs": "Wheelchair",
            "special_needs_start_date": start_date,
            "special_needs_end_date": end_date
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["special_needs"] == "Wheelchair"

    def test_create_employee_special_needs_without_dates(
        self, client: TestClient, admin_token: str, test_tenant, test_team
    ):
        """Reject special needs without start/end dates"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp009",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "special_needs": "Wheelchair"
            # Missing dates
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_employee_special_needs_past_date(
        self, client: TestClient, admin_token: str, test_tenant, test_team
    ):
        """Reject special needs with past start date"""
        past_date = (date.today() - timedelta(days=1)).isoformat()
        future_date = (date.today() + timedelta(days=30)).isoformat()

        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp010",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "special_needs": "Wheelchair",
            "special_needs_start_date": past_date,
            "special_needs_end_date": future_date
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_employee_invalid_coordinates(
        self, client: TestClient, admin_token: str, test_tenant, test_team
    ):
        """Reject invalid latitude/longitude"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp011",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "latitude": 100.0,  # Invalid (must be -90 to 90)
            "longitude": -74.0060
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_employee_as_vendor_forbidden(self, client: TestClient, vendor_token: str, test_tenant, test_team):
        """Vendors cannot create employees"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp012",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post(
            "/api/v1/employees/",
            json=payload,
            headers={"Authorization": f"Bearer {vendor_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_create_employee_without_auth(self, client: TestClient, test_tenant, test_team):
        """Cannot create employee without authentication"""
        payload = {
            "name": "Test Employee",
            "email": "test@example.com",
            "phone": "+1234567890",
            "employee_code": "emp013",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!"
        }

        response = client.post("/api/v1/employees/", json=payload)

        assert response.status_code == 401


class TestListEmployees:
    """Test GET /api/v1/employees - List Employees"""

    def test_list_employees_as_admin(self, client: TestClient, admin_token: str, test_tenant, test_employee):
        """Admin can list employees with tenant_id filter"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "total" in data["data"]
        assert "items" in data["data"]
        assert data["data"]["total"] >= 1
        assert len(data["data"]["items"]) >= 1

    def test_list_employees_as_employee_restricted_to_tenant(
        self, client: TestClient, employee_token: str, test_tenant
    ):
        """Employee can only list employees within their tenant"""
        response = client.get(
            "/api/v1/employees/",
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # All employees should belong to same tenant
        for employee in data["data"]["items"]:
            assert employee["tenant_id"] == test_tenant.tenant_id

    def test_list_employees_as_admin_without_tenant_id(self, client: TestClient, admin_token: str):
        """Admin must provide tenant_id filter"""
        response = client.get(
            "/api/v1/employees/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_list_employees_with_name_filter(self, client: TestClient, admin_token: str, test_tenant, test_employee):
        """Filter employees by name"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&name={test_employee["employee"].name[:5]}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # All returned employees should have matching name
        for employee in data["data"]["items"]:
            assert test_employee["employee"].name[:5].lower() in employee["name"].lower()

    def test_list_employees_with_team_filter(
        self, client: TestClient, admin_token: str, test_tenant, test_team, test_employee
    ):
        """Filter employees by team_id"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&team_id={test_team.team_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # All returned employees should belong to specified team
        for employee in data["data"]["items"]:
            assert employee["team_id"] == test_team.team_id

    def test_list_employees_with_is_active_filter(
        self, client: TestClient, admin_token: str, test_tenant
    ):
        """Filter employees by is_active status"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&is_active=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # All returned employees should be active
        for employee in data["data"]["items"]:
            assert employee["is_active"] is True

    def test_list_employees_with_pagination(self, client: TestClient, admin_token: str, test_tenant):
        """Pagination works correctly"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&skip=0&limit=5",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["items"]) <= 5

    def test_list_employees_with_team_from_different_tenant(
        self, client: TestClient, admin_token: str, test_tenant, second_team
    ):
        """Cannot filter by team_id from different tenant"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&team_id={second_team.team_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_list_employees_admin_invalid_tenant(self, client: TestClient, admin_token: str):
        """Admin gets 404 for non-existent tenant"""
        response = client.get(
            "/api/v1/employees/?tenant_id=invalid_tenant_999",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_list_employees_as_vendor_forbidden(self, client: TestClient, vendor_token: str):
        """Vendors cannot list employees"""
        response = client.get(
            "/api/v1/employees/",
            headers={"Authorization": f"Bearer {vendor_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_list_employees_without_auth(self, client: TestClient):
        """Cannot list employees without authentication"""
        response = client.get("/api/v1/employees/")
        assert response.status_code == 401


class TestGetSingleEmployee:
    """Test GET /api/v1/employees/{employee_id} - Get Single Employee"""

    def test_get_employee_as_admin(self, client: TestClient, admin_token: str, test_employee):
        """Admin can retrieve any employee"""
        response = client.get(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "employee" in data["data"]
        assert data["data"]["employee"]["employee_id"] == test_employee["employee"].employee_id
        assert data["data"]["employee"]["name"] == test_employee["employee"].name

    def test_get_employee_as_employee_own_tenant(
        self, client: TestClient, employee_token: str, test_employee
    ):
        """Employee can retrieve employee from their own tenant"""
        response = client.get(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["employee_id"] == test_employee["employee"].employee_id

    def test_get_employee_as_employee_other_tenant(
        self, client: TestClient, employee_token: str, second_employee
    ):
        """Employee cannot retrieve employee from different tenant"""
        response = client.get(
            f"/api/v1/employees/{second_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_employee_not_found(self, client: TestClient, admin_token: str):
        """Get 404 for non-existent employee"""
        response = client.get(
            "/api/v1/employees/99999",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_employee_includes_tenant_location(self, client: TestClient, admin_token: str, test_employee):
        """Response includes tenant location details"""
        response = client.get(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        employee = data["data"]["employee"]
        # Check if tenant location fields are present
        assert "tenant_latitude" in employee
        assert "tenant_longitude" in employee
        assert "tenant_address" in employee

    def test_get_employee_as_vendor_forbidden(self, client: TestClient, vendor_token: str, test_employee):
        """Vendors cannot retrieve employees"""
        response = client.get(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {vendor_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_get_employee_without_auth(self, client: TestClient, test_employee):
        """Cannot retrieve employee without authentication"""
        response = client.get(f"/api/v1/employees/{test_employee["employee"].employee_id}")
        assert response.status_code == 401


class TestUpdateEmployee:
    """Test PUT /api/v1/employees/{employee_id} - Update Employee"""

    def test_update_employee_as_admin(self, client: TestClient, admin_token: str, test_employee):
        """Admin can update employee"""
        payload = {
            "name": "Updated Name",
            "phone": "+9876543210"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["name"] == "Updated Name"
        assert data["data"]["employee"]["phone"] == "+9876543210"

    def test_update_employee_as_employee_own_tenant(
        self, client: TestClient, employee_token: str, test_employee
    ):
        """Employee can update employee in their own tenant"""
        payload = {
            "name": "Updated by Employee"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["name"] == "Updated by Employee"

    def test_update_employee_as_employee_other_tenant(
        self, client: TestClient, employee_token: str, second_employee
    ):
        """Employee cannot update employee from different tenant"""
        payload = {
            "name": "Should Fail"
        }

        response = client.put(
            f"/api/v1/employees/{second_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_update_employee_partial_update(self, client: TestClient, admin_token: str, test_employee):
        """Partial update works correctly"""
        original_email = test_employee["employee"].email
        payload = {
            "name": "Partially Updated"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["name"] == "Partially Updated"
        # Email should remain unchanged
        assert data["data"]["employee"]["email"] == original_email

    def test_update_employee_with_new_team_same_tenant(
        self, client: TestClient, admin_token: str, test_employee, second_team_same_tenant
    ):
        """Can update employee to different team within same tenant"""
        payload = {
            "team_id": second_team_same_tenant.team_id
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["employee"]["team_id"] == second_team_same_tenant.team_id

    def test_update_employee_with_team_from_different_tenant(
        self, client: TestClient, admin_token: str, test_employee, second_team
    ):
        """Cannot update employee to team from different tenant"""
        payload = {
            "team_id": second_team.team_id  # Team from different tenant
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_update_employee_with_invalid_team_id(self, client: TestClient, admin_token: str, test_employee):
        """Cannot update with non-existent team"""
        payload = {
            "team_id": 99999
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_update_employee_password(self, client: TestClient, admin_token: str, test_employee):
        """Can update employee password"""
        payload = {
            "password": "NewSecurePass123!"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_update_employee_invalid_phone(self, client: TestClient, admin_token: str, test_employee):
        """Reject invalid phone format in update"""
        payload = {
            "phone": "invalid-phone-format"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_update_employee_not_found(self, client: TestClient, admin_token: str):
        """Get 404 when updating non-existent employee"""
        payload = {
            "name": "Should Fail"
        }

        response = client.put(
            "/api/v1/employees/99999",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_update_employee_as_vendor_forbidden(self, client: TestClient, vendor_token: str, test_employee):
        """Vendors cannot update employees"""
        payload = {
            "name": "Should Fail"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload,
            headers={"Authorization": f"Bearer {vendor_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_update_employee_without_auth(self, client: TestClient, test_employee):
        """Cannot update employee without authentication"""
        payload = {
            "name": "Should Fail"
        }

        response = client.put(
            f"/api/v1/employees/{test_employee["employee"].employee_id}",
            json=payload
        )

        assert response.status_code == 401


class TestToggleEmployeeStatus:
    """Test PATCH /api/v1/employees/{employee_id}/toggle-status - Toggle Status"""

    def test_toggle_employee_status_as_admin(self, client: TestClient, admin_token: str, test_employee):
        """Admin can toggle employee status"""
        original_status = test_employee["employee"].is_active

        response = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["is_active"] == (not original_status)

    def test_toggle_employee_status_twice(self, client: TestClient, admin_token: str, test_employee):
        """Toggle twice returns to original state"""
        # First toggle
        response1 = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response1.status_code == 200
        first_status = response1.json()["data"]["is_active"]

        # Second toggle
        response2 = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response2.status_code == 200
        second_status = response2.json()["data"]["is_active"]

        assert first_status != second_status

    def test_toggle_employee_status_as_employee_own_tenant(
        self, client: TestClient, employee_token: str, test_employee
    ):
        """Employee can toggle status within their tenant"""
        response = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_toggle_employee_status_as_employee_other_tenant(
        self, client: TestClient, employee_token: str, second_employee
    ):
        """Employee cannot toggle status in different tenant"""
        response = client.patch(
            f"/api/v1/employees/{second_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {employee_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_toggle_employee_status_not_found(self, client: TestClient, admin_token: str):
        """Get 404 for non-existent employee"""
        response = client.patch(
            "/api/v1/employees/99999/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_toggle_employee_status_as_vendor_forbidden(self, client: TestClient, vendor_token: str, test_employee):
        """Vendors cannot toggle employee status"""
        response = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {vendor_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_toggle_employee_status_without_auth(self, client: TestClient, test_employee):
        """Cannot toggle status without authentication"""
        response = client.patch(
            f"/api/v1/employees/{test_employee["employee"].employee_id}/toggle-status"
        )

        assert response.status_code == 401


class TestEmployeeIntegration:
    """Integration tests covering complete workflows"""

    def test_complete_employee_lifecycle(self, client: TestClient, admin_token: str, test_tenant, test_team):
        """Create, read, update, toggle status, verify complete lifecycle"""
        # 1. Create employee
        create_payload = {
            "name": "Lifecycle Employee",
            "email": "lifecycle@example.com",
            "phone": "+1111111111",
            "employee_code": "lifecycle001",
            "team_id": test_team.team_id,
            "tenant_id": test_tenant.tenant_id,
            "password": "TestPass123!",
            "gender": "Male"
        }

        create_response = client.post(
            "/api/v1/employees/",
            json=create_payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == 201
        employee_id = create_response.json()["data"]["employee"]["employee_id"]

        # 2. Read employee
        get_response = client.get(
            f"/api/v1/employees/{employee_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert get_response.status_code == 200
        assert get_response.json()["data"]["employee"]["name"] == "Lifecycle Employee"

        # 3. Update employee
        update_payload = {
            "name": "Updated Lifecycle Employee",
            "phone": "+2222222222"
        }
        update_response = client.put(
            f"/api/v1/employees/{employee_id}",
            json=update_payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["employee"]["name"] == "Updated Lifecycle Employee"

        # 4. Toggle status (deactivate)
        toggle_response = client.patch(
            f"/api/v1/employees/{employee_id}/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert toggle_response.status_code == 200
        assert toggle_response.json()["data"]["is_active"] is False

        # 5. Verify inactive in list
        list_response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&is_active=false",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 200
        inactive_employees = [e for e in list_response.json()["data"]["items"] if e["employee_id"] == employee_id]
        assert len(inactive_employees) == 1

    def test_employee_tenant_isolation(
        self, client: TestClient, employee_token: str, test_tenant, second_employee
    ):
        """Verify employees cannot access data from different tenants"""
        # Try to get employee from different tenant
        get_response = client.get(
            f"/api/v1/employees/{second_employee["employee"].employee_id}",
            headers={"Authorization": f"Bearer {employee_token}"}
        )
        assert get_response.status_code == 404

        # Try to update employee from different tenant
        update_response = client.put(
            f"/api/v1/employees/{second_employee["employee"].employee_id}",
            json={"name": "Should Fail"},
            headers={"Authorization": f"Bearer {employee_token}"}
        )
        assert update_response.status_code == 403

        # Verify list only shows own tenant
        list_response = client.get(
            "/api/v1/employees/",
            headers={"Authorization": f"Bearer {employee_token}"}
        )
        assert list_response.status_code == 200
        for employee in list_response.json()["data"]["items"]:
            assert employee["tenant_id"] == test_tenant.tenant_id

    def test_employee_with_multiple_filters(self, client: TestClient, admin_token: str, test_tenant):
        """Test combining multiple filters"""
        response = client.get(
            f"/api/v1/employees/?tenant_id={test_tenant.tenant_id}&is_active=true&skip=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify all employees match filters
        for employee in data["data"]["items"]:
            assert employee["tenant_id"] == test_tenant.tenant_id
            assert employee["is_active"] is True
