"""
app/services/stale_driver_service.py
--------------------------------------
IMP-5 — Stale Driver Alerting.

Called by the APScheduler every 2 minutes.

Logic
-----
For each tenant, the job finds all ONGOING routes whose driver has not sent
a GPS ping within the past `stale_driver_threshold_minutes` (default 5 min).
When a stale route is detected, an FCM alert is dispatched to all active
admins for that tenant.

Deduplication
-------------
A module-level dict ``_last_alert_at`` keyed by route_id holds the last time
an alert was sent for that route.  A new alert is suppressed if the previous
one was sent within the last 10 minutes.  The dict is reset on process restart
(acceptable: ops admins get at most one extra alert after a deploy).

Session ownership
-----------------
The job creates its own ``SessionLocal()`` instance so the scheduler thread
owns the connection — it is not shared with any request-handler session.
The session is always closed in a ``finally`` block.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.session import SessionLocal
from app.models.driver_location_history import DriverLocationHistory
from app.models.route_management import RouteManagement
from app.models.route_management import RouteManagementStatusEnum
from app.models.tenant_config import TenantConfig
from app.models.user_session import UserSession

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-process deduplication: route_id → last alert datetime (UTC)
# ---------------------------------------------------------------------------
_last_alert_at: Dict[int, datetime] = {}

# Minimum gap between two alerts for the same route (minutes).
_ALERT_COOLDOWN_MINUTES: int = 10

# Default staleness threshold when TenantConfig row is missing.
_DEFAULT_THRESHOLD_MINUTES: int = 5


# ---------------------------------------------------------------------------
# Module-level runner — used by SchedulerService
# ---------------------------------------------------------------------------

def run_stale_driver_check_job() -> None:
    """
    Called by APScheduler every 2 minutes.
    Creates its own DB session so the scheduler thread owns the connection.
    """
    db: Session = SessionLocal()
    try:
        _run_check(db)
    except Exception:
        logger.exception("[stale_driver_job] Unhandled error")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _run_check(db: Session) -> None:
    now_utc = datetime.now(timezone.utc)

    # ── Step 1: Find all ONGOING routes grouped by tenant ─────────────────
    ongoing_routes = (
        db.query(RouteManagement)
        .filter(RouteManagement.status == RouteManagementStatusEnum.ONGOING)
        .all()
    )

    if not ongoing_routes:
        logger.debug("[stale_driver] No ONGOING routes — nothing to check.")
        return

    logger.debug("[stale_driver] Checking %d ONGOING route(s).", len(ongoing_routes))

    # ── Step 2: Batch load the latest ping time per route ─────────────────
    route_ids = [r.route_id for r in ongoing_routes]
    latest_pings = (
        db.query(
            DriverLocationHistory.route_id,
            func.max(DriverLocationHistory.recorded_at).label("last_ping"),
        )
        .filter(DriverLocationHistory.route_id.in_(route_ids))
        .group_by(DriverLocationHistory.route_id)
        .all()
    )
    last_ping_map: Dict[int, datetime] = {row.route_id: row.last_ping for row in latest_pings}

    # ── Step 3: Load tenant configs for threshold resolution ──────────────
    tenant_ids = list({r.tenant_id for r in ongoing_routes})
    configs = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id.in_(tenant_ids))
        .all()
    )
    threshold_map: Dict[str, int] = {
        c.tenant_id: (c.stale_driver_threshold_minutes or _DEFAULT_THRESHOLD_MINUTES)
        for c in configs
    }

    # ── Step 4: Identify stale routes ─────────────────────────────────────
    stale_routes = []
    for route in ongoing_routes:
        threshold_min = threshold_map.get(route.tenant_id, _DEFAULT_THRESHOLD_MINUTES)
        last_ping = last_ping_map.get(route.route_id)

        if last_ping is None:
            # Never sent a ping — consider stale only if route has been
            # ongoing for longer than the threshold.
            if route.actual_start_time is None:
                continue
            start = route.actual_start_time
            # Normalise to UTC-aware if naive
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            elapsed_min = (now_utc - start).total_seconds() / 60
        else:
            # Normalise last_ping to UTC-aware if naive
            if last_ping.tzinfo is None:
                last_ping = last_ping.replace(tzinfo=timezone.utc)
            elapsed_min = (now_utc - last_ping).total_seconds() / 60

        if elapsed_min < threshold_min:
            continue  # Driver is active

        # Cooldown check — suppress if alerted recently
        prev_alert = _last_alert_at.get(route.route_id)
        if prev_alert is not None:
            since_last = (now_utc - prev_alert).total_seconds() / 60
            if since_last < _ALERT_COOLDOWN_MINUTES:
                logger.debug(
                    "[stale_driver] route=%s already alerted %.1f min ago — suppressed",
                    route.route_id, since_last,
                )
                continue

        stale_routes.append((route, elapsed_min))

    if not stale_routes:
        logger.debug("[stale_driver] No stale drivers detected this tick.")
        return

    logger.info("[stale_driver] %d stale route(s) detected.", len(stale_routes))

    # ── Step 5: Alert admins ───────────────────────────────────────────────
    for route, elapsed_min in stale_routes:
        _alert_admins(db=db, route=route, elapsed_min=elapsed_min, now_utc=now_utc)


def _alert_admins(
    db: Session,
    route: RouteManagement,
    elapsed_min: float,
    now_utc: datetime,
) -> None:
    """Send FCM to all active admins of the tenant; update cooldown dict."""
    try:
        admin_sessions = (
            db.query(UserSession.user_id)
            .filter(
                UserSession.tenant_id == route.tenant_id,
                UserSession.user_type == "admin",
                UserSession.is_active.is_(True),
                UserSession.fcm_token.isnot(None),
            )
            .all()
        )

        if not admin_sessions:
            logger.debug(
                "[stale_driver] No active admin sessions for tenant=%s — skipping FCM",
                route.tenant_id,
            )
            # Still stamp the cooldown so we don't hammer the DB every 2 min.
            _last_alert_at[route.route_id] = now_utc
            return

        from app.services.unified_notification_service import UnifiedNotificationService

        svc = UnifiedNotificationService(db)
        minutes_str = f"{elapsed_min:.0f}"

        for row in admin_sessions:
            try:
                svc.send_to_user(
                    user_type="admin",
                    user_id=row.user_id,
                    title="Driver Location Update Overdue",
                    body=(
                        f"No GPS ping received for route {route.route_code or route.route_id} "
                        f"in the last {minutes_str} min. Please verify the driver's status."
                    ),
                    data={
                        "type":        "stale_driver",
                        "route_id":    str(route.route_id),
                        "route_code":  str(route.route_code or ""),
                        "driver_id":   str(route.assigned_driver_id or ""),
                        "elapsed_min": minutes_str,
                    },
                    priority="high",
                )
            except Exception:
                logger.exception(
                    "[stale_driver] FCM failed for admin user_id=%s route=%s",
                    row.user_id, route.route_id,
                )

        # Stamp cooldown regardless of individual FCM outcomes
        _last_alert_at[route.route_id] = now_utc

        logger.info(
            "[stale_driver] Alerted %d admin(s) for route=%s (%.0f min stale)",
            len(admin_sessions), route.route_id, elapsed_min,
        )

    except Exception:
        logger.exception(
            "[stale_driver] Failed to alert admins for route=%s", route.route_id
        )
