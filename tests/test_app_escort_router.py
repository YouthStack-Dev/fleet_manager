"""
Test cases for Escort App Router & Escort Login

Covers:
1. POST /auth/escort/login
   - Successful login
   - Wrong password
   - Password not set
   - Inactive account
   - Non-existent phone / wrong tenant

2. GET /escort/profile
   - Returns profile for authenticated escort
   - Blocked for non-escort token (wrong user_type)

3. GET /escort/routes
   - Returns routes assigned to escort
   - OTP hidden before dispatch, visible after dispatch
   - Status filter works correctly
   - Include-completed flag works correctly
   - Cross-tenant isolation: escort can't see other tenant's routes
   - Pagination (limit/offset)

4. GET /escort/routes/{route_id}
   - Returns full detail including stops
   - Returns 404 for route not assigned to escort
   - Shows OTP only after dispatch
   - Shows escort_boarded correctly
"""
import pytest
from datetime import date, datetime
from common_utils.auth.utils import create_access_token, hash_password


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

ESCORT_PHONE = "9871234560"
ESCORT_PASSWORD = "EscortPass123"


@pytest.fixture(scope="function")
def escort_with_password(test_db, test_tenant, test_vendor):
    """Escort with a hashed password set — can log in."""
    from app.models.escort import Escort

    escort = Escort(
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        name="Active Escort",
        phone=ESCORT_PHONE,
        email="active.escort@test.com",
        gender="FEMALE",
        is_active=True,
        is_available=True,
        password=hash_password(ESCORT_PASSWORD),
    )
    test_db.add(escort)
    test_db.commit()
    test_db.refresh(escort)
    return escort


@pytest.fixture(scope="function")
def escort_no_password(test_db, test_tenant, test_vendor):
    """Escort without any password set — cannot log in."""
    from app.models.escort import Escort

    escort = Escort(
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        name="No-Password Escort",
        phone="9871234561",
        email="nopwd.escort@test.com",
        gender="MALE",
        is_active=True,
        is_available=True,
        password=None,
    )
    test_db.add(escort)
    test_db.commit()
    test_db.refresh(escort)
    return escort


@pytest.fixture(scope="function")
def escort_inactive(test_db, test_tenant, test_vendor):
    """Inactive escort — login blocked."""
    from app.models.escort import Escort

    escort = Escort(
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        name="Inactive Escort",
        phone="9871234562",
        email="inactive.escort@test.com",
        gender="MALE",
        is_active=False,
        is_available=False,
        password=hash_password(ESCORT_PASSWORD),
    )
    test_db.add(escort)
    test_db.commit()
    test_db.refresh(escort)
    return escort


@pytest.fixture(scope="function")
def escort_token(escort_with_password, test_tenant):
    """Valid JWT token for the escort_with_password fixture."""
    token = create_access_token(
        user_id=str(escort_with_password.escort_id),
        tenant_id=test_tenant.tenant_id,
        user_type="escort",
        custom_claims={
            "vendor_id": str(escort_with_password.vendor_id),
            "permissions": [{"module": "app-escort", "action": ["read", "write"]}],
        },
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def non_escort_token(test_tenant):
    """Token with user_type='employee' — must be rejected by EscortAuth."""
    token = create_access_token(
        user_id="9999",
        tenant_id=test_tenant.tenant_id,
        user_type="employee",
        custom_claims={
            "permissions": [{"module": "app-escort", "action": ["read", "write"]}],
        },
    )
    return f"Bearer {token}"


# ─── Test Shift ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def test_shift_for_escort(test_db, test_tenant):
    from app.models.shift import Shift, ShiftLogTypeEnum
    from datetime import time

    shift = Shift(
        tenant_id=test_tenant.tenant_id,
        shift_code="ESCORT_SHIFT",
        shift_time=time(8, 0, 0),
        log_type=ShiftLogTypeEnum.IN,
        is_active=True,
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


# ─── Route assigned to escort (no OTP yet — not dispatched) ──────────────────
@pytest.fixture(scope="function")
def route_assigned_no_otp(test_db, test_tenant, test_driver, test_vehicle,
                          escort_with_password, test_shift_for_escort):
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift_for_escort.shift_id,
        route_code="RT-ESCORT-001",
        assigned_vendor_id=test_driver.vendor_id,
        assigned_driver_id=test_driver.driver_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_escort_id=escort_with_password.escort_id,
        escort_required=True,
        escort_otp=None,
        escort_boarded=False,
        status=RouteManagementStatusEnum.DRIVER_ASSIGNED,
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


# ─── Route with OTP set (dispatched) ─────────────────────────────────────────
@pytest.fixture(scope="function")
def route_dispatched_with_otp(test_db, test_tenant, test_driver, test_vehicle,
                               escort_with_password, test_shift_for_escort):
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift_for_escort.shift_id,
        route_code="RT-ESCORT-002",
        assigned_vendor_id=test_driver.vendor_id,
        assigned_driver_id=test_driver.driver_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_escort_id=escort_with_password.escort_id,
        escort_required=True,
        escort_otp=5678,
        escort_boarded=False,
        status=RouteManagementStatusEnum.ONGOING,
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


# ─── Route where escort already boarded ──────────────────────────────────────
@pytest.fixture(scope="function")
def route_escort_boarded(test_db, test_tenant, test_driver, test_vehicle,
                          escort_with_password, test_shift_for_escort):
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift_for_escort.shift_id,
        route_code="RT-ESCORT-003",
        assigned_vendor_id=test_driver.vendor_id,
        assigned_driver_id=test_driver.driver_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_escort_id=escort_with_password.escort_id,
        escort_required=True,
        escort_otp=1234,
        escort_boarded=True,
        status=RouteManagementStatusEnum.ONGOING,
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


# ─── Completed route ──────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def route_completed(test_db, test_tenant, test_driver, test_vehicle,
                     escort_with_password, test_shift_for_escort):
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift_for_escort.shift_id,
        route_code="RT-ESCORT-004",
        assigned_vendor_id=test_driver.vendor_id,
        assigned_driver_id=test_driver.driver_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_escort_id=escort_with_password.escort_id,
        escort_required=True,
        escort_otp=9999,
        escort_boarded=True,
        status=RouteManagementStatusEnum.COMPLETED,
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


# ─── Route with stops ─────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def route_with_stops(test_db, test_tenant, test_driver, test_vehicle,
                      escort_with_password, test_shift_for_escort):
    from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
    from app.models.booking import Booking, BookingStatusEnum
    from app.models.employee import Employee, GenderEnum

    # Create minimal employee
    emp = Employee(
        tenant_id=test_tenant.tenant_id,
        team_id=None,
        role_id=None,
        employee_code="ESCTEST01",
        name="Escort Test Employee",
        email="esctest01@test.com",
        password=hash_password("pass"),
        phone="9800000001",
        gender=GenderEnum.FEMALE,
        is_active=True,
    )
    test_db.add(emp)
    test_db.flush()

    # Create booking
    booking = Booking(
        tenant_id=test_tenant.tenant_id,
        employee_id=emp.employee_id,
        employee_code=emp.employee_code,
        shift_id=test_shift_for_escort.shift_id,
        booking_date=date.today(),
        pickup_location="Gate 1, Sector 5",
        pickup_latitude=12.9716,
        pickup_longitude=77.5946,
        drop_location="Office HQ",
        drop_latitude=12.9800,
        drop_longitude=77.6000,
        status=BookingStatusEnum.SCHEDULED,
    )
    test_db.add(booking)
    test_db.flush()

    # Create route
    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift_for_escort.shift_id,
        route_code="RT-ESCORT-STOPS",
        assigned_driver_id=test_driver.driver_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_escort_id=escort_with_password.escort_id,
        escort_required=True,
        escort_otp=4321,
        escort_boarded=False,
        status=RouteManagementStatusEnum.ONGOING,
    )
    test_db.add(route)
    test_db.flush()

    # Add stop
    stop = RouteManagementBooking(
        route_id=route.route_id,
        booking_id=booking.booking_id,
        order_id=1,
        estimated_pick_up_time="08:30",
    )
    test_db.add(stop)
    test_db.commit()
    test_db.refresh(route)
    return route


# ─────────────────────────────────────────────────────────────────────────────
# Test Class: Escort Login
# ─────────────────────────────────────────────────────────────────────────────

class TestEscortLogin:
    """POST /api/v1/auth/escort/login"""

    BASE = "/api/v1/auth/escort/login"

    def test_login_success(self, client, escort_with_password, test_tenant):
        """Happy path: valid phone + password + tenant_id → tokens returned."""
        resp = client.post(
            self.BASE,
            json={
                "username": ESCORT_PHONE,
                "password": ESCORT_PASSWORD,
                "tenant_id": test_tenant.tenant_id,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["token_type"] == "bearer"
        user = data["user"]
        assert user["escort_id"] == escort_with_password.escort_id
        assert user["phone"] == ESCORT_PHONE
        assert user["is_active"] is True
        assert {"module": "app-escort", "action": ["read", "write"]} in user["permissions"]

    def test_login_wrong_password(self, client, escort_with_password, test_tenant):
        """Wrong password → 401 INVALID_CREDENTIALS."""
        resp = client.post(
            self.BASE,
            json={
                "username": ESCORT_PHONE,
                "password": "WrongPassword!",
                "tenant_id": test_tenant.tenant_id,
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"

    def test_login_password_not_set(self, client, escort_no_password, test_tenant):
        """Escort exists but no password → 401 PASSWORD_NOT_SET."""
        resp = client.post(
            self.BASE,
            json={
                "username": escort_no_password.phone,
                "password": ESCORT_PASSWORD,
                "tenant_id": test_tenant.tenant_id,
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "PASSWORD_NOT_SET"

    def test_login_inactive_escort(self, client, escort_inactive, test_tenant):
        """Inactive escort account → 403 ACCOUNT_INACTIVE."""
        resp = client.post(
            self.BASE,
            json={
                "username": escort_inactive.phone,
                "password": ESCORT_PASSWORD,
                "tenant_id": test_tenant.tenant_id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "ACCOUNT_INACTIVE"

    def test_login_unknown_phone(self, client, test_tenant):
        """Phone not in DB → 401 INVALID_CREDENTIALS."""
        resp = client.post(
            self.BASE,
            json={
                "username": "0000000000",
                "password": ESCORT_PASSWORD,
                "tenant_id": test_tenant.tenant_id,
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"

    def test_login_wrong_tenant(self, client, escort_with_password, second_tenant):
        """Correct phone but wrong tenant → 401."""
        resp = client.post(
            self.BASE,
            json={
                "username": ESCORT_PHONE,
                "password": ESCORT_PASSWORD,
                "tenant_id": second_tenant.tenant_id,
            },
        )
        assert resp.status_code == 401

    def test_login_missing_body_fields(self, client):
        """Missing required fields → 422 Unprocessable Entity."""
        resp = client.post(self.BASE, json={"username": ESCORT_PHONE})
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Test Class: GET /escort/profile
# ─────────────────────────────────────────────────────────────────────────────

class TestEscortProfile:
    """GET /api/v1/escort/profile"""

    BASE = "/api/v1/escort/profile"

    def test_get_own_profile(self, client, escort_token, escort_with_password):
        """Authenticated escort can fetch their own profile."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["escort_id"] == escort_with_password.escort_id
        assert data["name"] == escort_with_password.name
        assert data["phone"] == ESCORT_PHONE
        assert data["is_active"] is True
        # Password must NOT appear in the response
        assert "password" not in data

    def test_rejected_without_token(self, client):
        """No token → 401 or 403."""
        resp = client.get(self.BASE)
        assert resp.status_code in (401, 403)

    def test_rejected_for_non_escort_user_type(self, client, non_escort_token):
        """Token with user_type='employee' (not escort) → 403."""
        resp = client.get(self.BASE, headers={"Authorization": non_escort_token})
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Test Class: GET /escort/routes
# ─────────────────────────────────────────────────────────────────────────────

class TestEscortRoutesList:
    """GET /api/v1/escort/routes"""

    BASE = "/api/v1/escort/routes"

    def test_returns_assigned_routes(self, client, escort_token,
                                     route_assigned_no_otp, route_dispatched_with_otp):
        """Escort can see routes assigned to them."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        route_ids = [r["route_id"] for r in data["routes"]]
        assert route_assigned_no_otp.route_id in route_ids
        assert route_dispatched_with_otp.route_id in route_ids

    def test_otp_hidden_before_dispatch(self, client, escort_token, route_assigned_no_otp):
        """Before dispatch (escort_otp=None), OTP fields are null/false."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        target = next(
            (r for r in routes if r["route_id"] == route_assigned_no_otp.route_id), None
        )
        assert target is not None
        assert target["otp_available"] is False
        assert target["escort_otp"] is None
        assert target["escort_status"] == "pending_dispatch"

    def test_otp_visible_after_dispatch(self, client, escort_token, route_dispatched_with_otp):
        """After dispatch, the OTP is returned so escort can tell driver."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        target = next(
            (r for r in routes if r["route_id"] == route_dispatched_with_otp.route_id), None
        )
        assert target is not None
        assert target["otp_available"] is True
        assert target["escort_otp"] == 5678
        assert target["escort_boarded"] is False
        assert target["escort_status"] == "awaiting_boarding"

    def test_boarded_status(self, client, escort_token, route_escort_boarded):
        """When escort_boarded=True, escort_status is 'boarded'."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        target = next(
            (r for r in routes if r["route_id"] == route_escort_boarded.route_id), None
        )
        assert target is not None
        assert target["escort_boarded"] is True
        assert target["escort_status"] == "boarded"

    def test_completed_excluded_by_default(self, client, escort_token, route_completed):
        """Completed routes are excluded unless include_completed=true."""
        resp = client.get(self.BASE, headers={"Authorization": escort_token})
        assert resp.status_code == 200
        route_ids = [r["route_id"] for r in resp.json()["data"]["routes"]]
        assert route_completed.route_id not in route_ids

    def test_completed_included_when_flag_set(self, client, escort_token, route_completed):
        """With ?include_completed=true, completed routes appear."""
        resp = client.get(
            f"{self.BASE}?include_completed=true",
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 200
        route_ids = [r["route_id"] for r in resp.json()["data"]["routes"]]
        assert route_completed.route_id in route_ids

    def test_status_filter_ongoing(self, client, escort_token,
                                    route_dispatched_with_otp, route_assigned_no_otp):
        """?status=ongoing returns only ONGOING routes."""
        resp = client.get(
            f"{self.BASE}?status=ongoing",
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        for r in routes:
            assert r["status"] == "Ongoing"
        # route_assigned_no_otp has status DRIVER_ASSIGNED — must not appear
        route_ids = [r["route_id"] for r in routes]
        assert route_assigned_no_otp.route_id not in route_ids

    def test_status_filter_invalid(self, client, escort_token):
        """?status=invalid → 400."""
        resp = client.get(
            f"{self.BASE}?status=invalid_status",
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "INVALID_STATUS"

    def test_pagination(self, client, escort_token,
                         route_assigned_no_otp, route_dispatched_with_otp):
        """limit/offset pagination works correctly."""
        resp1 = client.get(
            f"{self.BASE}?limit=1&offset=0",
            headers={"Authorization": escort_token},
        )
        assert resp1.status_code == 200
        assert len(resp1.json()["data"]["routes"]) == 1

        resp2 = client.get(
            f"{self.BASE}?limit=1&offset=1",
            headers={"Authorization": escort_token},
        )
        assert resp2.status_code == 200
        # Different route returned
        if resp1.json()["data"]["total"] >= 2:
            assert (
                resp1.json()["data"]["routes"][0]["route_id"]
                != resp2.json()["data"]["routes"][0]["route_id"]
            )

    def test_cross_tenant_isolation(self, client, second_tenant, second_tenant_escort, test_db):
        """Escort from tenant A cannot see routes of tenant B."""
        from common_utils.auth.utils import create_access_token
        from app.models.route_management import RouteManagement, RouteManagementStatusEnum

        # Token belonging to second_tenant_escort
        token = create_access_token(
            user_id=str(second_tenant_escort.escort_id),
            tenant_id=second_tenant.tenant_id,
            user_type="escort",
            custom_claims={
                "vendor_id": str(second_tenant_escort.vendor_id),
                "permissions": [{"module": "app-escort", "action": ["read", "write"]}],
            },
        )
        resp = client.get(
            self.BASE,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # Should see 0 routes (no routes were assigned to this escort)
        assert resp.json()["data"]["total"] == 0

    def test_no_token_returns_401_or_403(self, client):
        resp = client.get(self.BASE)
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# Test Class: GET /escort/routes/{route_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestEscortRouteDetail:
    """GET /api/v1/escort/routes/{route_id}"""

    def _url(self, route_id: int) -> str:
        return f"/api/v1/escort/routes/{route_id}"

    def test_get_route_detail(self, client, escort_token, route_dispatched_with_otp):
        """Escort can retrieve detail of their assigned route."""
        resp = client.get(
            self._url(route_dispatched_with_otp.route_id),
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["route_id"] == route_dispatched_with_otp.route_id
        assert data["escort_otp"] == 5678
        assert data["otp_available"] is True
        assert data["escort_boarded"] is False
        assert data["escort_status"] == "awaiting_boarding"
        assert "stops" in data

    def test_detail_shows_stops(self, client, escort_token, route_with_stops):
        """Route with bookings includes the ordered stop list."""
        resp = client.get(
            self._url(route_with_stops.route_id),
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data["stops"]) == 1
        stop = data["stops"][0]
        assert stop["stop_number"] == 1
        assert stop["pickup_location"] is not None

    def test_detail_otp_hidden_before_dispatch(self, client, escort_token,
                                                route_assigned_no_otp):
        """Before dispatch, OTP is null even in detail view."""
        resp = client.get(
            self._url(route_assigned_no_otp.route_id),
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["otp_available"] is False
        assert data["escort_otp"] is None
        assert data["escort_status"] == "pending_dispatch"

    def test_detail_404_for_unassigned_route(self, client, escort_token, test_db, test_tenant):
        """Returns 404 if route exists but is not assigned to this escort."""
        from app.models.route_management import RouteManagement, RouteManagementStatusEnum

        # Route with no escort assigned
        other_route = RouteManagement(
            tenant_id=test_tenant.tenant_id,
            route_code="RT-OTHER-001",
            assigned_escort_id=None,
            escort_required=False,
            escort_otp=None,
            escort_boarded=False,
            status=RouteManagementStatusEnum.PLANNED,
        )
        test_db.add(other_route)
        test_db.commit()
        test_db.refresh(other_route)

        resp = client.get(
            self._url(other_route.route_id),
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_code"] == "ROUTE_NOT_FOUND"

    def test_detail_404_for_nonexistent_route(self, client, escort_token):
        """Non-existent route_id → 404."""
        resp = client.get(
            self._url(999999),
            headers={"Authorization": escort_token},
        )
        assert resp.status_code == 404

    def test_detail_no_token(self, client, route_dispatched_with_otp):
        """No token → 401/403."""
        resp = client.get(self._url(route_dispatched_with_otp.route_id))
        assert resp.status_code in (401, 403)

    def test_detail_wrong_user_type(self, client, non_escort_token,
                                     route_dispatched_with_otp):
        """Non-escort token → 403."""
        resp = client.get(
            self._url(route_dispatched_with_otp.route_id),
            headers={"Authorization": non_escort_token},
        )
        assert resp.status_code == 403
