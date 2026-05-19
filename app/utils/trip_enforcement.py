"""
app/utils/trip_enforcement.py
------------------------------
One-trip-per-shift enforcement utility.

Called from route_management.py → update_route() when operation == "add".
Replaces the original inline block (lines 3691–3706) that always auto-removed
bookings from other routes regardless of tenant config flags.

Decision matrix
---------------
one_trip_per_shift_enabled = False
    → Skip all enforcement; allow the booking to exist on multiple routes.

one_trip_per_shift_enabled = True, auto_move_on_conflict = True  (default)
    → Auto-remove the booking from any other active route for this tenant.
      Block if the booking is already actively being serviced (ONGOING status).

one_trip_per_shift_enabled = True, auto_move_on_conflict = False
    → Block the entire operation if the booking already exists on another active
      route (same tenant), even if it has not been picked up yet.
      Also block if already ONGOING.
"""

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session
from typing import Set
import logging

from app.models.booking import Booking, BookingStatusEnum
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.utils.response_utils import ResponseWrapper

logger = logging.getLogger(__name__)

# Statuses that mean "this booking is actively being serviced – do not touch it"
_ACTIVE_BOOKING_STATUSES = {BookingStatusEnum.ONGOING, BookingStatusEnum.COMPLETED}


def enforce_one_trip_per_shift(
    db: Session,
    route_id: int,
    tenant_id: str,
    booking_ids: Set[int],
    one_trip_per_shift_enabled: bool,
    auto_move_on_conflict: bool,
) -> None:
    """
    Enforce the one-trip-per-shift policy before adding *booking_ids* to
    *route_id*.

    Parameters
    ----------
    db                          : active SQLAlchemy session
    route_id                    : target route being modified
    tenant_id                   : tenant scope
    booking_ids                 : set of booking IDs being added to route_id
    one_trip_per_shift_enabled  : tenant config flag
    auto_move_on_conflict       : tenant config flag (only used when enforcement is on)

    Raises
    ------
    HTTPException 409  – booking already actively serviced (always blocked)
    HTTPException 409  – booking exists on another route and auto_move=False
    """
    if not one_trip_per_shift_enabled:
        # Feature disabled – nothing to do
        logger.debug(
            "[enforce_one_trip] Enforcement disabled for tenant %s — skipping.",
            tenant_id,
        )
        return

    for booking_id in booking_ids:
        # Find every link for this booking on a *different* route within this tenant
        existing_links = (
            db.query(RouteManagementBooking)
            .join(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .filter(
                RouteManagementBooking.booking_id == booking_id,
                RouteManagementBooking.route_id != route_id,
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.is_active == True,
            )
            .all()
        )

        if not existing_links:
            continue  # No conflict for this booking

        # Check if the booking is already being actively serviced
        booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
        if booking and booking.status in _ACTIVE_BOOKING_STATUSES:
            logger.warning(
                "[enforce_one_trip] Blocked: booking %s is %s — cannot reassign.",
                booking_id,
                booking.status.value,
            )
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=(
                        f"Booking {booking_id} is already {booking.status.value} "
                        "and cannot be moved to another route."
                    ),
                    error_code="BOOKING_ALREADY_ACTIVE",
                    details={"booking_id": booking_id, "booking_status": booking.status.value},
                ),
            )

        if not auto_move_on_conflict:
            # Block mode: reject the entire request
            conflict_route_ids = [link.route_id for link in existing_links]
            logger.warning(
                "[enforce_one_trip] Blocked: booking %s already on routes %s.",
                booking_id,
                conflict_route_ids,
            )
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=(
                        f"Booking {booking_id} is already assigned to route(s) "
                        f"{conflict_route_ids}. Remove it first or enable "
                        "auto-move in tenant config."
                    ),
                    error_code="BOOKING_ALREADY_ASSIGNED",
                    details={
                        "booking_id": booking_id,
                        "conflict_route_ids": conflict_route_ids,
                    },
                ),
            )

        # auto_move_on_conflict == True → silently remove from other routes
        for link in existing_links:
            logger.info(
                "[enforce_one_trip] Auto-moving booking %s from route %s → route %s.",
                booking_id,
                link.route_id,
                route_id,
            )
            db.delete(link)

    # Flush removals so the subsequent INSERT does not hit the unique constraint
    db.flush()
