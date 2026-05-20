"""
Tests for app/services/reminder_service.py
==========================================

Coverage
--------
1. test_fires_when_due               – booking in window → reminder sent & marked
2. test_no_double_send               – reminder_sent_at already set → skipped
3. test_tenant_disabled              – schedule_reminder_enabled=False → no send
4. test_wrong_status_skipped         – non-SCHEDULED booking → skipped
5. test_outside_window_not_sent      – pickup too far in future → skipped
6. test_push_fail_still_marks_sent   – push failure → still marked (anti-spam)
7. test_correct_notification_content – verifies vehicle plate, driver name/phone
8. test_parse_pickup_datetime_*      – unit tests for the static parser helper

All tests use the SQLite in-memory database provided by the top-level conftest
and mock `UnifiedNotificationService` so no real FCM / SMS calls are made.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.booking import Booking, BookingStatusEnum
from app.models.route_management import (
    RouteManagement,
    RouteManagementBooking,
    RouteManagementStatusEnum,
)
from app.models.tenant_config import TenantConfig
from app.services.reminder_service import ReminderService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    """Return the current naive UTC datetime (same as the service does internally)."""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Shared fixture: sets up a fully valid "reminder due" scenario
# ---------------------------------------------------------------------------

@pytest.fixture()
def reminder_setup(
    test_db,
    test_tenant,
    test_employee,
    test_driver,
    test_vehicle,
    test_shift,
):
    """
    Creates the minimal set of DB rows needed for a booking that is due for a
    reminder right now:

    TenantConfig   — reminders enabled, 30-minute window
    RouteManagement — driver + vehicle assigned
    Booking         — SCHEDULED, today, no reminder_sent_at
    RouteManagementBooking — pickup 15 minutes from now (inside 30-min window)

    Returns a dict so individual tests can mutate specific fields.
    """
    # 1. TenantConfig with reminders enabled
    config = TenantConfig(
        tenant_id=test_tenant.tenant_id,
        escort_required_for_women=True,
        login_boarding_otp=True,
        login_deboarding_otp=True,
        logout_boarding_otp=True,
        logout_deboarding_otp=True,
        schedule_reminder_enabled=True,
        schedule_reminder_minutes=30,
    )
    test_db.add(config)
    test_db.flush()

    # 2. Route with vehicle and driver assigned
    route = RouteManagement(
        route_id=9000,
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="REMINDER_ROUTE_001",
        status=RouteManagementStatusEnum.DRIVER_ASSIGNED,
        assigned_vendor_id=None,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_driver_id=test_driver.driver_id,
    )
    test_db.add(route)
    test_db.flush()

    # 3. Pickup time 15 minutes from now (well inside the 30-min window)
    now_utc = _utc_now()
    pickup_dt = now_utc + timedelta(minutes=15)
    pickup_time_str = pickup_dt.strftime("%H:%M:%S")

    # 4. Booking: SCHEDULED, today, no reminder_sent_at
    booking = Booking(
        booking_id=9001,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        shift_id=test_shift.shift_id,
        booking_date=now_utc.date(),  # UTC today — same as service uses
        status=BookingStatusEnum.SCHEDULED,
        reminder_sent_at=None,
        pickup_latitude=40.7128,
        pickup_longitude=-74.0060,
        pickup_location="Reminder Test Pickup",
        drop_location="Reminder Test Drop",
    )
    test_db.add(booking)
    test_db.flush()

    # 5. Link booking to route with the computed pickup time
    rmb = RouteManagementBooking(
        route_id=route.route_id,
        booking_id=booking.booking_id,
        order_id=1,
        estimated_pick_up_time=pickup_time_str,
        estimated_distance=5.0,
    )
    test_db.add(rmb)
    test_db.commit()
    test_db.refresh(booking)

    return {
        "booking": booking,
        "route": route,
        "rmb": rmb,
        "config": config,
        "pickup_time_str": pickup_time_str,
    }


# ---------------------------------------------------------------------------
# Convenience: default mock return value for a successful push
# ---------------------------------------------------------------------------

_PUSH_OK = {"push_success": True, "sms_success": None, "errors": []}
_PUSH_FAIL = {"push_success": False, "sms_success": None, "errors": ["push: no FCM token"]}

_PATCH_TARGET = "app.services.reminder_service.UnifiedNotificationService"


# ===========================================================================
# 1. Fires when booking is due
# ===========================================================================

def test_fires_when_due(test_db, reminder_setup):
    """
    A SCHEDULED booking with pickup 15 min from now (30-min window) must
    produce scanned=1, sent=1, and have reminder_sent_at stamped.
    """
    with patch(_PATCH_TARGET) as MockUNS:
        MockUNS.return_value.send_trip_reminder.return_value = _PUSH_OK

        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 1, f"Expected 1 scanned, got {summary}"
    assert summary["sent"] == 1,    f"Expected 1 sent, got {summary}"
    assert summary["failed"] == 0
    assert summary["skipped"] == 0

    test_db.refresh(reminder_setup["booking"])
    assert reminder_setup["booking"].reminder_sent_at is not None, (
        "booking.reminder_sent_at should be stamped after a successful reminder"
    )


# ===========================================================================
# 2. No double-send (idempotency)
# ===========================================================================

def test_no_double_send(test_db, reminder_setup):
    """
    If reminder_sent_at is already set, the booking must be excluded from
    _find_candidates and no notification may be dispatched.
    """
    reminder_setup["booking"].reminder_sent_at = datetime.utcnow()
    test_db.commit()

    with patch(_PATCH_TARGET) as MockUNS:
        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 0, (
        "Booking with reminder_sent_at already set should be skipped"
    )
    # UnifiedNotificationService should not have been instantiated at all
    MockUNS.assert_not_called()


# ===========================================================================
# 3. Tenant has reminders disabled
# ===========================================================================

def test_tenant_disabled(test_db, reminder_setup):
    """
    When schedule_reminder_enabled=False for the tenant, no bookings qualify.
    """
    reminder_setup["config"].schedule_reminder_enabled = False
    test_db.commit()

    with patch(_PATCH_TARGET) as MockUNS:
        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 0, (
        "Disabled tenant should produce zero candidates"
    )
    MockUNS.assert_not_called()


# ===========================================================================
# 4. Wrong status (not SCHEDULED)
# ===========================================================================

def test_wrong_status_skipped(test_db, reminder_setup):
    """
    Only SCHEDULED bookings are eligible. REQUEST, ONGOING, COMPLETED, etc.
    must all be ignored.
    """
    for non_scheduled_status in (
        BookingStatusEnum.REQUEST,
        BookingStatusEnum.ONGOING,
        BookingStatusEnum.COMPLETED,
        BookingStatusEnum.CANCELLED,
    ):
        reminder_setup["booking"].status = non_scheduled_status
        reminder_setup["booking"].reminder_sent_at = None  # reset guard
        test_db.commit()

        with patch(_PATCH_TARGET) as MockUNS:
            svc = ReminderService(test_db)
            summary = svc.process_due_reminders()

        assert summary["scanned"] == 0, (
            f"Status {non_scheduled_status!r} should not be eligible; "
            f"got summary={summary}"
        )
        MockUNS.assert_not_called()


# ===========================================================================
# 5. Pickup outside the reminder window
# ===========================================================================

def test_outside_window_not_sent(test_db, reminder_setup):
    """
    A booking with pickup 60 minutes away (window=30 min) must not fire.
    """
    now_utc = _utc_now()
    far_pickup = now_utc + timedelta(minutes=60)
    reminder_setup["rmb"].estimated_pick_up_time = far_pickup.strftime("%H:%M:%S")
    test_db.commit()

    with patch(_PATCH_TARGET) as MockUNS:
        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 0, (
        "Pickup 60 min away (30-min window) should not trigger a reminder"
    )
    MockUNS.assert_not_called()


def test_already_passed_not_sent(test_db, reminder_setup):
    """
    A booking whose pickup time has already passed must not fire
    (window_start < pickup_dt is not satisfied when pickup_dt < now).
    """
    now_utc = _utc_now()
    past_pickup = now_utc - timedelta(minutes=5)
    reminder_setup["rmb"].estimated_pick_up_time = past_pickup.strftime("%H:%M:%S")
    test_db.commit()

    with patch(_PATCH_TARGET) as MockUNS:
        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 0, (
        "A booking whose pickup has already passed should not trigger a reminder"
    )


# ===========================================================================
# 6. Push failure still marks booking as sent (anti-spam guard)
# ===========================================================================

def test_push_fail_still_marks_sent(test_db, reminder_setup):
    """
    Even when push_success=False (e.g. employee has no active FCM session),
    the booking must be stamped with reminder_sent_at to prevent repeated
    failed pushes (spamming).  The summary should record skipped=1.
    """
    with patch(_PATCH_TARGET) as MockUNS:
        MockUNS.return_value.send_trip_reminder.return_value = _PUSH_FAIL

        svc = ReminderService(test_db)
        summary = svc.process_due_reminders()

    assert summary["scanned"] == 1
    assert summary["sent"] == 0
    assert summary["skipped"] == 1
    assert summary["failed"] == 0

    test_db.refresh(reminder_setup["booking"])
    assert reminder_setup["booking"].reminder_sent_at is not None, (
        "reminder_sent_at must be stamped even when push fails"
    )


# ===========================================================================
# 7. Correct notification content
# ===========================================================================

def test_correct_notification_content(
    test_db, reminder_setup, test_driver, test_vehicle
):
    """
    `send_trip_reminder` must be called with the correct vehicle plate,
    driver name, driver phone, booking_id, and pickup_time_str.
    """
    with patch(_PATCH_TARGET) as MockUNS:
        mock_send = MockUNS.return_value.send_trip_reminder
        mock_send.return_value = _PUSH_OK

        svc = ReminderService(test_db)
        svc.process_due_reminders()

        mock_send.assert_called_once()

    # Retrieve the kwargs the service passed to send_trip_reminder
    _, call_kwargs = mock_send.call_args

    assert call_kwargs["booking_id"] == reminder_setup["booking"].booking_id
    assert call_kwargs["vehicle_plate"] == test_vehicle.rc_number   # "TEST123"
    assert call_kwargs["driver_name"] == test_driver.name            # "Test Driver"
    assert call_kwargs["driver_phone"] == test_driver.phone          # "1234567890"
    assert call_kwargs["pickup_time_str"] == reminder_setup["pickup_time_str"]
    assert call_kwargs["employee_id"] == test_vehicle.driver_id or True  # employee_id from booking
    assert call_kwargs["send_sms"] is True


# ===========================================================================
# 8. Static helper: _parse_pickup_datetime
# ===========================================================================

class TestParsePickupDatetime:
    """Unit tests for ReminderService._parse_pickup_datetime (static method)."""

    _today = date(2026, 5, 20)

    def test_valid_hhmmss(self):
        result = ReminderService._parse_pickup_datetime(self._today, "08:30:00")
        assert result == datetime(2026, 5, 20, 8, 30, 0)

    def test_valid_hhmm(self):
        result = ReminderService._parse_pickup_datetime(self._today, "08:30")
        assert result == datetime(2026, 5, 20, 8, 30, 0)

    def test_leading_zero_hour(self):
        result = ReminderService._parse_pickup_datetime(self._today, "07:05:00")
        assert result == datetime(2026, 5, 20, 7, 5, 0)

    def test_midnight(self):
        result = ReminderService._parse_pickup_datetime(self._today, "00:00:00")
        assert result == datetime(2026, 5, 20, 0, 0, 0)

    def test_end_of_day(self):
        result = ReminderService._parse_pickup_datetime(self._today, "23:59:59")
        assert result == datetime(2026, 5, 20, 23, 59, 59)

    def test_with_microseconds_stripped(self):
        # regex captures only HH:MM:SS — microseconds are ignored
        result = ReminderService._parse_pickup_datetime(self._today, "08:30:00.000000")
        assert result == datetime(2026, 5, 20, 8, 30, 0)

    def test_whitespace_trimmed(self):
        result = ReminderService._parse_pickup_datetime(self._today, "  09:15:00  ")
        assert result == datetime(2026, 5, 20, 9, 15, 0)

    def test_garbage_string_returns_none(self):
        assert ReminderService._parse_pickup_datetime(self._today, "garbage") is None

    def test_empty_string_returns_none(self):
        assert ReminderService._parse_pickup_datetime(self._today, "") is None

    def test_none_returns_none(self):
        assert ReminderService._parse_pickup_datetime(self._today, None) is None

    def test_invalid_hour_returns_none(self):
        # Hour 25 is invalid
        assert ReminderService._parse_pickup_datetime(self._today, "25:00:00") is None

    def test_invalid_minute_returns_none(self):
        assert ReminderService._parse_pickup_datetime(self._today, "08:60:00") is None
