"""
OTP (One-Time Password) utility functions for Fleet Manager
"""

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def get_required_otp_count(booking_type: str, shift_log_type: str, cutoff) -> int:
    """
    Determine the number of OTPs required based on booking type and shift type.

    Args:
        booking_type: Type of booking (regular, adhoc, medical_emergency)
        shift_log_type: Type of shift (IN for login, OUT for logout)
        cutoff: Cutoff configuration object

    Returns:
        Number of OTPs required
    """
    # Use the same OTP counts for all booking types (regular, adhoc, medical_emergency)
    # Only differentiate by shift type (login vs logout)
    if shift_log_type == "IN":
        return cutoff.login_otp_count if cutoff else 1
    elif shift_log_type == "OUT":
        return cutoff.logout_otp_count if cutoff else 1
    else:
        return 1  # default fallback


def get_otp_purposes(booking_type: str, shift_log_type: str, otp_count: int, escort_enabled: bool = False) -> dict:
    """
    Determine the purposes of each OTP based on shift type and escort configuration.
    All shifts (login and logout) use the same boarding/deboarding journey flow.

    Args:
        booking_type: Type of booking (regular, adhoc, medical_emergency) - kept for future extensibility
        shift_log_type: Type of shift (IN for login, OUT for logout) - kept for future extensibility
        otp_count: Number of OTPs required
        escort_enabled: Whether escort feature is enabled for this tenant

    Returns:
        Dictionary mapping OTP positions to their purposes
    """
    purposes = {}

    # Use consistent boarding/deboarding flow for all shifts
    if otp_count == 1:
        purposes[1] = "boarding"    # Getting into the vehicle
    elif otp_count == 2:
        purposes[1] = "boarding"    # Getting into the vehicle
        purposes[2] = "deboarding"  # Getting out of the vehicle
    elif otp_count >= 3:
        purposes[1] = "boarding"    # Getting into the vehicle
        purposes[2] = "deboarding"  # Getting out of the vehicle
        # Third OTP is supervisor unless escort is enabled
        purposes[3] = "escort" if escort_enabled else "supervisor"

    return purposes


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