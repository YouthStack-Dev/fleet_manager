"""
Tests for IAM Router — Permissions, Policies, Roles, Policy Packages
Coverage: 17 routes
  - 5 Permissions  (POST/GET/GET{id}/PUT{id}/DELETE{id})
  - 5 Policies     (POST/GET/GET{id}/PUT{id}/DELETE{id})
  - 5 Roles        (POST/GET/GET{id}/PUT{id}/DELETE{id})
  - 2 Policy Pkgs  (GET/?tenant_id=, PUT{id}/permissions)
"""
import pytest
from app.models.iam.permission import Permission
from app.models.iam.policy import Policy, PolicyPackage
from app.models.iam.role import Role
from app.models.tenant import Tenant
from common_utils.auth.utils import create_access_token

IAM_PERM_URL = "/api/v1/iam/permissions"
IAM_POLICY_URL = "/api/v1/iam/policies"
IAM_ROLE_URL = "/api/v1/iam/roles"
IAM_PKG_URL = "/api/v1/iam/policy-packages"


# ─────────────────────────────────────────────────────────────────────────────
# Token fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def iam_admin_headers():
    """Admin JWT with all IAM permissions. Admin has no tenant_id in token."""
    token = create_access_token(
        user_id="1",
        user_type="admin",
        custom_claims={
            "permissions": [
                "permissions.create", "permissions.read",
                "permissions.update", "permissions.delete",
                "policy.create", "policy.read",
                "policy.update", "policy.delete",
                "role.create", "role.read",
                "role.update", "role.delete",
                "policy-package.read", "policy-package.update",
            ]
        },
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def iam_employee_headers():
    """Employee JWT with read-only IAM permissions and tenant TEST001."""
    token = create_access_token(
        user_id="42",
        tenant_id="TEST001",
        user_type="employee",
        custom_claims={
            "permissions": [
                "permissions.read",
                "policy.read",
                "role.read",
                "policy-package.read",
            ]
        },
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_iam_headers():
    """JWT with completely unrelated permissions — exercises 403 paths."""
    token = create_access_token(
        user_id="99",
        tenant_id="OTHER001",
        user_type="employee",
        custom_claims={"permissions": ["booking.read"]},
    )
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# DB seed fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def seed_tenant(test_db):
    existing = test_db.query(Tenant).filter_by(tenant_id="TEST001").first()
    if existing:
        return existing
    tenant = Tenant(tenant_id="TEST001", name="IAM Test Corp", is_active=True)
    test_db.add(tenant)
    test_db.flush()
    return tenant


@pytest.fixture
def seed_perm(test_db):
    """One Permission row."""
    perm = Permission(
        module="vehicle", action="read", description="Read vehicles", is_active=True
    )
    test_db.add(perm)
    test_db.flush()
    return perm


@pytest.fixture
def seed_policy(test_db, seed_tenant):
    """One tenant Policy row for TEST001."""
    policy = Policy(
        name="IAMTestPolicy",
        tenant_id="TEST001",
        is_system_policy=False,
        is_active=True,
    )
    test_db.add(policy)
    test_db.flush()
    return policy


@pytest.fixture
def seed_system_policy(test_db):
    """One system-level Policy (tenant_id=NULL)."""
    pol = Policy(
        name="IAMSystemPolicy",
        tenant_id=None,
        is_system_policy=True,
        is_active=True,
    )
    test_db.add(pol)
    test_db.flush()
    return pol


@pytest.fixture
def seed_role(test_db, seed_tenant):
    """One tenant Role row for TEST001."""
    role = Role(
        name="IAMTestRole",
        tenant_id="TEST001",
        is_system_role=False,
        is_active=True,
    )
    test_db.add(role)
    test_db.flush()
    return role


@pytest.fixture
def seed_package(test_db, seed_tenant):
    """PolicyPackage for TEST001."""
    pkg = PolicyPackage(
        tenant_id="TEST001",
        name="Default Package",
        description="IAM Test Package",
        permission_ids=[],
    )
    test_db.add(pkg)
    test_db.flush()
    return pkg


# ─────────────────────────────────────────────────────────────────────────────
# 1. PERMISSIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePermission:
    def test_create_permission_success(self, client, iam_admin_headers):
        payload = {"module": "booking", "action": "create", "description": "Create bookings"}
        r = client.post(f"{IAM_PERM_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["success"] is True
        assert body["data"]["module"] == "booking"
        assert body["data"]["action"] == "create"

    def test_create_permission_minimal_payload(self, client, iam_admin_headers):
        r = client.post(
            f"{IAM_PERM_URL}/",
            json={"module": "driver", "action": "read"},
            headers=iam_admin_headers,
        )
        assert r.status_code == 201
        assert r.json()["data"]["is_active"] is True

    def test_create_permission_missing_module(self, client, iam_admin_headers):
        r = client.post(
            f"{IAM_PERM_URL}/", json={"action": "read"}, headers=iam_admin_headers
        )
        assert r.status_code == 422

    def test_create_permission_invalid_action_enum(self, client, iam_admin_headers):
        r = client.post(
            f"{IAM_PERM_URL}/",
            json={"module": "booking", "action": "fly"},
            headers=iam_admin_headers,
        )
        assert r.status_code == 422

    def test_create_permission_no_auth(self, client):
        r = client.post(
            f"{IAM_PERM_URL}/", json={"module": "booking", "action": "create"}
        )
        assert r.status_code == 401

    def test_create_permission_forbidden(self, client, no_iam_headers):
        r = client.post(
            f"{IAM_PERM_URL}/",
            json={"module": "booking", "action": "create"},
            headers=no_iam_headers,
        )
        assert r.status_code == 403


class TestGetPermissions:
    def test_get_permissions_empty_db(self, client, iam_admin_headers):
        r = client.get(f"{IAM_PERM_URL}/", headers=iam_admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert isinstance(body["data"]["items"], list)
        assert isinstance(body["data"]["total"], int)

    def test_get_permissions_returns_seeded(self, client, iam_admin_headers, seed_perm):
        r = client.get(f"{IAM_PERM_URL}/", headers=iam_admin_headers)
        assert r.status_code == 200
        ids = [p["permission_id"] for p in r.json()["data"]["items"]]
        assert seed_perm.permission_id in ids

    def test_get_permissions_filter_by_module(self, client, iam_admin_headers, seed_perm):
        r = client.get(f"{IAM_PERM_URL}/?module=vehicle", headers=iam_admin_headers)
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            assert item["module"] == "vehicle"

    def test_get_permissions_filter_no_match(self, client, iam_admin_headers):
        r = client.get(f"{IAM_PERM_URL}/?module=nonexistent_xyz", headers=iam_admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_get_permissions_pagination_limit(self, client, iam_admin_headers):
        r = client.get(f"{IAM_PERM_URL}/?skip=0&limit=5", headers=iam_admin_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) <= 5

    def test_get_permissions_no_auth(self, client):
        assert client.get(f"{IAM_PERM_URL}/").status_code == 401

    def test_get_permissions_forbidden(self, client, no_iam_headers):
        assert client.get(f"{IAM_PERM_URL}/", headers=no_iam_headers).status_code == 403


class TestGetPermissionById:
    def test_get_permission_success(self, client, iam_admin_headers, seed_perm):
        r = client.get(f"{IAM_PERM_URL}/{seed_perm.permission_id}", headers=iam_admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["permission_id"] == seed_perm.permission_id

    def test_get_permission_not_found(self, client, iam_admin_headers):
        assert client.get(f"{IAM_PERM_URL}/999999", headers=iam_admin_headers).status_code == 404

    def test_get_permission_no_auth(self, client, seed_perm):
        assert client.get(f"{IAM_PERM_URL}/{seed_perm.permission_id}").status_code == 401

    def test_get_permission_forbidden(self, client, no_iam_headers, seed_perm):
        assert (
            client.get(
                f"{IAM_PERM_URL}/{seed_perm.permission_id}", headers=no_iam_headers
            ).status_code
            == 403
        )


class TestUpdatePermission:
    def test_update_permission_description(self, client, iam_admin_headers, seed_perm):
        r = client.put(
            f"{IAM_PERM_URL}/{seed_perm.permission_id}",
            json={"description": "Updated description"},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Updated description"

    def test_update_permission_deactivate(self, client, iam_admin_headers, seed_perm):
        r = client.put(
            f"{IAM_PERM_URL}/{seed_perm.permission_id}",
            json={"is_active": False},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_active"] is False

    def test_update_permission_not_found(self, client, iam_admin_headers):
        assert (
            client.put(
                f"{IAM_PERM_URL}/999999",
                json={"description": "x"},
                headers=iam_admin_headers,
            ).status_code
            == 404
        )

    def test_update_permission_no_auth(self, client, seed_perm):
        assert (
            client.put(
                f"{IAM_PERM_URL}/{seed_perm.permission_id}", json={"description": "x"}
            ).status_code
            == 401
        )

    def test_update_permission_forbidden(self, client, no_iam_headers, seed_perm):
        assert (
            client.put(
                f"{IAM_PERM_URL}/{seed_perm.permission_id}",
                json={"description": "x"},
                headers=no_iam_headers,
            ).status_code
            == 403
        )


class TestDeletePermission:
    def test_delete_permission_success(self, client, iam_admin_headers, seed_perm):
        r = client.delete(
            f"{IAM_PERM_URL}/{seed_perm.permission_id}", headers=iam_admin_headers
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_delete_permission_not_found(self, client, iam_admin_headers):
        assert (
            client.delete(f"{IAM_PERM_URL}/999999", headers=iam_admin_headers).status_code == 404
        )

    def test_delete_permission_no_auth(self, client, seed_perm):
        assert client.delete(f"{IAM_PERM_URL}/{seed_perm.permission_id}").status_code == 401

    def test_delete_permission_forbidden(self, client, no_iam_headers, seed_perm):
        assert (
            client.delete(
                f"{IAM_PERM_URL}/{seed_perm.permission_id}", headers=no_iam_headers
            ).status_code
            == 403
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. POLICIES
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePolicy:
    def test_admin_create_tenant_policy(self, client, iam_admin_headers, seed_tenant):
        payload = {
            "name": "NewTenantPolicy",
            "tenant_id": "TEST001",
            "is_system_policy": False,
            "permission_ids": [],
        }
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 201
        assert r.json()["data"]["name"] == "NewTenantPolicy"

    def test_admin_create_system_policy(self, client, iam_admin_headers):
        payload = {"name": "GlobalPolicy", "is_system_policy": True, "permission_ids": []}
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 201
        assert r.json()["data"]["is_system_policy"] is True
        assert r.json()["data"]["tenant_id"] is None

    def test_admin_must_provide_tenant_id_for_tenant_policy(self, client, iam_admin_headers):
        """Admin omits tenant_id when creating a non-system policy → 400."""
        payload = {"name": "MissingTenantPolicy", "is_system_policy": False, "permission_ids": []}
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 400

    def test_employee_cannot_create_system_policy(self, client, iam_employee_headers, seed_tenant):
        payload = {"name": "EmpSystemPol", "is_system_policy": True, "permission_ids": []}
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_employee_headers)
        assert r.status_code == 403

    def test_create_policy_missing_name(self, client, iam_admin_headers, seed_tenant):
        r = client.post(
            f"{IAM_POLICY_URL}/",
            json={"tenant_id": "TEST001", "is_system_policy": False, "permission_ids": []},
            headers=iam_admin_headers,
        )
        assert r.status_code == 422

    def test_create_policy_invalid_permission_ids(self, client, iam_admin_headers, seed_tenant):
        payload = {
            "name": "BadPermPolicy",
            "tenant_id": "TEST001",
            "is_system_policy": False,
            "permission_ids": [99999],
        }
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 400

    def test_create_policy_duplicate_name(self, client, iam_admin_headers, seed_policy):
        payload = {
            "name": seed_policy.name,
            "tenant_id": "TEST001",
            "is_system_policy": False,
            "permission_ids": [],
        }
        r = client.post(f"{IAM_POLICY_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code in (409, 400)

    def test_create_policy_no_auth(self, client):
        assert (
            client.post(f"{IAM_POLICY_URL}/", json={"name": "x", "permission_ids": []}).status_code
            == 401
        )


class TestGetPolicies:
    def test_admin_sees_system_policies(self, client, iam_admin_headers, seed_system_policy):
        r = client.get(f"{IAM_POLICY_URL}/", headers=iam_admin_headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["data"]["items"]]
        assert seed_system_policy.name in names

    def test_admin_with_tenant_id_param_sees_tenant_policies(
        self, client, iam_admin_headers, seed_policy
    ):
        r = client.get(f"{IAM_POLICY_URL}/?tenant_id=TEST001", headers=iam_admin_headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["data"]["items"]]
        assert seed_policy.name in names

    def test_employee_sees_own_tenant_policies(
        self, client, iam_employee_headers, seed_policy, seed_system_policy
    ):
        r = client.get(f"{IAM_POLICY_URL}/", headers=iam_employee_headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["data"]["items"]]
        assert seed_policy.name in names
        assert seed_system_policy.name in names

    def test_employee_cannot_access_other_tenant_policies(self, client, iam_employee_headers):
        r = client.get(f"{IAM_POLICY_URL}/?tenant_id=OTHER999", headers=iam_employee_headers)
        assert r.status_code == 403

    def test_get_policies_no_auth(self, client):
        assert client.get(f"{IAM_POLICY_URL}/").status_code == 401


class TestGetPolicyById:
    def test_get_system_policy_as_admin(self, client, iam_admin_headers, seed_system_policy):
        r = client.get(
            f"{IAM_POLICY_URL}/{seed_system_policy.policy_id}", headers=iam_admin_headers
        )
        assert r.status_code == 200
        assert r.json()["data"]["policy_id"] == seed_system_policy.policy_id

    def test_get_tenant_policy_as_employee(self, client, iam_employee_headers, seed_policy):
        r = client.get(
            f"{IAM_POLICY_URL}/{seed_policy.policy_id}", headers=iam_employee_headers
        )
        assert r.status_code == 200

    def test_get_policy_cross_tenant_denied(self, client, seed_policy):
        token = create_access_token(
            user_id="77",
            tenant_id="OTHER001",
            user_type="employee",
            custom_claims={"permissions": ["policy.read"]},
        )
        r = client.get(
            f"{IAM_POLICY_URL}/{seed_policy.policy_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_get_policy_not_found(self, client, iam_admin_headers):
        assert (
            client.get(f"{IAM_POLICY_URL}/999999", headers=iam_admin_headers).status_code == 404
        )

    def test_get_policy_no_auth(self, client, seed_policy):
        assert client.get(f"{IAM_POLICY_URL}/{seed_policy.policy_id}").status_code == 401


class TestUpdatePolicy:
    def test_admin_update_policy_name(self, client, iam_admin_headers, seed_policy):
        r = client.put(
            f"{IAM_POLICY_URL}/{seed_policy.policy_id}",
            json={"name": "RenamedPolicy"},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "RenamedPolicy"

    def test_non_admin_cannot_update_system_policy(
        self, client, iam_employee_headers, seed_system_policy
    ):
        r = client.put(
            f"{IAM_POLICY_URL}/{seed_system_policy.policy_id}",
            json={"name": "TryRename"},
            headers=iam_employee_headers,
        )
        assert r.status_code == 403

    def test_update_policy_with_invalid_permission_ids(
        self, client, iam_admin_headers, seed_policy
    ):
        r = client.put(
            f"{IAM_POLICY_URL}/{seed_policy.policy_id}",
            json={"permission_ids": [88888]},
            headers=iam_admin_headers,
        )
        assert r.status_code == 400

    def test_update_policy_not_found(self, client, iam_admin_headers):
        assert (
            client.put(
                f"{IAM_POLICY_URL}/999999", json={"name": "X"}, headers=iam_admin_headers
            ).status_code
            == 404
        )

    def test_update_policy_no_auth(self, client, seed_policy):
        assert (
            client.put(f"{IAM_POLICY_URL}/{seed_policy.policy_id}", json={"name": "x"}).status_code
            == 401
        )


class TestDeletePolicy:
    def test_delete_tenant_policy_as_admin(self, client, iam_admin_headers, seed_policy):
        r = client.delete(
            f"{IAM_POLICY_URL}/{seed_policy.policy_id}", headers=iam_admin_headers
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_non_admin_cannot_delete_system_policy(
        self, client, iam_employee_headers, seed_system_policy
    ):
        r = client.delete(
            f"{IAM_POLICY_URL}/{seed_system_policy.policy_id}", headers=iam_employee_headers
        )
        assert r.status_code == 403

    def test_delete_policy_not_found(self, client, iam_admin_headers):
        assert (
            client.delete(f"{IAM_POLICY_URL}/999999", headers=iam_admin_headers).status_code == 404
        )

    def test_delete_policy_no_auth(self, client, seed_policy):
        assert client.delete(f"{IAM_POLICY_URL}/{seed_policy.policy_id}").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 3. ROLES
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateRole:
    def test_admin_create_tenant_role(self, client, iam_admin_headers, seed_tenant):
        payload = {
            "name": "DriverRole",
            "tenant_id": "TEST001",
            "is_system_role": False,
            "policy_ids": [],
        }
        r = client.post(f"{IAM_ROLE_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 201
        assert r.json()["data"]["name"] == "DriverRole"

    def test_admin_create_system_role(self, client, iam_admin_headers):
        payload = {"name": "GlobalAdminRole", "is_system_role": True, "policy_ids": []}
        r = client.post(f"{IAM_ROLE_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 201
        assert r.json()["data"]["is_system_role"] is True
        assert r.json()["data"]["tenant_id"] is None

    def test_employee_cannot_create_system_role(self, client, seed_tenant):
        token = create_access_token(
            user_id="55",
            tenant_id="TEST001",
            user_type="employee",
            custom_claims={"permissions": ["role.create"]},
        )
        r = client.post(
            f"{IAM_ROLE_URL}/",
            json={"name": "EmpSysRole", "is_system_role": True, "policy_ids": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_admin_must_provide_tenant_id_for_tenant_role(self, client, iam_admin_headers):
        payload = {"name": "OrphanRole", "is_system_role": False, "policy_ids": []}
        r = client.post(f"{IAM_ROLE_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 400

    def test_create_role_invalid_policy_ids(self, client, iam_admin_headers, seed_tenant):
        payload = {
            "name": "BadPolicyRole",
            "tenant_id": "TEST001",
            "is_system_role": False,
            "policy_ids": [99999],
        }
        r = client.post(f"{IAM_ROLE_URL}/", json=payload, headers=iam_admin_headers)
        assert r.status_code == 400

    def test_create_role_missing_name(self, client, iam_admin_headers, seed_tenant):
        r = client.post(
            f"{IAM_ROLE_URL}/",
            json={"tenant_id": "TEST001", "is_system_role": False, "policy_ids": []},
            headers=iam_admin_headers,
        )
        assert r.status_code == 422

    def test_create_role_no_auth(self, client):
        assert client.post(f"{IAM_ROLE_URL}/", json={"name": "x", "policy_ids": []}).status_code == 401


class TestGetRoles:
    def test_get_roles_returns_seeded(self, client, iam_admin_headers, seed_role):
        # Admin must pass ?tenant_id= to see tenant roles (without it only system roles returned)
        r = client.get(f"{IAM_ROLE_URL}/?tenant_id=TEST001", headers=iam_admin_headers)
        assert r.status_code == 200
        ids = [ro["role_id"] for ro in r.json()["data"]["items"]]
        assert seed_role.role_id in ids

    def test_get_roles_pagination_respected(self, client, iam_admin_headers):
        r = client.get(f"{IAM_ROLE_URL}/?skip=0&limit=5", headers=iam_admin_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) <= 5

    def test_get_roles_no_auth(self, client):
        assert client.get(f"{IAM_ROLE_URL}/").status_code == 401

    def test_get_roles_forbidden(self, client, no_iam_headers):
        assert client.get(f"{IAM_ROLE_URL}/", headers=no_iam_headers).status_code == 403


class TestGetRoleById:
    def test_get_role_success(self, client, iam_admin_headers, seed_role):
        r = client.get(f"{IAM_ROLE_URL}/{seed_role.role_id}", headers=iam_admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["role_id"] == seed_role.role_id

    def test_get_role_includes_policies(self, client, iam_admin_headers, seed_role):
        body = client.get(
            f"{IAM_ROLE_URL}/{seed_role.role_id}", headers=iam_admin_headers
        ).json()
        assert "policies" in body["data"]

    def test_get_role_not_found(self, client, iam_admin_headers):
        assert client.get(f"{IAM_ROLE_URL}/999999", headers=iam_admin_headers).status_code == 404

    def test_get_role_no_auth(self, client, seed_role):
        assert client.get(f"{IAM_ROLE_URL}/{seed_role.role_id}").status_code == 401


class TestUpdateRole:
    def test_update_role_description(self, client, iam_admin_headers, seed_role):
        r = client.put(
            f"{IAM_ROLE_URL}/{seed_role.role_id}",
            json={"description": "Updated role desc"},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Updated role desc"

    def test_update_role_deactivate(self, client, iam_admin_headers, seed_role):
        r = client.put(
            f"{IAM_ROLE_URL}/{seed_role.role_id}",
            json={"is_active": False},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_active"] is False

    def test_update_role_not_found(self, client, iam_admin_headers):
        assert (
            client.put(
                f"{IAM_ROLE_URL}/999999", json={"name": "x"}, headers=iam_admin_headers
            ).status_code
            == 404
        )

    def test_update_role_no_auth(self, client, seed_role):
        assert client.put(f"{IAM_ROLE_URL}/{seed_role.role_id}", json={"name": "x"}).status_code == 401

    def test_update_role_forbidden(self, client, no_iam_headers, seed_role):
        assert (
            client.put(
                f"{IAM_ROLE_URL}/{seed_role.role_id}",
                json={"name": "x"},
                headers=no_iam_headers,
            ).status_code
            == 403
        )


class TestDeleteRole:
    def test_delete_role_success(self, client, iam_admin_headers, seed_role):
        r = client.delete(f"{IAM_ROLE_URL}/{seed_role.role_id}", headers=iam_admin_headers)
        assert r.status_code in (200, 204)

    def test_delete_role_not_found(self, client, iam_admin_headers):
        assert client.delete(f"{IAM_ROLE_URL}/999999", headers=iam_admin_headers).status_code == 404

    def test_delete_role_no_auth(self, client, seed_role):
        assert client.delete(f"{IAM_ROLE_URL}/{seed_role.role_id}").status_code == 401

    def test_delete_role_forbidden(self, client, no_iam_headers, seed_role):
        assert (
            client.delete(
                f"{IAM_ROLE_URL}/{seed_role.role_id}", headers=no_iam_headers
            ).status_code
            == 403
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. POLICY PACKAGES
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPolicyPackage:
    def test_admin_get_package_with_tenant_id(self, client, iam_admin_headers, seed_package):
        r = client.get(f"{IAM_PKG_URL}/?tenant_id=TEST001", headers=iam_admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["tenant_id"] == "TEST001"

    def test_admin_must_supply_tenant_id_param(self, client, iam_admin_headers):
        """Admin without ?tenant_id= → 400."""
        r = client.get(f"{IAM_PKG_URL}/", headers=iam_admin_headers)
        assert r.status_code == 400

    def test_employee_gets_own_package(self, client, iam_employee_headers, seed_package):
        r = client.get(f"{IAM_PKG_URL}/", headers=iam_employee_headers)
        assert r.status_code == 200
        assert r.json()["data"]["tenant_id"] == "TEST001"

    def test_employee_tenant_id_param_ignored(self, client, iam_employee_headers, seed_package):
        """Employee's own package is always returned even if ?tenant_id= is set differently."""
        r = client.get(f"{IAM_PKG_URL}/?tenant_id=OTHER999", headers=iam_employee_headers)
        assert r.status_code == 200
        assert r.json()["data"]["tenant_id"] == "TEST001"

    def test_get_package_not_found(self, client, iam_admin_headers):
        r = client.get(f"{IAM_PKG_URL}/?tenant_id=GHOST999", headers=iam_admin_headers)
        assert r.status_code == 404

    def test_get_package_no_auth(self, client):
        assert client.get(f"{IAM_PKG_URL}/").status_code == 401

    def test_get_package_forbidden(self, client, no_iam_headers):
        assert client.get(f"{IAM_PKG_URL}/", headers=no_iam_headers).status_code == 403


class TestUpdatePackagePermissions:
    def test_admin_replace_package_permissions(
        self, client, iam_admin_headers, seed_package, seed_perm
    ):
        r = client.put(
            f"{IAM_PKG_URL}/{seed_package.package_id}/permissions",
            json={"permission_ids": [seed_perm.permission_id]},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert seed_perm.permission_id in r.json()["data"]["permission_ids"]

    def test_admin_clear_package_permissions(self, client, iam_admin_headers, seed_package):
        r = client.put(
            f"{IAM_PKG_URL}/{seed_package.package_id}/permissions",
            json={"permission_ids": []},
            headers=iam_admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["permission_count"] == 0

    def test_non_admin_cannot_update_package(
        self, client, iam_employee_headers, seed_package, seed_perm
    ):
        r = client.put(
            f"{IAM_PKG_URL}/{seed_package.package_id}/permissions",
            json={"permission_ids": [seed_perm.permission_id]},
            headers=iam_employee_headers,
        )
        assert r.status_code == 403

    def test_update_package_not_found(self, client, iam_admin_headers):
        r = client.put(
            f"{IAM_PKG_URL}/999999/permissions",
            json={"permission_ids": []},
            headers=iam_admin_headers,
        )
        assert r.status_code == 404

    def test_update_package_no_auth(self, client, seed_package):
        assert (
            client.put(
                f"{IAM_PKG_URL}/{seed_package.package_id}/permissions",
                json={"permission_ids": []},
            ).status_code
            == 401
        )
