from pydantic import BaseModel, SerializationInfo, field_serializer, validator, field_validator, ConfigDict
from datetime import datetime, timedelta
from typing import Optional

class CutoffBase(BaseModel):
    # Time-based cutoffs (intervals before shift time) - format "HH:MM"
    booking_login_cutoff: Optional[str] = "0:00"
    cancel_login_cutoff: Optional[str] = "0:00"
    booking_logout_cutoff: Optional[str] = "0:00"
    cancel_logout_cutoff: Optional[str] = "0:00"
    medical_emergency_booking_cutoff: Optional[str] = "0:00"
    adhoc_booking_cutoff: Optional[str] = "0:00"
    
    # Enable/disable flags for special booking types
    allow_adhoc_booking: Optional[bool] = False
    allow_medical_emergency_booking: Optional[bool] = False

    @validator("booking_login_cutoff", "cancel_login_cutoff", "booking_logout_cutoff", "cancel_logout_cutoff", 
               "medical_emergency_booking_cutoff", "adhoc_booking_cutoff")
    def validate_time_format(cls, v):
        """Ensure format is HH:MM and valid numbers"""
        if not isinstance(v, str) or ":" not in v:
            raise ValueError("Time must be in 'HH:MM' format")
        parts = v.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("Time must be in 'HH:MM' format with numbers")
        hours, minutes = map(int, parts)
        if hours < 0 or minutes < 0 or minutes >= 60:
            raise ValueError("Hours must be >=0 and minutes must be 0-59")
        return v


class CutoffCreate(CutoffBase):
    tenant_id: str


class CutoffUpdate(CutoffBase):
    tenant_id: Optional[str] = None  # Optional for updates


class CutoffOut(BaseModel):
    booking_login_cutoff: timedelta
    cancel_login_cutoff: timedelta
    booking_logout_cutoff: timedelta
    cancel_logout_cutoff: timedelta
    medical_emergency_booking_cutoff: timedelta
    adhoc_booking_cutoff: timedelta
    allow_adhoc_booking: bool
    allow_medical_emergency_booking: bool
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("booking_login_cutoff", "cancel_login_cutoff", "booking_logout_cutoff", "cancel_logout_cutoff",
                     "medical_emergency_booking_cutoff", "adhoc_booking_cutoff")
    def serialize_cutoff(self, v: timedelta, _info):
        # Convert timedelta -> "HH:MM"
        total_minutes = int(v.total_seconds() // 60)
        h, m = divmod(total_minutes, 60)
        return f"{h}:{m:02d}"