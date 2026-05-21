"""
tests/test_delay_classification.py
------------------------------------
Feature 4 — OTA/OTD Delay Classification

Tests cover:
1. Unit tests for DelayClassificationService.classify_delay_category
   - ON_TIME / EARLY routes return NONE
   - LATE with first-stop driver delay returns DRIVER_DELAY
   - LATE with mid-route employee delay returns EMPLOYEE_DELAY
   - LATE with no stop data defaults to TRAFFIC_DELAY
   - LATE with all stops on-time defaults to TRAFFIC_DELAY
2. Unit tests for tag_trip_delay integration with classification
   - delay_category is written to RouteDelayEvent
3. Integration tests for GET /reports/delays
   - delay_category field present in response rows
   - delay_category filter works
4. Integration tests for GET /reports/delays/{route_id}
   - event objects include delay_category
"""

import pytest
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session

from common_utils.auth.utils import create_access_token


# ---------------------------------------------------------------------------
# Helper / fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def report_token(test_tenant):
    """JWT token with report.read permission."""
    token = create_access_token(
        user_id="1",
        tenant_id=test_tenant.tenant_id,
        user_type="admin",
        custom_claims={
            "permissions": ["report.read"],
        },
    )
    return f"Bearer {token}"


def _make_route(db, tenant_id, shift_id=20, estimated_total_time=60.0):
    """Create a minimal RouteManagement row and return it."""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    route = RouteManagement(
        tenant_id=tenant_id,
        shift_id=shift_id,
        route_code="TCLASSIFY001",
        estimated_total_time=estimated_total_time,
        status=RouteManagementStatusEnum.ONGOING,
        ota_grace_minutes=5,
    )
    db.add(route)
    db.flush()
    return route


def _add_stop(db, route_id, order_id, est_time, actual_time):
    """Add a RouteManagementBooking stop with pickup time strings."""
    from app.models.route_management import RouteManagementBooking
    from app.models.booking import Booking, BookingStatusEnum

    # Minimal booking row to satisfy FK
    booking = Booking(
        tenant_id="TEST001",
        employee_id=100,
        employee_code="TESTEMPLOYEE001",
        shift_id=20,
        booking_date=date.today(),
        status=BookingStatusEnum.COMPLETED,
        pickup_latitude=0.0,
        pickup_longitude=0.0,
        drop_latitude=0.0,
        drop_longitude=0.0,
    )
    db.add(booking)
    db.flush()

    rb = db.query(__import__("app.models.route_management", fromlist=["RouteManagementBooking"]).RouteManagementBooking).filter_by(
        route_id=route_id, order_id=order_id
    ).first()
    if rb is None:
        from app.models.route_management import RouteManagementBooking
        rb = RouteManagementBooking(
            route_id=route_id,
            booking_id=booking.booking_id,
            order_id=order_id,
            estimated_pick_up_time=est_time,
            actual_pick_up_time=actual_time,
        )
        db.add(rb)
    db.flush()
    return rb


# ===========================================================================
# 1. Unit tests — classify_delay_category
# ===========================================================================

class TestClassifyDelayCategory:

    def test_on_time_returns_none(self, test_db, test_tenant, test_shift):
        """ON_TIME routes should always return NONE regardless of stop data."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        _add_stop(test_db, route.route_id, 1, "09:00", "09:25")  # 25 min late at first stop
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="ON_TIME",
            db=test_db,
        )
        assert result == "NONE"

    def test_early_returns_none(self, test_db, test_tenant, test_shift):
        """EARLY routes should always return NONE."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="EARLY",
            db=test_db,
        )
        assert result == "NONE"

    def test_late_first_stop_over_driver_grace_returns_driver_delay(
        self, test_db, test_tenant, test_shift
    ):
        """First-stop lateness > driver_grace → DRIVER_DELAY."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        # First stop: 15 minutes late (driver_grace default = 10)
        _add_stop(test_db, route.route_id, 1, "09:00", "09:15")
        _add_stop(test_db, route.route_id, 2, "09:30", "09:31")  # within employee grace
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
            driver_grace_minutes=10,
            employee_grace_minutes=5,
        )
        assert result == "DRIVER_DELAY"

    def test_late_first_stop_within_driver_grace_returns_employee_delay(
        self, test_db, test_tenant, test_shift
    ):
        """First stop within driver grace but a later stop over employee grace → EMPLOYEE_DELAY."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        # First stop: 5 min late (within driver_grace=10)
        _add_stop(test_db, route.route_id, 1, "09:00", "09:05")
        # Second stop: 8 min late (over employee_grace=5)
        _add_stop(test_db, route.route_id, 2, "09:30", "09:38")
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
            driver_grace_minutes=10,
            employee_grace_minutes=5,
        )
        assert result == "EMPLOYEE_DELAY"

    def test_late_all_stops_within_grace_returns_traffic_delay(
        self, test_db, test_tenant, test_shift
    ):
        """All stops within grace → delay is traffic-caused."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        _add_stop(test_db, route.route_id, 1, "09:00", "09:03")  # 3 min — within both graces
        _add_stop(test_db, route.route_id, 2, "09:30", "09:32")  # 2 min — within employee grace
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
            driver_grace_minutes=10,
            employee_grace_minutes=5,
        )
        assert result == "TRAFFIC_DELAY"

    def test_late_no_stop_data_returns_traffic_delay(
        self, test_db, test_tenant, test_shift
    ):
        """If there are no booking stops at all, default to TRAFFIC_DELAY."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
        )
        assert result == "TRAFFIC_DELAY"

    def test_late_missing_actual_pickup_defaults_to_traffic(
        self, test_db, test_tenant, test_shift
    ):
        """Stop with no actual_pick_up_time is skipped; defaults to TRAFFIC_DELAY."""
        from app.services.delay_classification_service import classify_delay_category
        from app.models.route_management import RouteManagementBooking
        from app.models.booking import Booking, BookingStatusEnum

        route = _make_route(test_db, test_tenant.tenant_id)

        # Booking with estimated but NO actual pickup time
        booking = Booking(
            tenant_id="TEST001",
            employee_id=100,
            employee_code="TESTEMPLOYEE001",
            shift_id=20,
            booking_date=date.today(),
            status=BookingStatusEnum.COMPLETED,
            pickup_latitude=0.0,
            pickup_longitude=0.0,
            drop_latitude=0.0,
            drop_longitude=0.0,
        )
        test_db.add(booking)
        test_db.flush()

        rb = RouteManagementBooking(
            route_id=route.route_id,
            booking_id=booking.booking_id,
            order_id=1,
            estimated_pick_up_time="09:00",
            actual_pick_up_time=None,  # Missing
        )
        test_db.add(rb)
        test_db.commit()

        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
        )
        assert result == "TRAFFIC_DELAY"

    def test_custom_grace_thresholds_respected(self, test_db, test_tenant, test_shift):
        """Custom grace values override defaults."""
        from app.services.delay_classification_service import classify_delay_category

        route = _make_route(test_db, test_tenant.tenant_id)
        # First stop: 7 min late
        _add_stop(test_db, route.route_id, 1, "09:00", "09:07")
        test_db.commit()

        # With a tight driver grace of 5 min → DRIVER_DELAY
        result = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
            driver_grace_minutes=5,
        )
        assert result == "DRIVER_DELAY"

        # With a loose driver grace of 10 min → falls through to TRAFFIC_DELAY
        result2 = classify_delay_category(
            route=route,
            delay_type="LATE",
            db=test_db,
            driver_grace_minutes=10,
            employee_grace_minutes=10,
        )
        assert result2 == "TRAFFIC_DELAY"


# ===========================================================================
# 2. Unit tests — tag_trip_delay writes delay_category to RouteDelayEvent
# ===========================================================================

class TestTagTripDelayWithCategory:

    def _complete_route(self, db, tenant_id, shift_id, delay_offset_minutes=30):
        """
        Create and return a route with actual start/end times set.
        delay_offset_minutes > grace → LATE.
        """
        from app.models.route_management import RouteManagement, RouteManagementStatusEnum

        now = datetime(2026, 5, 20, 10, 0, 0)
        start = now - timedelta(minutes=60 + delay_offset_minutes)

        route = RouteManagement(
            tenant_id=tenant_id,
            shift_id=shift_id,
            route_code="TTAGDELAY001",
            estimated_total_time=60.0,
            status=RouteManagementStatusEnum.ONGOING,
            ota_grace_minutes=5,
            actual_start_time=start,
        )
        db.add(route)
        db.flush()
        return route, now

    def test_tag_trip_delay_sets_delay_category_on_event(
        self, test_db, test_tenant, test_shift
    ):
        """tag_trip_delay should insert a RouteDelayEvent row with delay_category set."""
        from app.utils.delay_tagging import tag_trip_delay
        from app.models.route_delay_event import RouteDelayEvent

        route, now = self._complete_route(
            test_db, test_tenant.tenant_id, test_shift.shift_id, delay_offset_minutes=30
        )
        route.actual_end_time = now

        # No stop data → TRAFFIC_DELAY
        tag_trip_delay(db=test_db, route=route, now=now)
        test_db.flush()

        event = (
            test_db.query(RouteDelayEvent)
            .filter(RouteDelayEvent.route_id == route.route_id)
            .order_by(RouteDelayEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.delay_type == "LATE"
        assert event.delay_category == "TRAFFIC_DELAY"

    def test_tag_trip_delay_on_time_sets_none_category(
        self, test_db, test_tenant, test_shift
    ):
        """ON_TIME routes should produce NONE delay_category."""
        from app.utils.delay_tagging import tag_trip_delay
        from app.models.route_delay_event import RouteDelayEvent

        # Offset = 0 → ON_TIME (within grace of 5 min)
        route, now = self._complete_route(
            test_db, test_tenant.tenant_id, test_shift.shift_id, delay_offset_minutes=0
        )
        route.actual_end_time = now  # Ends exactly on schedule

        tag_trip_delay(db=test_db, route=route, now=now)
        test_db.flush()

        event = (
            test_db.query(RouteDelayEvent)
            .filter(RouteDelayEvent.route_id == route.route_id)
            .order_by(RouteDelayEvent.id.desc())
            .first()
        )
        assert event is not None
        # ON_TIME → NONE category
        assert event.delay_category == "NONE"

    def test_tag_trip_delay_driver_delay_category(
        self, test_db, test_tenant, test_shift
    ):
        """LATE route with driver-caused first-stop lateness → DRIVER_DELAY category."""
        from app.utils.delay_tagging import tag_trip_delay
        from app.models.route_delay_event import RouteDelayEvent

        route, now = self._complete_route(
            test_db, test_tenant.tenant_id, test_shift.shift_id, delay_offset_minutes=20
        )
        route.actual_end_time = now

        # Add first stop with driver 15-min lateness (> driver_grace=10)
        _add_stop(test_db, route.route_id, 1, "09:00", "09:15")
        test_db.flush()

        tag_trip_delay(db=test_db, route=route, now=now)
        test_db.flush()

        event = (
            test_db.query(RouteDelayEvent)
            .filter(RouteDelayEvent.route_id == route.route_id)
            .order_by(RouteDelayEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.delay_type == "LATE"
        assert event.delay_category == "DRIVER_DELAY"


# ===========================================================================
# 3. Integration tests — GET /reports/delays
# ===========================================================================

@pytest.fixture(scope="function")
def tagged_route(test_db, test_tenant, test_shift):
    """Create a LATE, DRIVER_DELAY tagged route with delay event."""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    from app.models.route_delay_event import RouteDelayEvent
    from datetime import datetime

    now = datetime(2026, 5, 20, 10, 0, 0)
    start = now - timedelta(hours=2)

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="DELAYED_ROUTE",
        estimated_total_time=60.0,
        status=RouteManagementStatusEnum.COMPLETED,
        ota_grace_minutes=5,
        actual_start_time=start,
        actual_end_time=now,
        delay_type="LATE",
        delay_minutes=55,
        delay_tagged_at=now,
    )
    test_db.add(route)
    test_db.flush()

    event = RouteDelayEvent(
        route_id=route.route_id,
        tenant_id=test_tenant.tenant_id,
        event_kind="OTD",
        delay_type="LATE",
        delay_minutes=55,
        delay_category="DRIVER_DELAY",
        notes="test event",
        tagged_at=now,
    )
    test_db.add(event)
    test_db.commit()
    return route


class TestDelayReportEndpoint:

    def test_delay_report_includes_delay_category(
        self, client, test_tenant, report_token, tagged_route
    ):
        """GET /reports/delays should include delay_category in each route row."""
        today = date.today()
        resp = client.get(
            "/api/v1/reports/delays",
            params={
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
            },
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["routes"]
        route_row = data["data"]["routes"][0]
        assert "delay_category" in route_row
        assert route_row["delay_category"] == "DRIVER_DELAY"

    def test_delay_report_category_breakdown_in_summary(
        self, client, test_tenant, report_token, tagged_route
    ):
        """Summary should include by_category breakdown."""
        resp = client.get(
            "/api/v1/reports/delays",
            params={
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
            },
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        summary = resp.json()["data"]["summary"]
        assert "by_category" in summary
        assert "DRIVER_DELAY" in summary["by_category"]
        assert "EMPLOYEE_DELAY" in summary["by_category"]
        assert "TRAFFIC_DELAY" in summary["by_category"]

    def test_delay_report_filter_by_category_driver(
        self, client, test_tenant, report_token, tagged_route
    ):
        """Filter by delay_category=DRIVER_DELAY should return only matching routes."""
        resp = client.get(
            "/api/v1/reports/delays",
            params={
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
                "delay_category": "DRIVER_DELAY",
            },
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        assert len(routes) >= 1
        for row in routes:
            assert row["delay_category"] == "DRIVER_DELAY"

    def test_delay_report_filter_by_category_no_match(
        self, client, test_tenant, report_token, tagged_route
    ):
        """Filter by a category not present should return empty routes list."""
        resp = client.get(
            "/api/v1/reports/delays",
            params={
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
                "delay_category": "EMPLOYEE_DELAY",
            },
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        routes = resp.json()["data"]["routes"]
        assert routes == []


# ===========================================================================
# 4. Integration tests — GET /reports/delays/{route_id}
# ===========================================================================

class TestDelayDetailEndpoint:

    def test_delay_detail_events_include_category(
        self, client, test_tenant, report_token, tagged_route
    ):
        """Route delay detail events should include delay_category field."""
        resp = client.get(
            f"/api/v1/reports/delays/{tagged_route.route_id}",
            headers={"Authorization": report_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "events" in data
        assert len(data["events"]) >= 1
        event = data["events"][0]
        assert "delay_category" in event
        assert event["delay_category"] == "DRIVER_DELAY"
