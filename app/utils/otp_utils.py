"""
OTP (One-Time Password) utility functions for Fleet Manager
"""

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

    # If escort is assigned, add escort OTP
    if escort_enabled:
        return base_count + 1
    else:
        return base_count




def generate_otp_codes(count: int) -> list:
    """
    Generate the specified number of 4-digit OTP codes.

    Args:
        count: Number of OTP codes to generate

    Returns:
        List of OTP codes (integers)
    """
    import random
    return [random.randint(1000, 9999) for _ in range(count)]


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


def route_requires_escort(db: Session, route_id: int, tenant_id: str) -> bool:
    """
    Determine if a route requires escort based on tenant configuration and route characteristics.

    Args:
        db: Database session
        route_id: Route ID to check
        tenant_id: Tenant ID

    Returns:
        True if route requires escort for safety
    """
    from app.models.tenant import Tenant
    from app.models.route_management import RouteManagement, RouteManagementBooking
    from app.models.booking import Booking
    from app.models.employee import Employee, GenderEnum

    try:
        # Get tenant escort configuration using cache-first helper
        from app.utils import cache_manager
        safety_config = cache_manager.get_tenant_config_with_cache(db, tenant_id)

        if not safety_config or not safety_config.escort_required_for_women:
            return False

        if not safety_config.escort_required_start_time or not safety_config.escort_required_end_time:
            return False

        # Get route shift time
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        if not route or not route.shift_id:
            return False

        # Get shift time
        from app.models.shift import Shift
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id).first()
        if not shift:
            return False

        shift_time = shift.shift_time
        escort_start = safety_config.escort_required_start_time
        escort_end = safety_config.escort_required_end_time

        # Check if shift time requires escort
        time_requires_escort = is_time_in_escort_range(shift_time, escort_start, escort_end)
        if not time_requires_escort:
            return False

        # Check if route has women employees (especially last women)
        route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.order_id).all()

        booking_ids = [rb.booking_id for rb in route_bookings]
        if not booking_ids:
            return False

        # Get employees for these bookings
        women_employees = db.query(Employee).join(Booking).filter(
            Booking.booking_id.in_(booking_ids),
            Employee.gender == GenderEnum.FEMALE
        ).all()

        # Route requires escort if it has women employees during escort-required hours
        return len(women_employees) > 0

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