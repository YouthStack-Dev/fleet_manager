"""
app/services/driver_duty_hours_service.py
------------------------------------------
Feature 1 — Driver Duty Hours & Rest-Time Enforcement

Core logic for checking whether a driver has had sufficient rest before being
assigned to a new route.

Algorithm
---------
1. Define a 24-hour lookback window:
       window_start = proposed_start_dt - 24h
       window_end   = proposed_start_dt

2. Query all COMPLETED / ONGOING routes where:
       assigned_driver_id = driver_id
       actual_start_time  < window_end        (trip starts before window closes)
       actual_end_time    > window_start       (trip ends after window opens)
       actual_start_time IS NOT NULL

3. Merge overlapping/adjacent busy intervals into a sorted list of
   non-overlapping segments:  [(busy_start, busy_end), ...]

4. Walk the gaps between consecutive busy segments (and the gap after the last
   segment up to `proposed_start_dt`) to find the **longest continuous free
   (rest) gap** within the window.

5. required_rest_minutes = 24 * 60 − max_duty_minutes

6. Return a result dict:
   {
       ok                    : bool,       # True when rest gap ≥ required
       rest_gap_minutes      : int,        # Longest continuous rest gap found
       required_rest_minutes : int,        # Computed from config
       total_duty_minutes    : int,        # Sum of all duty time in window
       last_trip_end         : datetime | None,
   }

No exceptions are raised; all errors are handled gracefully (returns ok=True
with rest_gap_minutes = 24*60 when data is unavailable/insufficient).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_rest(
    driver_id: int,
    proposed_start_dt: datetime,
    db: Session,
    max_duty_minutes: int = 600,
) -> dict:
    """
    Check whether *driver_id* has had enough rest by *proposed_start_dt*.

    Parameters
    ----------
    driver_id           : DB primary key of the driver to check.
    proposed_start_dt   : When the new trip would (approximately) start.
    db                  : Active SQLAlchemy session.
    max_duty_minutes    : Configured maximum duty minutes in 24h (default 600).

    Returns
    -------
    dict with keys:
        ok                    bool
        rest_gap_minutes      int   – longest continuous rest gap (minutes)
        required_rest_minutes int
        total_duty_minutes    int   – sum of all duty minutes in the 24h window
        last_trip_end         Optional[datetime]
    """
    try:
        return _check_rest_impl(driver_id, proposed_start_dt, db, max_duty_minutes)
    except Exception:
        # Fail open: if the check crashes, do not block the assignment
        required = 24 * 60 - max_duty_minutes
        return {
            "ok": True,
            "rest_gap_minutes": 24 * 60,
            "required_rest_minutes": required,
            "total_duty_minutes": 0,
            "last_trip_end": None,
        }


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

def _check_rest_impl(
    driver_id: int,
    proposed_start_dt: datetime,
    db: Session,
    max_duty_minutes: int,
) -> dict:
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum

    window_start: datetime = proposed_start_dt - timedelta(hours=24)
    window_end: datetime   = proposed_start_dt
    required_rest: int     = 24 * 60 - max_duty_minutes

    # Retrieve all routes that overlap with the 24-hour window
    eligible_statuses = [
        RouteManagementStatusEnum.COMPLETED,
        RouteManagementStatusEnum.ONGOING,
    ]
    routes = (
        db.query(
            RouteManagement.actual_start_time,
            RouteManagement.actual_end_time,
        )
        .filter(
            RouteManagement.assigned_driver_id == driver_id,
            RouteManagement.actual_start_time.isnot(None),
            RouteManagement.actual_start_time < window_end,
            RouteManagement.status.in_(eligible_statuses),
        )
        .all()
    )

    if not routes:
        # No trips in window — driver is well-rested
        return {
            "ok": True,
            "rest_gap_minutes": 24 * 60,
            "required_rest_minutes": required_rest,
            "total_duty_minutes": 0,
            "last_trip_end": None,
        }

    # Build a list of (clipped_start, clipped_end) within the window
    intervals: list[tuple[datetime, datetime]] = []
    last_trip_end: Optional[datetime] = None

    for row in routes:
        trip_start: datetime = row.actual_start_time
        # If no actual_end_time (ongoing), treat end as window_end
        trip_end: datetime = row.actual_end_time if row.actual_end_time else window_end

        if last_trip_end is None or trip_end > last_trip_end:
            last_trip_end = trip_end

        # Clip to window boundaries
        clipped_start = max(trip_start, window_start)
        clipped_end   = min(trip_end,   window_end)
        if clipped_end > clipped_start:
            intervals.append((clipped_start, clipped_end))

    if not intervals:
        return {
            "ok": True,
            "rest_gap_minutes": 24 * 60,
            "required_rest_minutes": required_rest,
            "total_duty_minutes": 0,
            "last_trip_end": last_trip_end,
        }

    # Sort intervals by start time, then merge overlapping segments
    intervals.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [intervals[0]]
    for seg_start, seg_end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if seg_start <= prev_end:
            # Overlapping or adjacent — extend
            merged[-1] = (prev_start, max(prev_end, seg_end))
        else:
            merged.append((seg_start, seg_end))

    # Compute total duty minutes (sum of merged segments)
    total_duty_minutes: int = sum(
        int((e - s).total_seconds() / 60)
        for s, e in merged
    )

    # Find the longest continuous rest gap
    # Gaps are: [window_start → merged[0].start], between segments, and is
    # not extended past proposed_start_dt (= window_end) because we only
    # care about rest *before* the new trip starts.
    gap_candidates: list[int] = []

    # Gap before first busy segment
    first_gap = int((merged[0][0] - window_start).total_seconds() / 60)
    gap_candidates.append(max(0, first_gap))

    # Gaps between consecutive busy segments
    for i in range(len(merged) - 1):
        gap = int((merged[i + 1][0] - merged[i][1]).total_seconds() / 60)
        gap_candidates.append(max(0, gap))

    # Gap after last busy segment up to window_end (= proposed_start_dt)
    last_gap = int((window_end - merged[-1][1]).total_seconds() / 60)
    gap_candidates.append(max(0, last_gap))

    rest_gap_minutes: int = max(gap_candidates)
    ok: bool = rest_gap_minutes >= required_rest

    return {
        "ok": ok,
        "rest_gap_minutes": rest_gap_minutes,
        "required_rest_minutes": required_rest,
        "total_duty_minutes": total_duty_minutes,
        "last_trip_end": last_trip_end,
    }
