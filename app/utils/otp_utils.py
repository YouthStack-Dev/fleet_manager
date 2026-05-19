"""
OTP (One-Time Password) utility functions for Fleet Manager
"""

import secrets
from datetime import datetime, time
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def get_required_otp_count(booking_type: str, shift_log_type: str, tenant_config, escort_enabled: bool = False) -> int:
    """
    Determine the number of OTPs required based on booking type and shift type.

    Args:
        booking_type: Type of booking (regular, adhoc, medical_emergency)
        shift_log_type: Type of shift (IN for login, OUT for logout)
        tenant_config: TenantConfig object containing OTP settings
        escort_enabled: Whether escort is assigned to the route AND route requires escort

    Returns:
        Number of OTPs required
    """
    # Count the required OTPs based on boarding/deboarding flags
    if shift_log_type == "IN":
        base_count = (tenant_config.login_boarding_otp + tenant_config.login_deboarding_otp) if tenant_config else 0
    elif shift_log_type == "OUT":
        base_count = (tenant_config.logout_boarding_otp + tenant_config.logout_deboarding_otp) if tenant_config else 0
    else:
        base_count = 0  # default fallback

    # Escort OTP is now generated once at route level and sent directly to the escort.
    # Per-booking escort OTP generation is no longer used.
    return base_count


def generate_otp_codes(count: int) -> list:
    """
    Generate the specified number of cryptographically-secure 4-digit OTP codes.

    Args:
        count: Number of OTP codes to generate

    Returns:
        List of OTP codes (integers)
    """
    return [secrets.randbelow(9000) + 1000 for _ in range(count)]


def is_time_in_escort_range(check_time: time, start_time: time, end_time: time) -> bool:
    """
    Check if a given time falls within the escort-required time range.
    Handles overnight ranges (e.g., 18:00 to 06:00).

    Args:
        check_time: Time to check
        start_time: Start of escort-required period
        end_time: End of escort-required period

    Returns:
        True if time requires escort
    """
    if start_time <= end_time:
        # Same day range (e.g., 09:00 to 17:00)
        return start_time <= check_time <= end_time
    else:
        # Overnight range (e.g., 18:00 to 06:00)
        return check_time >= start_time or check_time <= end_time


def _employee_gender_at_position(booking_ids_ordered: list, db: Session):
    """
    Return a list of (booking_id, gender_value) in stop order.
    gender_value is the string value of GenderEnum or None.
    """
    from app.models.booking import Booking
    from app.models.employee import Employee

    # Preserve order: query once, map by booking_id
    employees_by_booking = {}
    rows = (
        db.query(Booking.booking_id, Employee.gender)
        .join(Employee, Employee.employee_id == Booking.employee_id)
        .filter(Booking.booking_id.in_(booking_ids_ordered))
        .all()
    )
    for booking_id, gender in rows:
        # gender may be an Enum member or a string
        gender_val = gender.value if hasattr(gender, "value") else str(gender) if gender else None
        employees_by_booking[booking_id] = gender_val

    return [(bid, employees_by_booking.get(bid)) for bid in booking_ids_ordered]


def _is_female(gender_val) -> bool:
    return gender_val in ("Female", "FEMALE")


def route_requires_escort(db: Session, route_id: int, tenant_id: str) -> bool:
    """
    Determine if a route requires escort based on:
      1. The shift's female_constraint (shift-level override), OR
      2. The tenant escort config (time-window + any-female fallback).

    female_constraint precedence (evaluated first):
      DISABLE                   → always False  (no escort for this shift)
      ANY_FEMALE                → True if any female employee on the route
      FIRST_LAST_FEMALE         → True if first OR last stop has a female employee
      SECOND_SECOND_LAST_FEMALE → True if 2nd OR 2nd-last stop has a female employee
      None (not set)            → fall back to tenant config logic below

    Tenant config fallback (when female_constraint is None):
      - escort_required_for_women must be True
      - shift time must fall inside [escort_required_start_time, escort_required_end_time]
      - at least one female employee on the route

    Args:
        db: Database session
        route_id: Route ID to check
        tenant_id: Tenant ID

    Returns:
        True if route requires escort
    """
    from app.models.tenant import Tenant
    from app.models.route_management import RouteManagement, RouteManagementBooking
    from app.models.booking import Booking
    from app.models.employee import Employee
    from app.models.enums import GenderEnum, FemaleConstraintEnum

    try:
        # ── Load route ────────────────────────────────────────────────
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id,
        ).first()

        if not route or not route.shift_id:
            return False

        # ── Load shift ────────────────────────────────────────────────
        from app.models.shift import Shift
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        if not shift:
            return False

        shift_time = shift.shift_time

        # ── Resolve female_constraint value ───────────────────────────
        fc_raw = shift.female_constraint
        if fc_raw is None:
            female_constraint = None
        elif hasattr(fc_raw, "value"):
            female_constraint = fc_raw.value          # Enum member → string value
        else:
            female_constraint = str(fc_raw)           # already a string from DB

        # ── DISABLE: short-circuit immediately ────────────────────────
        if female_constraint == FemaleConstraintEnum.DISABLE.value:
            logger.info(
                f"[escort] route {route_id}: female_constraint=DISABLE → no escort"
            )
            return False

        # ── Load ordered stops ────────────────────────────────────────
        route_bookings = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .order_by(RouteManagementBooking.order_id)
            .all()
        )
        booking_ids_ordered = [rb.booking_id for rb in route_bookings]
        if not booking_ids_ordered:
            return False

        ordered_gender = _employee_gender_at_position(booking_ids_ordered, db)
        # ordered_gender: [(booking_id, gender_val), ...]

        # ── Shift-level female_constraint rules ───────────────────────
        if female_constraint == FemaleConstraintEnum.ANY_FEMALE.value:
            result = any(_is_female(g) for _, g in ordered_gender)
            logger.info(
                f"[escort] route {route_id}: ANY_FEMALE → {result}"
            )
            return result

        if female_constraint == FemaleConstraintEnum.FIRST_LAST_FEMALE.value:
            first_female = _is_female(ordered_gender[0][1])
            last_female = _is_female(ordered_gender[-1][1])
            result = first_female or last_female
            logger.info(
                f"[escort] route {route_id}: FIRST_LAST_FEMALE "
                f"first={first_female} last={last_female} → {result}"
            )
            return result

        if female_constraint == FemaleConstraintEnum.SECOND_SECOND_LAST_FEMALE.value:
            if len(ordered_gender) < 2:
                # Only one stop — no second/second-last distinction
                logger.info(
                    f"[escort] route {route_id}: SECOND_SECOND_LAST_FEMALE "
                    f"only 1 stop → False"
                )
                return False
            second_female = _is_female(ordered_gender[1][1])
            second_last_female = _is_female(ordered_gender[-2][1])
            result = second_female or second_last_female
            logger.info(
                f"[escort] route {route_id}: SECOND_SECOND_LAST_FEMALE "
                f"2nd={second_female} 2nd-last={second_last_female} → {result}"
            )
            return result

        # ── Tenant config fallback (female_constraint is None) ────────
        from app.utils import cache_manager
        safety_config = cache_manager.get_tenant_config_with_cache(db, tenant_id)

        if not safety_config or not safety_config.escort_required_for_women:
            return False

        if not safety_config.escort_required_start_time or not safety_config.escort_required_end_time:
            return False

        time_requires_escort = is_time_in_escort_range(
            shift_time,
            safety_config.escort_required_start_time,
            safety_config.escort_required_end_time,
        )
        if not time_requires_escort:
            return False

        result = any(_is_female(g) for _, g in ordered_gender)
        logger.info(
            f"[escort] route {route_id}: tenant-config fallback "
            f"time_in_window=True any_female={result}"
        )
        return result

    except Exception as e:
        logger.error(f"Error checking if route {route_id} requires escort: {str(e)}")
        return False


def update_route_escort_requirement(db: Session, route_id: int, tenant_id: str) -> bool:
    """
    Update the escort_required flag for a route based on current safety requirements.

    Args:
        db: Database session
        route_id: Route ID to update
        tenant_id: Tenant ID

    Returns:
        True if route requires escort
    """
    from app.models.route_management import RouteManagement

    requires_escort = route_requires_escort(db, route_id, tenant_id)

    # Update route escort requirement
    db.query(RouteManagement).filter(
        RouteManagement.route_id == route_id,
        RouteManagement.tenant_id == tenant_id
    ).update({
        RouteManagement.escort_required: requires_escort
    })

    logger.info(f"Route {route_id} escort requirement updated: {requires_escort}")
    return requires_escort
