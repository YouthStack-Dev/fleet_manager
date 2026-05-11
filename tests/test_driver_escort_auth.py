"""
Tests for untested auth routes:
  POST /api/v1/auth/escort/login
  POST /api/v1/auth/driver/select-tenant
  POST /api/v1/auth/driver/refresh

Each class follows the 5-scenario pattern:
  ✅ Success
  ❌ Invalid input / wrong credentials
  🔒 No / expired credentials
  🚫 Inactive / forbidden account
  💥 Edge cases
"""

import sys
import importlib

import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app.models.escort import Escort
from app.models.driver import Driver, GenderEnum as DriverGenderEnum, VerificationStatusEnum
from app.models.vendor import Vendor
from app.models.tenant import Tenant
from common_utils.auth.utils import hash_password, create_access_token

# Resolve the real auth_router module, bypassing the app.routes.__init__ alias
# (app/routes/__init__.py does `from app.routes.auth_router import router as auth_router`,
# so getattr(app.routes, "auth_router") returns the APIRouter object, not the module.
# sys.modules always holds the real module after import_module.)
importlib.import_module("app.routes.auth_router")
_auth_module = sys.modules["app.routes.auth_router"]

AUTH_BASE = "/api/v1/auth"


# ─────────────────────────────────────────────────────────────────────────────
# Shared DB-seed fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def esc_tenant(test_db):
    existing = test_db.query(Tenant).filter_by(tenant_id="ESCTENANT").first()
    if existing:
        return existing
    t = Tenant(tenant_id="ESCTENANT", name="Escort Test Tenant", is_active=True)
    test_db.add(t)
    test_db.flush()
    return t


@pytest.fixture
def esc_vendor(test_db, esc_tenant):
    v = Vendor(
        tenant_id="ESCTENANT",
        name="Escort Vendor Co",
        vendor_code="ESCVND01",
        is_active=True,
    )
    test_db.add(v)
    test_db.flush()
    return v


@pytest.fixture
def active_escort(test_db, esc_tenant, esc_vendor):
    e = Escort(
        tenant_id="ESCTENANT",
        vendor_id=esc_vendor.vendor_id,
        name="Test Escort",
        phone="9990000001",
        email="escort@test.com",
        is_active=True,
        password=hash_password("EscortPass1!"),
    )
    test_db.add(e)
    test_db.flush()
    return e


@pytest.fixture
def inactive_escort(test_db, esc_tenant, esc_vendor):
    e = Escort(
        tenant_id="ESCTENANT",
        vendor_id=esc_vendor.vendor_id,
        name="Inactive Escort",
        phone="9990000002",
        email="inactive_escort@test.com",
        is_active=False,
        password=hash_password("EscortPass1!"),
    )
    test_db.add(e)
    test_db.flush()
    return e


@pytest.fixture
def no_password_escort(test_db, esc_tenant, esc_vendor):
    e = Escort(
        tenant_id="ESCTENANT",
        vendor_id=esc_vendor.vendor_id,
        name="No Password Escort",
        phone="9990000003",
        email="nopwd_escort@test.com",
        is_active=True,
        password=None,
    )
    test_db.add(e)
    test_db.flush()
    return e


@pytest.fixture
def drv_tenant(test_db):
    existing = test_db.query(Tenant).filter_by(tenant_id="DRVTENANT").first()
    if existing:
        return existing
    t = Tenant(
        tenant_id="DRVTENANT",
        name="Driver Auth Tenant",
        is_active=True,
        address="1 Driver Lane, Test City",
        longitude=77.5946,
        latitude=12.9716,
    )
    test_db.add(t)
    test_db.flush()
    return t


@pytest.fixture
def drv_vendor(test_db, drv_tenant):
    v = Vendor(
        tenant_id="DRVTENANT",
        name="Driver Vendor Co",
        vendor_code="DRVVND01",
        is_active=True,
    )
    test_db.add(v)
    test_db.flush()
    return v


@pytest.fixture
def auth_driver(test_db, drv_tenant, drv_vendor):
    d = Driver(
        tenant_id="DRVTENANT",
        vendor_id=drv_vendor.vendor_id,
        role_id=2,
        name="Auth Test Driver",
        code="ADRVCODE1",
        email="authdrv@test.com",
        password=hash_password("DriverPass1!"),
        phone="8880000001",
        license_number="DL_AUTH_001",
        gender=DriverGenderEnum.MALE,
        date_of_birth=date(1990, 1, 1),
        date_of_joining=date(2023, 1, 1),
        bg_verify_status=VerificationStatusEnum.APPROVED,
        is_active=True,
        active_android_id="DEVICE_ABC_001",
    )
    test_db.add(d)
    test_db.flush()
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. POST /auth/escort/login
# ─────────────────────────────────────────────────────────────────────────────

class TestEscortLogin:
    def test_escort_login_success_email(self, client, active_escort):
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "escort@test.com",
                "password": "EscortPass1!",
                "tenant_id": "ESCTENANT",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "access_token" in body["data"]
        assert body["data"].get("token_type") == "bearer"

    def test_escort_login_success_phone(self, client, active_escort):
        """LoginRequest.username is EmailStr — phone numbers are rejected with 422."""
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "9990000001",
                "password": "EscortPass1!",
                "tenant_id": "ESCTENANT",
            },
        )
        assert r.status_code == 422

    def test_escort_login_wrong_password(self, client, active_escort):
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "escort@test.com",
                "password": "WrongPassword!",
                "tenant_id": "ESCTENANT",
            },
        )
        assert r.status_code == 401

    def test_escort_login_nonexistent_user(self, client):
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "nobody@example.com",
                "password": "SomePass1!",
                "tenant_id": "NONEXISTENT",
            },
        )
        assert r.status_code == 401

    def test_escort_login_inactive_account(self, client, inactive_escort):
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "inactive_escort@test.com",
                "password": "EscortPass1!",
                "tenant_id": "ESCTENANT",
            },
        )
        assert r.status_code == 403

    def test_escort_login_no_password_set(self, client, no_password_escort):
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "nopwd_escort@test.com",
                "password": "anything",
                "tenant_id": "ESCTENANT",
            },
        )
        assert r.status_code == 401

    def test_escort_login_missing_fields(self, client):
        r = client.post(f"{AUTH_BASE}/escort/login", json={"username": "escort@test.com"})
        assert r.status_code == 422

    def test_escort_login_wrong_tenant(self, client, active_escort):
        """Correct email but wrong tenant_id → not found."""
        r = client.post(
            f"{AUTH_BASE}/escort/login",
            json={
                "username": "escort@test.com",
                "password": "EscortPass1!",
                "tenant_id": "WRONG_TENANT",
            },
        )
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 2. POST /auth/driver/select-tenant
# The route uses get_drivers_by_license_with_cache and
# get_driver_by_android_id_with_cache — both must be mocked.
# ─────────────────────────────────────────────────────────────────────────────

class TestDriverSelectTenant:
    """Tests for POST /api/v1/auth/driver/select-tenant"""

    def _driver_cache_entry(self, driver):
        """Build the dict structure the cache returns for a driver."""
        return {
            "driver_id": driver.driver_id,
            "name": driver.name,
            "license_number": driver.license_number,
            "vendor_id": driver.vendor_id,
            "tenant_id": driver.tenant_id,
            "active_android_id": driver.active_android_id,
        }

    def test_select_tenant_success(self, client, auth_driver, drv_vendor):
        cache_entry = self._driver_cache_entry(auth_driver)
        with (
            patch.object(
                _auth_module,
                "get_drivers_by_license_with_cache",
                return_value=[cache_entry],
            ),
            patch.object(
                _auth_module,
                "get_driver_by_android_id_with_cache",
                return_value=cache_entry,
            ),
        ):
            r = client.post(
                f"{AUTH_BASE}/driver/select-tenant",
                json={
                    "dl_number": "DL_AUTH_001",
                    "android_id": "DEVICE_ABC_001",
                    "tenant_id": "DRVTENANT",
                    "vendor_id": drv_vendor.vendor_id,
                },
            )
        assert r.status_code == 200
        assert "access_token" in r.json()["data"]

    def test_select_tenant_driver_not_found_for_vendor(self, client, drv_vendor):
        """Cache returns no driver matching the vendor → 404."""
        with (
            patch.object(
                _auth_module,
                "get_drivers_by_license_with_cache",
                return_value=[],
            ),
            patch.object(
                _auth_module,
                "get_driver_by_android_id_with_cache",
                return_value=None,
            ),
        ):
            r = client.post(
                f"{AUTH_BASE}/driver/select-tenant",
                json={
                    "dl_number": "NONEXISTENT_DL",
                    "android_id": "DEVICE_XYZ",
                    "tenant_id": "DRVTENANT",
                    "vendor_id": drv_vendor.vendor_id,
                },
            )
        assert r.status_code == 404

    def test_select_tenant_device_not_authorized(self, client, auth_driver, drv_vendor):
        """active_android_id doesn't match → 403."""
        cache_entry = {**self._driver_cache_entry(auth_driver), "active_android_id": "OTHER_DEVICE"}
        with (
            patch.object(
                _auth_module,
                "get_drivers_by_license_with_cache",
                return_value=[cache_entry],
            ),
            patch.object(
                _auth_module,
                "get_driver_by_android_id_with_cache",
                return_value=None,
            ),
        ):
            r = client.post(
                f"{AUTH_BASE}/driver/select-tenant",
                json={
                    "dl_number": "DL_AUTH_001",
                    "android_id": "DEVICE_ABC_001",
                    "tenant_id": "DRVTENANT",
                    "vendor_id": drv_vendor.vendor_id,
                },
            )
        assert r.status_code == 403

    def test_select_tenant_tenant_mismatch(self, client, auth_driver, drv_vendor):
        """Driver's tenant differs from requested tenant → 403."""
        cache_entry = {**self._driver_cache_entry(auth_driver), "tenant_id": "OTHER_TENANT"}
        with (
            patch.object(
                _auth_module,
                "get_drivers_by_license_with_cache",
                return_value=[cache_entry],
            ),
            patch.object(
                _auth_module,
                "get_driver_by_android_id_with_cache",
                return_value=cache_entry,
            ),
        ):
            r = client.post(
                f"{AUTH_BASE}/driver/select-tenant",
                json={
                    "dl_number": "DL_AUTH_001",
                    "android_id": "DEVICE_ABC_001",
                    "tenant_id": "DRVTENANT",
                    "vendor_id": drv_vendor.vendor_id,
                },
            )
        assert r.status_code == 403

    def test_select_tenant_missing_fields(self, client):
        r = client.post(
            f"{AUTH_BASE}/driver/select-tenant",
            json={"dl_number": "DL_AUTH_001"},
        )
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST /auth/driver/refresh
# ─────────────────────────────────────────────────────────────────────────────

class TestDriverRefreshToken:
    """Tests for POST /api/v1/auth/driver/refresh"""

    @staticmethod
    def _make_driver_token(driver_id: int) -> str:
        return create_access_token(
            user_id=str(driver_id),
            user_type="driver",
            tenant_id="DRVTENANT",
        )

    def _mock_oauth_no_redis(self):
        """Return a mock Oauth2AsAccessor where use_redis is False (skips device check)."""
        m = MagicMock()
        m.use_redis = False
        return m

    def test_refresh_success(self, client, auth_driver):
        token = self._make_driver_token(auth_driver.driver_id)
        with patch.object(_auth_module, "Oauth2AsAccessor", return_value=self._mock_oauth_no_redis()):
            r = client.post(
                f"{AUTH_BASE}/driver/refresh",
                json={"refresh_token": token},
            )
        assert r.status_code == 200
        assert "access_token" in r.json()["data"]

    def test_refresh_nonexistent_driver(self, client):
        """Token references a driver_id that doesn't exist → 401."""
        token = self._make_driver_token(999999)
        with patch.object(_auth_module, "Oauth2AsAccessor", return_value=self._mock_oauth_no_redis()):
            r = client.post(
                f"{AUTH_BASE}/driver/refresh",
                json={"refresh_token": token},
            )
        assert r.status_code == 401

    def test_refresh_wrong_user_type(self, client, auth_driver):
        """Token carries user_type='employee' → invalid token type → 401."""
        token = create_access_token(
            user_id=str(auth_driver.driver_id),
            user_type="employee",
            tenant_id="DRVTENANT",
        )
        with patch.object(_auth_module, "Oauth2AsAccessor", return_value=self._mock_oauth_no_redis()):
            r = client.post(
                f"{AUTH_BASE}/driver/refresh",
                json={"refresh_token": token},
            )
        assert r.status_code == 401

    def test_refresh_invalid_token_string(self, client):
        r = client.post(
            f"{AUTH_BASE}/driver/refresh",
            json={"refresh_token": "this.is.not.a.jwt"},
        )
        assert r.status_code in (401, 422)

    def test_refresh_missing_body(self, client):
        r = client.post(f"{AUTH_BASE}/driver/refresh", json={})
        assert r.status_code == 422
