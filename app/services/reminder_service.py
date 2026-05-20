"""
Schedule Reminder Service
=========================
Finds every Scheduled booking whose estimated pickup time falls within the
tenant-configured reminder window (default: 30 min) and has not yet had a
reminder sent, then dispatches a push notification + optional SMS.

Called by SchedulerService every 5 minutes.

Query logic (single SQL join, no N+1):
  bookings   ← INNER JOIN route_management_bookings  (gets pickup time)
             ← INNER JOIN route_management           (gets vehicle / driver IDs)
             ← INNER JOIN employees                  (gets employee phone)
             ← INNER JOIN tenant_configs             (gets reminder settings)
  WHERE
      b.status          = 'Scheduled'
      b.booking_date    = TODAY
      b.reminder_sent_at IS NULL
      tc.schedule_reminder_enabled = TRUE
      -- pickup datetime is within (now, now + reminder_minutes]
      CAST(booking_date AS TIMESTAMP) + estimated_pick_up_time::interval
          BETWEEN now() AND now() + reminder_minutes * interval '1 minute'

Vehicle / driver resolved lazily from route_management.assigned_vehicle_id /
assigned_driver_id (plain Integer columns, no FK).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.session import SessionLocal
from app.models.booking import Booking, BookingStatusEnum
from app.models.driver import Driver
from app.models.employee import Employee
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.models.tenant_config import TenantConfig
from app.models.vehicle import Vehicle
from app.services.unified_notification_service import UnifiedNotificationService

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data class for a reminder job item
# ---------------------------------------------------------------------------

class _ReminderCandidate:
    """All data needed to send one reminder, gathered in a single DB pass."""

    __slots__ = (
        "booking_id",
        "tenant_id",
        "employee_id",
        "employee_phone",
        "pickup_time_str",
        "vehicle_plate",
        "driver_name",
        "driver_phone",
        "route_id",
        "send_sms",
    )

    def __init__(
        self,
        booking_id: int,
        tenant_id: str,
        employee_id: int,
        employee_phone: str,
        pickup_time_str: str,
        vehicle_plate: str,
        driver_name: str,
        driver_phone: str,
        route_id: int,
        send_sms: bool,
    ):
        self.booking_id = booking_id
        self.tenant_id = tenant_id
        self.employee_id = employee_id
        self.employee_phone = employee_phone
        self.pickup_time_str = pickup_time_str
        self.vehicle_plate = vehicle_plate
        self.driver_name = driver_name
        self.driver_phone = driver_phone
        self.route_id = route_id
        self.send_sms = send_sms


# ---------------------------------------------------------------------------
# ReminderService
# ---------------------------------------------------------------------------

class ReminderService:
    """
    Stateless service — instantiate fresh each scheduler tick so that a stale
    DB session never accumulates between runs.
    """

    # Fallback text shown when vehicle / driver data is missing
    _UNKNOWN_PLATE = "TBA"
    _UNKNOWN_NAME = "Driver"
    _UNKNOWN_PHONE = "—"

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process_due_reminders(self) -> dict:
        """
        Main entry point called by the scheduler every 5 minutes.

        Returns a summary dict for logging:
            {
                "scanned": int,   # bookings that were candidates
                "sent": int,      # reminders successfully pushed
                "failed": int,    # reminders that errored
                "skipped": int,   # driver/vehicle info missing → still marked sent
            }
        """
        candidates = self._find_candidates()

        if not candidates:
            logger.debug("[reminder_service] No reminders due this tick.")
            return {"scanned": 0, "sent": 0, "failed": 0, "skipped": 0}

        logger.info("[reminder_service] %d reminder(s) due this tick.", len(candidates))

        sent = failed = skipped = 0
        notification_svc = UnifiedNotificationService(self.db)

        for candidate in candidates:
            try:
                result = notification_svc.send_trip_reminder(
                    employee_id=candidate.employee_id,
                    employee_phone=candidate.employee_phone,
                    pickup_time_str=candidate.pickup_time_str,
                    vehicle_plate=candidate.vehicle_plate,
                    driver_name=candidate.driver_name,
                    driver_phone=candidate.driver_phone,
                    booking_id=candidate.booking_id,
                    route_id=candidate.route_id,
                    send_sms=candidate.send_sms,
                )

                # Mark as sent regardless of push outcome so we don't spam.
                # A push failure (e.g. no active FCM session) is still recorded.
                self._mark_sent(candidate.booking_id)

                if result.get("push_success"):
                    sent += 1
                    logger.info(
                        "[reminder_service] Reminder sent "
                        "booking_id=%s employee_id=%s pickup=%s",
                        candidate.booking_id,
                        candidate.employee_id,
                        candidate.pickup_time_str,
                    )
                else:
                    skipped += 1
                    logger.warning(
                        "[reminder_service] Push not delivered (no session?) "
                        "booking_id=%s errors=%s",
                        candidate.booking_id,
                        result.get("errors"),
                    )

            except Exception as exc:
                failed += 1
                logger.error(
                    "[reminder_service] Error processing booking_id=%s: %s",
                    candidate.booking_id,
                    exc,
                    exc_info=True,
                )
                # Don't mark as sent — will retry on next tick.

        logger.info(
            "[reminder_service] Tick complete: scanned=%d sent=%d skipped=%d failed=%d",
            len(candidates), sent, skipped, failed,
        )
        return {
            "scanned": len(candidates),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }

    # ------------------------------------------------------------------
    # Query: find bookings due for a reminder
    # ------------------------------------------------------------------

    def _find_candidates(self) -> List[_ReminderCandidate]:
        """
        Return all bookings that need a reminder right now.

        Strategy:
        1. One query to get all (booking, route_booking, route, employee, tenant_config)
           rows where the reminder is due.
        2. Batch-fetch vehicles and drivers by their IDs.
        3. Assemble _ReminderCandidate objects.
        """
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)  # naive UTC matches DB
        today = now.date()

        # ------------------------------------------------------------------
        # Step 1: Find eligible (booking, route_booking, route, employee, config)
        # ------------------------------------------------------------------
        rows = (
            self.db.query(
                Booking,
                RouteManagementBooking,
                RouteManagement,
                Employee,
                TenantConfig,
            )
            .join(
                RouteManagementBooking,
                RouteManagementBooking.booking_id == Booking.booking_id,
            )
            .join(
                RouteManagement,
                RouteManagement.route_id == RouteManagementBooking.route_id,
            )
            .join(
                Employee,
                Employee.employee_id == Booking.employee_id,
            )
            .join(
                TenantConfig,
                TenantConfig.tenant_id == Booking.tenant_id,
            )
            .filter(
                Booking.status == BookingStatusEnum.SCHEDULED,
                Booking.booking_date == today,
                Booking.reminder_sent_at.is_(None),
                TenantConfig.schedule_reminder_enabled.is_(True),
                RouteManagementBooking.estimated_pick_up_time.isnot(None),
                # Route must have a driver assigned (otherwise nothing useful to show)
                RouteManagement.assigned_driver_id.isnot(None),
                RouteManagement.assigned_vehicle_id.isnot(None),
            )
            .all()
        )

        if not rows:
            return []

        # ------------------------------------------------------------------
        # Step 2: Filter to only those inside the reminder window
        # ------------------------------------------------------------------
        candidates: List[_ReminderCandidate] = []

        # Batch load vehicles and drivers referenced by the routes (avoid N+1)
        vehicle_ids = {r[2].assigned_vehicle_id for r in rows if r[2].assigned_vehicle_id}
        driver_ids  = {r[2].assigned_driver_id  for r in rows if r[2].assigned_driver_id}

        vehicles = {}
        if vehicle_ids:
            for v in self.db.query(Vehicle).filter(Vehicle.vehicle_id.in_(vehicle_ids)).all():
                vehicles[v.vehicle_id] = v

        drivers = {}
        if driver_ids:
            for d in self.db.query(Driver).filter(Driver.driver_id.in_(driver_ids)).all():
                drivers[d.driver_id] = d

        for booking, rmb, route, employee, config in rows:
            pickup_time_str: str = rmb.estimated_pick_up_time  # e.g. "08:30:00"

            # Parse pickup time and compute the absolute pickup datetime
            pickup_dt = self._parse_pickup_datetime(today, pickup_time_str)
            if pickup_dt is None:
                logger.warning(
                    "[reminder_service] Cannot parse pickup time '%s' "
                    "for booking_id=%s — skipping.",
                    pickup_time_str, booking.booking_id,
                )
                continue

            reminder_minutes: int = config.schedule_reminder_minutes or 30
            window_start = now
            window_end   = now + timedelta(minutes=reminder_minutes)

            # Reminder fires when: now < pickup_dt <= now + reminder_minutes
            if not (window_start < pickup_dt <= window_end):
                continue  # Not in window yet (or already passed)

            # Resolve vehicle plate
            vehicle = vehicles.get(route.assigned_vehicle_id)
            plate = vehicle.rc_number if vehicle else self._UNKNOWN_PLATE

            # Resolve driver info
            driver = drivers.get(route.assigned_driver_id)
            d_name  = driver.name  if driver else self._UNKNOWN_NAME
            d_phone = driver.phone if driver else self._UNKNOWN_PHONE

            candidates.append(
                _ReminderCandidate(
                    booking_id=booking.booking_id,
                    tenant_id=booking.tenant_id,
                    employee_id=employee.employee_id,
                    employee_phone=employee.phone or "",
                    pickup_time_str=pickup_time_str,
                    vehicle_plate=plate,
                    driver_name=d_name,
                    driver_phone=d_phone,
                    route_id=route.route_id,
                    send_sms=True,  # SMS gated by SMSService.enabled in the service itself
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pickup_datetime(booking_date, time_str: str) -> Optional[datetime]:
        """
        Combine a date with a time string (HH:MM or HH:MM:SS) into a naive datetime.
        Returns None on any parse error.
        """
        if not time_str:
            return None
        # Accept "HH:MM" or "HH:MM:SS" or "HH:MM:SS.ffffff"
        match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", time_str.strip())
        if not match:
            return None
        hour   = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3) or 0)
        try:
            return datetime(
                booking_date.year,
                booking_date.month,
                booking_date.day,
                hour, minute, second,
            )
        except ValueError:
            return None

    def _mark_sent(self, booking_id: int) -> None:
        """Stamp reminder_sent_at = now() on the booking row."""
        (
            self.db.query(Booking)
            .filter(Booking.booking_id == booking_id)
            .update(
                {"reminder_sent_at": datetime.utcnow()},
                synchronize_session=False,
            )
        )
        self.db.commit()
        logger.debug("[reminder_service] Marked reminder_sent_at for booking_id=%s", booking_id)


# ---------------------------------------------------------------------------
# Module-level runner — used by SchedulerService
# ---------------------------------------------------------------------------

def run_reminder_job() -> None:
    """
    Called by APScheduler every 5 minutes.
    Creates its own DB session so the scheduler thread owns the connection.
    """
    db: Session = SessionLocal()
    try:
        svc = ReminderService(db)
        summary = svc.process_due_reminders()
        if summary["scanned"] > 0:
            logger.info("[reminder_job] Summary: %s", summary)
    except Exception as exc:
        logger.error("[reminder_job] Unhandled error: %s", exc, exc_info=True)
    finally:
        db.close()
