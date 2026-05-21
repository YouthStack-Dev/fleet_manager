"""
app/utils/delay_tagging.py
---------------------------
OTA / OTD delay tagging utility for completed routes.

Called from app_driver_router.py → end_duty() immediately after
`route.actual_end_time` is set, before the session commit.

How delay is computed
---------------------
planned_end_time = actual_start_time + timedelta(minutes=estimated_total_time)
delay_minutes    = round((actual_end_time - planned_end_time).total_seconds() / 60)

delay_type
  "LATE"    — delay_minutes >  ota_grace_minutes
  "EARLY"   — delay_minutes < -ota_grace_minutes
  "ON_TIME" — within ±grace window

delay_category  (Feature 4 — OTA/OTD Delay Classification)
  "NONE"           — route was ON_TIME or EARLY
  "DRIVER_DELAY"   — driver arrived at first stop late
  "EMPLOYEE_DELAY" — an employee caused boarding delay
  "TRAFFIC_DELAY"  — delay attributable to traffic / other causes

The summary columns on RouteManagement are updated in-place.
A RouteDelayEvent row is inserted for full audit history.

Helper
------
parse_hhmm_to_minutes(value: str | None) -> int | None
    Parses "HH:MM" or "HH:MM:SS" strings stored on RouteManagementBooking
    columns (estimated_pick_up_time, actual_pick_up_time, etc.) to total
    minutes from midnight.  Returns None for None / bad input.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import logging

from sqlalchemy.orm import Session

from app.models.route_management import RouteManagement
from app.models.route_delay_event import RouteDelayEvent
from app.models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def parse_hhmm_to_minutes(value: Optional[str]) -> Optional[int]:
    """
    Convert a time string "HH:MM" or "HH:MM:SS" to total minutes from midnight.

    Returns None if the input is None, empty, or cannot be parsed.

    Examples
    --------
    >>> parse_hhmm_to_minutes("09:30")
    570
    >>> parse_hhmm_to_minutes("09:30:45")
    570
    >>> parse_hhmm_to_minutes(None)
    None
    """
    if not value:
        return None
    try:
        parts = value.strip().split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours * 60 + minutes
    except (IndexError, ValueError):
        logger.warning("[parse_hhmm_to_minutes] Cannot parse time string: %r", value)
        return None


# ---------------------------------------------------------------------------
# Main tagging function
# ---------------------------------------------------------------------------

def tag_trip_delay(
    db: Session,
    route: RouteManagement,
    now: datetime,
) -> None:
    """
    Compute and persist the OTD (On Time Delivery) delay for *route*.

    This function mutates *route* in-place (delay_type, delay_minutes,
    delay_tagged_at) and inserts a RouteDelayEvent row.  It does **not**
    commit — the caller is responsible for the commit.

    Parameters
    ----------
    db    : active SQLAlchemy session (no commit called here)
    route : RouteManagement ORM object; must have actual_start_time and
            actual_end_time already set
    now   : current IST timestamp (pass the same value used for actual_end_time)

    Side effects
    ------------
    - Sets route.delay_type, route.delay_minutes, route.delay_tagged_at
    - Inserts one RouteDelayEvent(event_kind="OTD") row with delay_category
    - Logs result at INFO level
    """
    # --- Guard: can only tag if we have start time and estimated duration ---
    if not route.actual_start_time:
        logger.warning(
            "[tag_trip_delay] route %s has no actual_start_time — skipping delay tag.",
            route.route_id,
        )
        return

    if route.estimated_total_time is None:
        logger.warning(
            "[tag_trip_delay] route %s has no estimated_total_time — skipping delay tag.",
            route.route_id,
        )
        return

    # --- Compute planned vs actual end time ---
    planned_end_time: datetime = route.actual_start_time + timedelta(
        minutes=float(route.estimated_total_time)
    )
    actual_end_time: datetime = route.actual_end_time or now

    raw_delay_seconds = (actual_end_time - planned_end_time).total_seconds()
    delay_minutes: int = round(raw_delay_seconds / 60)

    grace: int = route.ota_grace_minutes if route.ota_grace_minutes is not None else 5

    if delay_minutes > grace:
        delay_type = "LATE"
    elif delay_minutes < -grace:
        delay_type = "EARLY"
    else:
        delay_type = "ON_TIME"

    # --- Update summary columns on the route ---
    route.delay_type = delay_type
    route.delay_minutes = delay_minutes
    route.delay_tagged_at = now

    # --- Resolve delay classification category (Feature 4) ---------------
    delay_category = _resolve_delay_category(
        db=db, route=route, delay_type=delay_type
    )

    # --- Insert audit event ---
    event = RouteDelayEvent(
        route_id=route.route_id,
        tenant_id=route.tenant_id,
        event_kind="OTD",
        delay_type=delay_type,
        delay_minutes=delay_minutes,
        delay_category=delay_category,
        notes=(
            f"planned_end={planned_end_time.isoformat()}, "
            f"actual_end={actual_end_time.isoformat()}, "
            f"grace={grace}min, "
            f"category={delay_category}"
        ),
        tagged_at=now,
    )
    db.add(event)

    logger.info(
        "[tag_trip_delay] route=%s tenant=%s OTD delay_type=%s delay_minutes=%d "
        "delay_category=%s (planned_end=%s, actual_end=%s, grace=%dmin)",
        route.route_id,
        route.tenant_id,
        delay_type,
        delay_minutes,
        delay_category,
        planned_end_time.strftime("%H:%M"),
        actual_end_time.strftime("%H:%M"),
        grace,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_delay_category(
    db: Session,
    route: RouteManagement,
    delay_type: str,
) -> str:
    """
    Look up tenant grace config and call the classification service.

    Falls back to safe defaults if TenantConfig is missing.
    Never raises.
    """
    try:
        # Import here to avoid circular-import at module load time
        from app.services.delay_classification_service import classify_delay_category

        # Fetch per-tenant grace overrides (best-effort; defaults used on miss)
        config: Optional[TenantConfig] = (
            db.query(TenantConfig)
            .filter(TenantConfig.tenant_id == route.tenant_id)
            .first()
        )
        driver_grace = (
            config.delay_driver_grace_minutes
            if config and config.delay_driver_grace_minutes is not None
            else 10
        )
        employee_grace = (
            config.delay_employee_grace_minutes
            if config and config.delay_employee_grace_minutes is not None
            else 5
        )

        return classify_delay_category(
            route=route,
            delay_type=delay_type,
            db=db,
            driver_grace_minutes=driver_grace,
            employee_grace_minutes=employee_grace,
        )
    except Exception:
        logger.exception(
            "[tag_trip_delay] Failed to classify delay category for route=%s "
            "— defaulting to TRAFFIC_DELAY",
            route.route_id,
        )
        return "TRAFFIC_DELAY"

