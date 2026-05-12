"""
Speed Violation Router
======================
POST /api/v1/speed-violations/
    Driver app reports a single speed violation event.
    On record: fires background tasks for email + push alerts and escalation checks.

GET  /api/v1/speed-violations/
    Tenant-wide paginated list.  Filters: route_id, driver_id, date_from, date_to.

GET  /api/v1/speed-violations/route/{route_id}/summary
    Aggregated summary for one ride: total count, max/avg speed, full list.

GET  /api/v1/speed-violations/driver/{driver_id}
    All violations for a specific driver (paginated, optionally filtered by route/date).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import get_db, SessionLocal
from app.models.speed_violation import SpeedViolation
from app.models.driver import Driver
from app.models.vehicle import Vehicle
from app.schemas.speed_violation import (
    SpeedViolationCreate,
    SpeedViolationResponse,
    SpeedViolationListResponse,
    SpeedViolationRouteSummary,
)
from app.utils.response_utils import ResponseWrapper, handle_db_error
from app.core.logging_config import get_logger
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)

router = APIRouter(prefix="/speed-violations", tags=["speed-violations"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_response(
    v: SpeedViolation,
    driver_name: Optional[str],
    vehicle_rc: Optional[str],
) -> SpeedViolationResponse:
    return SpeedViolationResponse(
        violation_id=v.violation_id,
        tenant_id=v.tenant_id,
        route_id=v.route_id,
        driver_id=v.driver_id,
        driver_name=driver_name,
        vehicle_id=v.vehicle_id,
        vehicle_rc=vehicle_rc,
        speed_recorded=v.speed_recorded,
        speed_limit=v.speed_limit,
        overspeed_by=round(v.speed_recorded - v.speed_limit, 2),
        latitude=v.latitude,
        longitude=v.longitude,
        recorded_at=v.recorded_at,
        created_at=v.created_at,
    )


def _enrich_violations(
    db: Session, violations: list[SpeedViolation]
) -> list[SpeedViolationResponse]:
    """Batch-load driver names and vehicle RC numbers for a list of violations."""
    driver_ids  = {v.driver_id  for v in violations if v.driver_id}
    vehicle_ids = {v.vehicle_id for v in violations if v.vehicle_id}

    driver_map:  dict[int, str] = {}
    vehicle_map: dict[int, str] = {}

    if driver_ids:
        rows = (
            db.query(Driver.driver_id, Driver.name)
            .filter(Driver.driver_id.in_(driver_ids))
            .all()
        )
        driver_map = {r.driver_id: r.name for r in rows}

    if vehicle_ids:
        rows = (
            db.query(Vehicle.vehicle_id, Vehicle.rc_number)
            .filter(Vehicle.vehicle_id.in_(vehicle_ids))
            .all()
        )
        vehicle_map = {r.vehicle_id: r.rc_number for r in rows}

    return [
        _to_response(
            v,
            driver_name=driver_map.get(v.driver_id) if v.driver_id else None,
            vehicle_rc=vehicle_map.get(v.vehicle_id) if v.vehicle_id else None,
        )
        for v in violations
    ]


def _get_speed_limit(db: Session, tenant_id: str, vehicle_id: Optional[int]) -> float:
    """
    Resolve the effective speed limit for a given vehicle + tenant.

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
            return override

    from app.models.tenant_config import TenantConfig
    tenant_limit = (
        db.query(TenantConfig.speed_limit_kmph)
        .filter(TenantConfig.tenant_id == tenant_id)
        .scalar()
    )
    return tenant_limit if tenant_limit is not None else 60.0


def _resolve_tenant(user_data: dict, tenant_id_param: Optional[str]) -> str:
    """Extract tenant_id from token (or query param for admin)."""
    user_type = user_data.get("user_type")
    if user_type == "admin":
        if not tenant_id_param:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id query parameter required for admin",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        return tenant_id_param
    tid = user_data.get("tenant_id")
    if not tid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Tenant ID missing in token",
                error_code="TENANT_ID_REQUIRED",
            ),
        )
    return tid


# ---------------------------------------------------------------------------
# Background task: email + push notifications
# ---------------------------------------------------------------------------

async def _send_violation_notifications(
    tenant_id: str,
    driver_id: Optional[int],
    violation_id: int,
    driver_name: str,
    vehicle_rc: str,
    violation_count: int,
    is_escalation: bool = False,
) -> None:
    """
    Fired as a FastAPI BackgroundTask after a violation is persisted.

    1. Finds all managers (employees with alert.read permission) → email + push
    2. Finds vendor of the driver → email
    3. Sends speed violation alert email to all recipients
    4. Sends FCM push to all manager employees
    """
    db = SessionLocal()
    try:
        # --- Load violation record ---
        violation = db.query(SpeedViolation).filter(
            SpeedViolation.violation_id == violation_id
        ).first()
        if not violation:
            return

        # --- Vendor emails ---
        vendor_emails: list[str] = []
        if driver_id:
            from app.models.driver import Driver as DriverModel
            from app.models.vendor import Vendor
            from app.models.vendor_user import VendorUser

            driver = db.query(DriverModel).filter(
                DriverModel.driver_id == driver_id
            ).first()
            if driver and driver.vendor_id:
                vendor = db.query(Vendor).filter(
                    Vendor.vendor_id == driver.vendor_id
                ).first()
                if vendor and vendor.email:
                    vendor_emails.append(vendor.email)

                # Also email active vendor portal users for that vendor
                v_users = db.query(VendorUser.email).filter(
                    VendorUser.vendor_id == driver.vendor_id,
                    VendorUser.is_active.is_(True),
                ).all()
                vendor_emails.extend(r.email for r in v_users if r.email)

        # --- Manager emails + push recipients ---
        manager_emails: list[str]     = []
        push_recipients: list[dict]   = []

        from app.models.employee import Employee
        from app.models.iam.role import Role, role_policy
        from app.models.iam.policy import Policy, policy_permission
        from app.models.iam.permission import Permission

        alert_perm = (
            db.query(Permission)
            .filter(
                Permission.module == "alert",
                Permission.action.in_(["read", "*"]),
            )
            .first()
        )
        if alert_perm:
            managers = (
                db.query(Employee)
                .join(Role, Employee.role_id == Role.role_id)
                .join(role_policy, Role.role_id == role_policy.c.role_id)
                .join(Policy, role_policy.c.policy_id == Policy.policy_id)
                .join(
                    policy_permission,
                    Policy.policy_id == policy_permission.c.policy_id,
                )
                .filter(
                    policy_permission.c.permission_id == alert_perm.permission_id,
                    Employee.tenant_id == tenant_id,
                    Employee.is_active.is_(True),
                )
                .all()
            )
            for mgr in managers:
                if mgr.email:
                    manager_emails.append(mgr.email)
                push_recipients.append(
                    {"user_type": "employee", "user_id": mgr.employee_id}
                )

        # --- Send emails ---
        all_emails = list({*vendor_emails, *manager_emails})   # deduplicated
        if all_emails:
            from app.core.email_service import get_email_service
            email_svc = get_email_service()
            await email_svc.send_speed_violation_alert_email(
                to_emails=all_emails,
                driver_name=driver_name,
                vehicle_rc=vehicle_rc or "N/A",
                speed_recorded=violation.speed_recorded,
                speed_limit=violation.speed_limit,
                recorded_at=violation.recorded_at,
                route_id=violation.route_id,
                latitude=violation.latitude,
                longitude=violation.longitude,
                violation_count_in_ride=violation_count,
                is_escalation=is_escalation,
            )
            logger.info(
                f"Speed violation email sent to {len(all_emails)} recipients "
                f"(tenant={tenant_id}, driver={driver_id}, escalation={is_escalation})"
            )

        # --- Send push notifications to managers ---
        if push_recipients:
            try:
                from app.services.unified_notification_service import UnifiedNotificationService

                notif_svc = UnifiedNotificationService(db)
                title = "🚨 Escalation: Repeated Speeding" if is_escalation else "⚠️ Speed Violation Alert"
                body = (
                    f"{driver_name} recorded {violation.speed_recorded:.1f} km/h "
                    f"(limit {violation.speed_limit:.1f} km/h)"
                )
                notif_svc.send_to_users_batch(
                    recipients=push_recipients,
                    title=title,
                    body=body,
                    data={
                        "type": "speed_violation",
                        "driver_id": str(driver_id or ""),
                        "route_id": str(violation.route_id or ""),
                        "violation_id": str(violation.violation_id),
                        "is_escalation": "1" if is_escalation else "0",
                    },
                )
                logger.info(
                    f"Speed violation push sent to {len(push_recipients)} managers"
                )
            except Exception as push_err:
                logger.warning(f"Push notification failed (non-critical): {push_err}")

    except Exception:
        logger.exception("Error in _send_violation_notifications background task")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Background task: escalation check
# ---------------------------------------------------------------------------

_ESCALATION_LEVELS = [
    # (window_minutes, count_threshold, label)
    (5,  3,  "Level-1"),
    (10, 5,  "Level-2"),
    (20, 10, "Critical"),
]


async def _check_and_escalate(
    tenant_id: str,
    driver_id: Optional[int],
    route_id: Optional[int],
    driver_name: str,
    vehicle_rc: str,
) -> None:
    """
    After each new violation, check whether the driver has crossed any escalation
    threshold on the current ride.  Only fires an escalation notification when the
    count is *exactly* at a threshold boundary to avoid spam.

    Thresholds:
      Level-1  : 3 violations within  5 minutes
      Level-2  : 5 violations within 10 minutes
      Critical : 10 violations within 20 minutes
    """
    if not route_id:
        return

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        for window_min, threshold, label in _ESCALATION_LEVELS:
            since = now - timedelta(minutes=window_min)
            count = (
                db.query(func.count(SpeedViolation.violation_id))
                .filter(
                    SpeedViolation.tenant_id == tenant_id,
                    SpeedViolation.driver_id == driver_id,
                    SpeedViolation.route_id  == route_id,
                    SpeedViolation.recorded_at >= since,
                )
                .scalar()
            ) or 0

            if count == threshold:
                # Exactly hit this threshold → fire escalation once
                logger.warning(
                    f"Speed escalation {label}: driver={driver_id} route={route_id} "
                    f"count={count} in {window_min}min"
                )
                # Get latest violation record for details
                latest = (
                    db.query(SpeedViolation)
                    .filter(
                        SpeedViolation.tenant_id == tenant_id,
                        SpeedViolation.driver_id == driver_id,
                        SpeedViolation.route_id  == route_id,
                    )
                    .order_by(SpeedViolation.recorded_at.desc())
                    .first()
                )
                if latest:
                    await _send_violation_notifications(
                        tenant_id=tenant_id,
                        driver_id=driver_id,
                        violation_id=latest.violation_id,
                        driver_name=driver_name,
                        vehicle_rc=vehicle_rc,
                        violation_count=count,
                        is_escalation=True,
                    )
                break  # Only fire the highest-severity escalation per violation event
    except Exception:
        logger.exception("Error in _check_and_escalate background task")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /speed-violations/ — driver reports a violation
# ---------------------------------------------------------------------------

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Report a speed violation (driver app)",
)
def report_speed_violation(
    payload: SpeedViolationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver_app.access"], check_tenant=True)),
):
    """
    Called by the driver mobile app whenever GPS speed exceeds the configured threshold.

    - Resolves effective speed limit (vehicle override → tenant config → 60 km/h default)
    - Persists the violation record
    - Fires background tasks for email alerts, push notifications, and escalation checks
    """
    try:
        tenant_id = user_data.get("tenant_id")
        driver_id = user_data.get("user_id")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        # Resolve effective speed limit
        speed_limit = _get_speed_limit(db, tenant_id, payload.vehicle_id)

        violation = SpeedViolation(
            tenant_id=tenant_id,
            route_id=payload.route_id,
            driver_id=driver_id,
            vehicle_id=payload.vehicle_id,
            speed_recorded=payload.speed_recorded,
            speed_limit=speed_limit,
            latitude=payload.latitude,
            longitude=payload.longitude,
            recorded_at=payload.recorded_at,
        )
        db.add(violation)
        db.commit()
        db.refresh(violation)

        logger.info(
            f"Speed violation recorded: tenant={tenant_id} driver={driver_id} "
            f"route={payload.route_id} speed={payload.speed_recorded} limit={speed_limit}"
        )

        # Enrich for response
        driver_name = (
            db.query(Driver.name).filter(Driver.driver_id == driver_id).scalar()
            if driver_id else None
        )
        vehicle_rc = (
            db.query(Vehicle.rc_number).filter(
                Vehicle.vehicle_id == payload.vehicle_id
            ).scalar()
            if payload.vehicle_id else None
        )

        # Count violations on this ride (for notification context)
        ride_count = (
            db.query(func.count(SpeedViolation.violation_id))
            .filter(
                SpeedViolation.tenant_id == tenant_id,
                SpeedViolation.driver_id == driver_id,
                SpeedViolation.route_id  == payload.route_id,
            )
            .scalar()
        ) or 1 if payload.route_id else 1

        # Background: notify managers + vendor
        background_tasks.add_task(
            _send_violation_notifications,
            tenant_id=tenant_id,
            driver_id=driver_id,
            violation_id=violation.violation_id,
            driver_name=driver_name or f"Driver #{driver_id}",
            vehicle_rc=vehicle_rc or "N/A",
            violation_count=ride_count,
            is_escalation=False,
        )

        # Background: check escalation thresholds
        background_tasks.add_task(
            _check_and_escalate,
            tenant_id=tenant_id,
            driver_id=driver_id,
            route_id=payload.route_id,
            driver_name=driver_name or f"Driver #{driver_id}",
            vehicle_rc=vehicle_rc or "N/A",
        )

        return ResponseWrapper.created(
            data=_to_response(violation, driver_name, vehicle_rc),
            message="Speed violation recorded",
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error while recording speed violation")
        raise handle_db_error(e)
    except Exception:
        logger.exception("Unexpected error while recording speed violation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


# ---------------------------------------------------------------------------
# GET /speed-violations/ — tenant-wide list
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=SpeedViolationListResponse,
    summary="List speed violations (admin / employee)",
)
def list_speed_violations(
    route_id:        Optional[int]      = Query(None, description="Filter by route/ride ID"),
    driver_id:       Optional[int]      = Query(None, description="Filter by driver ID"),
    date_from:       Optional[datetime] = Query(None, description="Violations on or after (ISO-8601)"),
    date_to:         Optional[datetime] = Query(None, description="Violations on or before (ISO-8601)"),
    page:            int                = Query(1, ge=1),
    limit:           int                = Query(20, ge=1, le=200),
    tenant_id_param: Optional[str]      = Query(None, alias="tenant_id"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["speed_violation.read"], check_tenant=False)),
):
    """Paginated tenant-wide list with optional filters."""
    try:
        resolved_tenant_id = _resolve_tenant(user_data, tenant_id_param)

        q = db.query(SpeedViolation).filter(
            SpeedViolation.tenant_id == resolved_tenant_id
        )
        if route_id  is not None: q = q.filter(SpeedViolation.route_id  == route_id)
        if driver_id is not None: q = q.filter(SpeedViolation.driver_id == driver_id)
        if date_from is not None: q = q.filter(SpeedViolation.recorded_at >= date_from)
        if date_to   is not None: q = q.filter(SpeedViolation.recorded_at <= date_to)

        total = q.count()
        violations = (
            q.order_by(SpeedViolation.recorded_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        return SpeedViolationListResponse(
            items=_enrich_violations(db, violations),
            total=total,
            page=page,
            limit=limit,
            total_pages=math.ceil(total / limit) if total else 0,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error while listing speed violations")
        raise handle_db_error(e)
    except Exception:
        logger.exception("Unexpected error while listing speed violations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


# ---------------------------------------------------------------------------
# GET /speed-violations/route/{route_id}/summary — per-ride summary
# ---------------------------------------------------------------------------

@router.get(
    "/route/{route_id}/summary",
    response_model=SpeedViolationRouteSummary,
    summary="Speed violation summary for a specific ride",
)
def get_route_violation_summary(
    route_id:        int,
    tenant_id_param: Optional[str] = Query(None, alias="tenant_id"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["speed_violation.read"], check_tenant=False)),
):
    """
    Full summary for a ride:
    - Total violation count
    - Driver + vehicle info
    - Max / average recorded speed
    - Speed limit in effect
    - First and last violation timestamps
    - Full ordered list of all individual events
    """
    try:
        resolved_tenant_id = _resolve_tenant(user_data, tenant_id_param)

        violations = (
            db.query(SpeedViolation)
            .filter(
                SpeedViolation.tenant_id == resolved_tenant_id,
                SpeedViolation.route_id  == route_id,
            )
            .order_by(SpeedViolation.recorded_at.asc())
            .all()
        )

        enriched = _enrich_violations(db, violations)

        if not violations:
            return SpeedViolationRouteSummary(
                route_id=route_id,
                total_violations=0,
                driver_id=None, driver_name=None,
                vehicle_id=None, vehicle_rc=None,
                max_speed_recorded=None, avg_speed_recorded=None,
                speed_limit=None,
                first_violation_at=None, last_violation_at=None,
                violations=[],
            )

        speeds = [v.speed_recorded for v in violations]
        first, last = violations[0], violations[-1]

        return SpeedViolationRouteSummary(
            route_id=route_id,
            total_violations=len(violations),
            driver_id=first.driver_id,
            driver_name=enriched[0].driver_name if enriched else None,
            vehicle_id=first.vehicle_id,
            vehicle_rc=enriched[0].vehicle_rc if enriched else None,
            max_speed_recorded=round(max(speeds), 2),
            avg_speed_recorded=round(sum(speeds) / len(speeds), 2),
            speed_limit=first.speed_limit,
            first_violation_at=first.recorded_at,
            last_violation_at=last.recorded_at,
            violations=enriched,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error while fetching route violation summary")
        raise handle_db_error(e)
    except Exception:
        logger.exception("Unexpected error while fetching route violation summary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


# ---------------------------------------------------------------------------
# GET /speed-violations/driver/{driver_id} — by driver
# ---------------------------------------------------------------------------

@router.get(
    "/driver/{driver_id}",
    response_model=SpeedViolationListResponse,
    summary="All speed violations for a specific driver",
)
def get_driver_violations(
    driver_id:       int,
    route_id:        Optional[int]      = Query(None),
    date_from:       Optional[datetime] = Query(None),
    date_to:         Optional[datetime] = Query(None),
    page:            int                = Query(1, ge=1),
    limit:           int                = Query(20, ge=1, le=200),
    tenant_id_param: Optional[str]      = Query(None, alias="tenant_id"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["speed_violation.read"], check_tenant=False)),
):
    """All violations by a specific driver, optionally filtered by route or date."""
    try:
        resolved_tenant_id = _resolve_tenant(user_data, tenant_id_param)

        q = db.query(SpeedViolation).filter(
            SpeedViolation.tenant_id == resolved_tenant_id,
            SpeedViolation.driver_id == driver_id,
        )
        if route_id  is not None: q = q.filter(SpeedViolation.route_id  == route_id)
        if date_from is not None: q = q.filter(SpeedViolation.recorded_at >= date_from)
        if date_to   is not None: q = q.filter(SpeedViolation.recorded_at <= date_to)

        total = q.count()
        violations = (
            q.order_by(SpeedViolation.recorded_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        return SpeedViolationListResponse(
            items=_enrich_violations(db, violations),
            total=total,
            page=page,
            limit=limit,
            total_pages=math.ceil(total / limit) if total else 0,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error while fetching driver violations")
        raise handle_db_error(e)
    except Exception:
        logger.exception("Unexpected error while fetching driver violations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )
