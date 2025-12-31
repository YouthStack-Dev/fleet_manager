"""
Comprehensive tests for vendor user management endpoints.

Tests cover:
- POST /vendor-users/ - Create vendor user
- GET /vendor-users/ - List vendor users with filters
- GET /vendor-users/{vendor_user_id} - Get single vendor user
- PUT /vendor-users/{vendor_user_id} - Update vendor user
- PATCH /vendor-users/{vendor_user_id}/toggle-status - Toggle status
- DELETE /vendor-users/{vendor_user_id} - Delete vendor user

Edge cases tested:
- User type restrictions (admin, employee, others forbidden)
- Tenant isolation (admin requires tenant_id, employee automatic)
- Vendor must exist and belong to tenant
- Duplicate email/phone prevention within tenant
- Role validation (must exist, be active, belong to tenant or be system role)
- Password hashing
- Permission-based access control
- Filter combinations (name, email, vendor_id, is_active)
- Pagination
"""
import pytest
from fastapi import status


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture(scope="function")
def vendor_user_role(test_db, test_tenant):
    """Create a test role for vendor users"""
    from app.models.iam.role import Role
    
    role = test_db.query(Role).filter(
        Role.name == "VendorUser",
        Role.tenant_id == test_tenant.tenant_id
    ).first()
    
    if not role:
        role = Role(
            tenant_id=test_tenant.tenant_id,
            name="VendorUser",
            description="Test Vendor User Role",
            is_system_role=False,
            is_active=True
        )
        test_db.add(role)
        test_db.commit()
        test_db.refresh(role)
    
    return role


@pytest.fixture(scope="function")
def system_vendor_role(test_db):
    """Create VendorAdmin system role if it doesn't exist"""
    from app.models.iam.role import Role
    
    vendor_admin_role = test_db.query(Role).filter(
        Role.name == "VendorAdmin",
        Role.is_system_role == True
    ).first()
    
    if not vendor_admin_role:
        vendor_admin_role = Role(
            tenant_id=None,
            name="VendorAdmin",
            description="System Vendor Admin Role",
            is_system_role=True,
            is_active=True
        )
        test_db.add(vendor_admin_role)
        test_db.commit()
        test_db.refresh(vendor_admin_role)
    
    return vendor_admin_role


@pytest.fixture(scope="function")
def employee_vendor_user_token(test_tenant, test_employee):
    """Generate JWT token for employee with vendor-user permissions"""
    from common_utils.auth.utils import create_access_token
    
    token = create_access_token(
        user_id=str(test_employee["employee"].employee_id),
        tenant_id=test_tenant.tenant_id,
        user_type="employee",
        custom_claims={
            "permissions": [
                "vendor-user.create",
                "vendor-user.read",
                "vendor-user.update",
                "vendor-user.delete"
            ]
        }
    )
    return token


@pytest.fixture(scope="function")
def driver_token(test_tenant, test_driver):
    """Generate JWT token for driver user"""
    from common_utils.auth.utils import create_access_token
    
    token = create_access_token(
        user_id=str(test_driver.driver_id),
        tenant_id=test_tenant.tenant_id,
        user_type="driver",
        custom_claims={
            "permissions": []
        }
    )
    return token


@pytest.fixture(scope="function")
def vendor_user_create_data(test_tenant, test_vendor, vendor_user_role):
    """Common vendor user creation data"""
    return {
        "tenant_id": test_tenant.tenant_id,
        "vendor_id": test_vendor.vendor_id,
        "name": "Test Vendor User",
        "email": "vendoruser@test.com",
        "phone": "+1234567890",
        "password": "SecurePass@123",
        "role_id": vendor_user_role.role_id,
        "is_active": True
    }


@pytest.fixture(scope="function")
def test_vendor_user(test_db, test_tenant, test_vendor, vendor_user_role):
    """Create a test vendor user"""
    from app.models.vendor_user import VendorUser
    from common_utils.auth.utils import hash_password
    
    vendor_user = VendorUser(
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        name="Existing Vendor User",
        email="existing@vendoruser.com",
        phone="+9876543210",
        password=hash_password("password123"),
        role_id=vendor_user_role.role_id,
        is_active=True
    )
    test_db.add(vendor_user)
    test_db.commit()
    test_db.refresh(vendor_user)
    return vendor_user


@pytest.fixture(scope="function")
def second_tenant_vendor_user(test_db, second_tenant, second_vendor, vendor_user_role):
    """Create a vendor user in second tenant"""
    from app.models.vendor_user import VendorUser
    from common_utils.auth.utils import hash_password
    
    vendor_user = VendorUser(
        tenant_id=second_tenant.tenant_id,
        vendor_id=second_vendor.vendor_id,
        name="Second Tenant Vendor User",
        email="second@vendoruser.com",
        phone="+1111111111",
        password=hash_password("password123"),
        role_id=vendor_user_role.role_id,
        is_active=True
    )
    test_db.add(vendor_user)
    test_db.commit()
    test_db.refresh(vendor_user)
    return vendor_user


# =====================================================================
# TEST: POST /vendor-users/ (Create Vendor User)
# =====================================================================

class TestCreateVendorUser:
    """Test suite for creating vendor users"""

    def test_create_vendor_user_as_admin(self, client, test_db, admin_token, vendor_user_create_data):
        """Admin can create vendor user with tenant_id in body"""
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["name"] == "Test Vendor User"
        assert data["data"]["email"] == "vendoruser@test.com"

    def test_create_vendor_user_as_employee(self, client, test_db, employee_vendor_user_token, test_tenant, test_vendor, vendor_user_role):
        """Employee can create vendor user (tenant_id from token)"""
        response = client.post(
            "/api/v1/vendor-users/",
            json={
                "vendor_id": test_vendor.vendor_id,
                "name": "Employee Created User",
                "email": "empcreated@test.com",
                "phone": "+2222222222",
                "password": "Pass@123",
                "role_id": vendor_user_role.role_id,
                "is_active": True
            },
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["tenant_id"] == test_tenant.tenant_id

    def test_create_vendor_user_admin_without_tenant_id(self, client, test_db, admin_token, vendor_user_create_data):
        """Admin must provide tenant_id in body"""
        vendor_user_create_data.pop("tenant_id")
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "tenant id" in str(response.json()).lower()

    def test_create_vendor_user_as_driver_forbidden(self, client, test_db, driver_token, vendor_user_create_data):
        """Driver users cannot create vendor users"""
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {driver_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_vendor_user_invalid_vendor(self, client, test_db, admin_token, vendor_user_create_data):
        """Cannot create vendor user with non-existent vendor"""
        vendor_user_create_data["vendor_id"] = 99999
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "vendor" in str(response.json()).lower()

    def test_create_vendor_user_vendor_wrong_tenant(self, client, test_db, admin_token, second_vendor, vendor_user_create_data):
        """Cannot create vendor user if vendor belongs to different tenant"""
        vendor_user_create_data["vendor_id"] = second_vendor.vendor_id
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "tenant" in str(response.json()).lower()

    def test_create_vendor_user_duplicate_email(self, client, test_db, admin_token, test_vendor_user, vendor_user_create_data):
        """Cannot create vendor user with duplicate email in same tenant"""
        vendor_user_create_data["email"] = test_vendor_user.email
        vendor_user_create_data["phone"] = "+3333333333"
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in str(response.json()).lower()

    def test_create_vendor_user_duplicate_phone(self, client, test_db, admin_token, test_vendor_user, vendor_user_create_data):
        """Cannot create vendor user with duplicate phone in same tenant"""
        vendor_user_create_data["phone"] = test_vendor_user.phone
        vendor_user_create_data["email"] = "different@email.com"
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone" in str(response.json()).lower()

    def test_create_vendor_user_invalid_role(self, client, test_db, admin_token, vendor_user_create_data):
        """Cannot create vendor user with non-existent role"""
        vendor_user_create_data["role_id"] = 99999
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "role" in str(response.json()).lower()

    def test_create_vendor_user_with_system_role(self, client, test_db, admin_token, vendor_user_create_data, system_vendor_role):
        """Can create vendor user with system role"""
        vendor_user_create_data["role_id"] = system_vendor_role.role_id
        vendor_user_create_data["email"] = "systemrole@test.com"
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_vendor_user_unauthorized(self, client, test_db, vendor_user_create_data):
        """Unauthorized users cannot create vendor users"""
        response = client.post(
            "/api/v1/vendor-users/",
            json=vendor_user_create_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: GET /vendor-users/ (List Vendor Users)
# =====================================================================

class TestListVendorUsers:
    """Test suite for listing vendor users"""

    def test_list_vendor_users_as_admin(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Admin can list vendor users with tenant_id parameter"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert "items" in data["data"]
        assert len(data["data"]["items"]) >= 1

    def test_list_vendor_users_as_employee(self, client, test_db, employee_vendor_user_token, test_vendor_user):
        """Employee can list vendor users (tenant_id from token)"""
        response = client.get(
            "/api/v1/vendor-users/",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        # All users should belong to employee's tenant
        for item in data["data"]["items"]:
            assert item["tenant_id"] == test_vendor_user.tenant_id

    def test_list_vendor_users_admin_without_tenant_id(self, client, test_db, admin_token):
        """Admin must provide tenant_id parameter"""
        response = client.get(
            "/api/v1/vendor-users/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "tenant id" in str(response.json()).lower()

    def test_list_vendor_users_as_driver_forbidden(self, client, test_db, driver_token, test_tenant):
        """Driver users cannot list vendor users"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {driver_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_vendor_users_filter_by_name(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can filter vendor users by name"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&name={test_vendor_user.name[:5]}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data["data"]["items"]) >= 1

    def test_list_vendor_users_filter_by_email(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can filter vendor users by email"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&email={test_vendor_user.email}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert any(item["email"] == test_vendor_user.email for item in data["data"]["items"])

    def test_list_vendor_users_filter_by_vendor(self, client, test_db, admin_token, test_tenant, test_vendor, test_vendor_user):
        """Can filter vendor users by vendor_id"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        for item in data["data"]["items"]:
            assert item["vendor_id"] == test_vendor.vendor_id

    def test_list_vendor_users_filter_by_active(self, client, test_db, admin_token, test_tenant):
        """Can filter vendor users by is_active"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&is_active=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        for item in data["data"]["items"]:
            assert item["is_active"] is True

    def test_list_vendor_users_pagination(self, client, test_db, admin_token, test_tenant):
        """Pagination works correctly"""
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&skip=0&limit=5",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert len(data["data"]["items"]) <= 5

    def test_list_vendor_users_tenant_isolation(self, client, test_db, employee_vendor_user_token, test_vendor_user, second_tenant_vendor_user):
        """Employee only sees vendor users from their tenant"""
        response = client.get(
            "/api/v1/vendor-users/",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Should only see users from test_tenant, not second_tenant
        for item in data["data"]["items"]:
            assert item["tenant_id"] == test_vendor_user.tenant_id
            assert item["vendor_user_id"] != second_tenant_vendor_user.vendor_user_id


# =====================================================================
# TEST: GET /vendor-users/{vendor_user_id} (Get Single Vendor User)
# =====================================================================

class TestGetVendorUser:
    """Test suite for getting single vendor user"""

    def test_get_vendor_user_as_admin(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Admin can get vendor user with tenant_id parameter"""
        response = client.get(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vendor_user_id"] == test_vendor_user.vendor_user_id

    def test_get_vendor_user_as_employee(self, client, test_db, employee_vendor_user_token, test_vendor_user):
        """Employee can get vendor user (tenant_id from token)"""
        response = client.get(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["vendor_user_id"] == test_vendor_user.vendor_user_id

    def test_get_vendor_user_admin_without_tenant_id(self, client, test_db, admin_token, test_vendor_user):
        """Admin must provide tenant_id parameter"""
        response = client.get(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_vendor_user_wrong_tenant(self, client, test_db, employee_vendor_user_token, second_tenant_vendor_user):
        """Employee cannot get vendor user from different tenant"""
        response = client.get(
            f"/api/v1/vendor-users/{second_tenant_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_vendor_user_not_found(self, client, test_db, admin_token, test_tenant):
        """Returns 404 for non-existent vendor user"""
        response = client.get(
            f"/api/v1/vendor-users/99999?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_vendor_user_unauthorized(self, client, test_db, test_vendor_user):
        """Unauthorized users cannot get vendor user"""
        response = client.get(f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =====================================================================
# TEST: PUT /vendor-users/{vendor_user_id} (Update Vendor User)
# =====================================================================

class TestUpdateVendorUser:
    """Test suite for updating vendor users"""

    def test_update_vendor_user_name_as_admin(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Admin can update vendor user name"""
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={"name": "Updated Name"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["name"] == "Updated Name"

    def test_update_vendor_user_as_employee(self, client, test_db, employee_vendor_user_token, test_vendor_user):
        """Employee can update vendor user"""
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            json={"phone": "+9999999999"},
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["phone"] == "+9999999999"

    def test_update_vendor_user_multiple_fields(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can update multiple fields at once"""
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={
                "name": "Multi Update",
                "email": "multiupdate@test.com",
                "phone": "+8888888888"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["name"] == "Multi Update"
        assert data["data"]["email"] == "multiupdate@test.com"

    def test_update_vendor_user_password(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can update password (should be hashed)"""
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={"password": "NewSecurePass@123"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        # Password should be hashed, not returned in plain text
        data = response.json()
        assert "password" not in data["data"] or data["data"].get("password") != "NewSecurePass@123"

    def test_update_vendor_user_duplicate_email(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Cannot update to duplicate email"""
        # Create another user first
        from app.models.vendor_user import VendorUser
        from common_utils.auth.utils import hash_password
        another_user = VendorUser(
            tenant_id=test_tenant.tenant_id,
            vendor_id=test_vendor_user.vendor_id,
            name="Another User",
            email="another@user.com",
            phone="+5555555555",
            password=hash_password("pass123"),
            role_id=test_vendor_user.role_id,
            is_active=True
        )
        test_db.add(another_user)
        test_db.commit()
        
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={"email": "another@user.com"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in str(response.json()).lower()

    def test_update_vendor_user_wrong_tenant(self, client, test_db, employee_vendor_user_token, second_tenant_vendor_user):
        """Employee cannot update vendor user from different tenant"""
        response = client.put(
            f"/api/v1/vendor-users/{second_tenant_vendor_user.vendor_user_id}",
            json={"name": "Should Fail"},
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_vendor_user_not_found(self, client, test_db, admin_token, test_tenant):
        """Returns 404 when updating non-existent vendor user"""
        response = client.put(
            f"/api/v1/vendor-users/99999?tenant_id={test_tenant.tenant_id}",
            json={"name": "Not Found"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_vendor_user_change_vendor_wrong_tenant(self, client, test_db, admin_token, test_tenant, test_vendor_user, second_vendor):
        """Cannot update vendor_id to vendor from different tenant"""
        response = client.put(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={"vendor_id": second_vendor.vendor_id},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# =====================================================================
# TEST: PATCH /vendor-users/{vendor_user_id}/toggle-status
# =====================================================================

class TestToggleVendorUserStatus:
    """Test suite for toggling vendor user status"""

    def test_toggle_vendor_user_to_inactive(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can toggle active vendor user to inactive"""
        assert test_vendor_user.is_active is True
        
        response = client.patch(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}/toggle-status?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["is_active"] is False

    def test_toggle_vendor_user_to_active(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Can toggle inactive vendor user to active"""
        # First deactivate
        test_vendor_user.is_active = False
        test_db.commit()
        
        response = client.patch(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}/toggle-status?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["is_active"] is True

    def test_toggle_vendor_user_as_employee(self, client, test_db, employee_vendor_user_token, test_vendor_user):
        """Employee can toggle vendor user status"""
        response = client.patch(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}/toggle-status",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True

    def test_toggle_vendor_user_admin_without_tenant_id(self, client, test_db, admin_token, test_vendor_user):
        """Admin must provide tenant_id parameter"""
        response = client.patch(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}/toggle-status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_toggle_vendor_user_wrong_tenant(self, client, test_db, employee_vendor_user_token, second_tenant_vendor_user):
        """Employee cannot toggle vendor user from different tenant"""
        response = client.patch(
            f"/api/v1/vendor-users/{second_tenant_vendor_user.vendor_user_id}/toggle-status",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_toggle_vendor_user_not_found(self, client, test_db, admin_token, test_tenant):
        """Returns 404 when toggling non-existent vendor user"""
        response = client.patch(
            f"/api/v1/vendor-users/99999/toggle-status?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# =====================================================================
# TEST: DELETE /vendor-users/{vendor_user_id}
# =====================================================================

class TestDeleteVendorUser:
    """Test suite for deleting vendor users"""

    def test_delete_vendor_user_as_admin(self, client, test_db, admin_token, test_tenant, test_vendor_user):
        """Admin can delete vendor user"""
        response = client.delete(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_vendor_user_as_employee(self, client, test_db, employee_vendor_user_token, test_vendor_user):
        """Employee can delete vendor user"""
        response = client.delete(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_vendor_user_admin_without_tenant_id(self, client, test_db, admin_token, test_vendor_user):
        """Admin must provide tenant_id parameter"""
        response = client.delete(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_vendor_user_wrong_tenant(self, client, test_db, employee_vendor_user_token, second_tenant_vendor_user):
        """Employee cannot delete vendor user from different tenant"""
        response = client.delete(
            f"/api/v1/vendor-users/{second_tenant_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_vendor_user_not_found(self, client, test_db, admin_token, test_tenant):
        """Returns 404 when deleting non-existent vendor user"""
        response = client.delete(
            f"/api/v1/vendor-users/99999?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# =====================================================================
# INTEGRATION TESTS
# =====================================================================

class TestVendorUserIntegration:
    """Integration tests for complete vendor user workflows"""

    def test_vendor_user_complete_lifecycle(self, client, test_db, admin_token, test_tenant, test_vendor, vendor_user_role):
        """Test complete lifecycle: create, read, update, toggle, delete"""
        # 1. Create
        create_data = {
            "tenant_id": test_tenant.tenant_id,
            "vendor_id": test_vendor.vendor_id,
            "name": "Lifecycle User",
            "email": "lifecycle@test.com",
            "phone": "+7777777777",
            "password": "Pass@123",
            "role_id": vendor_user_role.role_id,
            "is_active": True
        }
        create_response = client.post(
            "/api/v1/vendor-users/",
            json=create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        vendor_user_id = create_response.json()["data"]["vendor_user_id"]
        
        # 2. Read
        get_response = client.get(
            f"/api/v1/vendor-users/{vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["data"]["name"] == "Lifecycle User"
        
        # 3. Update
        update_response = client.put(
            f"/api/v1/vendor-users/{vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            json={"name": "Updated Lifecycle"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["data"]["name"] == "Updated Lifecycle"
        
        # 4. Toggle status
        toggle_response = client.patch(
            f"/api/v1/vendor-users/{vendor_user_id}/toggle-status?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert toggle_response.status_code == status.HTTP_200_OK
        assert toggle_response.json()["data"]["is_active"] is False
        
        # 5. Delete
        delete_response = client.delete(
            f"/api/v1/vendor-users/{vendor_user_id}?tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    def test_employee_tenant_isolation(self, client, test_db, employee_vendor_user_token, test_vendor_user, second_tenant_vendor_user):
        """Employee can only access vendor users in their tenant"""
        # Can access same tenant
        response1 = client.get(
            f"/api/v1/vendor-users/{test_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response1.status_code == status.HTTP_200_OK
        
        # Cannot access different tenant
        response2 = client.get(
            f"/api/v1/vendor-users/{second_tenant_vendor_user.vendor_user_id}",
            headers={"Authorization": f"Bearer {employee_vendor_user_token}"}
        )
        assert response2.status_code == status.HTTP_404_NOT_FOUND

    def test_filter_combinations(self, client, test_db, admin_token, test_tenant, test_vendor, vendor_user_role):
        """Test various filter combinations"""
        # Create multiple test users
        from app.models.vendor_user import VendorUser
        from common_utils.auth.utils import hash_password
        
        for i in range(3):
            user = VendorUser(
                tenant_id=test_tenant.tenant_id,
                vendor_id=test_vendor.vendor_id,
                name=f"Filter User {i}",
                email=f"filter{i}@test.com",
                phone=f"+666666666{i}",
                password=hash_password("pass123"),
                role_id=vendor_user_role.role_id,
                is_active=i % 2 == 0  # Alternate active/inactive
            )
            test_db.add(user)
        test_db.commit()
        
        # Filter by name
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&name=Filter",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        assert all("Filter" in item["name"] for item in items)
        
        # Filter by vendor + active
        response = client.get(
            f"/api/v1/vendor-users/?tenant_id={test_tenant.tenant_id}&vendor_id={test_vendor.vendor_id}&is_active=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["data"]["items"]
        assert all(item["vendor_id"] == test_vendor.vendor_id and item["is_active"] for item in items)

    def test_password_hashing(self, client, test_db, admin_token, test_tenant, test_vendor, vendor_user_role):
        """Verify password is hashed and not returned"""
        create_data = {
            "tenant_id": test_tenant.tenant_id,
            "vendor_id": test_vendor.vendor_id,
            "name": "Password Test",
            "email": "passtest@test.com",
            "phone": "+4444444444",
            "password": "PlainTextPass@123",
            "role_id": vendor_user_role.role_id,
            "is_active": True
        }
        response = client.post(
            "/api/v1/vendor-users/",
            json=create_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        
        # Password should not be in response
        data = response.json()["data"]
        assert "password" not in data or data.get("password") != "PlainTextPass@123"
        
        # Verify in database that password is hashed
        from app.models.vendor_user import VendorUser
        db_user = test_db.query(VendorUser).filter(
            VendorUser.email == "passtest@test.com"
        ).first()
        assert db_user.password != "PlainTextPass@123"
        assert len(db_user.password) > 50  # Hashed passwords are long
