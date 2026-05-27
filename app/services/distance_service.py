"""
app/services/distance_service.py
----------------------------------
IMP-8 — Actual Distance Tracking.

Called synchronously inside `end_duty` (before db.commit()) to compute the
total GPS distance covered by the driver during the route and persist it to
RouteManagement.actual_total_distance.

Algorithm
---------
1. Load all DriverLocationHistory rows for the route ordered by recorded_at.
2. Walk consecutive (lat, lng) pairs and sum the geodesic distances.
3. Write the total (km, rounded to 3 decimal places) into
   route.actual_total_distance.

The call is wrapped in a try/except by the caller so that a failure here
never blocks duty completion.

Minimum pings
-------------
At least 2 pings are required to produce a non-zero distance.  Routes with
0 or 1 pings get actual_total_distance = 0.0 (not NULL) so that downstream
aggregations never need to handle NULL.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from geopy.distance import geodesic
from sqlalchemy.orm import Session

from app.models.driver_location_history import DriverLocationHistory
from app.models.route_management import RouteManagement

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_and_persist_actual_distance(
    db: Session,
    route: RouteManagement,
) -> float:
    """
    Compute the cumulative GPS distance for *route* and write it to
    ``route.actual_total_distance``.

    Does **not** call ``db.commit()`` — the caller owns the transaction.

    Returns
    -------
    float
        Total distance in kilometres (0.0 if fewer than 2 pings exist).
    """
    route_id = route.route_id

    pings = (
        db.query(DriverLocationHistory.latitude, DriverLocationHistory.longitude)
        .filter(DriverLocationHistory.route_id == route_id)
        .order_by(DriverLocationHistory.recorded_at.asc())
        .all()
    )

    if len(pings) < 2:
        logger.debug(
            "[distance_service] route=%s has %d ping(s) — distance=0.0 km",
            route_id, len(pings),
        )
        route.actual_total_distance = 0.0
        db.add(route)
        return 0.0

    total_km: float = 0.0
    for i in range(1, len(pings)):
        prev = pings[i - 1]
        curr = pings[i]
        try:
            segment_km = geodesic(
                (prev.latitude, prev.longitude),
                (curr.latitude, curr.longitude),
            ).kilometers
            total_km += segment_km
        except Exception as exc:  # noqa: BLE001 — malformed coord pair; skip segment
            logger.warning(
                "[distance_service] route=%s segment %d→%d geodesic error: %s",
                route_id, i - 1, i, exc,
            )

    total_km = round(total_km, 3)
    route.actual_total_distance = total_km
    db.add(route)

    logger.info(
        "[distance_service] route=%s actual_distance=%.3f km (%d pings)",
        route_id, total_km, len(pings),
    )
    return total_km
