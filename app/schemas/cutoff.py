from pydantic import BaseModel, SerializationInfo, field_serializer, validator
from datetime import datetime, timedelta
from typing import Optional

class CutoffBase(BaseModel):
    booking_cutoff: Optional[str] = "0:00"  # format "HH:MM"
    cancel_cutoff: Optional[str] = "0:00"

    @property
    def booking_cutoff_timedelta(self) -> timedelta:
        """Convert booking_cutoff string to timedelta"""
        h, m = map(int, self.booking_cutoff.split(":"))
        return timedelta(hours=h, minutes=m)

    @property
    def cancel_cutoff_timedelta(self) -> timedelta:
        """Convert cancel_cutoff string to timedelta"""
        h, m = map(int, self.cancel_cutoff.split(":"))
        return timedelta(hours=h, minutes=m)

    @validator("booking_cutoff", "cancel_cutoff")
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
    tenant_id: str
    booking_cutoff: timedelta
    cancel_cutoff: timedelta
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

    @field_serializer("booking_cutoff", "cancel_cutoff")
    def serialize_cutoff(self, v: timedelta, _info):
        # Convert timedelta -> "HH:MM"
        total_minutes = int(v.total_seconds() // 60)
        h, m = divmod(total_minutes, 60)
        return f"{h}:{m:02d}"