"""
Common utilities for the Fleet Manager application
"""
from datetime import datetime, time, timezone, timedelta


def datetime_to_minutes(dt_val):
    """
    Convert datetime/time string or object to minutes from midnight

    Args:
        dt_val: datetime, time, or ISO string to convert

    Returns:
        int: Minutes from midnight

    Raises:
        TypeError: If dt_val is not a supported type
    """
    # If already datetime or time object
    if isinstance(dt_val, datetime):
        return dt_val.hour * 60 + dt_val.minute

    if isinstance(dt_val, time):
        return dt_val.hour * 60 + dt_val.minute

    # Else assume it's string
    if isinstance(dt_val, str):
        dt = datetime.fromisoformat(dt_val)
        return dt.hour * 60 + dt.minute

    raise TypeError(f"Unsupported type for datetime_to_minutes: {type(dt_val)}")


def get_current_ist_time():
    """
    Get current time in Indian Standard Time (IST, UTC+5:30)

    Returns:
        datetime: Current datetime in IST timezone
    """
    utc_now = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    ist_now = utc_now + ist_offset
    return ist_now.replace(tzinfo=timezone(ist_offset))


def get_current_ist_datetime():
    """
    Get current datetime in Indian Standard Time (IST, UTC+5:30)
    Alias for get_current_ist_time()

    Returns:
        datetime: Current datetime in IST timezone
    """
    return get_current_ist_time()