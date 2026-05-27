"""
app/services/speed_violation_service.py
-----------------------------------------
IMP-10 — Server-side Speed Violation Detection.

Called as a BackgroundTask on every POST /driver/location ping **when the
device reports a speed value**.

Logic
-----
1. Resolve the effective speed limit for the vehicle+tenant
   (vehicle override → tenant config → 60 km/h fallback).
2. If the reported speed does not exceed the limit → return immediately.
3. Insert a SpeedViolation row.
4. Push FCM to all active admin sessions for the tenant so the ops team
   is alerted in real-time.

Design decisions
----------------
* Server-side insert only — the full email-escalation pipeline already
  exists on the client-facing `POST /speed-violations/` endpoint; we reuse
  the same SpeedViolation table without duplicating that machinery.
* FCM to admins only — drivers and employees do not receive this alert.
* All exceptions are swallowed by the caller's wrapper so that a violation
  recording failure never affects the GPS ping HTTP response.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.speed_violation import SpeedViolation
from app.models.tenant_config import TenantConfig
from app.models.vehicle import Vehicle
from app.models.user_session import UserSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_and_record_speed_violation(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_id: int,
    vehicle_id: Optional[int],
    speed_kmph: float,
    latitude: float,
    longitude: float,
    recorded_at: datetime,
) -> None:
    """
    Check whether *speed_kmph* exceeds the effective limit; if so, insert a
    SpeedViolation row and push FCM alerts to all active tenant admins.

    All exceptions are caught and logged — never re-raised.
    """
    try:
        _run_violation_check(
            db=db,
            tenant_id=tenant_id,
            route_id=route_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            speed_kmph=speed_kmph,
            latitude=latitude,
            longitude=longitude,
            recorded_at=recorded_at,
        )
    except Exception:
        logger.exception(
            "[speed_violation] Unexpected error for route=%s driver=%s speed=%.1f",
            route_id, driver_id, speed_kmph,
        )


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _get_speed_limit(db: Session, tenant_id: str, vehicle_id: Optional[int]) -> float:
    """
    Resolve effective speed limit.

    Priority:
      1. Vehicle-specific override (vehicles.speed_limit_override_kmph)
      2. Tenant-wide limit (tenant_configs.speed_limit_kmph)
      3. Hard fallback: 60 km/h
    """
    if vehicle_id:
        override = (
            db.query(Vehicle.speed_limit_override_kmph)
            .filter(Vehicle.vehicle_id == vehicle_id)
            .scalar()
        )
        if override is not None:
            return float(override)

    tenant_limit = (
        db.query(TenantConfig.speed_limit_kmph)
        .filter(TenantConfig.tenant_id == tenant_id)
        .scalar()
    )
    return float(tenant_limit) if tenant_limit is not None else 60.0


def _run_violation_check(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_id: int,
    vehicle_id: Optional[int],
    speed_kmph: float,
    latitude: float,
    longitude: float,
    recorded_at: datetime,
) -> None:
    limit = _get_speed_limit(db, tenant_id, vehicle_id)

    if speed_kmph <= limit:
        logger.debug(
            "[speed_violation] route=%s driver=%s speed=%.1f <= limit=%.1f — no violation",
            route_id, driver_id, speed_kmph, limit,
        )
        return

    logger.info(
        "[speed_violation] route=%s driver=%s speed=%.1f > limit=%.1f — recording violation",
        route_id, driver_id, speed_kmph, limit,
    )

    # --- Persist violation ---
    violation = SpeedViolation(
        tenant_id      = tenant_id,
        route_id       = route_id,
        driver_id      = driver_id,
        vehicle_id     = vehicle_id,
        speed_recorded = speed_kmph,
        speed_limit    = limit,
        latitude       = latitude,
        longitude      = longitude,
        recorded_at    = recorded_at,
    )
    db.add(violation)
    db.commit()

    logger.debug(
        "[speed_violation] Inserted violation for route=%s overspeed_by=%.1f",
        route_id, speed_kmph - limit,
    )

    # --- Notify admins via FCM ---
    _notify_admins(
        db=db,
        tenant_id=tenant_id,
        route_id=route_id,
        driver_id=driver_id,
        speed_kmph=speed_kmph,
        limit=limit,
    )


def _notify_admins(
    db: Session,
    tenant_id: str,
    route_id: int,
    driver_id: int,
    speed_kmph: float,
    limit: float,
) -> None:
    """Push FCM speed-violation alert to every active admin for the tenant."""
    try:
        admin_sessions = (
            db.query(UserSession.user_id)
            .filter(
                UserSession.tenant_id == tenant_id,
                UserSession.user_type == "admin",
                UserSession.is_active.is_(True),
                UserSession.fcm_token.isnot(None),
            )
            .all()
        )

        if not admin_sessions:
            logger.debug(
                "[speed_violation] No active admin sessions for tenant=%s — skipping FCM",
                tenant_id,
            )
            return

        from app.services.unified_notification_service import UnifiedNotificationService

        svc = UnifiedNotificationService(db)
        overspeed = round(speed_kmph - limit, 1)

        for row in admin_sessions:
            try:
                svc.send_to_user(
                    user_type="admin",
                    user_id=row.user_id,
                    title="Speed Violation Detected",
                    body=(
                        f"Driver (ID {driver_id}) on route {route_id} is travelling at "
                        f"{speed_kmph:.0f} km/h — {overspeed} km/h over the {limit:.0f} km/h limit."
                    ),
                    data={
                        "type":       "speed_violation",
                        "route_id":   str(route_id),
                        "driver_id":  str(driver_id),
                        "speed":      str(speed_kmph),
                        "limit":      str(limit),
                        "overspeed":  str(overspeed),
                    },
                    priority="high",
                )
            except Exception:
                logger.exception(
                    "[speed_violation] FCM failed for admin user_id=%s", row.user_id
                )

        logger.info(
            "[speed_violation] FCM dispatched to %d admin(s) for route=%s",
            len(admin_sessions), route_id,
        )

    except Exception:
        logger.exception(
            "[speed_violation] Failed to notify admins for route=%s", route_id
        )
