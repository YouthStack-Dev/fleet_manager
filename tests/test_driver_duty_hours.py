"""
tests/test_driver_duty_hours.py
---------------------------------
Feature 1 — Driver Duty Hours & Rest-Time Enforcement

Test coverage:
1. Unit tests for check_rest()
   - No prior trips → rest_gap = 24h, ok=True
   - One prior trip well within duty limit → ok=True
   - One prior trip that fills most of the 24h window → rest gap too short → ok=False
   - Multiple trips with gaps; correct longest-gap calculation
   - Trips partially outside the 24h window are clipped correctly
2. Integration tests for PUT /api/v1/route-management/assign-vehicle
   - Enforcement mode 'warn': insufficient rest → 200 + warning in response
   - Enforcement mode 'block': insufficient rest → 409
   - Well-rested driver → 200, no warning
3. Integration tests for GET /api/v1/reports/driver-duty-hours
   - Returns expected driver rows and summary
   - Per-trip rest_ok flag reflects violations
"""

import pytest
from datetime import datetime, timedelta, date

from common_utils.auth.utils import create_access_token


# ===========================================================================
# Helpers
# ===========================================================================

def _make_route(
    db,
    tenant_id: str,
    driver_id: int,
    shift_id: int,
    actual_start: datetime,
    actual_end: datetime,
    status=None,
):
    """Insert a COMPLETED RouteManagement row with actual times set."""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=tenant_id,
        shift_id=shift_id,
        route_code="DUTYTEST",
        estimated_total_time=60.0,
        status=status or RouteManagementStatusEnum.COMPLETED,
        ota_grace_minutes=5,
        assigned_driver_id=driver_id,
        actual_start_time=actual_start,
        actual_end_time=actual_end,
    )
    db.add(route)
    db.flush()
    return route


# ===========================================================================
# 1. Unit tests — check_rest()
# ===========================================================================

class TestCheckRest:

    def test_no_prior_trips_returns_full_rest(self, test_db, test_driver):
        """No trips in the 24h window → driver has had 24h rest."""
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 20, 8, 0, 0)
        result = check_rest(
            driver_id=test_driver.driver_id,
            proposed_start_dt=now,
            db=test_db,
            max_duty_minutes=600,
        )
        assert result["ok"] is True
        assert result["rest_gap_minutes"] == 24 * 60
        assert result["total_duty_minutes"] == 0

    def test_single_short_trip_still_ok(self, test_db, test_driver, test_shift):
        """One 2-hour trip well within the 10h duty limit → ok."""
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 20, 14, 0, 0)  # Proposed start
        # Trip: 08:00 – 10:00 (2 hours)
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=6),
            actual_end=now - timedelta(hours=4),
        )
        test_db.commit()

        result = check_rest(
            driver_id=test_driver.driver_id,
            proposed_start_dt=now,
            db=test_db,
            max_duty_minutes=600,
        )
        assert result["ok"] is True
        # Duty = 2h = 120 min
        assert result["total_duty_minutes"] == 120
        # Rest gap after the trip = 4h = 240 min (from trip_end to now)
        assert result["rest_gap_minutes"] >= 240

    def test_insufficient_rest_detected(self, test_db, test_driver, test_shift):
        """
        Driver worked 22 hours yesterday, leaving only 2h rest — well below
        required 14h rest (given max_duty_minutes=600 → required_rest=840).
        """
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 21, 9, 0, 0)
        # Trip: 2026-05-20 10:00 – 2026-05-21 08:00 (22 hours)
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=23),
            actual_end=now - timedelta(hours=1),
        )
        test_db.commit()

        result = check_rest(
            driver_id=test_driver.driver_id,
            proposed_start_dt=now,
            db=test_db,
            max_duty_minutes=600,  # required rest = 24*60 - 600 = 840 min
        )
        assert result["ok"] is False
        assert result["required_rest_minutes"] == 840
        # Only 1 hour rest (between trip_end and now)
        assert result["rest_gap_minutes"] <= 60

    def test_multiple_trips_largest_gap_used(self, test_db, test_driver, test_shift):
        """
        Three trips with different gaps; correct maximum gap is identified.
        """
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 20, 20, 0, 0)
        # Trip A: 00:00 – 02:00 (2h)
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=20),
            actual_end=now - timedelta(hours=18),
        )
        # Trip B: 05:00 – 07:00 (2h) → 3h gap after A
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=15),
            actual_end=now - timedelta(hours=13),
        )
        # Trip C: 16:00 – 18:00 (2h) → 9h gap after B (largest)
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=4),
            actual_end=now - timedelta(hours=2),
        )
        test_db.commit()

        result = check_rest(
            driver_id=test_driver.driver_id,
            proposed_start_dt=now,
            db=test_db,
            max_duty_minutes=600,
        )
        # Largest gap is between Trip B end (07:00) and Trip C start (16:00) = 9h = 540 min
        assert result["rest_gap_minutes"] == pytest.approx(540, abs=2)

    def test_trips_outside_window_not_counted(self, test_db, test_driver, test_shift):
        """Trip that ended >24h ago should not affect the rest check."""
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 22, 8, 0, 0)
        # Old trip: 2 days ago — should be ignored
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=49),
            actual_end=now - timedelta(hours=47),
        )
        test_db.commit()

        result = check_rest(
            driver_id=test_driver.driver_id,
            proposed_start_dt=now,
            db=test_db,
            max_duty_minutes=600,
        )
        assert result["ok"] is True
        assert result["total_duty_minutes"] == 0

    def test_required_rest_scales_with_max_duty(self, test_db, test_driver, test_shift):
        """Higher max_duty_minutes → less required rest → more likely ok."""
        from app.services.driver_duty_hours_service import check_rest

        now = datetime(2026, 5, 20, 10, 0, 0)
        # Trip: 8 hours ago – 6 hours ago (2h trip, 6h gap to now)
        _make_route(
            test_db,
            test_driver.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=8),
            actual_end=now - timedelta(hours=6),
        )
        test_db.commit()

        # max_duty=600 → required_rest=840 → 6h gap → NOT ok
        r1 = check_rest(test_driver.driver_id, now, test_db, max_duty_minutes=600)
        assert r1["required_rest_minutes"] == 840

        # max_duty=1080 → required_rest=360 → 6h gap = 360 min → just ok
        r2 = check_rest(test_driver.driver_id, now, test_db, max_duty_minutes=1080)
        assert r2["required_rest_minutes"] == 360
        assert r2["ok"] is True


# ===========================================================================
# 2. Integration tests — assign-vehicle endpoint
# ===========================================================================

@pytest.fixture(scope="function")
def assign_token(test_tenant):
    """JWT token with route_vehicle_assignment permissions."""
    token = create_access_token(
        user_id="1",
        tenant_id=test_tenant.tenant_id,
        user_type="admin",
        custom_claims={
            "permissions": [
                "route_vehicle_assignment.update",
                "route_vehicle_assignment.create",
                "route_vehicle_assignment.read",
                "route_vehicle_assignment.delete",
            ],
        },
    )
    return f"Bearer {token}"


def _make_assignable_route(db, tenant_id, vendor_id, shift_id):
    """Create a VENDOR_ASSIGNED route ready for vehicle assignment."""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=tenant_id,
        shift_id=shift_id,
        route_code="ASSIGNTEST",
        estimated_total_time=60.0,
        status=RouteManagementStatusEnum.VENDOR_ASSIGNED,
        ota_grace_minutes=5,
        assigned_vendor_id=vendor_id,
    )
    db.add(route)
    db.flush()
    db.commit()
    db.refresh(route)
    return route


class TestAssignVehicleDutyHours:

    def test_well_rested_driver_assigned_without_warning(
        self, client, test_db, test_tenant, test_shift, test_driver, test_vehicle, assign_token
    ):
        """No prior trips → 200 OK, no warnings."""
        route = _make_assignable_route(
            test_db, test_tenant.tenant_id, test_vehicle.vendor_id, test_shift.shift_id
        )
        resp = client.put(
            "/api/v1/routes/assign-vehicle",
            params={"route_id": route.route_id, "vehicle_id": test_vehicle.vehicle_id},
            headers={"Authorization": assign_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data.get("warnings", []) == []

    def test_warn_mode_insufficient_rest_returns_200_with_warning(
        self, client, test_db, test_tenant, test_shift, test_driver, test_vehicle, assign_token
    ):
        """
        Enforcement = 'warn' (default).
        Driver has only 1h rest → 200 with driver_rest_insufficient warning.
        """
        # Exhaust driver rest: 22-hour trip ending 1h ago
        now = datetime.utcnow()
        _make_route(
            test_db,
            test_tenant.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=23),
            actual_end=now - timedelta(hours=1),
        )
        test_db.commit()

        route = _make_assignable_route(
            test_db, test_tenant.tenant_id, test_vehicle.vendor_id, test_shift.shift_id
        )
        resp = client.put(
            "/api/v1/routes/assign-vehicle",
            params={"route_id": route.route_id, "vehicle_id": test_vehicle.vehicle_id},
            headers={"Authorization": assign_token},
        )
        assert resp.status_code == 200
        warnings = resp.json()["data"].get("warnings", [])
        assert len(warnings) >= 1
        assert any("driver_rest_insufficient" in w for w in warnings)

    def test_block_mode_insufficient_rest_returns_409(
        self, client, test_db, test_tenant, test_shift, test_driver, test_vehicle, assign_token
    ):
        """
        Enforcement = 'block'.
        Driver has only 1h rest → 409 DRIVER_INSUFFICIENT_REST.
        """
        # Set enforcement to 'block' — create TenantConfig row if absent
        from app.models.tenant_config import TenantConfig
        cfg = test_db.query(TenantConfig).filter(
            TenantConfig.tenant_id == test_tenant.tenant_id
        ).first()
        if cfg is None:
            cfg = TenantConfig(tenant_id=test_tenant.tenant_id)
            test_db.add(cfg)
            test_db.flush()
        cfg.driver_rest_enforcement = "block"
        cfg.driver_max_duty_minutes = 600
        test_db.commit()

        now = datetime.utcnow()
        _make_route(
            test_db,
            test_tenant.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=23),
            actual_end=now - timedelta(hours=1),
        )
        test_db.commit()

        route = _make_assignable_route(
            test_db, test_tenant.tenant_id, test_vehicle.vendor_id, test_shift.shift_id
        )
        resp = client.put(
            "/api/v1/routes/assign-vehicle",
            params={"route_id": route.route_id, "vehicle_id": test_vehicle.vehicle_id},
            headers={"Authorization": assign_token},
        )
        assert resp.status_code == 409
        body = resp.json()
        error_data = body.get("detail", body)
        assert error_data["error_code"] == "DRIVER_INSUFFICIENT_REST"


# ===========================================================================
# 3. Integration tests — GET /reports/driver-duty-hours
# ===========================================================================

@pytest.fixture(scope="function")
def report_token(test_tenant):
    """JWT token with report.read permission."""
    token = create_access_token(
        user_id="1",
        tenant_id=test_tenant.tenant_id,
        user_type="admin",
        custom_claims={"permissions": ["report.read"]},
    )
    return f"Bearer {token}"


class TestDriverDutyHoursReport:

    def test_empty_date_range_returns_empty(
        self, client, test_tenant, report_token
    ):
        """Date range with no completed routes returns empty driver list."""
        resp = client.get(
            "/api/v1/reports/driver-duty-hours",
            params={"start_date": "2020-01-01", "end_date": "2020-01-07"},
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["drivers"] == []
        assert data["summary"]["total_drivers"] == 0

    def test_report_includes_driver_and_route_data(
        self, client, test_db, test_tenant, test_shift, test_driver, report_token
    ):
        """Completed routes are aggregated per driver."""
        now = datetime(2026, 5, 20, 12, 0, 0)
        _make_route(
            test_db,
            test_tenant.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=now - timedelta(hours=3),
            actual_end=now - timedelta(hours=1),
        )
        test_db.commit()

        resp = client.get(
            "/api/v1/reports/driver-duty-hours",
            params={"start_date": "2026-05-20", "end_date": "2026-05-20"},
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_drivers"] >= 1

        driver_row = next(
            (d for d in data["drivers"] if d["driver_id"] == test_driver.driver_id),
            None,
        )
        assert driver_row is not None
        assert driver_row["total_routes"] >= 1
        assert driver_row["total_duty_minutes"] == pytest.approx(120, abs=2)

    def test_report_flags_rest_violation(
        self, client, test_db, test_tenant, test_shift, test_driver, report_token
    ):
        """
        A driver with only 1h rest before a trip should have rest_violations > 0.
        """
        base = datetime(2026, 5, 19, 10, 0, 0)
        # Trip 1: 22h trip to exhaust rest
        _make_route(
            test_db,
            test_tenant.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=base,
            actual_end=base + timedelta(hours=22),
        )
        # Trip 2: starts 1h after Trip 1 ends (only 1h rest gap)
        trip2_start = base + timedelta(hours=23)
        _make_route(
            test_db,
            test_tenant.tenant_id,
            test_driver.driver_id,
            test_shift.shift_id,
            actual_start=trip2_start,
            actual_end=trip2_start + timedelta(hours=1),
        )
        test_db.commit()

        resp = client.get(
            "/api/v1/reports/driver-duty-hours",
            params={"start_date": "2026-05-19", "end_date": "2026-05-20"},
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        driver_row = next(
            (d for d in data["drivers"] if d["driver_id"] == test_driver.driver_id),
            None,
        )
        assert driver_row is not None
        # Trip 2 should be flagged as a rest violation
        assert driver_row["rest_violations"] >= 1
        trip2_row = next(
            (r for r in driver_row["routes"] if not r["rest_ok"]),
            None,
        )
        assert trip2_row is not None

    def test_report_invalid_date_range_returns_400(
        self, client, test_tenant, report_token
    ):
        """start_date after end_date → 400."""
        resp = client.get(
            "/api/v1/reports/driver-duty-hours",
            params={"start_date": "2026-05-25", "end_date": "2026-05-20"},
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 400
