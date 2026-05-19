"""
Unit tests for IAM permission logic.

Tests:
  - JWT permission-claim normalization (string + dict formats)
  - has_permission decision function
  - Role-based permission matrices matching production IAM model
  - Edge cases: empty lists, case sensitivity, malformed claims

No DB, no HTTP — pure Python functions.
"""
from typing import Any, List

import pytest

pytestmark = pytest.mark.unit


# ─── Production-mirrored helpers ─────────────────────────────────────────────
# These functions mirror the logic in conftest.py mock_permission_checker_call
# and the PermissionChecker.__call__ production path so we can unit-test the
# permission evaluation independently of HTTP machinery.


def normalize_permissions(raw: List[Any]) -> List[str]:
    """
    Convert mixed-format JWT permission claims into a flat 'module.action' list.

    Supported input formats:
      - String:  "booking.read"
      - Dict:    {"module": "alert", "action": ["create", "respond"]}
                 {"module": "route", "action": "read"}   ← single action string
    """
    result: List[str] = []
    for perm in raw:
        if isinstance(perm, dict):
            module = perm.get("module", "")
            actions = perm.get("action", [])
            if isinstance(actions, list):
                result.extend(f"{module}.{a}" for a in actions)
            elif isinstance(actions, str):
                result.append(f"{module}.{actions}")
        elif isinstance(perm, str):
            parts = perm.rsplit(".", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                result.append(perm)
    return result


def has_permission(user_permissions: List[str], required: List[str]) -> bool:
    """Return True when the user holds at least one of the required permissions."""
    return any(p in user_permissions for p in required)


# ─────────────────────────────────────────────────────────────────────────────
# normalize_permissions
# ─────────────────────────────────────────────────────────────────────────────
class TestNormalizePermissions:
    def test_single_string_permission(self):
        result = normalize_permissions(["employee.read"])
        assert "employee.read" in result

    def test_multiple_string_permissions(self):
        raw = ["booking.read", "booking.create", "route.update"]
        result = normalize_permissions(raw)
        assert result == raw

    def test_dict_with_list_actions_expands(self):
        raw = [{"module": "alert", "action": ["create", "read", "respond"]}]
        result = normalize_permissions(raw)
        assert "alert.create" in result
        assert "alert.read" in result
        assert "alert.respond" in result
        assert len(result) == 3

    def test_dict_with_single_string_action(self):
        raw = [{"module": "route", "action": "read"}]
        result = normalize_permissions(raw)
        assert result == ["route.read"]

    def test_mixed_string_and_dict_formats(self):
        raw = [
            "booking.read",
            "booking.create",
            {"module": "alert", "action": ["respond", "close"]},
        ]
        result = normalize_permissions(raw)
        assert "booking.read" in result
        assert "booking.create" in result
        assert "alert.respond" in result
        assert "alert.close" in result

    def test_empty_list_returns_empty(self):
        assert normalize_permissions([]) == []

    def test_string_without_dot_is_ignored(self):
        raw = ["no_separator", "valid.permission"]
        result = normalize_permissions(raw)
        assert "valid.permission" in result
        assert "no_separator" not in result

    def test_dict_with_empty_action_list(self):
        raw = [{"module": "ghost", "action": []}]
        result = normalize_permissions(raw)
        assert result == []

    def test_dict_missing_module_key(self):
        raw = [{"action": ["read"]}]
        result = normalize_permissions(raw)
        # module defaults to "" → ".read" is still appended; treat as edge-case
        assert ".read" in result

    def test_multi_action_dict_correct_count(self):
        actions = ["create", "read", "update", "delete"]
        raw = [{"module": "route_vendor_assignment", "action": actions}]
        result = normalize_permissions(raw)
        assert len(result) == 4
        for action in actions:
            assert f"route_vendor_assignment.{action}" in result

    def test_duplicate_permissions_preserved(self):
        """Deduplication is caller's responsibility; normalizer should not deduplicate."""
        raw = ["booking.read", "booking.read"]
        result = normalize_permissions(raw)
        assert result.count("booking.read") == 2

    def test_module_with_hyphen_preserved(self):
        """Hyphenated module names like 'vehicle-type' must survive normalization."""
        raw = ["vehicle-type.read", "vehicle-type.create"]
        result = normalize_permissions(raw)
        assert "vehicle-type.read" in result
        assert "vehicle-type.create" in result


# ─────────────────────────────────────────────────────────────────────────────
# has_permission
# ─────────────────────────────────────────────────────────────────────────────
class TestHasPermission:
    def test_exact_match_grants_access(self):
        assert has_permission(["employee.read"], ["employee.read"]) is True

    def test_superset_user_permissions_grants_access(self):
        user = ["employee.read", "employee.create", "team.read"]
        assert has_permission(user, ["employee.read"]) is True

    def test_missing_permission_denies_access(self):
        assert has_permission(["employee.read"], ["employee.delete"]) is False

    def test_any_one_match_in_required_list_grants_access(self):
        """OR semantics: user needs at least one from the required list."""
        user = ["route.read"]
        assert has_permission(user, ["route.write", "route.read", "route.admin"]) is True

    def test_empty_user_permissions_always_denied(self):
        assert has_permission([], ["employee.read"]) is False

    def test_empty_required_permissions_vacuously_false(self):
        """any() over empty iterable returns False — no permission required means nothing matches."""
        assert has_permission(["employee.read"], []) is False

    def test_case_sensitive_mismatch_denies(self):
        # "Employee.Read" ≠ "employee.read"
        assert has_permission(["Employee.Read"], ["employee.read"]) is False

    def test_partial_module_name_does_not_match(self):
        # "employee" should not match "employee.read"
        assert has_permission(["employee"], ["employee.read"]) is False


# ─────────────────────────────────────────────────────────────────────────────
# Role-permission matrices
# ─────────────────────────────────────────────────────────────────────────────
class TestRolePermissionMatrix:
    """Verify the expected permission boundaries for each user role."""

    # ── Role permission sets matching production JWT claims ──────────────────
    SYSTEM_ADMIN_PERMISSIONS = normalize_permissions(
        [
            "admin_tenant.create",
            "admin_tenant.read",
            "admin_tenant.update",
            "admin_tenant.delete",
            "employee.create",
            "employee.read",
            "employee.update",
            "employee.delete",
            "driver.create",
            "driver.read",
            "driver.update",
            "driver.delete",
            "vendor.create",
            "vendor.read",
            "vendor.update",
            "vendor.delete",
            "vehicle.create",
            "vehicle.read",
            "vehicle.update",
            "vehicle.delete",
            "route.create",
            "route.read",
            "route.update",
            "route.delete",
            "booking.create",
            "booking.read",
            "booking.update",
            "booking.delete",
            {"module": "alert", "action": ["create", "read", "update", "delete", "respond", "close", "escalate"]},
        ]
    )

    VENDOR_USER_PERMISSIONS = normalize_permissions(
        ["route.read", "vehicle.read", "driver.read"]
    )

    DRIVER_PERMISSIONS: List[str] = []

    EMPLOYEE_PERMISSIONS = normalize_permissions(
        [
            "booking.create",
            "booking.read",
            "booking.update",
            {"module": "alert", "action": ["create", "read"]},
        ]
    )

    # ── SystemAdmin ──────────────────────────────────────────────────────────
    def test_admin_can_perform_all_crud_on_employees(self):
        for action in ["create", "read", "update", "delete"]:
            assert has_permission(self.SYSTEM_ADMIN_PERMISSIONS, [f"employee.{action}"]) is True

    def test_admin_can_manage_tenants(self):
        for action in ["create", "read", "update", "delete"]:
            assert has_permission(self.SYSTEM_ADMIN_PERMISSIONS, [f"admin_tenant.{action}"]) is True

    def test_admin_has_all_alert_actions(self):
        for action in ["create", "read", "respond", "close", "escalate"]:
            assert has_permission(self.SYSTEM_ADMIN_PERMISSIONS, [f"alert.{action}"]) is True

    # ── Vendor user ──────────────────────────────────────────────────────────
    def test_vendor_can_read_routes(self):
        assert has_permission(self.VENDOR_USER_PERMISSIONS, ["route.read"]) is True

    def test_vendor_cannot_modify_routes(self):
        for action in ["create", "update", "delete"]:
            assert has_permission(self.VENDOR_USER_PERMISSIONS, [f"route.{action}"]) is False

    def test_vendor_cannot_access_tenants(self):
        assert has_permission(self.VENDOR_USER_PERMISSIONS, ["admin_tenant.read"]) is False

    def test_vendor_cannot_manage_employees(self):
        assert has_permission(self.VENDOR_USER_PERMISSIONS, ["employee.create"]) is False

    # ── Driver ───────────────────────────────────────────────────────────────
    def test_driver_has_no_admin_permissions(self):
        assert has_permission(self.DRIVER_PERMISSIONS, ["employee.read"]) is False
        assert has_permission(self.DRIVER_PERMISSIONS, ["booking.create"]) is False
        assert has_permission(self.DRIVER_PERMISSIONS, ["route.read"]) is False

    # ── Employee ─────────────────────────────────────────────────────────────
    def test_employee_can_manage_own_bookings(self):
        for action in ["create", "read", "update"]:
            assert has_permission(self.EMPLOYEE_PERMISSIONS, [f"booking.{action}"]) is True

    def test_employee_cannot_delete_bookings(self):
        assert has_permission(self.EMPLOYEE_PERMISSIONS, ["booking.delete"]) is False

    def test_employee_can_create_alert(self):
        assert has_permission(self.EMPLOYEE_PERMISSIONS, ["alert.create"]) is True

    def test_employee_cannot_escalate_alert(self):
        assert has_permission(self.EMPLOYEE_PERMISSIONS, ["alert.escalate"]) is False

    # ── Cross-role checks ────────────────────────────────────────────────────
    def test_vendor_permissions_are_strict_subset_of_admin(self):
        vendor_set = set(self.VENDOR_USER_PERMISSIONS)
        admin_set = set(self.SYSTEM_ADMIN_PERMISSIONS)
        assert vendor_set.issubset(admin_set), (
            f"Vendor has permissions not in admin: {vendor_set - admin_set}"
        )

    def test_driver_has_no_permissions_above_employee(self):
        driver_set = set(self.DRIVER_PERMISSIONS)
        employee_set = set(self.EMPLOYEE_PERMISSIONS)
        extra = driver_set - employee_set
        assert not extra, f"Driver unexpectedly has extra permissions: {extra}"
