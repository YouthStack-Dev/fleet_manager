"""
Common utilities for the Fleet Manager application
"""
from datetime import datetime, time


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