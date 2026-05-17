"""
Dashboard summary API — tenant-scoped operational snapshot for today.

GET /api/v1/dashboard/summary
  - Bookings by status (today)
  - Routes by status (today's shift routes)
  - Active drivers / vehicles / employees / vendors
  - Shift breakdown (IN vs OUT, nodal vs door-pickup)
  - Today's completion rate

Caching:
  - Normal TTL  : 5 minutes  (300 s) per tenant
  - Hard-refresh: ?refresh=true — bypasses cache; guarded by a 30-second
                  per-tenant cooldown key so clients cannot spam invalidations.
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.booking import Booking, BookingStatusEnum
from app.models.driver import Driver
from app.models.employee import Employee
from app.models.route_management import RouteManagement, RouteManagementStatusEnum
from app.models.shift import Shift, PickupTypeEnum, ShiftLogTypeEnum
from app.models.vendor import Vendor
from app.models.vehicle import Vehicle
from app.utils.cache_manager import cache
from app.utils.response_utils import ResponseWrapper, handle_db_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ──────────────────────────────────────────────────────────────
# Cache key helpers
# ──────────────────────────────────────────────────────────────
_SUMMARY_TTL     = 300   # 5 minutes — normal cache lifetime
_COOLDOWN_TTL    = 30    # 30 seconds — hard-refresh rate-limit per tenant


def _summary_key(tenant_id: str, today: str) -> str:
    return f"dashboard_summary:{tenant_id}:{today}"


def _cooldown_key(tenant_id: str) -> str:
    return f"dashboard_refresh_cooldown:{tenant_id}"


# ──────────────────────────────────────────────────────────────
# DB query helpers
# ──────────────────────────────────────────────────────────────

def _build_summary(db: Session, tenant_id: str, today: date) -> dict:
    """Execute all dashboard DB queries and return a plain dict."""

    today_str = today.isoformat()

    # ── 1. Bookings by status (today) ─────────────────────────
    booking_rows = (
        db.query(
            Booking.status,
            func.count(Booking.booking_id).label("cnt"),
        )
        .filter(
            Booking.tenant_id == tenant_id,
            Booking.booking_date == today,
        )
        .group_by(Booking.status)
        .all()
    )

    bookings_by_status: dict = {s.value: 0 for s in BookingStatusEnum}
    total_bookings = 0
    for status, cnt in booking_rows:
        key = status.value if hasattr(status, "value") else status
        bookings_by_status[key] = cnt
        total_bookings += cnt

    completed = bookings_by_status.get(BookingStatusEnum.COMPLETED.value, 0)
    completion_rate = round(completed / total_bookings * 100, 2) if total_bookings else 0.0

    # ── 2. Routes by status (all active routes for this tenant today) ─
    # "Today's routes" = routes whose linked bookings are dated today.
    # We filter route_management by tenant + created_at date as a proxy;
    # the route_code / shift is tenant-scoped anyway.
    route_rows = (
        db.query(
            RouteManagement.status,
            func.count(RouteManagement.route_id).label("cnt"),
        )
        .filter(
            RouteManagement.tenant_id == tenant_id,
            RouteManagement.is_active == True,
            func.date(RouteManagement.created_at) == today,
        )
        .group_by(RouteManagement.status)
        .all()
    )

    routes_by_status: dict = {s.value: 0 for s in RouteManagementStatusEnum}
    total_routes = 0
    for status, cnt in route_rows:
        key = status.value if hasattr(status, "value") else status
        routes_by_status[key] = cnt
        total_routes += cnt

    # ── 3. Active drivers (tenant-scoped via vendor) ───────────
    active_drivers = (
        db.query(func.count(Driver.driver_id))
        .join(Vendor, Driver.vendor_id == Vendor.vendor_id)
        .filter(
            Vendor.tenant_id == tenant_id,
            Driver.is_active == True,
            Vendor.is_active == True,
        )
        .scalar() or 0
    )

    # ── 4. Active vehicles (tenant-scoped via vendor) ──────────
    active_vehicles = (
        db.query(func.count(Vehicle.vehicle_id))
        .join(Vendor, Vehicle.vendor_id == Vendor.vendor_id)
        .filter(
            Vendor.tenant_id == tenant_id,
            Vehicle.is_active == True,
            Vendor.is_active == True,
        )
        .scalar() or 0
    )

    # ── 5. Active employees ────────────────────────────────────
    active_employees = (
        db.query(func.count(Employee.employee_id))
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.is_active == True,
        )
        .scalar() or 0
    )

    # ── 6. Active vendors ──────────────────────────────────────
    active_vendors = (
        db.query(func.count(Vendor.vendor_id))
        .filter(
            Vendor.tenant_id == tenant_id,
            Vendor.is_active == True,
        )
        .scalar() or 0
    )

    # ── 7. Shift breakdown ─────────────────────────────────────
    shift_rows = (
        db.query(
            Shift.log_type,
            Shift.pickup_type,
            func.count(Shift.shift_id).label("cnt"),
        )
        .filter(
            Shift.tenant_id == tenant_id,
            Shift.is_active == True,
        )
        .group_by(Shift.log_type, Shift.pickup_type)
        .all()
    )

    shift_breakdown = {
        "IN":  {"door_pickup": 0, "nodal": 0, "total": 0},
        "OUT": {"door_pickup": 0, "nodal": 0, "total": 0},
    }
    total_shifts = 0
    for log_type, pickup_type, cnt in shift_rows:
        lt = log_type.value if hasattr(log_type, "value") else log_type
        pt = pickup_type.value if (pickup_type and hasattr(pickup_type, "value")) else pickup_type
        if lt not in shift_breakdown:
            shift_breakdown[lt] = {"door_pickup": 0, "nodal": 0, "total": 0}
        if pt == PickupTypeEnum.NODAL.value:
            shift_breakdown[lt]["nodal"] += cnt
        else:
            shift_breakdown[lt]["door_pickup"] += cnt
        shift_breakdown[lt]["total"] += cnt
        total_shifts += cnt

    # ── 8. Today's ongoing routes (drivers on road right now) ─
    ongoing_routes = routes_by_status.get(RouteManagementStatusEnum.ONGOING.value, 0)

    return {
        "date": today_str,
        "bookings": {
            "total": total_bookings,
            "by_status": bookings_by_status,
            "completion_rate_pct": completion_rate,
        },
        "routes": {
            "total": total_routes,
            "by_status": routes_by_status,
            "ongoing": ongoing_routes,
        },
        "fleet": {
            "active_drivers":   active_drivers,
            "active_vehicles":  active_vehicles,
            "active_vendors":   active_vendors,
        },
        "employees": {
            "active": active_employees,
        },
        "shifts": {
            "total": total_shifts,
            "breakdown": shift_breakdown,
        },
    }


# ──────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_dashboard_summary(
    refresh: bool = Query(False, description="Bypass cache (max once per 30 s per tenant)"),
    tenant_id: str = Query(None, description="Required for superadmin; inferred from token for other roles"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["dashboard.read"], check_tenant=True)),
):
    """
    Return an operational snapshot for today scoped to the caller's tenant.

    - Cached for 5 minutes per tenant per day.
    - `?refresh=true` forces a DB re-query and refreshes the cache, but is
      rate-limited to once every 30 seconds per tenant to prevent cache-
      stampede attacks.
    - Superadmin must pass `?tenant_id=<id>`; all other roles use the tenant
      embedded in their JWT.
    """
    try:
        user_type: str = user_data.get("user_type")
        token_tenant_id: str = user_data.get("tenant_id")

        # Resolve tenant_id — same convention used across all routers
        if user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id query param is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context required",
                    error_code="TENANT_REQUIRED",
                ),
            )

        today = date.today()
        summary_key = _summary_key(tenant_id, today.isoformat())

        # ── Hard-refresh path ──────────────────────────────────
        if refresh:
            cooldown_key = _cooldown_key(tenant_id)
            if cache.exists(cooldown_key):
                # Still in cooldown — return stale cache if available, else query
                cached_data = cache.get(summary_key)
                if cached_data:
                    logger.info(
                        "[dashboard] refresh throttled for tenant=%s, serving cache",
                        tenant_id,
                    )
                    return ResponseWrapper.success(
                        data={**cached_data, "cache_status": "throttled"},
                        message="Dashboard summary (cached — refresh throttled)",
                    )
                # No cache at all: fall through to DB query without resetting cooldown
            else:
                # Arm cooldown BEFORE the query so concurrent requests are blocked
                cache.set(cooldown_key, 1, _COOLDOWN_TTL)
                # Invalidate stale summary so we definitely re-query
                cache.delete(summary_key)

        # ── Normal cache path ──────────────────────────────────
        else:
            cached_data = cache.get(summary_key)
            if cached_data is not None:
                logger.debug(
                    "[dashboard] cache hit for tenant=%s date=%s", tenant_id, today
                )
                return ResponseWrapper.success(
                    data={**cached_data, "cache_status": "hit"},
                    message="Dashboard summary (cached)",
                )

        # ── DB query ───────────────────────────────────────────
        logger.info(
            "[dashboard] querying DB for tenant=%s date=%s refresh=%s",
            tenant_id, today, refresh,
        )
        summary = _build_summary(db, tenant_id, today)
        cache.set(summary_key, summary, _SUMMARY_TTL)

        return ResponseWrapper.success(
            data={**summary, "cache_status": "miss"},
            message="Dashboard summary",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[dashboard] unexpected error: %s", exc)
        raise handle_db_error(exc)
