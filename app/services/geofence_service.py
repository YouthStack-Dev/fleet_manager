"""
app/services/geofence_service.py
---------------------------------
IMP-7 — Geofence Arrival Triggers.

Called as a BackgroundTask on every POST /driver/location ping.

Logic
-----
1. Look up the next pending stop on the route (lowest order_id whose booking
   status is SCHEDULED or REQUEST and whose geofence_notified_at is still NULL).
2. Compute the geodesic distance between the driver's current position and the
   stop's pickup coordinates.
3. If the distance is within the tenant-configured radius
   (TenantConfig.geofence_arrival_radius_meters, default 300 m):
   a. Set RouteManagementBooking.geofence_notified_at = now (prevents duplicates).
   b. Commit the flag before sending FCM so a crash during send doesn't leave
      the flag unset (causing a duplicate on the next ping).
   c. Push an FCM notification to the waiting employee.

Deduplication strategy
-----------------------
`geofence_notified_at` is set once and never cleared for the life of the stop.
Subsequent pings within the same radius will find a non-NULL value and skip.
When the stop is completed (employee boards), the next pending stop has its own
NULL `geofence_notified_at`, so the cycle continues correctly.

All exceptions are swallowed — a geofence failure must never affect the
location-ping HTTP response or the PostgreSQL breadcrumb write.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from geopy.distance import geodesic
from sqlalchemy.orm import Session

from app.models.route_management import RouteManagementBooking
from app.models.booking import Booking, BookingStatusEnum
from app.models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

# Statuses where the employee is still waiting to be picked up
_PENDING_STATUSES = [BookingStatusEnum.SCHEDULED, BookingStatusEnum.REQUEST]

# Fallback radius when TenantConfig row is missing
_DEFAULT_RADIUS_M = 300


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def check_and_fire_arrival_geofence(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_lat: float,
    driver_lng: float,
) -> None:
    """
    Entry point for the geofence background task.

    Wraps `_run_geofence_check` in a top-level exception handler so that any
    unexpected error is logged but never re-raised to the caller.
    """
    try:
        _run_geofence_check(
            db=db,
            tenant_id=tenant_id,
            route_id=route_id,
            driver_lat=driver_lat,
            driver_lng=driver_lng,
        )
    except Exception:
        logger.exception("[geofence] Unexpected error for route=%s", route_id)


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _run_geofence_check(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_lat: float,
    driver_lng: float,
) -> None:
    # --- Resolve tenant arrival radius ---
    config: Optional[TenantConfig] = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id == tenant_id)
        .first()
    )
    radius_m: int = (
        config.geofence_arrival_radius_meters
        if config and config.geofence_arrival_radius_meters is not None
        else _DEFAULT_RADIUS_M
    )

    # --- Find next unnotified pending stop ---
    result: Optional[Tuple[RouteManagementBooking, Booking]] = (
        db.query(RouteManagementBooking, Booking)
        .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
        .filter(
            RouteManagementBooking.route_id == route_id,
            Booking.status.in_(_PENDING_STATUSES),
            RouteManagementBooking.geofence_notified_at.is_(None),
        )
        .order_by(RouteManagementBooking.order_id.asc())
        .first()
    )

    if result is None:
        logger.debug(
            "[geofence] No unnotified pending stops for route=%s", route_id
        )
        return

    rmb, booking = result

    # --- Guard: stop must have coordinates ---
    if not booking.pickup_latitude or not booking.pickup_longitude:
        logger.debug(
            "[geofence] Booking %s has no pickup coordinates — skipping",
            booking.booking_id,
        )
        return

    # --- Compute distance ---
    distance_m: float = geodesic(
        (driver_lat, driver_lng),
        (booking.pickup_latitude, booking.pickup_longitude),
    ).meters

    logger.debug(
        "[geofence] route=%s booking=%s order=%s distance=%.0fm radius=%dm",
        route_id, booking.booking_id, rmb.order_id, distance_m, radius_m,
    )

    if distance_m > radius_m:
        return  # Driver not yet within arrival zone

    # --- Driver is within radius ---
    logger.info(
        "[geofence] Driver within %.0fm of stop (booking=%s, order=%s) for route=%s — "
        "firing arrival FCM",
        distance_m, booking.booking_id, rmb.order_id, route_id,
    )

    # Persist the flag BEFORE sending FCM to guarantee idempotency even if FCM
    # call crashes or times out; the next ping will see geofence_notified_at != NULL
    rmb.geofence_notified_at = datetime.now(timezone.utc)
    db.add(rmb)
    db.commit()

    # --- Send FCM to the waiting employee ---
    _notify_driver_arriving(
        db=db,
        employee_id=booking.employee_id,
        booking_id=booking.booking_id,
        route_id=route_id,
        distance_m=distance_m,
    )


def _notify_driver_arriving(
    db: Session,
    employee_id: int,
    booking_id: int,
    route_id: int,
    distance_m: float,
) -> None:
    """Send 'Driver is arriving' FCM push. Swallows all exceptions."""
    try:
        from app.services.unified_notification_service import UnifiedNotificationService

        UnifiedNotificationService(db).send_to_user(
            user_type="employee",
            user_id=employee_id,
            title="Your driver is arriving",
            body="Your cab is nearby. Please be ready at the pickup point.",
            data={
                "type": "driver_arriving",
                "route_id": str(route_id),
                "booking_id": str(booking_id),
                "distance_meters": str(round(distance_m)),
            },
            priority="high",
        )
        logger.info(
            "[geofence] Arrival FCM sent to employee %s (booking=%s)",
            employee_id, booking_id,
        )
    except Exception:
        logger.exception(
            "[geofence] FCM send failed for employee %s (booking=%s)",
            employee_id, booking_id,
        )
