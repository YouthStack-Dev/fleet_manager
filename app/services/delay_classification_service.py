"""
app/services/delay_classification_service.py
---------------------------------------------
OTA/OTD Delay Root-Cause Classification Service  (Feature 4).

Classifies a LATE route into one of three root-cause categories:

  DRIVER_DELAY    — Driver arrived at the first pickup stop more than
                    `delay_driver_grace_minutes` late.

  EMPLOYEE_DELAY  — At least one employee caused a boarding delay greater
                    than `delay_employee_grace_minutes` at their stop.

  TRAFFIC_DELAY   — Route was late but neither the driver nor employees
                    were responsible (e.g. road congestion, diversion).

  NONE            — Route was ON_TIME or EARLY; no delay to classify.

Priority order: DRIVER_DELAY > EMPLOYEE_DELAY > TRAFFIC_DELAY.

This service is intentionally decoupled from the HTTP layer — it operates
purely on ORM objects and a DB session so it can be called from anywhere
(delay_tagging utility, background task, data fix script).

Graceful-degradation contract
------------------------------
If stop-time data (estimated_pick_up_time / actual_pick_up_time) is absent
for all bookings, the function defaults to TRAFFIC_DELAY rather than raising.
All exceptions are caught and logged; callers receive TRAFFIC_DELAY on error.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.route_management import RouteManagement, RouteManagementBooking
from app.utils.delay_tagging import parse_hhmm_to_minutes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category constants  (strings stored in the DB column)
# ---------------------------------------------------------------------------

CATEGORY_NONE           = "NONE"
CATEGORY_DRIVER_DELAY   = "DRIVER_DELAY"
CATEGORY_EMPLOYEE_DELAY = "EMPLOYEE_DELAY"
CATEGORY_TRAFFIC_DELAY  = "TRAFFIC_DELAY"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_delay_category(
    *,
    route: RouteManagement,
    delay_type: str,
    db: Session,
    driver_grace_minutes: int = 10,
    employee_grace_minutes: int = 5,
) -> str:
    """
    Return the delay root-cause category string for *route*.

    Parameters
    ----------
    route                 : RouteManagement ORM object (route_id must exist).
    delay_type            : Pre-computed delay type string — "LATE" | "EARLY"
                            | "ON_TIME".
    db                    : Active SQLAlchemy session (no commit called here).
    driver_grace_minutes  : Tolerance (minutes) before first-stop lateness is
                            attributed to the driver (default 10).
    employee_grace_minutes: Per-stop tolerance before employee boarding delay is
                            counted as the cause (default 5).

    Returns
    -------
    One of: "NONE", "DRIVER_DELAY", "EMPLOYEE_DELAY", "TRAFFIC_DELAY".
    Never raises — logs and returns TRAFFIC_DELAY on unexpected errors.
    """
    try:
        return _classify(
            route=route,
            delay_type=delay_type,
            db=db,
            driver_grace_minutes=driver_grace_minutes,
            employee_grace_minutes=employee_grace_minutes,
        )
    except Exception:
        logger.exception(
            "[classify_delay] Unexpected error for route=%s — defaulting to TRAFFIC_DELAY",
            route.route_id,
        )
        return CATEGORY_TRAFFIC_DELAY


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _classify(
    *,
    route: RouteManagement,
    delay_type: str,
    db: Session,
    driver_grace_minutes: int,
    employee_grace_minutes: int,
) -> str:
    # ── Not late: nothing to classify ──────────────────────────────────────
    if delay_type in ("ON_TIME", "EARLY"):
        return CATEGORY_NONE

    # ── Fetch stop sequence for the route ──────────────────────────────────
    bookings: list[RouteManagementBooking] = (
        db.query(RouteManagementBooking)
        .filter(RouteManagementBooking.route_id == route.route_id)
        .order_by(RouteManagementBooking.order_id.asc())
        .all()
    )

    if not bookings:
        logger.info(
            "[classify_delay] route=%s — no booking stops found; "
            "defaulting to TRAFFIC_DELAY",
            route.route_id,
        )
        return CATEGORY_TRAFFIC_DELAY

    # ── 1. Driver Delay — first-stop lateness ──────────────────────────────
    first = bookings[0]
    first_delay = _stop_delay_minutes(first)
    if first_delay is not None and first_delay > driver_grace_minutes:
        logger.info(
            "[classify_delay] route=%s DRIVER_DELAY "
            "(first_stop_delay=%d min > driver_grace=%d min)",
            route.route_id,
            first_delay,
            driver_grace_minutes,
        )
        return CATEGORY_DRIVER_DELAY

    # ── 2. Employee Delay — any stop with excessive boarding wait ──────────
    for rb in bookings:
        stop_delay = _stop_delay_minutes(rb)
        if stop_delay is not None and stop_delay > employee_grace_minutes:
            logger.info(
                "[classify_delay] route=%s EMPLOYEE_DELAY "
                "(order_id=%s, stop_delay=%d min > employee_grace=%d min)",
                route.route_id,
                rb.order_id,
                stop_delay,
                employee_grace_minutes,
            )
            return CATEGORY_EMPLOYEE_DELAY

    # ── 3. Traffic Delay — default when no other root cause found ──────────
    logger.info(
        "[classify_delay] route=%s TRAFFIC_DELAY "
        "(no driver or employee delays detected)",
        route.route_id,
    )
    return CATEGORY_TRAFFIC_DELAY


def _stop_delay_minutes(rb: RouteManagementBooking) -> Optional[int]:
    """
    Compute (actual_pick_up_time - estimated_pick_up_time) in minutes
    for a single RouteManagementBooking stop.

    Returns None if either timestamp is missing or unparseable.
    Positive result means the stop was late; negative means early.
    """
    if not rb.estimated_pick_up_time or not rb.actual_pick_up_time:
        return None
    est = parse_hhmm_to_minutes(rb.estimated_pick_up_time)
    act = parse_hhmm_to_minutes(rb.actual_pick_up_time)
    if est is None or act is None:
        return None
    return act - est
