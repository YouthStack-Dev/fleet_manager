"""
app/services/eta_service.py
----------------------------
IMP-6 — ETA Recalculation from Live Driver Location.

Called as a BackgroundTask on every POST /driver/location ping.

Algorithm
---------
For each remaining stop (ordered by pickup order_id):

  1. Compute a rolling ETA using straight-line (geodesic) distance and an
     effective speed derived from the driver's reported speed.

     Stop 1  ETA = now + time(driver → stop_1)
     Stop N  ETA = ETA[N-1] + time(stop_{N-1} → stop_N)   (N > 1)

  2. Compare the new ETA against the currently stored estimated_pick_up_time.

  3. If |new_ETA - stored_ETA| >= eta_change_threshold_minutes AND the stop
     has not been updated within the last RATE_LIMIT_SECONDS:
       a. Update RouteManagementBooking.estimated_pick_up_time
       b. Set RouteManagementBooking.eta_updated_at = now
       c. Push an FCM notification to the employee.

Speed selection
---------------
  * If the driver reports a speed between MIN_SPEED_KMPH and MAX_SPEED_KMPH,
    that value is used.
  * Otherwise the default city speed (DEFAULT_CITY_SPEED_KMPH) is used.
  * The city default accounts for urban congestion and multi-stop waiting time.

Stops without pickup coordinates are skipped (preserving the cumulative time
from previous stops so subsequent stops are still estimated).

All exceptions are swallowed — an ETA failure must never affect the
location-ping HTTP response or the PostgreSQL breadcrumb write.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

from geopy.distance import geodesic
from sqlalchemy.orm import Session

from app.models.route_management import RouteManagementBooking
from app.models.booking import Booking, BookingStatusEnum
from app.models.tenant_config import TenantConfig
from app.utils.delay_tagging import parse_hhmm_to_minutes

logger = logging.getLogger(__name__)

# Statuses where the employee is still waiting to board
_PENDING_STATUSES = [BookingStatusEnum.SCHEDULED, BookingStatusEnum.REQUEST]

_DEFAULT_CITY_SPEED_KMPH: float = 25.0   # conservative urban default
_MIN_SPEED_KMPH: float = 5.0             # below this → treat as stopped → use default
_MAX_SPEED_KMPH: float = 80.0            # cap GPS speed noise
_DEFAULT_THRESHOLD_MIN: int = 5          # fallback when TenantConfig is missing
_RATE_LIMIT_SECONDS: int = 120           # max 1 ETA update per stop per 2 minutes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def recalculate_eta_for_remaining_stops(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_lat: float,
    driver_lng: float,
    driver_speed_kmph: Optional[float],
    now: datetime,
) -> None:
    """
    Entry point for the ETA recalculation background task.

    Parameters
    ----------
    db                : Active SQLAlchemy session.
    tenant_id         : Tenant scoping key.
    route_id          : The ONGOING route to recalculate ETAs for.
    driver_lat        : Driver's current latitude.
    driver_lng        : Driver's current longitude.
    driver_speed_kmph : Speed reported by the device (km/h); may be None.
    now               : Current IST datetime (same value used for the location record).
    """
    try:
        _run_eta_recalc(
            db=db,
            tenant_id=tenant_id,
            route_id=route_id,
            driver_lat=driver_lat,
            driver_lng=driver_lng,
            driver_speed_kmph=driver_speed_kmph,
            now=now,
        )
    except Exception:
        logger.exception("[eta] Unexpected error for route=%s", route_id)


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _run_eta_recalc(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_lat: float,
    driver_lng: float,
    driver_speed_kmph: Optional[float],
    now: datetime,
) -> None:
    speed_kmph: float = _effective_speed(driver_speed_kmph)

    # --- Fetch tenant threshold ---
    config: Optional[TenantConfig] = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id == tenant_id)
        .first()
    )
    threshold_min: int = (
        config.eta_change_threshold_minutes
        if config and config.eta_change_threshold_minutes is not None
        else _DEFAULT_THRESHOLD_MIN
    )

    # --- Fetch all remaining stops in pickup order ---
    rows: List[Tuple[RouteManagementBooking, Booking]] = (
        db.query(RouteManagementBooking, Booking)
        .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
        .filter(
            RouteManagementBooking.route_id == route_id,
            Booking.status.in_(_PENDING_STATUSES),
        )
        .order_by(RouteManagementBooking.order_id.asc())
        .all()
    )

    if not rows:
        logger.debug("[eta] No pending stops for route=%s", route_id)
        return

    # --- Rolling ETA computation ---
    prev_lat: float = driver_lat
    prev_lng: float = driver_lng
    cumulative_min: float = 0.0
    updated_count: int = 0

    for rmb, booking in rows:
        stop_lat: Optional[float] = booking.pickup_latitude
        stop_lng: Optional[float] = booking.pickup_longitude

        if not stop_lat or not stop_lng:
            logger.debug(
                "[eta] Booking %s missing pickup coordinates — skipping",
                booking.booking_id,
            )
            # Don't advance prev_lat/lng so the next stop inherits the driver pos
            continue

        # Segment distance and time
        segment_km: float = geodesic(
            (prev_lat, prev_lng),
            (stop_lat, stop_lng),
        ).km
        segment_min: float = (segment_km / speed_kmph) * 60.0
        cumulative_min += segment_min

        # Compute new ETA datetime and "HH:MM" string
        new_eta_dt: datetime = now + timedelta(minutes=cumulative_min)
        new_eta_str: str = f"{new_eta_dt.hour:02d}:{new_eta_dt.minute:02d}"
        new_total_min: int = new_eta_dt.hour * 60 + new_eta_dt.minute

        # Compare against stored ETA
        stored_total_min: Optional[int] = parse_hhmm_to_minutes(rmb.estimated_pick_up_time)
        if stored_total_min is not None:
            diff_min: int = abs(new_total_min - stored_total_min)
        else:
            diff_min = threshold_min + 1  # No stored value → always update

        if diff_min < threshold_min:
            prev_lat, prev_lng = stop_lat, stop_lng
            continue

        # Rate-limit: skip if this stop was updated too recently
        if rmb.eta_updated_at is not None:
            elapsed_s: float = (now - rmb.eta_updated_at).total_seconds()
            if elapsed_s < _RATE_LIMIT_SECONDS:
                prev_lat, prev_lng = stop_lat, stop_lng
                continue

        # --- Persist updated ETA ---
        old_eta_str: str = rmb.estimated_pick_up_time or "??"
        rmb.estimated_pick_up_time = new_eta_str
        rmb.eta_updated_at = now
        db.add(rmb)
        updated_count += 1

        logger.info(
            "[eta] route=%s booking=%s order=%s ETA %s → %s (Δ%d min, speed=%.0f km/h)",
            route_id, booking.booking_id, rmb.order_id,
            old_eta_str, new_eta_str, diff_min, speed_kmph,
        )

        # Send FCM (best-effort; never blocks the commit)
        _notify_eta_updated(
            db=db,
            employee_id=booking.employee_id,
            booking_id=booking.booking_id,
            route_id=route_id,
            new_eta_str=new_eta_str,
        )

        prev_lat, prev_lng = stop_lat, stop_lng

    if updated_count:
        db.commit()
        logger.info(
            "[eta] route=%s: committed ETA updates for %d stop(s)",
            route_id, updated_count,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _effective_speed(reported_kmph: Optional[float]) -> float:
    """
    Return a reliable driving speed (km/h) for ETA estimation.

    Uses the reported speed when it is plausible, otherwise falls back to the
    urban default.
    """
    if reported_kmph is None:
        return _DEFAULT_CITY_SPEED_KMPH
    if reported_kmph < _MIN_SPEED_KMPH:
        # Driver appears stopped (at traffic light, stuck in traffic, etc.)
        return _DEFAULT_CITY_SPEED_KMPH
    return min(reported_kmph, _MAX_SPEED_KMPH)


def _notify_eta_updated(
    db: Session,
    employee_id: int,
    booking_id: int,
    route_id: int,
    new_eta_str: str,
) -> None:
    """
    Push an FCM notification to the employee about the updated pickup time.
    Swallows all exceptions.
    """
    try:
        from app.services.unified_notification_service import UnifiedNotificationService

        UnifiedNotificationService(db).send_to_user(
            user_type="employee",
            user_id=employee_id,
            title="Pickup time updated",
            body=f"Your estimated pickup time has been updated to {new_eta_str}.",
            data={
                "type": "eta_updated",
                "route_id": str(route_id),
                "booking_id": str(booking_id),
                "new_eta": new_eta_str,
            },
            priority="normal",
        )
        logger.info(
            "[eta] FCM sent to employee %s (booking=%s) new_eta=%s",
            employee_id, booking_id, new_eta_str,
        )
    except Exception:
        logger.exception(
            "[eta] FCM notification failed for employee %s (booking=%s)",
            employee_id, booking_id,
        )
