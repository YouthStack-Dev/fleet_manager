"""
tests/test_dark_hour_boarding.py
---------------------------------
Feature 12 — Female Employee Dark-Hour Boarding Block

Test coverage:
1. Unit tests for check_dark_hour_boarding()  (12 tests)
   - mode='off' → always allow regardless of gender / time / escort
   - male employee → always allow
   - escort_required_for_women=False → always allow
   - window not configured (times are None) → always allow
   - outside the dark window → allow
   - inside overnight window (22:00-06:00)
   - inside same-day window  (20:00-23:00)
   - inside window + escort boarded → allow
   - inside window + no escort + mode='warn' → ok=True, warning
   - inside window + no escort + mode='block' → ok=False, error_code
   - boundary: exactly at window start → inside
   - boundary: exactly at window end → inside

2. Integration tests for POST /driver/trip/start  (6 tests)
   - mode='off': female, no escort, dark hours → 200 (feature off)
   - mode='warn': female, no escort, dark hours → 200 + warning in response
   - mode='block': female, no escort, dark hours → 423
   - mode='block': female, escort boarded, dark hours → 200 (escort present)
   - mode='block': male employee, dark hours → 200 (not female)
   - mode='block': outside dark window → 200
"""

import pytest
from datetime import time, date

from common_utils.auth.utils import create_access_token


# ===========================================================================
# 1. Unit tests — check_dark_hour_boarding()
# ===========================================================================

class _MockCfg:
    """Minimal TenantConfig stand-in for unit tests."""

    def __init__(
        self,
        dark_hour_boarding_mode="off",
        escort_required_for_women=True,
        escort_required_start_time=None,
        escort_required_end_time=None,
    ):
        self.dark_hour_boarding_mode = dark_hour_boarding_mode
        self.escort_required_for_women = escort_required_for_women
        self.escort_required_start_time = escort_required_start_time
        self.escort_required_end_time = escort_required_end_time


class TestCheckDarkHourBoarding:

    # ── feature-off gate ────────────────────────────────────────────────────

    def test_mode_off_always_allows(self):
        """mode='off' → ok=True even for female inside dark window, no escort."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="off",
            escort_required_for_women=True,
            escort_required_start_time=time(0, 0),
            escort_required_end_time=time(23, 59),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(3, 0),
        )
        assert result["ok"] is True
        assert result["warnings"] == []
        assert result["error_code"] is None

    # ── gender gate ─────────────────────────────────────────────────────────

    def test_male_employee_always_allowed(self):
        """Male employee → ok=True even in block mode inside dark window."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Male",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is True

    def test_none_gender_allowed(self):
        """gender=None → treated as unknown → allow through."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender=None,
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is True

    # ── escort-required gate ─────────────────────────────────────────────────

    def test_escort_not_required_for_women_always_allows(self):
        """escort_required_for_women=False → allow even in block mode."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=False,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is True

    # ── window-not-configured gate ───────────────────────────────────────────

    def test_window_not_configured_allows(self):
        """Both times None → window not set → allow through."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=None,
            escort_required_end_time=None,
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is True

    def test_window_partially_configured_allows(self):
        """Only start time set, end is None → not fully configured → allow."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=None,
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(23, 0),
        )
        assert result["ok"] is True

    # ── window detection ─────────────────────────────────────────────────────

    def test_outside_overnight_window_allowed(self):
        """22:00-06:00 window, now=10:00 → outside → allow."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(10, 0),
        )
        assert result["ok"] is True

    def test_inside_overnight_window_past_midnight(self):
        """22:00-06:00 window, now=02:00 → inside (post-midnight) → block."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is False
        assert result["error_code"] == "DARK_HOUR_NO_ESCORT"

    def test_inside_overnight_window_pre_midnight(self):
        """22:00-06:00 window, now=23:30 → inside (pre-midnight) → block."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(23, 30),
        )
        assert result["ok"] is False

    def test_inside_same_day_window(self):
        """20:00-23:00 window, now=21:30 → inside → block."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(20, 0),
            escort_required_end_time=time(23, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(21, 30),
        )
        assert result["ok"] is False

    # ── escort present → safe ────────────────────────────────────────────────

    def test_escort_boarded_in_dark_window_allows(self):
        """Inside dark window, but escort is present and boarded → allow."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="block",
            escort_required_for_women=True,
            escort_required_start_time=time(22, 0),
            escort_required_end_time=time(6, 0),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=True,
            cfg=cfg,
            now_time=time(2, 0),
        )
        assert result["ok"] is True
        assert result["warnings"] == []

    # ── warn mode ────────────────────────────────────────────────────────────

    def test_warn_mode_returns_warning_not_block(self):
        """Warn mode: ok=True but warnings contains 'dark_hour_no_escort'."""
        from app.services.dark_hour_boarding_service import check_dark_hour_boarding

        cfg = _MockCfg(
            dark_hour_boarding_mode="warn",
            escort_required_for_women=True,
            escort_required_start_time=time(0, 0),
            escort_required_end_time=time(23, 59),
        )
        result = check_dark_hour_boarding(
            gender="Female",
            escort_present_and_boarded=False,
            cfg=cfg,
            now_time=time(3, 0),
        )
        assert result["ok"] is True
        assert "dark_hour_no_escort" in result["warnings"]
        assert result["error_code"] is None


# ===========================================================================
# 2. Integration tests — POST /driver/trip/start
# ===========================================================================
#
# Strategy to avoid time-mocking:
#   - Set escort_required_start_time = time(0,0) and
#     escort_required_end_time = time(23,59) so the window covers all 24h.
#   - Set pickup_latitude=None to bypass validate_driver_location.
#   - Set order_id=1 to bypass sequential gate.
#   - Set boarding_otp=None to bypass OTP check.
#
# ===========================================================================

@pytest.fixture(scope="function")
def driver_trip_token(test_driver, test_tenant):
    """JWT for test_driver with driver_app permissions."""
    token = create_access_token(
        user_id=str(test_driver.driver_id),
        tenant_id=test_tenant.tenant_id,
        user_type="driver",
        custom_claims={
            "email": test_driver.email,
            "permissions": ["driver_app.read", "driver_app.update"],
        },
    )
    return f"Bearer {token}"


def _make_ongoing_route(db, tenant_id, shift_id, driver_id, vehicle_id, vendor_id,
                         escort_id=None, escort_boarded=False):
    """Create an ONGOING route assigned to the given driver."""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=tenant_id,
        shift_id=shift_id,
        route_code="DH_ROUTE",
        estimated_total_time=30.0,
        status=RouteManagementStatusEnum.ONGOING,
        assigned_vendor_id=vendor_id,
        assigned_vehicle_id=vehicle_id,
        assigned_driver_id=driver_id,
        assigned_escort_id=escort_id,
        escort_boarded=escort_boarded,
        escort_required=escort_id is not None,
    )
    db.add(route)
    db.flush()
    db.refresh(route)
    return route


def _make_female_booking(db, tenant_id, shift_id, route_id, employee_id,
                          employee_code, team_id):
    """Create a SCHEDULED booking for a female employee, linked to the route."""
    from app.models.booking import Booking, BookingStatusEnum
    from app.models.route_management import RouteManagementBooking

    booking = Booking(
        tenant_id=tenant_id,
        employee_id=employee_id,
        employee_code=employee_code,
        shift_id=shift_id,
        team_id=team_id,
        booking_date=date.today(),
        status=BookingStatusEnum.SCHEDULED,
        pickup_latitude=None,    # bypass validate_driver_location
        pickup_longitude=None,
        pickup_location="Test Office",
        drop_latitude=12.9716,
        drop_longitude=77.5946,
        drop_location="Test Home",
        boarding_otp=None,       # bypass OTP check
        deboarding_otp="5678",
    )
    db.add(booking)
    db.flush()

    rb = RouteManagementBooking(
        route_id=route_id,
        booking_id=booking.booking_id,
        order_id=1,              # bypass sequential gate
        estimated_pick_up_time="22:00",
        estimated_distance=5.0,
    )
    db.add(rb)
    db.commit()
    db.refresh(booking)
    return booking


def _set_dark_hour_config(db, tenant_id, mode):
    """Upsert TenantConfig for dark-hour testing (all-day window)."""
    from app.models.tenant_config import TenantConfig

    cfg = db.query(TenantConfig).filter(
        TenantConfig.tenant_id == tenant_id
    ).first()
    if cfg is None:
        cfg = TenantConfig(tenant_id=tenant_id)
        db.add(cfg)
        db.flush()

    cfg.dark_hour_boarding_mode = mode
    cfg.escort_required_for_women = True
    cfg.escort_required_start_time = time(0, 0)    # all-day window
    cfg.escort_required_end_time = time(23, 59)
    db.commit()
    return cfg


class TestDarkHourBoardingIntegration:

    def test_mode_off_female_no_escort_allowed(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, driver_trip_token
    ):
        """Feature off → female + dark hours + no escort → 200 OK."""
        from app.models.employee import Employee
        from app.models.iam.role import Role

        # Female employee
        female_emp = Employee(
            employee_id=500,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Female Worker",
            employee_code="FW500",
            email="fw500@test.com",
            phone="5000000000",
            password="hashed",
            gender="Female",
            is_active=True,
        )
        test_db.add(female_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
        )
        booking = _make_female_booking(
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, female_emp.employee_id,
            female_emp.employee_code, female_emp.team_id,
        )
        _set_dark_hour_config(test_db, test_tenant.tenant_id, "off")

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data.get("warnings", []) == []

    def test_mode_warn_female_no_escort_returns_200_with_warning(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, driver_trip_token
    ):
        """Warn mode → female + no escort + all-day window → 200 + warning."""
        from app.models.employee import Employee

        female_emp = Employee(
            employee_id=501,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Female Worker",
            employee_code="FW501",
            email="fw501@test.com",
            phone="5010000000",
            password="hashed",
            gender="Female",
            is_active=True,
        )
        test_db.add(female_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
        )
        booking = _make_female_booking(
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, female_emp.employee_id,
            female_emp.employee_code, female_emp.team_id,
        )
        _set_dark_hour_config(test_db, test_tenant.tenant_id, "warn")

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 200, resp.text
        warnings = resp.json()["data"].get("warnings", [])
        assert "dark_hour_no_escort" in warnings

    def test_mode_block_female_no_escort_returns_423(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, driver_trip_token
    ):
        """Block mode → female + no escort + all-day window → 423 Locked."""
        from app.models.employee import Employee

        female_emp = Employee(
            employee_id=502,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Female Worker",
            employee_code="FW502",
            email="fw502@test.com",
            phone="5020000000",
            password="hashed",
            gender="Female",
            is_active=True,
        )
        test_db.add(female_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
        )
        booking = _make_female_booking(
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, female_emp.employee_id,
            female_emp.employee_code, female_emp.team_id,
        )
        _set_dark_hour_config(test_db, test_tenant.tenant_id, "block")

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 423, resp.text
        body = resp.json()
        detail = body.get("detail", body)
        assert detail.get("error_code") == "DARK_HOUR_NO_ESCORT"

    def test_mode_block_female_escort_boarded_returns_200(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, test_escort, driver_trip_token
    ):
        """Block mode + escort boarded → female safe → 200 OK (not blocked)."""
        from app.models.employee import Employee

        female_emp = Employee(
            employee_id=503,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Female Worker",
            employee_code="FW503",
            email="fw503@test.com",
            phone="5030000000",
            password="hashed",
            gender="Female",
            is_active=True,
        )
        test_db.add(female_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
            escort_id=test_escort.escort_id,
            escort_boarded=True,         # escort IS boarded
        )
        booking = _make_female_booking(
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, female_emp.employee_id,
            female_emp.employee_code, female_emp.team_id,
        )
        _set_dark_hour_config(test_db, test_tenant.tenant_id, "block")

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 200, resp.text
        warnings = resp.json()["data"].get("warnings", [])
        assert warnings == []

    def test_mode_block_male_employee_returns_200(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, driver_trip_token
    ):
        """Block mode + male employee → not subject to rule → 200 OK."""
        from app.models.employee import Employee

        male_emp = Employee(
            employee_id=504,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Male Worker",
            employee_code="MW504",
            email="mw504@test.com",
            phone="5040000000",
            password="hashed",
            gender="Male",
            is_active=True,
        )
        test_db.add(male_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
        )
        booking = _make_female_booking(  # reuse helper but employee is male
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, male_emp.employee_id,
            male_emp.employee_code, male_emp.team_id,
        )
        _set_dark_hour_config(test_db, test_tenant.tenant_id, "block")

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 200, resp.text

    def test_mode_block_window_not_configured_returns_200(
        self, client, test_db, test_tenant, test_shift, test_driver,
        test_vehicle, test_vendor, driver_trip_token
    ):
        """Block mode but dark window times are None → feature skip → 200 OK."""
        from app.models.employee import Employee
        from app.models.tenant_config import TenantConfig

        female_emp = Employee(
            employee_id=505,
            tenant_id=test_tenant.tenant_id,
            team_id=None,
            role_id=3,
            name="Female Worker",
            employee_code="FW505",
            email="fw505@test.com",
            phone="5050000000",
            password="hashed",
            gender="Female",
            is_active=True,
        )
        test_db.add(female_emp)
        test_db.flush()

        route = _make_ongoing_route(
            test_db,
            test_tenant.tenant_id,
            test_shift.shift_id,
            test_driver.driver_id,
            test_vehicle.vehicle_id,
            test_vendor.vendor_id,
        )
        booking = _make_female_booking(
            test_db, test_tenant.tenant_id, test_shift.shift_id,
            route.route_id, female_emp.employee_id,
            female_emp.employee_code, female_emp.team_id,
        )

        # Set mode=block but leave times as None
        cfg = test_db.query(TenantConfig).filter(
            TenantConfig.tenant_id == test_tenant.tenant_id
        ).first()
        if cfg is None:
            cfg = TenantConfig(tenant_id=test_tenant.tenant_id)
            test_db.add(cfg)
            test_db.flush()
        cfg.dark_hour_boarding_mode = "block"
        cfg.escort_required_for_women = True
        cfg.escort_required_start_time = None   # not configured
        cfg.escort_required_end_time = None
        test_db.commit()

        resp = client.post(
            f"/api/v1/driver/trip/start"
            f"?route_id={route.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&current_latitude=0&current_longitude=0",
            headers={"Authorization": driver_trip_token},
        )
        assert resp.status_code == 200, resp.text
